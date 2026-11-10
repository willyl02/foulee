"""Base locale SQLite : schéma, connexion, réglages.

Principe : on garde le *brut* (réponses Garmin telles que reçues, table ``raw``)
et le *normalisé* (tables ``daily``, ``activities``, ``laps``, ``streams``).
Le normalisé peut toujours être reconstruit à partir du brut (``foulee reparse``).
"""

from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from . import config

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Réponses brutes des sources, une ligne par (source, flux, clé = date ou id)
CREATE TABLE IF NOT EXISTS raw (
    source     TEXT NOT NULL,
    kind       TEXT NOT NULL,
    key        TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    payload    TEXT NOT NULL,
    PRIMARY KEY (source, kind, key)
);

-- Métriques quotidiennes au format long : une ligne = (jour, métrique, source)
CREATE TABLE IF NOT EXISTS daily (
    date   TEXT NOT NULL,
    metric TEXT NOT NULL,
    value  REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'garmin',
    PRIMARY KEY (date, metric, source)
);
CREATE INDEX IF NOT EXISTS daily_metric_date ON daily(metric, date);

CREATE TABLE IF NOT EXISTS activities (
    id           TEXT PRIMARY KEY,      -- 'garmin:123456789'
    source       TEXT NOT NULL,
    source_id    TEXT NOT NULL,
    start_local  TEXT NOT NULL,         -- 'AAAA-MM-JJ HH:MM:SS' heure locale
    start_utc    TEXT,
    date         TEXT NOT NULL,         -- jour local
    sport        TEXT NOT NULL,         -- famille normalisée (course, trail, velo…)
    type_key     TEXT,                  -- type d'origine (Garmin typeKey)
    name         TEXT,
    description  TEXT,
    duration_s   REAL,
    moving_s     REAL,
    elapsed_s    REAL,
    distance_m   REAL,
    elev_gain_m  REAL,
    elev_loss_m  REAL,
    avg_hr       REAL,
    max_hr       REAL,
    avg_speed    REAL,                  -- m/s
    max_speed    REAL,
    avg_gap_speed REAL,                 -- allure ajustée à la pente (m/s) si fournie
    avg_cadence  REAL,
    avg_power    REAL,
    calories     REAL,
    te_aerobic   REAL,
    te_anaerobic REAL,
    garmin_load  REAL,                  -- charge d'entraînement calculée par Garmin
    vo2max       REAL,
    trimp        REAL,                  -- TRIMP calculé par Foulée (FC)
    load         REAL,                  -- charge retenue pour les calculs forme/fatigue
    hr_zones     TEXT,                  -- JSON : secondes en zones FC 1..5
    pace_zones   TEXT,                  -- JSON : secondes en zones d'allure 1..5
    start_lat    REAL,
    start_lon    REAL,
    lap_count    INTEGER,
    has_streams  INTEGER NOT NULL DEFAULT 0,
    fit_path     TEXT,
    updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS activities_date ON activities(date);
CREATE INDEX IF NOT EXISTS activities_sport ON activities(sport, date);

CREATE TABLE IF NOT EXISTS laps (
    activity_id TEXT NOT NULL,
    idx         INTEGER NOT NULL,
    start_s     REAL,
    duration_s  REAL,
    elapsed_s   REAL,
    distance_m  REAL,
    avg_hr      REAL,
    max_hr      REAL,
    avg_speed   REAL,
    max_speed   REAL,
    avg_cadence REAL,
    avg_power   REAL,
    elev_gain_m REAL,
    elev_loss_m REAL,
    intensity   TEXT,
    PRIMARY KEY (activity_id, idx)
);

-- Courbes d'une séance (FC, vitesse, altitude, GPS…) en JSON compressé
CREATE TABLE IF NOT EXISTS streams (
    activity_id TEXT PRIMARY KEY,
    payload     BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    source     TEXT NOT NULL,
    stream     TEXT NOT NULL,
    last_date  TEXT,
    updated_at TEXT,
    info       TEXT,
    PRIMARY KEY (source, stream)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT,
    finished_at TEXT,
    source      TEXT,
    status      TEXT,
    summary     TEXT
);

CREATE TABLE IF NOT EXISTS views (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    icon       TEXT,
    position   INTEGER NOT NULL DEFAULT 0,
    spec       TEXT NOT NULL,            -- JSON : liste de tuiles + options
    builtin    INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Réglages par défaut. Tous modifiables depuis la page « Réglages » ou par Claude.
DEFAULT_SETTINGS: dict[str, Any] = {
    "vma_kmh": 16.0,
    "fc_max": None,            # None = valeur de tes zones Garmin, sinon FC max observée
    "fc_repos": None,          # None = médiane de ta FC de repos sur 30 jours
    "sexe": "H",               # coefficient du TRIMP de Banister (H = 1,92 ; F = 1,67)
    "objectif": {
        "nom": "Semi-marathon de Paris",
        "date": "2027-03-07",
        "distance_km": 21.0975,
        "temps_cible": "1:25:00",
    },
    "postes": {
        "actif": True,
        "impaires": "matin",   # semaines ISO impaires
        "paires": "soir",      # semaines ISO paires
        "jours_ouvres": True,  # comparer uniquement du lundi au vendredi
        "semaines_exclues": [],  # ex. ["2026-W32", "2026-W33"] (congés)
    },
    "zones_allure_pct_vma": [70, 80, 88, 95],
    "fractions_seuil_pct_vma": 85,
    "fit_auto_jours": 180,     # télécharge automatiquement les FIT des N derniers jours
    "historique_depuis": None,  # date du premier import
    "carte_fond": "osm",       # osm | ign | aucun
    "canal_maj": "stable",     # stable | beta : quelles versions proposer aux mises à jour
    "charge_source": "garmin",  # garmin (charge Garmin si dispo) | trimp
}

ZONE_NAMES_PACE = ["Récup / EF", "Endurance active", "Seuil / semi", "Allure 10 km", "VMA"]


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def connect(path: Path | None = None, *, readonly: bool = False) -> sqlite3.Connection:
    path = path or config.db_path()
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=15, check_same_thread=False)
    else:
        conn = sqlite3.connect(path, timeout=15, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),)
    )
    conn.commit()
    from . import views  # import local pour éviter un cycle

    views.ensure_default_views(conn)


@contextmanager
def session(*, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    """Ouvre la base (et la crée si besoin), puis la referme proprement."""
    path = config.db_path()
    if readonly and not path.exists():
        readonly = False
    conn = connect(path, readonly=readonly)
    try:
        if not readonly:
            init(conn)
        yield conn
        if not readonly:
            conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------- meta
def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def delete_meta(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("DELETE FROM meta WHERE key = ?", (key,))


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


# ----------------------------------------------------------------- settings
def get_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    result = copy.deepcopy(DEFAULT_SETTINGS)
    for row in conn.execute("SELECT key, value FROM settings"):
        try:
            value = json.loads(row["value"])
        except json.JSONDecodeError:
            continue
        if isinstance(result.get(row["key"]), dict) and isinstance(value, dict):
            result[row["key"]].update(value)
        else:
            result[row["key"]] = value
    return result


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value, ensure_ascii=False)),
    )


# ---------------------------------------------------------------------- raw
def put_raw(conn: sqlite3.Connection, source: str, kind: str, key: str, payload: Any) -> None:
    conn.execute(
        "INSERT INTO raw(source, kind, key, fetched_at, payload) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(source, kind, key) DO UPDATE SET fetched_at = excluded.fetched_at, payload = excluded.payload",
        (source, kind, key, now_iso(), json.dumps(payload, ensure_ascii=False)),
    )


def get_raw(conn: sqlite3.Connection, source: str, kind: str, key: str) -> Any | None:
    row = conn.execute(
        "SELECT payload FROM raw WHERE source = ? AND kind = ? AND key = ?", (source, kind, key)
    ).fetchone()
    return json.loads(row["payload"]) if row else None


# -------------------------------------------------------------------- daily
def put_daily(
    conn: sqlite3.Connection, date: str, values: dict[str, float | None], source: str = "garmin"
) -> int:
    count = 0
    for metric, value in values.items():
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number != number:  # NaN
            continue
        conn.execute(
            "INSERT INTO daily(date, metric, value, source) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(date, metric, source) DO UPDATE SET value = excluded.value",
            (date, metric, number, source),
        )
        count += 1
    return count


def delete_daily(conn: sqlite3.Connection, date: str, metrics: list[str], source: str = "garmin") -> None:
    if not metrics:
        return
    marks = ",".join("?" for _ in metrics)
    conn.execute(
        f"DELETE FROM daily WHERE date = ? AND source = ? AND metric IN ({marks})", (date, source, *metrics)
    )


# --------------------------------------------------------------- sync state
def get_sync_state(conn: sqlite3.Connection, source: str, stream: str) -> str | None:
    row = conn.execute(
        "SELECT last_date FROM sync_state WHERE source = ? AND stream = ?", (source, stream)
    ).fetchone()
    return row["last_date"] if row else None


def set_sync_state(conn: sqlite3.Connection, source: str, stream: str, last_date: str, info: str = "") -> None:
    conn.execute(
        "INSERT INTO sync_state(source, stream, last_date, updated_at, info) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(source, stream) DO UPDATE SET last_date = excluded.last_date, "
        "updated_at = excluded.updated_at, info = excluded.info",
        (source, stream, last_date, now_iso(), info),
    )


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {}
    for table in ("activities", "daily", "laps", "streams", "raw", "views"):
        counts[table] = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    return counts
