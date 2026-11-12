"""Synchro Strava : la liste des séances (rafraîchie en entier chaque jour), leur détail et leurs courbes.

Rien de Strava n'entre dans la base de Foulée : tout va dans le cache du profil (voir ``cache``), reconfirmé
au moins une fois par jour. Une séance qui a disparu de Strava disparaît du cache à la synchro suivante.

Appels, dans l'ordre et selon le quota de Strava (partagé par les profils de l'installation) :
1. la liste des séances (200 par appel) : en entier une fois par jour, sinon les derniers jours ;
2. le détail (description, calories, tours) des séances récentes, et des séances de renfo faites sur Strava
   seulement (leurs exercices se lisent dans la description) ;
3. les courbes (FC, allure, GPS…) quand on ouvre une séance Strava : ``ensure_detail``.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Callable

from .. import analysis, config, db, fitfile, metrics, renfo
from . import cache, client, parse

LOG = logging.getLogger("foulee.strava")

SOURCE = "strava"
REFUSED = "strava_refus"     # meta de la base : Strava n'accepte plus l'accès de Foulée
FULL_EVERY_HOURS = 20        # liste complète au moins une fois par jour (séances effacées : sous 48 heures)
RECENT_DAYS = 3              # synchro légère : ce qui a commencé depuis trois jours
DETAIL_DAYS = 14             # détail des séances récentes (titre et description Strava des séances Garmin)
RENFO_DAYS = 90              # détail des séances de renfo faites sur Strava seulement (exercices)
MAX_DETAILS = 40             # au plus par synchro, en plus du quota
PER_PAGE = 200
STREAM_KEYS = "time,distance,latlng,altitude,velocity_smooth,heartrate,cadence,watts,temp"
SUMMARY_COLUMNS = ("source", "source_id", "start_local", "start_utc", "date", "sport", "type_key", "name",
                   "duration_s", "moving_s", "elapsed_s", "distance_m", "elev_gain_m", "avg_hr", "max_hr",
                   "avg_speed", "max_speed", "avg_cadence", "avg_power", "start_lat", "start_lon", "strava_id",
                   "external_id", "garmin_id", "device_name", "polyline")

Progress = Callable[..., None]


def history_start(settings: dict) -> date:
    """Le début de l'historique : celui choisi au premier import, sinon deux ans."""
    try:
        return analysis.to_date(settings["historique_depuis"]) if settings.get("historique_depuis") else \
            date.today() - timedelta(days=730)
    except (TypeError, ValueError):
        return date.today() - timedelta(days=730)


def _epoch(day: date) -> int:
    return int(datetime.combine(day, datetime.min.time()).timestamp())


# ------------------------------------------------------------- valeurs dérivées
def _derived(row: dict, streams: dict | None, settings: dict, hrp: dict) -> dict:
    """TRIMP, zones et charge d'une séance Strava (comme pour Garmin, avec la FC moyenne à défaut de courbe)."""
    coef = analysis.trimp_coef(settings)
    trimp = analysis.trimp_from_streams(streams, hrp["rest"], hrp["max"], coef) if streams else None
    if trimp is None:
        trimp = analysis.trimp_from_summary(row.get("duration_s"), row.get("avg_hr"), hrp["rest"], hrp["max"], coef)
    pace_zones = hr_zones = None
    if streams:
        if row.get("sport") in metrics.RUNNING_SPORTS:
            pz = analysis.pace_zone_seconds(streams, hrp["allure"]["vitesses"])
            pace_zones = json.dumps(pz) if pz else None
        hz = analysis.hr_zone_seconds(streams, hrp["floors"])
        hr_zones = json.dumps(hz) if hz else None
    return {"trimp": trimp, "load": trimp, "pace_zones": pace_zones, "hr_zones": hr_zones}


def _store_summary(cconn: sqlite3.Connection, row: dict, settings: dict, hrp: dict, now: str) -> bool:
    """Range une séance de la liste. Renvoie True si elle est nouvelle dans le cache."""
    old = cconn.execute("SELECT extra, streams_at FROM activities WHERE id = ?", (row["id"],)).fetchone()
    extra = json.loads(row["extra"])
    if old and old["extra"]:
        try:
            previous = json.loads(old["extra"])
        except ValueError:
            previous = {}
        for key in ("sets", "reps", "volume", "sets_effort"):  # totaux de renfo tirés du détail
            if key in previous:
                extra[key] = previous[key]
    values = {k: row[k] for k in SUMMARY_COLUMNS}
    values.update(id=row["id"], extra=json.dumps(extra, ensure_ascii=False, separators=(",", ":")), confirmed_at=now,
                  updated_at=now)
    if not (old and old["streams_at"]):
        values.update(_derived(row, None, settings, hrp))
        values["has_streams"] = 1 if row.get("polyline") else 0
    columns = list(values)
    cconn.execute(
        f"INSERT INTO activities({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)}) "
        f"ON CONFLICT(id) DO UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in columns if c != 'id')}",
        [values[c] for c in columns])
    return old is None


def _delete(cconn: sqlite3.Connection, activity_id: str) -> None:
    for table in ("laps", "streams", "exercises"):
        cconn.execute(f"DELETE FROM {table} WHERE activity_id = ?", (activity_id,))
    cconn.execute("DELETE FROM activities WHERE id = ?", (activity_id,))


def fetch_detail(session: client.StravaSession, cconn: sqlite3.Connection, row: sqlite3.Row) -> bool:
    """Description, calories, appareil et tours d'une séance ; exercices notés pour le renfo.
    Renvoie False si la séance n'existe plus chez Strava (elle quitte alors le cache)."""
    item = session.get(f"activities/{int(row['strava_id'])}", include_all_efforts="false")
    if item is None:
        _delete(cconn, row["id"])
        return False
    fields = parse.detail_fields(item, row["sport"])
    extra = json.loads(row["extra"] or "{}")
    if fields["device_name"]:
        extra["appareil"] = fields["device_name"]
    cconn.execute("DELETE FROM laps WHERE activity_id = ?", (row["id"],))
    for lap in fields["laps"]:
        cconn.execute("INSERT INTO laps(activity_id, idx, start_s, duration_s, elapsed_s, distance_m, avg_hr, max_hr, "
                      "avg_speed, max_speed, avg_cadence, avg_power, elev_gain_m, elev_loss_m, intensity) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (row["id"], lap["idx"], lap["start_s"], lap["duration_s"], lap["elapsed_s"], lap["distance_m"],
                       lap["avg_hr"], lap["max_hr"], lap["avg_speed"], lap["max_speed"], lap["avg_cadence"],
                       lap["avg_power"], lap["elev_gain_m"], lap["elev_loss_m"], lap["intensity"]))
    cconn.execute("DELETE FROM exercises WHERE activity_id = ?", (row["id"],))
    for key in ("sets", "reps", "volume", "sets_effort"):
        extra.pop(key, None)
    if row["sport"] in renfo.SPORTS:
        exercises = parse.exercises_from_text(fields["description"])
        for e in exercises:
            cconn.execute("INSERT INTO exercises(activity_id, idx, category, name, sets, reps, duration_s, max_kg, "
                          "volume_kg) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (row["id"], e["idx"], e["category"], e["name"], e["sets"], e["reps"], e["duration_s"],
                           e["max_kg"], e["volume_kg"]))
        extra.update(renfo.totals(exercises))
    cconn.execute("UPDATE activities SET description = ?, calories = ?, device_name = COALESCE(?, device_name), "
                  "lap_count = ?, extra = ?, detail_at = ? WHERE id = ?",
                  (fields["description"], fields["calories"], fields["device_name"], len(fields["laps"]) or None,
                   json.dumps(extra, ensure_ascii=False, separators=(",", ":")), cache.now_iso(), row["id"]))
    return True


def fetch_streams(session: client.StravaSession, cconn: sqlite3.Connection, row: sqlite3.Row, settings: dict,
                  hrp: dict) -> bool:
    payload = session.get(f"activities/{int(row['strava_id'])}/streams", keys=STREAM_KEYS, key_by_type="true")
    data = parse.streams(payload, row["sport"])
    now = cache.now_iso()
    if not data:
        cconn.execute("UPDATE activities SET streams_at = ? WHERE id = ?", (now, row["id"]))  # rien à redemander
        return False
    cconn.execute("INSERT INTO streams(activity_id, payload) VALUES (?, ?) ON CONFLICT(activity_id) DO UPDATE SET "
                  "payload = excluded.payload", (row["id"], fitfile.pack_streams(data)))
    derived = _derived(dict(row), data, settings, hrp)
    cconn.execute("UPDATE activities SET has_streams = 1, streams_at = ?, trimp = ?, load = ?, pace_zones = ?, "
                  "hr_zones = ? WHERE id = ?", (now, derived["trimp"], derived["load"], derived["pace_zones"],
                                                 derived["hr_zones"], row["id"]))
    return True


# ------------------------------------------------------------------ synchro
def _unpaired(ids: list[str]) -> set[str]:
    """Parmi ces séances du cache, celles qui ne sont pas des copies de séances Garmin."""
    if not ids:
        return set()
    with db.session(readonly=True) as conn:
        conn.execute("ATTACH DATABASE ? AS strava", (f"file:{cache.path().as_posix()}?mode=ro",))
        marks = ",".join("?" for _ in ids)
        return {r[0] for r in conn.execute(
            f"SELECT s.id FROM strava.activities s WHERE s.id IN ({marks}) AND NOT {cache.PAIRED}", ids)}


def run(conn: sqlite3.Connection, *, since: date | None = None, fit_days: int | None = None, with_fit: bool = True,
        progress: Progress | None = None) -> dict[str, Any]:
    """Synchro Strava du profil courant (``conn`` : sa base, pour les réglages et les séances Garmin)."""
    progress = progress or (lambda message, fraction=None: None)
    settings = db.get_settings(conn)
    hrp = analysis.hr_profile(conn, settings)
    summary: dict[str, Any] = {"seances": 0, "nouvelles": 0, "effacees": 0, "details": 0, "appels": 0, "erreurs": []}
    try:
        session = client.StravaSession()
    except client.StravaError as exc:
        if exc.access_refused:
            cache.forget()  # accès retiré : les données Strava du profil s'en vont avec lui
        raise
    progress("Strava : liste des séances…", None)
    first_day = since or history_start(settings)
    try:
        with cache.session() as cconn:
            summary["effacees"] += cache.purge(cconn)
            last_full = cache.get_meta(cconn, "liste_complete_le")
            full = since is not None or not last_full or \
                datetime.now() - datetime.fromisoformat(last_full) > timedelta(hours=FULL_EVERY_HOURS)
            if not full:
                row = cconn.execute("SELECT MAX(date) AS d FROM activities").fetchone()
                first_day = max(first_day, analysis.to_date(row["d"]) - timedelta(days=RECENT_DAYS)) if row["d"] \
                    else first_day
            now = cache.now_iso()
            seen: list[str] = []
            complete, page = False, 1
            try:
                while True:
                    items = session.get("athlete/activities", after=_epoch(first_day), page=page, per_page=PER_PAGE)
                    if not isinstance(items, list):
                        break
                    for item in items:
                        row = parse.summary_row(item)
                        if row and row["date"] >= first_day.isoformat():
                            summary["nouvelles"] += _store_summary(cconn, row, settings, hrp, now)
                            seen.append(row["id"])
                    cconn.commit()
                    if len(items) < PER_PAGE:
                        complete = True
                        break
                    page += 1
            except client.StravaError as exc:
                if not exc.rate_limited:
                    raise
                summary["erreurs"].append(str(exc))
            summary["seances"] = len(seen)
            if complete:
                # Ce que Strava n'a plus sur la période relue a été effacé chez Strava : on l'efface aussi
                window = cconn.execute("SELECT id FROM activities WHERE date >= ?", (first_day.isoformat(),)).fetchall()
                known = set(seen)
                for (activity_id,) in window:
                    if activity_id not in known:
                        _delete(cconn, activity_id)
                        summary["effacees"] += 1
                if full:
                    cache.set_meta(cconn, "liste_complete_le", now)
                    cache.set_meta(cconn, "historique_depuis", first_day.isoformat())
            cconn.commit()
            # Détails : les séances de renfo faites sur Strava seulement, puis les séances récentes
            progress("Strava : détail des séances récentes…", None)
            recent = (date.today() - timedelta(days=DETAIL_DAYS)).isoformat()
            renfo_since = (date.today() - timedelta(days=RENFO_DAYS)).isoformat()
            rows = cconn.execute(
                "SELECT * FROM activities WHERE detail_at IS NULL AND (date >= ? OR (date >= ? AND sport IN (?, ?))) "
                "ORDER BY start_local DESC", (recent, renfo_since, *renfo.SPORTS)).fetchall()
            alone = _unpaired([r["id"] for r in rows if r["sport"] in renfo.SPORTS])
            wanted = [r for r in rows if r["date"] >= recent or r["id"] in alone]
            try:
                for row in wanted[:MAX_DETAILS]:
                    if not client.can_spend(1):
                        summary["erreurs"].append("Quota de Strava ménagé : le détail des autres séances viendra "
                                                  "avec les prochaines synchros.")
                        break
                    if fetch_detail(session, cconn, row):
                        summary["details"] += 1
                    cconn.commit()
            except client.StravaError as exc:
                if not exc.rate_limited:
                    raise
                summary["erreurs"].append(str(exc))
            athlete = session.data.get("athlete_id")
            if athlete:
                cache.set_meta(cconn, "athlete_id", str(athlete))
            if cconn.execute("SELECT 1 FROM exercises LIMIT 1").fetchone():
                from .. import views  # la vue « Renfo » arrive aussi avec des exercices notés sur Strava

                views.sync_renfo_view(conn, present=True)
    except client.StravaError as exc:
        if exc.access_refused:
            cache.forget()
        raise
    finally:
        summary["appels"] = session.calls
    progress("Strava : à jour", None)
    LOG.info("Strava : %s séances relues, %s nouvelles, %s effacées, %s détails, %s appels", summary["seances"],
             summary["nouvelles"], summary["effacees"], summary["details"], summary["appels"])
    # Le journal des synchros (que Claude Desktop peut lire) ne garde rien des séances Strava : les appels et les
    # alertes seulement (règles de Strava : pas de données Strava, même résumées, pour une IA)
    return {"appels": summary["appels"], "erreurs": summary["erreurs"]}


# ------------------------------------------------------- séance ouverte
def ensure_detail(activity_id: str) -> str | None:
    """Séance Strava ouverte dans l'interface : son détail et ses courbes, demandés à Strava s'ils manquent.
    Renvoie un message à afficher (None si tout va bien)."""
    if config.is_demo() or not client.connected() or not cache.path().exists():
        return None
    with cache.session() as cconn:
        row = cconn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
        if not row:
            return None
        if row["detail_at"] and (row["streams_at"] or row["extra"] and json.loads(row["extra"]).get("manuelle")):
            return None
        if not client.can_spend(1, reserve15=2, reserve_day=10):
            return "quota de Strava atteint pour l'instant : les courbes viendront un peu plus tard"
        try:
            session = client.StravaSession()
            if not row["detail_at"]:
                if not fetch_detail(session, cconn, row):
                    return "cette séance n'existe plus chez Strava"
                cconn.commit()
            row = cconn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
            manual = json.loads(row["extra"] or "{}").get("manuelle")
            if not row["streams_at"] and not manual and client.can_spend(1, reserve15=2, reserve_day=10):
                with db.session(readonly=True) as conn:
                    settings = db.get_settings(conn)
                    hrp = analysis.hr_profile(conn, settings)
                fetch_streams(session, cconn, row, settings, hrp)
        except client.StravaError as exc:
            LOG.warning("Séance Strava %s : %s", activity_id, exc)
            if exc.access_refused:
                with db.session() as conn:
                    from .. import sync as sync_module

                    sync_module._note_refusal(conn, REFUSED, exc)
                cache.forget()
            return str(exc)
    return None


def polyline_streams(activity_id: str) -> dict | None:
    """Tracé résumé d'une séance Strava sans courbes (aucun appel à Strava) : latitude et longitude."""
    if not cache.path().exists():
        return None
    with cache.session() as cconn:
        row = cconn.execute("SELECT polyline, confirmed_at FROM activities WHERE id = ?", (activity_id,)).fetchone()
    if not row or not row["polyline"] or (not config.is_demo() and row["confirmed_at"] < cache.cutoff()):
        return None
    points = parse.decode_polyline(row["polyline"])
    if len(points) < 2:
        return None
    return {"t": list(range(len(points))), "lat": [p[0] for p in points], "lon": [p[1] for p in points]}


def counts() -> dict[str, Any]:
    """Ce que le cache contient (pour les Réglages) : séances, dont copies de séances Garmin."""
    empty = {"seances": 0, "seules": 0, "copies": 0, "liste_complete_le": None, "premiere": None}
    if not cache.path().exists():
        return empty
    try:
        with db.session(readonly=True) as conn:
            conn.execute("ATTACH DATABASE ? AS strava", (f"file:{cache.path().as_posix()}?mode=ro",))
            limit = "" if config.is_demo() else "AND s.confirmed_at >= ?"
            params = () if config.is_demo() else (cache.cutoff(),)
            total = conn.execute(f"SELECT COUNT(*) FROM strava.activities s WHERE 1 = 1 {limit}", params).fetchone()[0]
            alone = conn.execute(f"SELECT COUNT(*) FROM strava.activities s WHERE NOT {cache.PAIRED} {limit}",
                                 params).fetchone()[0]
            last = conn.execute("SELECT value FROM strava.meta WHERE key = 'liste_complete_le'").fetchone()
            first = conn.execute(f"SELECT MIN(date) FROM strava.activities s WHERE 1 = 1 {limit}", params).fetchone()[0]
    except sqlite3.Error:  # cache en cours de création par la synchro
        return empty
    return {"seances": total, "seules": alone, "copies": total - alone, "liste_complete_le": last[0] if last else None,
            "premiere": first}

