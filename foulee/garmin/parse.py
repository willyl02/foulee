"""Traduction des réponses brutes de Garmin vers le modèle commun de Foulée.

Chaque fonction reçoit le JSON tel que Garmin l'a renvoyé et produit des
lignes normalisées. Rien ici ne touche au réseau ni à la base : c'est ce qui
permet de tout recalculer depuis le brut (``foulee reparse``).

Particularités de l'API gérées ici :
- certains horodatages arrivent en millisecondes epoch, d'autres en texte ;
- les horodatages « Local » en millisecondes sont l'heure murale encodée
  comme si c'était de l'UTC ;
- beaucoup de champs peuvent être absents ou nuls, et quelques valeurs
  négatives servent de « pas de donnée » (stress à -1 ou -2).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from .. import renfo

# ---------------------------------------------------------------- helpers

def num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def positive(value: Any) -> float | None:
    number = num(value)
    return number if number is not None and number > 0 else None


def non_negative(value: Any) -> float | None:
    number = num(value)
    return number if number is not None and number >= 0 else None


def dig(data: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def to_datetime(value: Any) -> datetime | None:
    """Horodatage Garmin → datetime naïf (sans fuseau).

    Millisecondes epoch : interprétées en UTC puis rendues naïves. Pour un champ
    « Local », cela redonne l'heure murale ; pour un champ « GMT », l'heure UTC.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(value, str):
        text = value.strip().replace("T", " ")
        if not text:
            return None
        text = text.rstrip("Z")
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def epoch_ms(value: Any) -> float | None:
    """Horodatage GMT → millisecondes epoch."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    moment = to_datetime(value)
    if moment is None:
        return None
    return moment.replace(tzinfo=timezone.utc).timestamp() * 1000


def clock_hours(moment: datetime | None, *, bedtime: bool = False) -> float | None:
    """datetime → heure décimale. Pour un coucher après minuit : 24 + h."""
    if moment is None:
        return None
    hours = moment.hour + moment.minute / 60 + moment.second / 3600
    if bedtime and hours < 15:
        hours += 24
    return round(hours, 3)


def items_of(payload: Any, *keys: str) -> list[dict]:
    """Renvoie la liste d'éléments d'une réponse, qu'elle soit une liste ou un objet."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


# ------------------------------------------------------------ quotidien

DAILY_SUMMARY_METRICS = [
    "steps", "floors", "cal_total", "cal_active", "cal_resting", "resting_hr", "hr_min", "hr_max",
    "int_moderate", "int_vigorous", "int_minutes", "stress_avg", "stress_max", "stress_high_s",
    "stress_rest_s", "stress_low_s", "stress_med_s", "bb_min", "bb_max", "bb_charged", "bb_drained",
    "resp_avg", "hydration_ml",
    # 0.5
    "steps_goal", "steps_km", "floors_down", "int_goal", "stress_activity_s", "hydration_goal_ml",
    "spo2_avg", "spo2_min", "resp_min", "resp_max", "bb_last", "bb_sleep_gain", "bb_activity_cost",
]


def daily_summary_items(payload: Any) -> list[dict]:
    return items_of(payload, "data")


def parse_daily_summary(item: dict) -> tuple[str | None, dict[str, float | None]]:
    date = item.get("calendarDate")
    stress = item.get("stress") or {}
    moderate = non_negative(dig(item, "intensityMinutes", "moderate"))
    vigorous = non_negative(dig(item, "intensityMinutes", "vigorous"))

    def millis(key: str) -> float | None:
        value = non_negative(stress.get(key))
        return value / 1000 if value is not None else None

    values = {
        "steps": non_negative(dig(item, "movement", "steps", "value")),
        "floors": non_negative(dig(item, "movement", "floorsAscended", "value")),
        "cal_total": positive(dig(item, "calories", "burnedTotal")),
        "cal_active": non_negative(dig(item, "calories", "burnedActive")),
        "cal_resting": positive(dig(item, "calories", "burnedResting")),
        "resting_hr": positive(dig(item, "heartRate", "restingValue")),
        "hr_min": positive(dig(item, "heartRate", "minValue")),
        "hr_max": positive(dig(item, "heartRate", "maxValue")),
        "int_moderate": moderate,
        "int_vigorous": vigorous,
        "int_minutes": (moderate or 0) + 2 * (vigorous or 0) if (moderate is not None or vigorous is not None) else None,
        "stress_avg": non_negative(stress.get("avgLevel")),
        "stress_max": non_negative(stress.get("maxLevel")),
        "stress_high_s": millis("highStressDurationInMillis"),
        "stress_rest_s": millis("restDurationInMillis"),
        "stress_low_s": millis("lowStressDurationInMillis"),
        "stress_med_s": millis("mediumStressDurationInMillis"),
        "bb_min": non_negative(dig(item, "bodyBattery", "minValue")),
        "bb_max": non_negative(dig(item, "bodyBattery", "maxValue")),
        "bb_charged": non_negative(dig(item, "bodyBattery", "chargedValue")),
        "bb_drained": non_negative(dig(item, "bodyBattery", "drainedValue")),
        "resp_avg": positive(dig(item, "respiration", "avgValue")),
        "hydration_ml": positive(dig(item, "hydration", "consumedInMl")),
        "steps_goal": positive(dig(item, "movement", "steps", "goal")),
        "steps_km": _km(dig(item, "movement", "steps", "distanceInMeters")),
        "floors_down": non_negative(dig(item, "movement", "floorsDescended", "value")),
        "int_goal": positive(dig(item, "intensityMinutes", "goal")),
        "stress_activity_s": millis("activityDurationInMillis"),
        "hydration_goal_ml": positive(dig(item, "hydration", "goalInMl")),
        "spo2_avg": positive(dig(item, "pulseOx", "avgValue")),
        "spo2_min": positive(dig(item, "pulseOx", "minValue")),
        "resp_min": positive(dig(item, "respiration", "minValue")),
        "resp_max": positive(dig(item, "respiration", "maxValue")),
        "bb_last": non_negative(dig(item, "bodyBattery", "latestValue")),
        **_battery_events(dig(item, "bodyBattery", "activityEvents")),
    }
    return date, values


def _km(meters: Any) -> float | None:
    value = positive(meters)
    return round(value / 1000, 2) if value is not None else None


def _battery_events(events: Any) -> dict[str, float | None]:
    """Recharge de la nuit et coût des séances, d'après les événements Body Battery du jour."""
    if not isinstance(events, list):
        return {"bb_sleep_gain": None, "bb_activity_cost": None}
    sleep = [num(e.get("bodyBatteryImpact")) for e in events
             if isinstance(e, dict) and str(e.get("eventType", "")).upper() == "SLEEP"]
    sport = [num(e.get("bodyBatteryImpact")) for e in events
             if isinstance(e, dict) and str(e.get("eventType", "")).upper() == "ACTIVITY"]
    sleep = [v for v in sleep if v is not None]
    sport = [v for v in sport if v is not None and v < 0]
    return {"bb_sleep_gain": sum(sleep) if sleep else None, "bb_activity_cost": -sum(sport) if sport else None}


SLEEP_METRICS = [
    "sleep_s", "sleep_deep_s", "sleep_light_s", "sleep_rem_s", "sleep_awake_s", "sleep_score",
    "sleep_start_h", "sleep_end_h", "sleep_hr", "sleep_stress", "sleep_resp", "sleep_need_min", "nap_s",
    # 0.5
    "sleep_spo2_avg", "sleep_spo2_min", "sleep_resp_min", "sleep_resp_max", "sleep_awake_count",
    "sleep_deep_pct", "sleep_light_pct", "sleep_rem_pct", "sleep_need_base_min", "sleep_mid_h",
]


def sleep_items(payload: Any) -> list[dict]:
    items = items_of(payload, "dailySleepDTOList", "data")
    if not items and isinstance(payload, dict) and payload.get("calendarDate"):
        items = [payload]
    if not items and isinstance(payload, dict) and isinstance(payload.get("dailySleepDTO"), dict):
        items = [payload["dailySleepDTO"]]
    return items


def parse_sleep(item: dict) -> tuple[str | None, dict[str, float | None]]:
    date = item.get("calendarDate")
    total = non_negative(item.get("sleepTimeSeconds"))
    if not total:
        return date, {"nap_s": positive(item.get("napTimeSeconds"))}
    start = to_datetime(item.get("sleepStartTimestampLocal"))
    end = to_datetime(item.get("sleepEndTimestampLocal"))
    values = {
        "sleep_s": total,
        "sleep_deep_s": non_negative(item.get("deepSleepSeconds")),
        "sleep_light_s": non_negative(item.get("lightSleepSeconds")),
        "sleep_rem_s": non_negative(item.get("remSleepSeconds")),
        "sleep_awake_s": non_negative(item.get("awakeSleepSeconds")),
        "sleep_score": positive(dig(item, "sleepScores", "overall", "value")),
        "sleep_start_h": clock_hours(start, bedtime=True),
        "sleep_end_h": clock_hours(end),
        "sleep_hr": positive(item.get("avgHeartRate")),
        "sleep_stress": non_negative(item.get("avgSleepStress")),
        "sleep_resp": positive(item.get("averageRespirationValue")),
        "sleep_need_min": positive(dig(item, "sleepNeed", "actual")),
        "nap_s": positive(item.get("napTimeSeconds")),
        "sleep_spo2_avg": positive(item.get("averageSpO2Value")),
        "sleep_spo2_min": positive(item.get("lowestSpO2Value")),
        "sleep_resp_min": positive(item.get("lowestRespirationValue")),
        "sleep_resp_max": positive(item.get("highestRespirationValue")),
        "sleep_awake_count": non_negative(item.get("awakeCount")),
        "sleep_deep_pct": non_negative(dig(item, "sleepScores", "deepPercentage", "value")),
        "sleep_light_pct": non_negative(dig(item, "sleepScores", "lightPercentage", "value")),
        "sleep_rem_pct": non_negative(dig(item, "sleepScores", "remPercentage", "value")),
        "sleep_need_base_min": positive(dig(item, "sleepNeed", "baseline")),
        "sleep_mid_h": _midpoint(dig(item, "sleepAlignment", "lastSleepMidpointMins")),
    }
    return date, values


def _midpoint(minutes: Any) -> float | None:
    """Milieu de la nuit (minutes après minuit, négatif = avant) → heure décimale."""
    value = num(minutes)
    if value is None:
        return None
    return round((value / 60) % 24, 3)


HRV_METRICS = ["hrv_night", "hrv_week", "hrv_high", "hrv_bl_low", "hrv_bl_high", "hrv_status"]
HRV_STATUS_CODES = {"POOR": 0, "LOW": 1, "UNBALANCED": 2, "BALANCED": 3}


def hrv_items(payload: Any) -> list[dict]:
    items = items_of(payload, "hrvSummaries")
    if not items and isinstance(payload, dict) and isinstance(payload.get("hrvSummary"), dict):
        items = [payload["hrvSummary"]]
    return items


def parse_hrv(item: dict) -> tuple[str | None, dict[str, float | None]]:
    status = item.get("status")
    values = {
        "hrv_night": positive(item.get("lastNightAvg")),
        "hrv_week": positive(item.get("weeklyAvg")),
        "hrv_high": positive(item.get("lastNight5MinHigh")),
        "hrv_bl_low": positive(dig(item, "baseline", "balancedLow")),
        "hrv_bl_high": positive(dig(item, "baseline", "balancedUpper")),
        "hrv_status": HRV_STATUS_CODES.get(str(status).upper()) if status else None,
    }
    return item.get("calendarDate"), values


def body_battery_items(payload: Any) -> list[dict]:
    return items_of(payload, "data")


def body_battery_samples(item: dict) -> list[tuple[float, float]]:
    """Échantillons (millisecondes epoch GMT, niveau) d'un rapport Body Battery."""
    values = item.get("bodyBatteryValuesArray") or []
    ts_index, level_index = 0, None
    for descriptor in item.get("bodyBatteryValueDescriptorDTOList") or []:
        key = str(descriptor.get("bodyBatteryValueDescriptorKey", "")).lower()
        index = descriptor.get("bodyBatteryValueDescriptorIndex")
        if not isinstance(index, int):
            continue
        if "timestamp" in key:
            ts_index = index
        elif "level" in key:
            level_index = index
    if level_index is None:
        level_index = 1
    samples = []
    for row in values:
        if not isinstance(row, list) or len(row) <= max(ts_index, level_index):
            continue
        ts, level = num(row[ts_index]), num(row[level_index])
        if ts is None or level is None or level < 0:
            continue
        samples.append((ts, level))
    samples.sort()
    return samples


def wake_body_battery(bb_item: dict, sleep_item: dict | None) -> float | None:
    """Niveau de Body Battery au réveil : premier échantillon après la fin du sommeil."""
    if not sleep_item:
        return None
    end_ms = epoch_ms(sleep_item.get("sleepEndTimestampGMT"))
    if end_ms is None:
        return None
    samples = body_battery_samples(bb_item)
    best = None
    for ts, level in samples:
        if end_ms - 20 * 60_000 <= ts <= end_ms + 60 * 60_000:
            if best is None or abs(ts - end_ms) < abs(best[0] - end_ms):
                best = (ts, level)
    return best[1] if best else None


WEIGHT_METRICS = ["weight_kg", "body_fat_pct", "bmi", "muscle_kg", "body_water_pct", "bone_kg", "visceral_fat",
                  "metabolic_age"]


def weight_items(payload: Any) -> list[dict]:
    return items_of(payload, "dailyWeightSummaries")


def _grams_to_kg(value: Any) -> float | None:
    number = positive(value)
    if number is None:
        return None
    return round(number / 1000, 2) if number > 500 else round(number, 2)


def parse_weight(item: dict) -> tuple[str | None, dict[str, float | None]]:
    latest = item.get("latestWeight") or {}
    values = {
        "weight_kg": _grams_to_kg(latest.get("weight")),
        "body_fat_pct": positive(latest.get("bodyFat")),
        "bmi": positive(latest.get("bmi")),
        "muscle_kg": _grams_to_kg(latest.get("muscleMass")),
        "body_water_pct": positive(latest.get("bodyWater")),
        "bone_kg": _grams_to_kg(latest.get("boneMass")),
        "visceral_fat": positive(latest.get("visceralFat")),
        "metabolic_age": positive(latest.get("metabolicAge")),
    }
    return item.get("summaryDate") or latest.get("calendarDate"), values


def parse_fitness_age(payload: Any) -> dict[str, float | None]:
    if not isinstance(payload, dict):
        return {}
    return {
        "fitness_age": positive(payload.get("fitnessAge")),
        "vigorous_days": non_negative(dig(payload, "components", "vigorousDaysAvg", "value")),
        "vigorous_min": non_negative(dig(payload, "components", "vigorousMinutesAvg", "value")),
    }


# ------------------------------------------------------------- séances

_SPORT_MAP = {
    "course": {
        "running", "track_running", "treadmill_running", "indoor_running", "street_running",
        "virtual_run", "obstacle_run", "ultra_run", "indoor_track",
    },
    "trail": {"trail_running"},
    "velo": {
        "cycling", "road_biking", "mountain_biking", "gravel_cycling", "indoor_cycling",
        "virtual_ride", "e_bike_fitness", "e_bike_mountain", "cyclocross", "track_cycling",
        "recumbent_cycling", "bmx", "downhill_biking", "hand_cycling", "indoor_hand_cycling",
    },
    "marche": {"walking", "casual_walking", "speed_walking", "indoor_walking"},
    "rando": {"hiking", "mountaineering", "rucking"},
    "natation": {"swimming", "lap_swimming", "open_water_swimming"},
    "renfo": {"strength_training", "indoor_climbing", "bouldering"},
    "souplesse": {"yoga", "pilates", "breathwork", "mobility", "meditation", "stretching"},
    "cardio": {
        "hiit", "cardio", "indoor_cardio", "fitness_equipment", "elliptical", "stair_climbing",
        "indoor_rowing", "rowing", "jump_rope", "floor_climbing",
    },
}


def normalize_sport(type_key: str | None) -> str:
    key = (type_key or "").lower()
    for family, keys in _SPORT_MAP.items():
        if key in keys:
            return family
    if "trail" in key:
        return "trail"
    if "run" in key:
        return "course"
    if "cycl" in key or "bik" in key or "ride" in key:
        return "velo"
    if "swim" in key:
        return "natation"
    if "walk" in key:
        return "marche"
    if "hik" in key:
        return "rando"
    return "autre"


# Valeurs de séance rangées dans la colonne « extra » : clé Foulée → (clés Garmin possibles, lecture)
ACTIVITY_EXTRAS: dict[str, tuple[tuple[str, ...], str]] = {
    "gct": (("avgGroundContactTime",), "positive"),            # temps de contact au sol, ms
    "gcb": (("avgGroundContactBalance",), "positive"),         # équilibre gauche / droite, % à gauche
    "vo": (("avgVerticalOscillation",), "positive"),           # oscillation verticale, cm
    "vr": (("avgVerticalRatio",), "positive"),                 # ratio vertical, %
    "stride": (("avgStrideLength",), "positive"),              # longueur de foulée, cm
    "ssl": (("avgStepSpeedLoss",), "positive"),                # perte de vitesse par pas, cm/s
    "ssl_pct": (("avgStepSpeedLossPercent",), "positive"),     # même chose, en %
    "resp": (("avgRespirationRate",), "positive"),             # respiration, resp/min
    "resp_min": (("minRespirationRate",), "positive"),
    "resp_max": (("maxRespirationRate",), "positive"),
    "np": (("normPower", "normalizedPower"), "positive"),      # puissance normalisée, W
    "pmax": (("maxPower",), "positive"),
    "temp_min": (("minTemperature",), "num"),                  # °C
    "temp_max": (("maxTemperature",), "num"),
    "sweat": (("waterEstimated",), "positive"),                # perte hydrique estimée, ml
    "bb_impact": (("differenceBodyBattery",), "num"),          # effet sur la Body Battery
    "steps": (("steps",), "positive"),
    "cad_max": (("maxRunningCadenceInStepsPerMinute", "maxBikingCadenceInRevPerMinute"), "positive"),
    "alt_min": (("minElevation",), "num"),
    "alt_max": (("maxElevation",), "num"),
    "im_mod": (("moderateIntensityMinutes",), "non_negative"),
    "im_vig": (("vigorousIntensityMinutes",), "non_negative"),
    "tss": (("trainingStressScore",), "positive"),
    "if": (("intensityFactor",), "positive"),
    "swolf": (("averageSwolf", "avgSwolf"), "positive"),
    "strokes": (("totalNumberOfStrokes",), "positive"),
    "pz1": (("powerTimeInZone_1",), "non_negative"),
    "pz2": (("powerTimeInZone_2",), "non_negative"),
    "pz3": (("powerTimeInZone_3",), "non_negative"),
    "pz4": (("powerTimeInZone_4",), "non_negative"),
    "pz5": (("powerTimeInZone_5",), "non_negative"),
}
_READERS = {"positive": positive, "non_negative": non_negative, "num": num}


def activity_extra(item: dict) -> dict:
    """Valeurs supplémentaires d'une séance (dynamique de course, puissance, records de la sortie…)."""
    summary = item.get("summaryDTO") if isinstance(item.get("summaryDTO"), dict) else {}
    extra: dict[str, Any] = {}
    for key, (names, reader) in ACTIVITY_EXTRAS.items():
        for name in names:
            raw = item.get(name) if item.get(name) is not None else summary.get(name)
            value = _READERS[reader](raw)
            if value is not None:
                extra[key] = round(value, 3)
                break
    for name, value in list(item.items()) + list(summary.items()):
        match = re.fullmatch(r"fastestSplit_(\d+)", str(name))
        if match and positive(value):
            extra[f"best_{match[1]}"] = round(float(value), 2)  # meilleur temps (s) sur cette distance (m)
    for key, name in (("te_label", "trainingEffectLabel"), ("lieu", "locationName")):
        text = item.get(name) or summary.get(name)
        if isinstance(text, str) and text.strip():
            extra[key] = text.strip()[:60]
    extra.update(renfo.totals(renfo.parse_summary(item)))  # renfo : séries, répétitions, tonnage, effort
    return extra


def _json_or_none(value: dict) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value else None


def parse_activity(item: dict) -> dict | None:
    """Résumé d'activité (liste ou détail) → ligne de la table ``activities``."""
    activity_id = item.get("activityId")
    if activity_id is None:
        return None
    summary = item.get("summaryDTO") if isinstance(item.get("summaryDTO"), dict) else {}

    def pick(*keys: str) -> Any:
        for key in keys:
            if item.get(key) is not None:
                return item.get(key)
            if summary.get(key) is not None:
                return summary.get(key)
        return None

    type_info = item.get("activityType") or item.get("activityTypeDTO") or {}
    type_key = type_info.get("typeKey") if isinstance(type_info, dict) else None
    start_local = to_datetime(pick("startTimeLocal"))
    if start_local is None:
        return None
    start_utc = to_datetime(pick("startTimeGMT"))
    zones = [non_negative(pick(f"hrTimeInZone_{i}")) for i in range(1, 6)]
    cadence = pick(
        "averageRunningCadenceInStepsPerMinute", "averageBikingCadenceInRevPerMinute", "averageRunCadence",
    )
    return {
        "id": f"garmin:{activity_id}",
        "source": "garmin",
        "source_id": str(activity_id),
        "start_local": start_local.strftime("%Y-%m-%d %H:%M:%S"),
        "start_utc": start_utc.strftime("%Y-%m-%d %H:%M:%S") if start_utc else None,
        "date": start_local.strftime("%Y-%m-%d"),
        "sport": normalize_sport(type_key),
        "type_key": type_key,
        "name": pick("activityName"),
        "description": pick("description"),
        "duration_s": positive(pick("duration")),
        "moving_s": positive(pick("movingDuration")),
        "elapsed_s": positive(pick("elapsedDuration")),
        "distance_m": non_negative(pick("distance")),
        "elev_gain_m": non_negative(pick("elevationGain")),
        "elev_loss_m": non_negative(pick("elevationLoss")),
        "avg_hr": positive(pick("averageHR")),
        "max_hr": positive(pick("maxHR")),
        "avg_speed": positive(pick("averageSpeed")),
        "max_speed": positive(pick("maxSpeed")),
        "avg_gap_speed": positive(pick("avgGradeAdjustedSpeed")),
        "avg_cadence": positive(cadence),
        "avg_power": positive(pick("avgPower")),
        "calories": positive(pick("calories")),
        "te_aerobic": non_negative(pick("aerobicTrainingEffect", "trainingEffect")),
        "te_anaerobic": non_negative(pick("anaerobicTrainingEffect")),
        "garmin_load": non_negative(pick("activityTrainingLoad")),
        "vo2max": positive(pick("vO2MaxValue")),
        "hr_zones_garmin": json.dumps(zones) if any(z for z in zones) else None,
        "extra": _json_or_none(activity_extra(item)),
        "start_lat": num(pick("startLatitude")),
        "start_lon": num(pick("startLongitude")),
        "lap_count": int(num(pick("lapCount")) or 0) or None,
    }


def heart_rate_zones(payload: Any) -> dict | None:
    """Zones FC Garmin (profil « DEFAULT » ou course) → bornes basses et FC max."""
    items = items_of(payload)
    if not items:
        return None
    chosen = None
    for preferred in ("RUNNING", "DEFAULT"):
        for item in items:
            if str(item.get("sport", "")).upper() == preferred:
                chosen = item
                break
        if chosen:
            break
    chosen = chosen or items[0]
    floors = [positive(chosen.get(f"zone{i}Floor")) for i in range(1, 6)]
    hr_max = positive(chosen.get("maxHeartRateUsed"))
    if not hr_max or not all(floors):
        return None
    return {
        "floors": floors,
        "max": hr_max,
        "rest": positive(chosen.get("restingHeartRateUsed")),
        "method": chosen.get("trainingMethod"),
        "lthr": positive(chosen.get("lactateThresholdHeartRateUsed")),
        "sport": chosen.get("sport"),
    }


def profile_settings(payload: Any) -> dict:
    """Réglages du profil Garmin utiles à Foulée (seuil lactique, VO2max, mensurations)."""
    if not isinstance(payload, dict):
        return {}
    data = payload.get("userData") if isinstance(payload.get("userData"), dict) else payload
    speed = positive(data.get("lactateThresholdSpeed"))
    if speed is not None and speed < 1.5:
        speed *= 10  # Garmin range parfois cette vitesse en dizaines de m/s (0,34 pour 3,4 m/s)
    if speed is not None and not 1.5 <= speed <= 8:
        speed = None
    weight = positive(data.get("weight"))
    return {
        "seuil_fc": positive(data.get("lactateThresholdHeartRate")),
        "seuil_vitesse": round(speed, 3) if speed else None,
        "vo2max_course": positive(data.get("vo2MaxRunning")),
        "vo2max_velo": positive(data.get("vo2MaxCycling")),
        "poids_kg": round(weight / 1000, 1) if weight and weight > 500 else weight,
        "taille_cm": positive(data.get("height")),
        "systeme": payload.get("measurementSystem") or data.get("measurementSystem"),
    }


def iter_dates(items: Iterable[dict], key: str = "calendarDate") -> list[str]:
    return sorted({item.get(key) for item in items if item.get(key)})
