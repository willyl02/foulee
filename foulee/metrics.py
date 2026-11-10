"""Catalogue des métriques : ce que chaque clé veut dire, son unité, son format.

Le même catalogue sert à l'interface (libellés, formats) et à Claude (outil
``catalogue_metriques``), pour que tout le monde parle la même langue.

Formats : duration (secondes → h:mm), clock (heure décimale → hh:mm),
pace (m/s → min/km), int, dec1, dec2, km, num (entier ou décimal selon la valeur).

Au-delà du catalogue, toute valeur numérique d'une réponse brute de Garmin est une
métrique : « garmin:<flux>:<chemin> » (voir RAW_KINDS et raw_metric).
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any


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
    Metric("sleep_awake_count", "Réveils dans la nuit", "", "int", "Sommeil", better="down"),
    Metric("sleep_deep_pct", "Part de sommeil profond", "%", "int", "Sommeil", better="up"),
    Metric("sleep_light_pct", "Part de sommeil léger", "%", "int", "Sommeil"),
    Metric("sleep_rem_pct", "Part de sommeil paradoxal", "%", "int", "Sommeil", better="up"),
    Metric("sleep_mid_h", "Milieu de la nuit", "", "clock", "Sommeil",
           description="Heure du milieu de ton sommeil, d'après Garmin."),
    Metric("sleep_need_base_min", "Besoin de sommeil habituel (Garmin)", "min", "int", "Sommeil"),
    Metric("sleep_spo2_avg", "SpO2 moyenne de la nuit", "%", "int", "Sommeil", better="up",
           description="Saturation en oxygène du sang pendant le sommeil (oxymètre de la montre)."),
    Metric("sleep_spo2_min", "SpO2 la plus basse de la nuit", "%", "int", "Sommeil", better="up"),
    Metric("sleep_resp_min", "Respiration nocturne min", "resp/min", "dec1", "Sommeil"),
    Metric("sleep_resp_max", "Respiration nocturne max", "resp/min", "dec1", "Sommeil"),
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
    Metric("bb_sleep_gain", "Body Battery rechargée la nuit", "", "int", "Récupération", better="up",
           description="Ce que la nuit a rendu à ta Body Battery, d'après Garmin."),
    Metric("bb_activity_cost", "Body Battery dépensée en séance", "", "int", "Récupération"),
    Metric("bb_last", "Body Battery : dernière valeur du jour", "", "int", "Récupération"),
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
    Metric("hydration_goal_ml", "Objectif d'hydratation", "ml", "int", "Journée"),
    Metric("steps_goal", "Objectif de pas", "pas", "int", "Journée"),
    Metric("steps_km", "Distance parcourue à pied", "km", "km", "Journée", agg="sum"),
    Metric("floors_down", "Étages descendus", "", "int", "Journée"),
    Metric("int_goal", "Objectif de minutes d'intensité", "min", "int", "Journée"),
    Metric("cal_resting", "Calories au repos", "kcal", "int", "Journée"),
    Metric("spo2_avg", "SpO2 moyenne du jour", "%", "int", "Journée", better="up"),
    Metric("spo2_min", "SpO2 la plus basse du jour", "%", "int", "Journée", better="up"),
    Metric("resp_min", "Respiration min du jour", "resp/min", "dec1", "Journée"),
    Metric("resp_max", "Respiration max du jour", "resp/min", "dec1", "Journée"),
    # ----------------------------------------------------------------- Stress
    Metric("stress_avg", "Stress moyen", "", "int", "Stress", better="down"),
    Metric("stress_max", "Stress max", "", "int", "Stress", better="down"),
    Metric("stress_high_s", "Temps en stress élevé", "h", "duration", "Stress", better="down"),
    Metric("stress_rest_s", "Temps de repos", "h", "duration", "Stress", better="up"),
    Metric("stress_low_s", "Temps en stress faible", "h", "duration", "Stress"),
    Metric("stress_med_s", "Temps en stress moyen", "h", "duration", "Stress"),
    Metric("stress_activity_s", "Temps en activité (stress non mesuré)", "h", "duration", "Stress"),
    # ------------------------------------------------------------------ Corps
    Metric("weight_kg", "Poids", "kg", "dec1", "Corps", agg="last"),
    Metric("body_fat_pct", "Masse grasse", "%", "dec1", "Corps", agg="last", better="down"),
    Metric("muscle_kg", "Masse musculaire", "kg", "dec1", "Corps", agg="last", better="up"),
    Metric("bmi", "IMC", "", "dec1", "Corps", agg="last"),
    Metric("body_water_pct", "Eau corporelle", "%", "dec1", "Corps", agg="last"),
    Metric("bone_kg", "Masse osseuse", "kg", "dec1", "Corps", agg="last"),
    Metric("visceral_fat", "Graisse viscérale (indice)", "", "int", "Corps", agg="last", better="down"),
    Metric("metabolic_age", "Âge métabolique", "ans", "int", "Corps", agg="last", better="down"),
    Metric("fitness_age", "Âge fitness", "ans", "dec1", "Corps", agg="last", better="down"),
    Metric("vigorous_days", "Jours d'activité intense par semaine", "j", "dec1", "Corps", agg="last", better="up",
           description="Moyenne sur 6 semaines, telle que Garmin la compte pour l'âge fitness."),
    Metric("vigorous_min", "Minutes intenses par semaine", "min", "int", "Corps", agg="last", better="up"),
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
    Metric("act.az1_s", "Temps en zone d'allure 1", "h", "duration", "Séances", agg="sum", kind="activity"),
    Metric("act.az2_s", "Temps en zone d'allure 2", "h", "duration", "Séances", agg="sum", kind="activity"),
    Metric("act.az3_s", "Temps en zone d'allure 3", "h", "duration", "Séances", agg="sum", kind="activity"),
    Metric("act.az4_s", "Temps en zone d'allure 4", "h", "duration", "Séances", agg="sum", kind="activity"),
    Metric("act.az5_s", "Temps en zone d'allure 5", "h", "duration", "Séances", agg="sum", kind="activity"),
    Metric("act.gap", "Allure ajustée à la pente", "/km", "pace", "Séances", kind="activity", better="up",
           description="Allure moyenne corrigée du dénivelé, calculée par Garmin."),
    Metric("act.cadence", "Cadence moyenne", "pas/min", "int", "Séances", kind="activity",
           description="Pas par minute en course (tours de pédale par minute à vélo)."),
    Metric("act.max_hr", "FC max en séance", "bpm", "int", "Séances", agg="max", kind="activity"),
    Metric("act.trimp", "TRIMP des séances", "", "int", "Séances", agg="sum", kind="activity"),
    Metric("act.te_aero", "Effet d'entraînement aérobie", "", "dec1", "Séances", agg="max", kind="activity",
           description="De 0 à 5, le plus haut de la journée."),
    Metric("act.te_anaero", "Effet d'entraînement anaérobie", "", "dec1", "Séances", agg="max", kind="activity"),
    Metric("act.steps", "Pas en séance", "pas", "int", "Séances", agg="sum", kind="activity"),
    Metric("act.sweat", "Perte hydrique estimée", "ml", "int", "Séances", agg="sum", kind="activity",
           description="Estimation Garmin de l'eau perdue en transpirant."),
    Metric("act.bb_impact", "Effet des séances sur la Body Battery", "", "int", "Séances", agg="sum",
           kind="activity"),
    Metric("act.resp", "Respiration en séance", "resp/min", "dec1", "Séances", kind="activity"),
    Metric("act.temp_max", "Température max en séance", "°C", "int", "Séances", agg="max", kind="activity"),
    # ------------------------------------------------- technique de course
    Metric("act.gct", "Temps de contact au sol", "ms", "int", "Technique de course", kind="activity",
           better="down", description="Moyenne des séances (pondérée par la durée). Capteur ou montre compatible."),
    Metric("act.gcb", "Équilibre du contact au sol (gauche)", "%", "dec1", "Technique de course", kind="activity",
           description="Part du temps de contact sur le pied gauche : 50 % = équilibré."),
    Metric("act.vo", "Oscillation verticale", "cm", "dec1", "Technique de course", kind="activity", better="down"),
    Metric("act.vr", "Ratio vertical", "%", "dec1", "Technique de course", kind="activity", better="down",
           description="Oscillation verticale ÷ longueur de foulée : plus bas = foulée plus efficace."),
    Metric("act.stride", "Longueur de foulée", "m", "dec2", "Technique de course", kind="activity"),
    Metric("act.ssl_pct", "Perte de vitesse par pas", "%", "dec1", "Technique de course", kind="activity",
           better="down"),
    # ------------------------------------------------------------ puissance
    Metric("act.power", "Puissance moyenne", "W", "int", "Puissance", kind="activity"),
    Metric("act.np", "Puissance normalisée", "W", "int", "Puissance", kind="activity"),
    Metric("act.pmax", "Puissance max", "W", "int", "Puissance", agg="max", kind="activity"),
    Metric("act.tss", "Training Stress Score", "", "int", "Puissance", agg="sum", kind="activity"),
    Metric("act.pz1_s", "Temps en zone de puissance 1", "h", "duration", "Puissance", agg="sum", kind="activity"),
    Metric("act.pz2_s", "Temps en zone de puissance 2", "h", "duration", "Puissance", agg="sum", kind="activity"),
    Metric("act.pz3_s", "Temps en zone de puissance 3", "h", "duration", "Puissance", agg="sum", kind="activity"),
    Metric("act.pz4_s", "Temps en zone de puissance 4", "h", "duration", "Puissance", agg="sum", kind="activity"),
    Metric("act.pz5_s", "Temps en zone de puissance 5", "h", "duration", "Puissance", agg="sum", kind="activity"),
]

# Métriques de séance calculées de façon générique : clé → (source, champ, calcul, facteur)
#   source : « col » = colonne de la table activities, « extra » = colonne JSON extra,
#            « az » = zones d'allure (index) ; calcul : sum | avg (pondérée par la durée) | max | min
ACTIVITY_SOURCES: dict[str, tuple[str, Any, str, float]] = {
    "act.cadence": ("col", "avg_cadence", "avg", 1),
    "act.max_hr": ("col", "max_hr", "max", 1),
    "act.trimp": ("col", "trimp", "sum", 1),
    "act.te_aero": ("col", "te_aerobic", "max", 1),
    "act.te_anaero": ("col", "te_anaerobic", "max", 1),
    "act.power": ("col", "avg_power", "avg", 1),
    "act.steps": ("extra", "steps", "sum", 1),
    "act.sweat": ("extra", "sweat", "sum", 1),
    "act.bb_impact": ("extra", "bb_impact", "sum", 1),
    "act.resp": ("extra", "resp", "avg", 1),
    "act.temp_max": ("extra", "temp_max", "max", 1),
    "act.gct": ("extra", "gct", "avg", 1),
    "act.gcb": ("extra", "gcb", "avg", 1),
    "act.vo": ("extra", "vo", "avg", 1),
    "act.vr": ("extra", "vr", "avg", 1),
    "act.stride": ("extra", "stride", "avg", 0.01),
    "act.ssl_pct": ("extra", "ssl_pct", "avg", 1),
    "act.np": ("extra", "np", "avg", 1),
    "act.pmax": ("extra", "pmax", "max", 1),
    "act.tss": ("extra", "tss", "sum", 1),
    **{f"act.pz{i}_s": ("extra", f"pz{i}", "sum", 1) for i in range(1, 6)},
    **{f"act.az{i}_s": ("az", i - 1, "sum", 1) for i in range(1, 6)},
}

CATEGORIES = ["Sommeil", "Récupération", "Journée", "Stress", "Corps", "Charge", "Séances", "Technique de course",
              "Puissance"]

# --------------------------------------------------- données brutes de Garmin
# Toute valeur numérique des réponses gardées telles quelles (table raw) peut servir de métrique :
# clé « garmin:<flux>:<chemin.dans.le.json> », par exemple « garmin:daily:pulseOx.avgValue ».
RAW_KINDS = {
    "daily": "Résumé du jour", "sleep": "Sommeil", "hrv": "VFC", "body_battery": "Body Battery",
    "weight": "Poids", "fitness_age": "Âge fitness", "activity": "Séances",
}
RAW_KEY = re.compile(r"garmin:(" + "|".join(RAW_KINDS) + r"):([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*){0,5})")
RAW_WORDS = {
    "pulseOx": "SpO2", "respiration": "respiration", "stress": "stress", "bodyBattery": "Body Battery",
    "movement": "mouvement", "steps": "pas", "floorsAscended": "étages montés", "floorsDescended": "étages descendus",
    "heartRate": "FC", "calories": "calories", "hydration": "hydratation", "intensityMinutes": "minutes d'intensité",
    "avgValue": "moyenne", "minValue": "min", "maxValue": "max", "latestValue": "dernière valeur", "goal": "objectif",
    "value": "valeur", "restingValue": "repos", "burnedActive": "actives", "burnedResting": "au repos",
    "burnedTotal": "totales", "distanceInMeters": "distance (m)", "sleepScores": "scores", "overall": "global",
    "baseline": "référence", "lastNightAvg": "moyenne de la nuit", "weeklyAvg": "moyenne 7 j",
    "lastNight5MinHigh": "pic 5 min", "latestWeight": "dernière pesée", "components": "composantes",
}


def raw_parts(key: str) -> tuple[str, str] | None:
    match = RAW_KEY.fullmatch(key or "")
    return (match[1], match[2]) if match else None


def raw_label(kind: str, path: str) -> str:
    words = [RAW_WORDS.get(part, re.sub(r"(?<=[a-z])(?=[A-Z])", " ", part).lower()) for part in path.split(".")]
    return f"{RAW_KINDS[kind]} › {' › '.join(words)}"


def raw_metric(key: str) -> Metric | None:
    parts = raw_parts(key)
    if not parts:
        return None
    kind, path = parts
    return Metric(key, raw_label(kind, path), "", "num", f"Données brutes : {RAW_KINDS[kind].lower()}",
                  kind="raw", description=f"Valeur « {path} » telle que Garmin la renvoie (réponse « {kind} »).")

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
    if key in CATALOG:
        return CATALOG[key]
    metric = raw_metric(key)
    if metric is None:
        raise KeyError(f"Métrique inconnue : {key}")
    return metric


def exists(key: str) -> bool:
    """Métrique du catalogue, ou valeur brute de Garmin bien formée."""
    return key in CATALOG or raw_parts(key) is not None


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
    metric = CATALOG.get(key) or raw_metric(key)
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
    if fmt == "num":
        text = f"{round(value):,}".replace(",", " ") if float(value).is_integer() else f"{value:.2f}".rstrip("0").replace(".", ",")
        return f"{text} {unit}".strip() if unit else text
    if fmt == "dec1":
        text = f"{value:.1f}".replace(".", ",")
    elif fmt == "dec2":
        text = f"{value:.2f}".replace(".", ",")
    else:
        text = f"{round(value):,}".replace(",", " ")
    return f"{text} {unit}".strip() if unit and unit not in ("/100",) else (text + (unit or ""))
