"""Synchronisation Withings → base locale.

Trois flux, chacun repris là où la synchro précédente s'est arrêtée (paramètre « lastupdate »
de Withings : tout ce qui a été ajouté ou modifié depuis, avec un jour de recouvrement) :

- les mesures (pesées, composition, tension, pouls, température…) ;
- les nuits (résumés de sommeil : Sleep Analyzer, montre) ;
- l'activité de chaque journée (pas, distance, calories…).

La réponse brute de Withings est gardée (table ``raw``, source « withings »), puis les
journées touchées sont recalculées (table ``daily``, métriques « wi_… »). Au premier
branchement, l'historique remonte jusqu'à la date du premier import de Foulée (deux ans
par défaut).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import date, datetime, timedelta
from typing import Callable

from .. import analysis, db
from . import parse, vue
from .client import WithingsError, WithingsSession

LOG = logging.getLogger("foulee.withings")
SOURCE = "withings"
REFUSED = "withings_refus"
OVERLAP = 86400  # Withings complète parfois une journée après coup : on redemande la veille
Progress = Callable[[str, float | None], None]
LABELS = {"meas": "mesures", "sleep": "nuits", "activity": "activité"}


def note_error(summary: dict, label: str, exc: WithingsError) -> None:
    """Erreur sur un flux : notée, et la synchro continue. Sauf un accès refusé, qui arrête tout."""
    if exc.access_refused:
        raise exc
    summary["erreurs"].append(f"{label} : {exc}")


def _since(conn: sqlite3.Connection, stream: str, since: date | None, default_since: date) -> int:
    if since:
        return int(datetime.combine(since, datetime.min.time()).timestamp())
    last = db.get_sync_state(conn, SOURCE, stream)
    try:
        return max(0, int(float(last)) - OVERLAP)
    except (TypeError, ValueError):
        return int(datetime.combine(default_since, datetime.min.time()).timestamp())


def _pages(session: WithingsSession, path: str, action: str, key: str, **params) -> tuple[list[dict], dict]:
    """Tous les éléments d'une réponse, page après page (« more » et « offset » de Withings)."""
    items: list[dict] = []
    body: dict = {}
    offset = None
    for _ in range(200):  # garde-fou
        body = session.call(path, action, offset=offset, **params)
        items.extend(body.get(key) or [])
        if not body.get("more") or body.get("offset") in (None, offset):
            break
        offset = body.get("offset")
    return items, body


# ------------------------------------------------------------------ mesures
def height(conn: sqlite3.Connection) -> float | None:
    try:
        return float(db.get_meta(conn, "withings_taille_m") or "") or None
    except ValueError:
        return None


def recompute_measures(conn: sqlite3.Connection, day: str) -> None:
    rows = conn.execute("SELECT payload FROM raw WHERE source = ? AND kind = 'meas' AND key LIKE ?",
                        (SOURCE, f"{day}:%")).fetchall()
    values = parse.daily_from_groups([json.loads(r["payload"]) for r in rows], height(conn))
    db.delete_daily(conn, day, parse.MEASURE_METRICS, source=SOURCE)
    db.put_daily(conn, day, values, source=SOURCE)


def fetch_height(conn: sqlite3.Connection, session: WithingsSession) -> bool:
    """La taille sert à l'IMC. Saisie une fois, souvent à la création du compte Withings, bien avant l'historique
    importé : on la demande à part, sans limite de date. Une fois connue, l'IMC des pesées déjà là se recalcule."""
    groups, _ = _pages(session, "measure", "getmeas", "measuregrps", meastype=parse.HEIGHT, category=1)
    found = None
    for group in sorted(groups, key=lambda g: g.get("date") or 0):
        found = parse.height_of(group) or found
    if not found:
        return False
    db.set_meta(conn, "withings_taille_m", f"{found:.3f}")
    for row in conn.execute("SELECT DISTINCT substr(key, 1, 10) AS day FROM raw WHERE source = ? AND kind = 'meas'",
                            (SOURCE,)).fetchall():
        recompute_measures(conn, row["day"])
    return True


def store_groups(conn: sqlite3.Connection, groups: list[dict], zone: str | None) -> set[str]:
    """Range les groupes de mesures et renvoie les journées à recalculer."""
    days: set[str] = set()
    for group in groups:
        group = {**group, "timezone": group.get("timezone") or zone}
        day = parse.group_day(group)
        grpid = group.get("grpid")
        if not day or grpid is None:
            continue
        key = f"{day}:{grpid}"
        # Mesure déplacée à un autre jour (heure corrigée dans l'appli Withings) : on retire l'ancienne
        for row in conn.execute("SELECT key FROM raw WHERE source = ? AND kind = 'meas' AND key LIKE ? AND key <> ?",
                                (SOURCE, f"%:{grpid}", key)).fetchall():
            conn.execute("DELETE FROM raw WHERE source = ? AND kind = 'meas' AND key = ?", (SOURCE, row["key"]))
            days.add(row["key"].split(":", 1)[0])
        db.put_raw(conn, SOURCE, "meas", key, group)
        days.add(day)
        tall = parse.height_of(group)
        if tall:
            db.set_meta(conn, "withings_taille_m", f"{tall:.3f}")
    return days


# ------------------------------------------------------------------ sommeil
def recompute_sleep(conn: sqlite3.Connection, day: str) -> None:
    rows = conn.execute("SELECT payload FROM raw WHERE source = ? AND kind = 'sleep' AND key LIKE ?",
                        (SOURCE, f"{day}:%")).fetchall()
    values = parse.main_sleep([json.loads(r["payload"]) for r in rows])
    db.delete_daily(conn, day, parse.SLEEP_METRICS, source=SOURCE)
    db.put_daily(conn, day, values, source=SOURCE)


def store_sleep(conn: sqlite3.Connection, items: list[dict]) -> set[str]:
    days: set[str] = set()
    for item in items:
        day = parse.sleep_day(item)
        if not day:
            continue
        ident = item.get("id") or item.get("startdate") or "nuit"
        db.put_raw(conn, SOURCE, "sleep", f"{day}:{ident}", item)
        days.add(day)
    return days


# ------------------------------------------------------------------- synchro
def run(conn: sqlite3.Connection, *, since: date | None = None, fit_days: int | None = None,
        with_fit: bool = True, progress: Progress | None = None) -> dict:
    progress = progress or (lambda message, fraction=None: None)
    settings = db.get_settings(conn)
    today = date.today()
    default_since = analysis.to_date(settings["historique_depuis"]) if settings.get("historique_depuis") \
        else today - timedelta(days=730)
    summary: dict = {"mesures": 0, "jours_mesures": 0, "nuits": 0, "jours_activite": 0, "erreurs": [], "appels": 0}
    progress("Connexion à Withings…", None)
    session = WithingsSession()
    started = str(int(time.time()))

    progress("Withings : pesées et mesures…", None)
    try:
        if height(conn) is None:
            fetch_height(conn, session)
        groups, body = _pages(session, "measure", "getmeas", "measuregrps",
                              lastupdate=_since(conn, "meas", since, default_since))
        days = store_groups(conn, groups, body.get("timezone"))
        for day in sorted(days):
            recompute_measures(conn, day)
        summary["mesures"], summary["jours_mesures"] = len(groups), len(days)
        db.set_sync_state(conn, SOURCE, "meas", started, "lastupdate")
        conn.commit()
    except WithingsError as exc:
        note_error(summary, "mesures", exc)

    progress("Withings : nuits…", None)
    try:
        items, _ = _pages(session, "v2/sleep", "getsummary", "series", data_fields=parse.SLEEP_FIELDS,
                          lastupdate=_since(conn, "sleep", since, default_since))
        days = store_sleep(conn, items)
        for day in sorted(days):
            recompute_sleep(conn, day)
        summary["nuits"] = len(days)
        db.set_sync_state(conn, SOURCE, "sleep", started, "lastupdate")
        conn.commit()
    except WithingsError as exc:
        note_error(summary, "nuits", exc)

    progress("Withings : activité…", None)
    try:
        items, _ = _pages(session, "v2/measure", "getactivity", "activities", data_fields=parse.ACTIVITY_FIELDS,
                          lastupdate=_since(conn, "activity", since, default_since))
        count = 0
        for item in items:
            day, values = parse.parse_activity(item)
            if not day:
                continue
            db.put_raw(conn, SOURCE, "activity", day, item)
            db.delete_daily(conn, day, parse.ACTIVITY_METRICS, source=SOURCE)
            db.put_daily(conn, day, values, source=SOURCE)
            count += 1
        summary["jours_activite"] = count
        db.set_sync_state(conn, SOURCE, "activity", started, "lastupdate")
        conn.commit()
    except WithingsError as exc:
        note_error(summary, "activité", exc)

    summary["appels"] = session.calls
    if summary["erreurs"] and not session.answered:
        raise WithingsError(f"Aucune donnée n'a pu être lue chez Withings. {summary['erreurs'][0]}")
    vue.refresh_view(conn)
    conn.commit()
    return summary


def reparse_all(conn: sqlite3.Connection) -> dict:
    """Reconstruit les métriques Withings à partir des réponses brutes gardées."""
    days = {r["key"].split(":", 1)[0] for r in conn.execute(
        "SELECT key FROM raw WHERE source = ? AND kind = 'meas'", (SOURCE,))}
    for day in days:
        recompute_measures(conn, day)
    nights = {r["key"].split(":", 1)[0] for r in conn.execute(
        "SELECT key FROM raw WHERE source = ? AND kind = 'sleep'", (SOURCE,))}
    for day in nights:
        recompute_sleep(conn, day)
    rows = conn.execute("SELECT payload FROM raw WHERE source = ? AND kind = 'activity'", (SOURCE,)).fetchall()
    for row in rows:
        day, values = parse.parse_activity(json.loads(row["payload"]))
        if day:
            db.delete_daily(conn, day, parse.ACTIVITY_METRICS, source=SOURCE)
            db.put_daily(conn, day, values, source=SOURCE)
    return {"jours_mesures": len(days), "nuits": len(nights), "jours_activite": len(rows)}
