"""Synchronisation Garmin → base locale.

Pour chaque flux (résumés quotidiens, sommeil, VFC, Body Battery, poids) :
1. on reprend là où la dernière synchro s'est arrêtée (avec 3 jours de
   recouvrement, car Garmin complète parfois les journées après coup) ;
2. on découpe la plage selon la limite de chaque flux ;
3. on range la réponse brute (table ``raw``) puis sa version normalisée.

Les séances suivent le même principe, et leur fichier FIT d'origine est
téléchargé automatiquement pour les N derniers jours (réglage
« fit_auto_jours ») ; les plus anciennes sont téléchargées à la demande.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, timedelta
from typing import Callable

from .. import analysis, config, db, fitfile
from . import parse
from .client import GarminError, GarminSession

LOG = logging.getLogger("foulee.garmin")
SOURCE = "garmin"
Progress = Callable[[str, float | None], None]

# (flux, méthode du client officiel, jours max par appel, extraction, normalisation, métriques, champ date)
DAILY_STREAMS = [
    ("daily", "get_daily_summaries", 31, parse.daily_summary_items, parse.parse_daily_summary,
     parse.DAILY_SUMMARY_METRICS, "calendarDate"),
    ("sleep", "get_daily_sleep_summaries", 31, parse.sleep_items, parse.parse_sleep,
     parse.SLEEP_METRICS, "calendarDate"),
    ("hrv", "get_daily_hrv_summaries", 365, parse.hrv_items, parse.parse_hrv,
     parse.HRV_METRICS, "calendarDate"),
    ("body_battery", "get_daily_body_battery", 31, parse.body_battery_items, None, [], "date"),
    ("weight", "get_weight_measurements", 180, parse.weight_items, parse.parse_weight,
     parse.WEIGHT_METRICS, "summaryDate"),
]
STREAM_LABELS = {
    "daily": "résumés quotidiens", "sleep": "sommeil", "hrv": "VFC", "body_battery": "Body Battery",
    "weight": "poids", "activities": "séances",
}


def note_error(summary: dict, label: str, exc: GarminError) -> None:
    """Erreur sur un flux : notée, et la synchro continue. Sauf une clé refusée, qui arrête tout :
    inutile de redemander dix fois, et l'interface doit afficher « remplace ta clé »."""
    if exc.key_rejected:
        raise exc
    summary["erreurs"].append(f"{label} : {exc}")


def windows(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    result, current = [], start
    while current <= end:
        last = min(current + timedelta(days=max_days - 1), end)
        result.append((current, last))
        current = last + timedelta(days=1)
    return result


# ------------------------------------------------------------ normalisation
def normalize_daily_item(conn: sqlite3.Connection, stream: str, item: dict) -> str | None:
    spec = next(s for s in DAILY_STREAMS if s[0] == stream)
    _, _, _, _, parser, metric_keys, date_field = spec
    day = item.get(date_field) or item.get("calendarDate")
    if not day:
        return None
    day = str(day)[:10]
    db.put_raw(conn, SOURCE, stream, day, item)
    if parser:
        _, values = parser(item)
        db.delete_daily(conn, day, metric_keys)
        db.put_daily(conn, day, values)
    return day


def update_wake_battery(conn: sqlite3.Connection, days: set[str]) -> None:
    for day in days:
        bb_item = db.get_raw(conn, SOURCE, "body_battery", day)
        sleep_item = db.get_raw(conn, SOURCE, "sleep", day)
        if not bb_item or not sleep_item:
            continue
        value = parse.wake_body_battery(bb_item, sleep_item)
        if value is not None:
            db.put_daily(conn, day, {"bb_wake": value})


def upsert_activity(conn: sqlite3.Connection, row: dict) -> bool:
    """Insère ou met à jour le résumé d'une séance. Renvoie True si elle est nouvelle."""
    exists = conn.execute("SELECT 1 FROM activities WHERE id = ?", (row["id"],)).fetchone() is not None
    columns = [k for k in row.keys()]
    placeholders = ",".join("?" for _ in columns)
    updates = ",".join(f"{c} = excluded.{c}" for c in columns if c != "id")
    conn.execute(
        f"INSERT INTO activities({','.join(columns)}, updated_at) VALUES ({placeholders}, ?) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}, updated_at = excluded.updated_at",
        [row[c] for c in columns] + [db.now_iso()],
    )
    return not exists


def reparse_all(conn: sqlite3.Connection) -> dict:
    """Reconstruit toutes les tables normalisées Garmin à partir du brut."""
    counts: dict[str, int] = {}
    for stream, *_ in DAILY_STREAMS:
        rows = conn.execute("SELECT payload FROM raw WHERE source = ? AND kind = ?", (SOURCE, stream)).fetchall()
        for r in rows:
            normalize_daily_item(conn, stream, json.loads(r["payload"]))
        counts[stream] = len(rows)
    days = {r["key"] for r in conn.execute("SELECT key FROM raw WHERE source = ? AND kind = 'body_battery'", (SOURCE,))}
    update_wake_battery(conn, days)
    for r in conn.execute("SELECT key, payload FROM raw WHERE source = ? AND kind = 'fitness_age'", (SOURCE,)).fetchall():
        db.put_daily(conn, r["key"], parse.parse_fitness_age(json.loads(r["payload"])))
    zones = db.get_raw(conn, SOURCE, "hr_zones", "latest")
    if zones is not None and parse.heart_rate_zones(zones):
        db.set_meta(conn, "garmin_hr_zones", json.dumps(parse.heart_rate_zones(zones)))
    profile = db.get_raw(conn, SOURCE, "profile", "latest")
    if isinstance(profile, dict):
        db.set_meta(conn, "garmin_profil", json.dumps(parse.profile_settings(profile)))
    rows = conn.execute("SELECT payload FROM raw WHERE source = ? AND kind = 'activity'", (SOURCE,)).fetchall()
    for r in rows:
        row = parse.parse_activity(json.loads(r["payload"]))
        if row:
            upsert_activity(conn, row)
    counts["activities"] = len(rows)
    settings = db.get_settings(conn)
    analysis.refresh_all_activities(conn, settings)
    return counts


# --------------------------------------------------------------- fichiers FIT
def fetch_fit(session: GarminSession, conn: sqlite3.Connection, activity_id: str, settings: dict,
              hrp: dict) -> str:
    """Télécharge, décode et range le FIT d'une séance. Renvoie un statut court."""
    row = conn.execute("SELECT source_id FROM activities WHERE id = ?", (activity_id,)).fetchone()
    if not row:
        return "inconnue"
    content = session.download_activity(row["source_id"])
    fit = fitfile.extract_fit(content or b"")
    if not fit:
        conn.execute("UPDATE activities SET has_streams = -1 WHERE id = ?", (activity_id,))
        return "pas de fichier FIT"
    path = config.fit_dir() / f"{row['source_id']}.fit"
    path.write_bytes(fit)
    try:
        decoded = fitfile.decode(fit)
    except Exception as exc:  # fichier corrompu ou inattendu : on le note et on continue
        LOG.warning("FIT illisible pour %s : %s", activity_id, exc)
        conn.execute("UPDATE activities SET has_streams = -1, fit_path = ? WHERE id = ?", (str(path), activity_id))
        return "FIT illisible"
    analysis.store_activity_streams(conn, activity_id, decoded, str(path), settings, hrp)
    return "ok"


def ensure_streams(conn: sqlite3.Connection, activity_id: str) -> str:
    """Téléchargement à la demande (séance ancienne ouverte dans l'interface ou par Claude)."""
    row = conn.execute("SELECT source, has_streams FROM activities WHERE id = ?", (activity_id,)).fetchone()
    if not row:
        return "inconnue"
    if row["has_streams"] == 1:
        return "ok"
    if row["has_streams"] == -1:
        return "pas de fichier FIT"
    if row["source"] != SOURCE or config.is_demo():
        return "indisponible"
    settings = db.get_settings(conn)
    hrp = analysis.hr_profile(conn, settings)
    with GarminSession() as session:
        status = fetch_fit(session, conn, activity_id, settings, hrp)
    analysis.recompute_daily_calc(conn)
    conn.commit()
    return status


# ------------------------------------------------------------------- synchro
def run(conn: sqlite3.Connection, *, since: date | None = None, fit_days: int | None = None,
        with_fit: bool = True, progress: Progress | None = None) -> dict:
    progress = progress or (lambda message, fraction=None: None)
    settings = db.get_settings(conn)
    today = date.today()
    default_since = analysis.to_date(settings["historique_depuis"]) if settings.get("historique_depuis") \
        else today - timedelta(days=730)
    if since and (not settings.get("historique_depuis") or since < default_since):
        db.set_setting(conn, "historique_depuis", since.isoformat())
    fit_days = settings.get("fit_auto_jours", 180) if fit_days is None else fit_days
    summary: dict = {"flux": {}, "seances_nouvelles": 0, "seances_maj": 0, "fit": 0, "erreurs": [], "appels": 0}

    progress("Connexion à Garmin…", 0.0)
    session = GarminSession()
    try:
        total_steps = len(DAILY_STREAMS) + 2
        touched_days: set[str] = set()
        for step, (stream, method, max_days, extractor, _parser, _keys, _field) in enumerate(DAILY_STREAMS):
            last = db.get_sync_state(conn, SOURCE, stream)
            start = since or (analysis.to_date(last) - timedelta(days=3) if last else default_since)
            spans = windows(start, today, max_days)
            count = 0
            for index, (a, b) in enumerate(spans):
                progress(f"{STREAM_LABELS[stream].capitalize()} : {a:%d/%m/%Y} → {b:%d/%m/%Y}",
                         (step + index / max(len(spans), 1)) / total_steps)
                try:
                    payload = session.call(method, a, b)
                except GarminError as exc:
                    note_error(summary, f"{STREAM_LABELS[stream]} ({a} → {b})", exc)
                    break
                for item in extractor(payload):
                    day = normalize_daily_item(conn, stream, item)
                    if day:
                        count += 1
                        if stream in ("sleep", "body_battery"):
                            touched_days.add(day)
                db.set_sync_state(conn, SOURCE, stream, b.isoformat())
                conn.commit()
            summary["flux"][STREAM_LABELS[stream]] = count
        update_wake_battery(conn, touched_days)

        # Profil : zones FC, seuil lactique et âge fitness du jour (un appel chacun)
        progress("Profil : zones FC, seuil et âge fitness…", (len(DAILY_STREAMS)) / total_steps)
        try:
            payload = session.call("get_heart_rate_zones")
            if payload:
                db.put_raw(conn, SOURCE, "hr_zones", "latest", payload)
            zones = parse.heart_rate_zones(payload)
            if zones:
                db.set_meta(conn, "garmin_hr_zones", json.dumps(zones))
            settings_payload = session.call("get_user_profile_settings")
            if isinstance(settings_payload, dict):
                db.put_raw(conn, SOURCE, "profile", "latest", settings_payload)
                db.set_meta(conn, "garmin_profil", json.dumps(parse.profile_settings(settings_payload)))
            fitness = session.call("get_fitness_age", today)
            if fitness:
                db.put_raw(conn, SOURCE, "fitness_age", today.isoformat(), fitness)
                db.put_daily(conn, today.isoformat(), parse.parse_fitness_age(fitness))
        except GarminError as exc:
            note_error(summary, "profil", exc)

        # Séances
        last = db.get_sync_state(conn, SOURCE, "activities")
        start = since or (analysis.to_date(last) - timedelta(days=7) if last else default_since)
        progress(f"Séances depuis le {start:%d/%m/%Y}…", (len(DAILY_STREAMS) + 1) / total_steps)
        need_fit: list[tuple[str, str]] = []
        offset, page = 0, 20
        listed = True
        while True:
            try:
                items = session.call("search_activities", start=offset, limit=page,
                                     start_date=start, end_date=today)
            except GarminError as exc:
                note_error(summary, "séances", exc)
                listed = False
                break
            items = parse.items_of(items, "activityList", "activities")
            if not items:
                break
            for item in items:
                row = parse.parse_activity(item)
                if not row:
                    continue
                db.put_raw(conn, SOURCE, "activity", row["source_id"], item)
                if upsert_activity(conn, row):
                    summary["seances_nouvelles"] += 1
                else:
                    summary["seances_maj"] += 1
                state = conn.execute("SELECT has_streams FROM activities WHERE id = ?", (row["id"],)).fetchone()
                if state["has_streams"] == 0:
                    need_fit.append((row["id"], row["date"]))
            conn.commit()
            if len(items) < page:
                break
            offset += page
        if listed:  # liste incomplète : la prochaine synchro repartira du même point
            db.set_sync_state(conn, SOURCE, "activities", today.isoformat())

        hrp = analysis.hr_profile(conn, settings)
        for row in conn.execute(
            "SELECT id FROM activities WHERE source = ? AND date >= ?", (SOURCE, start.isoformat())
        ).fetchall():
            analysis.update_activity_derived(conn, row["id"], settings, hrp)

        if with_fit and fit_days:
            cutoff = (today - timedelta(days=int(fit_days))).isoformat()
            queue = [a for a, d in need_fit if d >= cutoff]
            for index, activity_id in enumerate(queue):
                progress(f"Fichiers FIT : {index + 1} / {len(queue)}",
                         (len(DAILY_STREAMS) + 1 + index / max(len(queue), 1)) / total_steps)
                try:
                    if fetch_fit(session, conn, activity_id, settings, hrp) == "ok":
                        summary["fit"] += 1
                except GarminError as exc:
                    note_error(summary, f"FIT {activity_id}", exc)
                conn.commit()

        if summary["erreurs"] and not session.answered:
            # Rien n'a abouti : ce n'est pas une synchro « partielle » mais un échec
            raise GarminError(f"Aucune donnée n'a pu être lue chez Garmin. {summary['erreurs'][0]}")
        progress("Calcul de la charge d'entraînement…", 0.98)
        analysis.recompute_daily_calc(conn)
        summary["appels"] = session.calls
    finally:
        session.close()
    return summary
