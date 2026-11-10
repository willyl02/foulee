"""Catalogue des métriques : ce que chaque clé veut dire, son unité, son format.

Le même catalogue sert à l'interface (libellés, formats) et à Claude (outil
``catalogue_metriques``), pour que tout le monde parle la même langue.

Formats : duration (secondes → h:mm), clock (heure décimale → hh:mm),
pace (m/s → min/km), int, dec1, km, m, kg, pct, bpm, ms.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    fmt: str
    category: str
    agg: str = "avg"          # agrégation naturelle par semaine/mois : avg | sum | last | max | min
    better: str | None = None  # up | down | None : sens « favorable » pour les couleurs
    kind: str = "daily"       # daily | activity | calc
    description: str = ""


_METRICS = [
    # ---------------------------------------------------------------- Sommeil
    Metric("sleep_s", "Durée de sommeil", "h", "duration", "Sommeil", better="up",
           description="Temps de sommeil de la nuit qui se termine ce jour-là."),
    Metric("sleep_score", "Score de sommeil", "/100", "int", "Sommeil", better="up"),
    Metric("sleep_deep_s", "Sommeil profond", "h", "duration", "Sommeil", better="up"),
    Metric("sleep_light_s", "Sommeil léger", "h", "duration", "Sommeil"),
    Metric("sleep_rem_s", "Sommeil paradoxal", "h", "duration", "Sommeil", better="up"),
    Metric("sleep_awake_s", "Éveils nocturnes", "h", "duration", "Sommeil", better="down"),
    Metric("sleep_start_h", "Heure de coucher", "", "clock", "Sommeil",
           description="Heure d'endormissement (au-delà de 24 = après minuit)."),
    Metric("sleep_end_h", "Heure de lever", "", "clock", "Sommeil"),
    Metric("sleep_hr", "FC moyenne de nuit", "bpm", "int", "Sommeil", better="down"),
    Metric("sleep_stress", "Stress pendant le sommeil", "", "dec1", "Sommeil", better="down"),
    Metric("sleep_resp", "Respiration nocturne", "resp/min", "dec1", "Sommeil"),
    Metric("sleep_need_min", "Besoin de sommeil (Garmin)", "min", "int", "Sommeil"),
    Metric("nap_s", "Siestes", "h", "duration", "Sommeil", agg="sum"),
    # ----------------------------------------------------------- Récupération
    Metric("hrv_night", "VFC de la nuit", "ms", "int", "Récupération", better="up",
           description="Moyenne de la variabilité de la fréquence cardiaque pendant la nuit."),
    Metric("hrv_week", "VFC moyenne 7 jours", "ms", "int", "Récupération", better="up"),
    Metric("hrv_high", "VFC pic 5 min", "ms", "int", "Récupération"),
    Metric("hrv_bl_low", "VFC : bas de ta zone", "ms", "int", "Récupération"),
    Metric("hrv_bl_high", "VFC : haut de ta zone", "ms", "int", "Récupération"),
    Metric("hrv_status", "Statut VFC (0 à 3)", "", "int", "Récupération", better="up",
           description="0 = faible, 1 = bas, 2 = déséquilibré, 3 = équilibré."),
    Metric("resting_hr", "FC de repos", "bpm", "int", "Récupération", better="down"),
    Metric("bb_max", "Body Battery max", "", "int", "Récupération", better="up"),
    Metric("bb_min", "Body Battery min", "", "int", "Récupération", better="up"),
    Metric("bb_wake", "Body Battery au réveil", "", "int", "Récupération", better="up"),
    Metric("bb_charged", "Body Battery rechargée", "", "int", "Récupération", better="up"),
    Metric("bb_drained", "Body Battery dépensée", "", "int", "Récupération"),
    # --------------------------------------------------- Activité quotidienne
    Metric("steps", "Pas", "pas", "int", "Journée", better="up"),
    Metric("floors", "Étages montés", "", "int", "Journée"),
    Metric("cal_total", "Calories totales", "kcal", "int", "Journée"),
    Metric("cal_active", "Calories actives", "kcal", "int", "Journée"),
    Metric("int_minutes", "Minutes d'intensité", "min", "int", "Journée", agg="sum",
           description="Modérées + 2 × intenses, comme le compte Garmin."),
    Metric("int_moderate", "Minutes modérées", "min", "int", "Journée", agg="sum"),
    Metric("int_vigorous", "Minutes intenses", "min", "int", "Journée", agg="sum"),
    Metric("hr_min", "FC min du jour", "bpm", "int", "Journée"),
    Metric("hr_max", "FC max du jour", "bpm", "int", "Journée"),
    Metric("resp_avg", "Respiration moyenne", "resp/min", "dec1", "Journée"),
    Metric("hydration_ml", "Hydratation", "ml", "int", "Journée"),
    # ----------------------------------------------------------------- Stress
    Metric("stress_avg", "Stress moyen", "", "int", "Stress", better="down"),
    Metric("stress_max", "Stress max", "", "int", "Stress", better="down"),
    Metric("stress_high_s", "Temps en stress élevé", "h", "duration", "Stress", better="down"),
    Metric("stress_rest_s", "Temps de repos", "h", "duration", "Stress", better="up"),
    # ------------------------------------------------------------------ Corps
    Metric("weight_kg", "Poids", "kg", "dec1", "Corps", agg="last"),
    Metric("body_fat_pct", "Masse grasse", "%", "dec1", "Corps", agg="last", better="down"),
    Metric("muscle_kg", "Masse musculaire", "kg", "dec1", "Corps", agg="last", better="up"),
    Metric("bmi", "IMC", "", "dec1", "Corps", agg="last"),
    Metric("fitness_age", "Âge fitness", "ans", "dec1", "Corps", agg="last", better="down"),
    Metric("vo2max", "VO2max (Garmin)", "ml/kg/min", "dec1", "Corps", agg="last", better="up"),
    # ------------------------------------------------------- Charge (calculée)
    Metric("load_day", "Charge du jour", "", "int", "Charge", agg="sum", kind="calc",
           description="Somme des charges des séances du jour (charge Garmin, ou TRIMP à défaut)."),
    Metric("ctl", "Charge chronique (42 j)", "", "int", "Charge", kind="calc", better="up",
           description="Moyenne pondérée de la charge sur ~6 semaines : ta « forme » de fond."),
    Metric("atl", "Charge aiguë (7 j)", "", "int", "Charge", kind="calc",
           description="Moyenne pondérée de la charge sur ~1 semaine : ta fatigue récente."),
    Metric("tsb", "Fraîcheur", "", "int", "Charge", kind="calc", better="up",
           description="Chronique de la veille − aiguë de la veille. Négatif = tu encaisses, positif = frais."),
    Metric("acwr", "Ratio aiguë / chronique", "", "dec2", "Charge", kind="calc",
           description="Autour de 0,8 à 1,3 : progression maîtrisée. Au-delà de 1,5 : hausse brutale."),
    # ---------------------------------------------- Séances (agrégats par jour)
    Metric("act.count", "Nombre de séances", "", "int", "Séances", agg="sum", kind="activity"),
    Metric("act.distance_km", "Distance", "km", "km", "Séances", agg="sum", kind="activity"),
    Metric("act.duration_s", "Durée d'activité", "h", "duration", "Séances", agg="sum", kind="activity"),
    Metric("act.elev_gain", "Dénivelé positif", "m", "int", "Séances", agg="sum", kind="activity"),
    Metric("act.load", "Charge des séances", "", "int", "Séances", agg="sum", kind="activity"),
    Metric("act.pace", "Allure moyenne", "/km", "pace", "Séances", kind="activity", better="up",
           description="Allure moyenne pondérée par la distance (allure réelle, pas ajustée à la pente)."),
    Metric("act.avg_hr", "FC moyenne en séance", "bpm", "int", "Séances", kind="activity"),
    Metric("act.calories", "Calories des séances", "kcal", "int", "Séances", agg="sum", kind="activity"),
    Metric("act.z1_s", "Temps en zone FC 1", "h", "duration", "Séances", agg="sum", kind="activity"),
    Metric("act.z2_s", "Temps en zone FC 2", "h", "duration", "Séances", agg="sum", kind="activity"),
    Metric("act.z3_s", "Temps en zone FC 3", "h", "duration", "Séances", agg="sum", kind="activity"),
    Metric("act.z4_s", "Temps en zone FC 4", "h", "duration", "Séances", agg="sum", kind="activity"),
    Metric("act.z5_s", "Temps en zone FC 5", "h", "duration", "Séances", agg="sum", kind="activity"),
]

CATALOG: dict[str, Metric] = {m.key: m for m in _METRICS}

SPORTS = {
    "course": "Course à pied",
    "trail": "Trail",
    "velo": "Vélo",
    "marche": "Marche",
    "rando": "Randonnée",
    "natation": "Natation",
    "renfo": "Renforcement",
    "souplesse": "Souplesse / yoga",
    "cardio": "Cardio / HIIT",
    "autre": "Autre",
}
RUNNING_SPORTS = ("course", "trail")


def get(key: str) -> Metric:
    if key not in CATALOG:
        raise KeyError(f"Métrique inconnue : {key}")
    return CATALOG[key]


def catalog_json() -> list[dict]:
    return [asdict(m) for m in _METRICS]


# ----------------------------------------------------------------- formats
def _round(value: float) -> int:
    """Arrondi « à la française » (0,5 vers le haut), comme l'interface."""
    return int(math.floor(value + 0.5))


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "–"
    seconds = _round(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d}"
    if minutes >= 10:
        return f"{minutes} min"
    return f"{minutes} min {secs:02d} s" if minutes else f"{secs} s"


def fmt_pace(speed_mps: float | None) -> str:
    if not speed_mps or speed_mps <= 0:
        return "–"
    sec_per_km = 1000 / speed_mps
    minutes, secs = divmod(_round(sec_per_km), 60)
    return f"{minutes}:{secs:02d} /km"


def fmt_clock(hours: float | None) -> str:
    if hours is None:
        return "–"
    total = _round(hours * 60) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def format_value(key: str, value: float | None) -> str:
    if value is None:
        return "–"
    metric = CATALOG.get(key)
    fmt = metric.fmt if metric else "dec1"
    unit = metric.unit if metric else ""
    if fmt == "duration":
        return fmt_duration(value)
    if fmt == "pace":
        return fmt_pace(value)
    if fmt == "clock":
        return fmt_clock(value)
    if fmt == "km":
        return f"{value:.1f} km".replace(".", ",")
    if fmt == "dec1":
        text = f"{value:.1f}".replace(".", ",")
    elif fmt == "dec2":
        text = f"{value:.2f}".replace(".", ",")
    else:
        text = f"{round(value):,}".replace(",", " ")
    return f"{text} {unit}".strip() if unit and unit not in ("/100",) else (text + (unit or ""))
