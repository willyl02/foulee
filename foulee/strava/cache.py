"""Cache Strava : séances, tours, courbes et exercices lus chez Strava, gardés 48 heures au plus.

Les règles de l'API de Strava (API Policy du 1er juin 2026) encadrent ce que Foulée en fait :
- pas de stockage durable : un cache de 7 jours au plus (§ 5.5, § 6.2), et une séance effacée chez Strava
  doit disparaître sous 48 heures (§ 6.3). Chaque ligne porte donc l'heure à laquelle Strava l'a confirmée ;
  au-delà de 48 heures sans confirmation, elle n'est plus montrée, puis elle est effacée ;
- pas d'IA (§ 5.3) : ce cache est un fichier à part (``strava-cache.db``), que seule l'interface ouvre. Le
  connecteur de Claude Desktop n'y a pas accès (pour Strava, Claude passe par le connecteur officiel de Strava) ;
- les données d'un profil ne sont montrées qu'à ce profil (§ 2.3) : un cache par profil, dans son dossier.

Côté interface, ``attach`` branche le cache sur une connexion en lecture : des vues temporaires du même nom
(``activities``, ``laps``, ``streams``, ``exercises``) masquent alors les tables de la base pour cette
connexion seulement, et y ajoutent les séances Strava qui ne sont pas des copies de séances Garmin. Les
calculs de Foulée (listes, tuiles, renfo, charge) les voient sans rien changer d'autre.

Doublons : une séance Strava est la copie d'une séance Garmin si Strava la tient de Garmin Connect (son
``external_id`` porte le numéro Garmin) ou si les deux se recouvrent au moins de moitié dans le temps (une
même personne ne fait pas deux séances à la fois). Garmin l'emporte toujours : ses données sont plus riches,
gardées pour de bon et lisibles par Claude. Le titre et la description Strava s'affichent sur la séance Garmin.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from .. import config

LOG = logging.getLogger("foulee.strava")

KEEP_HOURS = 48
CALC_KEYS = ("load_day", "ctl", "atl", "tsb", "acwr")

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL, start_local TEXT NOT NULL, start_utc TEXT,
    date TEXT NOT NULL, sport TEXT NOT NULL, type_key TEXT, name TEXT, description TEXT, duration_s REAL, moving_s REAL,
    elapsed_s REAL, distance_m REAL, elev_gain_m REAL, elev_loss_m REAL, avg_hr REAL, max_hr REAL, avg_speed REAL,
    max_speed REAL, avg_gap_speed REAL, avg_cadence REAL, avg_power REAL, calories REAL, te_aerobic REAL,
    te_anaerobic REAL, garmin_load REAL, vo2max REAL, trimp REAL, load REAL, hr_zones TEXT, pace_zones TEXT,
    hr_zones_garmin TEXT, extra TEXT, start_lat REAL, start_lon REAL, lap_count INTEGER,
    has_streams INTEGER NOT NULL DEFAULT 0, fit_path TEXT, updated_at TEXT,
    -- propres au cache
    strava_id INTEGER NOT NULL, external_id TEXT, garmin_id TEXT, device_name TEXT, polyline TEXT,
    confirmed_at TEXT NOT NULL,   -- dernière fois que Strava a donné cette séance
    detail_at TEXT,               -- détail (description, calories, tours) lu à cette heure
    streams_at TEXT               -- courbes lues à cette heure
);
CREATE INDEX IF NOT EXISTS activities_date ON activities(date);
CREATE TABLE IF NOT EXISTS laps (
    activity_id TEXT NOT NULL, idx INTEGER NOT NULL, start_s REAL, duration_s REAL, elapsed_s REAL, distance_m REAL,
    avg_hr REAL, max_hr REAL, avg_speed REAL, max_speed REAL, avg_cadence REAL, avg_power REAL, elev_gain_m REAL,
    elev_loss_m REAL, intensity TEXT, PRIMARY KEY (activity_id, idx)
);
CREATE TABLE IF NOT EXISTS streams (activity_id TEXT PRIMARY KEY, payload BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS exercises (
    activity_id TEXT NOT NULL, idx INTEGER NOT NULL, category TEXT NOT NULL, name TEXT, sets INTEGER NOT NULL,
    reps INTEGER, duration_s REAL, max_kg REAL, volume_kg REAL, PRIMARY KEY (activity_id, idx)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
"""
EXTRA_COLUMNS = ("strava_id", "external_id", "garmin_id", "device_name", "polyline", "confirmed_at", "detail_at",
                 "streams_at")
TABLES = ("activities", "laps", "streams", "exercises")

# Recouvrement : la séance Strava est une copie si elle partage au moins la moitié de la plus courte des deux
# (une minute au moins), ou si Strava la tient de Garmin Connect avec le même numéro.
PAIRED = """EXISTS (
    SELECT 1 FROM main.activities g
    WHERE g.source <> 'strava' AND g.date BETWEEN date(s.date, '-1 day') AND date(s.date, '+1 day')
      AND ((s.garmin_id IS NOT NULL AND g.source = 'garmin' AND g.source_id = s.garmin_id)
        OR (MIN(julianday(g.start_local) + COALESCE(g.elapsed_s, g.duration_s, 0) / 86400.0,
                julianday(s.start_local) + COALESCE(s.elapsed_s, s.duration_s, 0) / 86400.0)
            - MAX(julianday(g.start_local), julianday(s.start_local))) * 86400.0
           >= 0.5 * MAX(60, MIN(COALESCE(g.elapsed_s, g.duration_s, 0), COALESCE(s.elapsed_s, s.duration_s, 0)))))"""


def path() -> Path:
    return config.data_dir() / ("strava-cache-demo.db" if config.is_demo() else "strava-cache.db")


def now_iso(at: datetime | None = None) -> str:
    return (at or datetime.now()).replace(microsecond=0).isoformat(sep=" ")


def cutoff(at: datetime | None = None) -> str:
    """Ce qui a été confirmé par Strava avant cette heure n'est plus montré (puis effacé)."""
    return now_iso((at or datetime.now()) - timedelta(hours=KEEP_HOURS))


def connect(target: Path | None = None) -> sqlite3.Connection:
    target = target or path()
    conn = sqlite3.connect(target, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_meta(conn: sqlite3.Connection, key: str, schema: str = "main") -> str | None:
    row = conn.execute(f"SELECT value FROM {schema}.meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    if value is None:
        conn.execute("DELETE FROM meta WHERE key = ?", (key,))
        return
    conn.execute("INSERT INTO meta(key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                 "value = excluded.value, updated_at = excluded.updated_at", (key, value, now_iso()))


def purge(conn: sqlite3.Connection, at: datetime | None = None) -> int:
    """Efface ce que Strava n'a pas reconfirmé depuis 48 heures (séances, détails, courbes, informations)."""
    if config.is_demo():
        return 0
    limit = cutoff(at)
    gone = [r[0] for r in conn.execute("SELECT id FROM activities WHERE confirmed_at < ?", (limit,))]
    for table in ("laps", "streams", "exercises"):
        conn.execute(f"DELETE FROM {table} WHERE activity_id NOT IN (SELECT id FROM activities WHERE confirmed_at >= ?)",
                     (limit,))
    conn.execute("DELETE FROM activities WHERE confirmed_at < ?", (limit,))
    # Détail lu il y a plus de 48 heures : description, calories, tours et exercices repartent avec lui
    stale = [r[0] for r in conn.execute("SELECT id FROM activities WHERE detail_at IS NOT NULL AND detail_at < ?",
                                        (limit,))]
    for activity_id in stale:
        conn.execute("DELETE FROM laps WHERE activity_id = ?", (activity_id,))
        conn.execute("DELETE FROM exercises WHERE activity_id = ?", (activity_id,))
        conn.execute("UPDATE activities SET description = NULL, calories = NULL, detail_at = NULL, lap_count = NULL "
                     "WHERE id = ?", (activity_id,))
    old_streams = [r[0] for r in conn.execute(
        "SELECT id FROM activities WHERE streams_at IS NOT NULL AND streams_at < ?", (limit,))]
    for activity_id in old_streams:
        conn.execute("DELETE FROM streams WHERE activity_id = ?", (activity_id,))
        conn.execute("UPDATE activities SET streams_at = NULL, hr_zones = NULL, pace_zones = NULL, "
                     "has_streams = CASE WHEN polyline IS NOT NULL THEN 1 ELSE 0 END WHERE id = ?", (activity_id,))
    conn.execute("DELETE FROM meta WHERE updated_at < ?", (limit,))
    return len(gone)


def purge_file() -> int:
    """Purge du cache du profil courant, s'il existe (au démarrage, puis à chaque vérification de la synchro
    automatique) : rien de Strava ne dure plus de 48 heures tant que Foulée tourne, même sans synchro."""
    if config.is_demo() or not path().exists():
        return 0
    try:
        with session() as conn:
            return purge(conn)
    except sqlite3.Error as exc:
        LOG.warning("Cache Strava : purge impossible (%s)", exc)
        return 0


def purge_all() -> None:
    """Purge des caches Strava de tous les profils."""
    from .. import utilisateurs  # import tardif : les profils importent beaucoup de choses

    for entry in utilisateurs.profiles():
        with config.using_profile(entry):
            purge_file()


def forget() -> None:
    """Efface tout le cache Strava du profil courant (déconnexion, accès retiré chez Strava)."""
    target = path()
    for suffix in ("", "-wal", "-shm"):
        candidate = target.with_name(target.name + suffix)
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:  # fichier ouvert ailleurs (Windows) : vidé à défaut d'être supprimé
            LOG.warning("Cache Strava : %s", exc)
            if not suffix:
                try:
                    with session() as conn:
                        for table in (*TABLES, "meta"):
                            conn.execute(f"DELETE FROM {table}")
                except sqlite3.Error:
                    pass


# ----------------------------------------------------------- côté interface
_calc_memo: dict[tuple, list[tuple[str, str, float]]] = {}
_calc_lock = threading.Lock()


def attached(conn: sqlite3.Connection) -> bool:
    return any(row[1] == "strava" for row in conn.execute("PRAGMA database_list"))


def attach(conn: sqlite3.Connection) -> bool:
    """Branche le cache Strava du profil sur une connexion en lecture (voir le haut du module).

    Renvoie False s'il n'y a rien à brancher : pas de cache, ou une connexion qui n'est pas en lecture seule."""
    target = path()
    if not target.exists() or attached(conn):
        return False
    try:
        conn.execute("ATTACH DATABASE ? AS strava", (f"file:{target.as_posix()}?mode=ro",))
    except sqlite3.Error as exc:
        LOG.warning("Cache Strava illisible : %s", exc)
        return False
    try:
        columns = {r[1] for r in conn.execute("PRAGMA strava.table_info(activities)")}
        if "confirmed_at" not in columns:  # cache d'une version future ou abîmé : on ne s'en sert pas
            conn.execute("DETACH DATABASE strava")
            return False
        limit = "" if config.is_demo() else "s.confirmed_at >= ? AND"
        params = () if config.is_demo() else (cutoff(),)
        conn.execute("DROP TABLE IF EXISTS temp.strava_seen")
        conn.execute(f"CREATE TEMP TABLE strava_seen AS SELECT s.id FROM strava.activities s "
                     f"WHERE {limit} NOT {PAIRED}", params)
        if not conn.execute("SELECT 1 FROM temp.strava_seen LIMIT 1").fetchone():
            return True  # branché pour les titres Strava des séances Garmin, rien à ajouter aux listes
        for table in TABLES:
            main_columns = [r[1] for r in conn.execute(f"PRAGMA main.table_info({table})")]
            cache_columns = {r[1] for r in conn.execute(f"PRAGMA strava.table_info({table})")}
            picked = ", ".join(c if c in cache_columns else f"NULL AS {c}" for c in main_columns)
            plain = ", ".join(main_columns)
            key = "id" if table == "activities" else "activity_id"
            conn.execute(f"CREATE TEMP VIEW {table} AS SELECT {plain} FROM main.{table} UNION ALL "
                         f"SELECT {picked} FROM strava.{table} WHERE {key} IN (SELECT id FROM temp.strava_seen)")
        _attach_calc(conn)
    except sqlite3.Error as exc:
        LOG.warning("Cache Strava : branchement impossible (%s)", exc)
        for table in TABLES:
            conn.execute(f"DROP VIEW IF EXISTS temp.{table}")
        return False
    return True


def _attach_calc(conn: sqlite3.Connection) -> None:
    """Charge du jour, chronique, aiguë et fraîcheur avec les séances Strava : recalculées à la volée (rien de
    Strava n'est écrit dans la base), seulement si des séances Strava apportent une charge."""
    if not conn.execute("SELECT 1 FROM strava.activities WHERE id IN (SELECT id FROM temp.strava_seen) "
                        "AND COALESCE(load, 0) > 0 LIMIT 1").fetchone():
        return
    from .. import analysis  # import tardif : analysis importe beaucoup de choses

    stamp = conn.execute("SELECT COUNT(*), MAX(updated_at), SUM(COALESCE(load, 0)) FROM activities").fetchone()
    key = (str(config.db_path()), tuple(stamp), datetime.now().date().isoformat())
    with _calc_lock:
        rows = _calc_memo.get(key)
    if rows is None:
        rows = [(day, metric, value) for day, values in analysis.daily_calc_values(conn).items()
                for metric, value in values.items() if metric in CALC_KEYS]
        with _calc_lock:
            _calc_memo.clear()
            _calc_memo[key] = rows
    conn.execute("CREATE TEMP TABLE strava_calc (date TEXT, metric TEXT, value REAL)")
    conn.executemany("INSERT INTO temp.strava_calc VALUES (?, ?, ?)", rows)
    keys = ", ".join(f"'{k}'" for k in CALC_KEYS)
    conn.execute("CREATE TEMP VIEW daily AS SELECT date, metric, value, source FROM main.daily "
                 f"WHERE NOT (source = 'calc' AND metric IN ({keys})) "
                 "UNION ALL SELECT date, metric, value, 'calc' AS source FROM temp.strava_calc")


def paired_with(conn: sqlite3.Connection, garmin: sqlite3.Row | dict) -> sqlite3.Row | None:
    """La copie Strava d'une séance Garmin (cache branché), pour afficher son titre et sa description."""
    if not attached(conn):
        return None
    duration = float(garmin["elapsed_s"] or garmin["duration_s"] or 0)
    params: list = [str(garmin["source_id"]), garmin["start_local"], duration, garmin["start_local"], duration,
                    garmin["date"], garmin["date"]]
    limit = ""
    if not config.is_demo():
        limit = "AND s.confirmed_at >= ?"
        params.append(cutoff())
    return conn.execute(
        "SELECT s.* FROM strava.activities s WHERE (s.garmin_id = ? OR "
        "(MIN(julianday(?) + ? / 86400.0, julianday(s.start_local) + COALESCE(s.elapsed_s, s.duration_s, 0) / 86400.0)"
        " - MAX(julianday(?), julianday(s.start_local))) * 86400.0 >= "
        "0.5 * MAX(60, MIN(?, COALESCE(s.elapsed_s, s.duration_s, 0)))) "
        f"AND s.date BETWEEN date(?, '-1 day') AND date(?, '+1 day') {limit} ORDER BY s.start_local LIMIT 1",
        params).fetchone()
