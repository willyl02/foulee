"""Withings dans l'interface : état de la connexion, résumé pour la tuile, vue « Withings ».

La vue « Withings » arrive d'office quand on connecte son compte (comme « Mon club » quand
on coche son club) et repart quand on le déconnecte. Ses tuiles suivent ce que tes appareils
mesurent (balance, tensiomètre, Sleep Analyzer, montre) tant que tu ne l'as pas modifiée
toi-même ; ensuite, elle est à toi.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from .. import config, db, views
from . import client

SOURCE = "withings"
REFUSED = "withings_refus"
# Familles de mesures : une métrique témoin pour savoir si l'appareil existe
FAMILIES = {
    "corps": "wi_weight_kg",
    "tension": "wi_bp_sys",
    "sommeil": "wi_sleep_s",
    "activite": "wi_steps",
}
BODY = ["wi_weight_kg", "wi_fat_pct", "wi_fat_kg", "wi_muscle_kg", "wi_water_pct", "wi_water_kg", "wi_bone_kg",
        "wi_lean_kg", "wi_visceral", "wi_bmr", "wi_bmi", "wi_pwv", "wi_vascular_age", "wi_metabolic_age"]
PRESSURE = ["wi_bp_sys", "wi_bp_dia", "wi_pulse"]
SLEEP = ["wi_sleep_s", "wi_sleep_score", "wi_deep_s", "wi_light_s", "wi_rem_s", "wi_awake_s", "wi_wake_count",
         "wi_sleep_hr", "wi_sleep_resp", "wi_bed_h", "wi_rise_h", "wi_snoring_s"]
ACTIVITY = ["wi_steps", "wi_distance_km", "wi_active_s", "wi_cal_active"]


ACTIVITY_DAYS = 90  # l'activité Withings compte si des pas ont été comptés sur cette durée


def _activity_since() -> str:
    return (date.today() - timedelta(days=ACTIVITY_DAYS)).isoformat()


def families(conn: sqlite3.Connection) -> list[str]:
    """Les familles de mesures présentes. L'activité demande des pas récents : sans podomètre Withings, son
    appli envoie des journées à 0 pas (et quelques séances importées), qui ne font pas une activité à suivre."""
    found = []
    for name, metric in FAMILIES.items():
        if name == "activite":
            query = "SELECT 1 FROM daily WHERE source = ? AND metric = ? AND value > 0 AND date >= ? LIMIT 1"
            params: tuple = (SOURCE, metric, _activity_since())
        else:
            query, params = "SELECT 1 FROM daily WHERE source = ? AND metric = ? LIMIT 1", (SOURCE, metric)
        if conn.execute(query, params).fetchone():
            found.append(name)
    return found


def refused(conn: sqlite3.Connection) -> dict | None:
    raw = db.get_meta(conn, REFUSED)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def last_sync(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(updated_at) AS t FROM sync_state WHERE source = ?", (SOURCE,)).fetchone()
    return row["t"] if row else None


def status(conn: sqlite3.Connection) -> dict:
    """Ce que l'interface affiche dans Réglages → Withings (jamais le Secret ni les jetons)."""
    demo = config.is_demo()
    data = {} if demo else client.load()
    return {
        "demo": demo,
        "appli": bool(data.get("client_id") and data.get("client_secret")),
        "client_id_fin": (data.get("client_id") or "")[-4:] if data.get("client_id") else "",
        "connecte": bool(data.get("refresh_token")) or (demo and bool(families(conn))),
        "connecte_le": db.get_meta(conn, "withings_connecte_le"),
        "appli_le": db.get_meta(conn, "withings_appli_le"),
        "refus": refused(conn),
        "derniere_synchro": last_sync(conn),
        "familles": families(conn),
        "relais": client.relay_url(),
        "tableau_de_bord": client.DASHBOARD,
        "vue": bool(conn.execute("SELECT 1 FROM views WHERE id = ?", (views.WITHINGS_VIEW,)).fetchone()),
    }


def refresh_view(conn: sqlite3.Connection) -> None:
    """Après une synchro : la vue suit les familles de mesures, tant qu'elle n'a pas été modifiée."""
    if conn.execute("SELECT 1 FROM views WHERE id = ?", (views.WITHINGS_VIEW,)).fetchone():
        views.sync_withings_view(conn, True, families(conn))


# ------------------------------------------------------------------ résumé
def _day_values(conn: sqlite3.Connection, day: str, keys: list[str]) -> dict[str, float]:
    marks = ",".join("?" for _ in keys)
    return {r["metric"]: r["value"] for r in conn.execute(
        f"SELECT metric, value FROM daily WHERE source = ? AND date = ? AND metric IN ({marks})", (SOURCE, day, *keys))}


def _latest(conn: sqlite3.Connection, metric: str, until: str | None = None) -> str | None:
    if until:
        row = conn.execute("SELECT MAX(date) AS d FROM daily WHERE source = ? AND metric = ? AND date <= ?",
                           (SOURCE, metric, until)).fetchone()
    else:
        row = conn.execute("SELECT MAX(date) AS d FROM daily WHERE source = ? AND metric = ?", (SOURCE, metric)).fetchone()
    return row["d"] if row else None


def _average(conn: sqlite3.Connection, metric: str, start: str, end: str) -> tuple[float | None, int]:
    row = conn.execute("SELECT AVG(value) AS m, COUNT(*) AS n FROM daily WHERE source = ? AND metric = ? "
                       "AND date BETWEEN ? AND ?", (SOURCE, metric, start, end)).fetchone()
    return (row["m"], row["n"]) if row and row["n"] else (None, 0)


def pressure_level(systolic: float | None, diastolic: float | None) -> dict | None:
    """Repères de la Société européenne d'hypertension (mesures au cabinet) : une indication, pas un diagnostic."""
    if systolic is None or diastolic is None:
        return None
    if systolic >= 180 or diastolic >= 110:
        return {"niveau": "hta3", "libelle": "Très élevée"}
    if systolic >= 160 or diastolic >= 100:
        return {"niveau": "hta2", "libelle": "Élevée (grade 2)"}
    if systolic >= 140 or diastolic >= 90:
        return {"niveau": "hta1", "libelle": "Élevée (grade 1)"}
    if systolic >= 130 or diastolic >= 85:
        return {"niveau": "haute", "libelle": "Normale haute"}
    if systolic >= 120 or diastolic >= 80:
        return {"niveau": "normale", "libelle": "Normale"}
    return {"niveau": "optimale", "libelle": "Optimale"}


def summary(conn: sqlite3.Connection) -> dict:
    """Dernière pesée, dernière tension, dernière nuit, dernière journée : pour la tuile de la vue Withings."""
    out: dict = {"etat": status(conn)}
    day = _latest(conn, "wi_weight_kg")
    if day:
        values = _day_values(conn, day, BODY)
        ref_day = _latest(conn, "wi_weight_kg", (date.fromisoformat(day) - timedelta(days=28)).isoformat())
        out["corps"] = {"date": day, "valeurs": values,
                        "reference": {"date": ref_day, "valeurs": _day_values(conn, ref_day, BODY)} if ref_day else None,
                        "pesees_30j": _average(conn, "wi_weight_kg", (date.fromisoformat(day) - timedelta(days=29)).isoformat(), day)[1]}
    day = _latest(conn, "wi_bp_sys")
    if day:
        values = _day_values(conn, day, PRESSURE)
        start = (date.fromisoformat(day) - timedelta(days=6)).isoformat()
        sys7, n7 = _average(conn, "wi_bp_sys", start, day)
        dia7, _ = _average(conn, "wi_bp_dia", start, day)
        out["tension"] = {"date": day, "valeurs": values, "niveau": pressure_level(values.get("wi_bp_sys"), values.get("wi_bp_dia")),
                          "moyenne_7j": {"wi_bp_sys": sys7, "wi_bp_dia": dia7, "jours": n7},
                          "niveau_7j": pressure_level(sys7, dia7) if n7 >= 3 else None}
    day = _latest(conn, "wi_sleep_s")
    if day:
        start = (date.fromisoformat(day) - timedelta(days=6)).isoformat()
        out["sommeil"] = {"date": day, "valeurs": _day_values(conn, day, SLEEP),
                          "moyenne_7j": _average(conn, "wi_sleep_s", start, day)[0]}
    row = conn.execute("SELECT MAX(date) AS d FROM daily WHERE source = ? AND metric = 'wi_steps' AND value > 0 "
                       "AND date >= ?", (SOURCE, _activity_since())).fetchone()
    day = row["d"] if row else None  # dernière journée avec des pas (pas de carte « 0 pas »)
    if day:
        start = (date.fromisoformat(day) - timedelta(days=6)).isoformat()
        out["activite"] = {"date": day, "valeurs": _day_values(conn, day, ACTIVITY),
                           "moyenne_7j": _average(conn, "wi_steps", start, day)[0]}
    return out
