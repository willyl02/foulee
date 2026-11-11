"""Réponses de Withings → métriques quotidiennes « wi_… » (table ``daily``, source « withings »).

- Mesures (balance, tensiomètre, thermomètre…) : une valeur par jour. Pour le corps, la
  dernière pesée du jour ; pour la tension, le pouls et la SpO2, la moyenne des mesures du jour.
- Sommeil : la nuit compte pour le jour du réveil (comme chez Garmin) ; s'il y a plusieurs
  résumés le même jour (sieste, deux appareils), on garde le plus long.
- Activité : le résumé de la journée tel que Withings le donne.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

# Codes « meastype » de Withings → (métrique, calcul sur la journée)
MEASURES: dict[int, tuple[str, str]] = {
    1: ("wi_weight_kg", "last"),
    5: ("wi_lean_kg", "last"),
    6: ("wi_fat_pct", "last"),
    8: ("wi_fat_kg", "last"),
    76: ("wi_muscle_kg", "last"),
    77: ("wi_water_kg", "last"),
    88: ("wi_bone_kg", "last"),
    170: ("wi_visceral", "last"),
    226: ("wi_bmr", "last"),
    227: ("wi_metabolic_age", "last"),
    91: ("wi_pwv", "last"),
    155: ("wi_vascular_age", "last"),
    10: ("wi_bp_sys", "avg"),
    9: ("wi_bp_dia", "avg"),
    11: ("wi_pulse", "avg"),
    54: ("wi_spo2", "avg"),
    12: ("wi_temp", "last"),
    71: ("wi_body_temp", "last"),
    73: ("wi_skin_temp", "last"),
    123: ("wi_vo2max", "last"),
}
HEIGHT = 4  # taille (m) : sert à l'IMC
MEASURE_METRICS = sorted({key for key, _ in MEASURES.values()} | {"wi_water_pct", "wi_bmi"})

SLEEP_FIELDS = ",".join([
    "total_sleep_time", "total_timeinbed", "deepsleepduration", "lightsleepduration", "remsleepduration",
    "wakeupduration", "wakeupcount", "sleep_latency", "wakeup_latency", "sleep_efficiency", "sleep_score",
    "hr_average", "hr_min", "hr_max", "rr_average", "rr_min", "rr_max", "snoring", "snoringepisodecount",
    "out_of_bed_count", "nb_rem_episodes", "waso", "rmssd_start_avg", "rmssd_end_avg",
])
SLEEP_METRICS = ["wi_sleep_s", "wi_inbed_s", "wi_deep_s", "wi_light_s", "wi_rem_s", "wi_awake_s", "wi_wake_count",
                 "wi_sleep_latency_s", "wi_sleep_eff_pct", "wi_sleep_score", "wi_sleep_hr", "wi_sleep_hr_min",
                 "wi_sleep_resp", "wi_snoring_s", "wi_out_of_bed", "wi_sleep_hrv", "wi_bed_h", "wi_rise_h"]

ACTIVITY_FIELDS = ",".join(["steps", "distance", "elevation", "soft", "moderate", "intense", "active", "calories",
                            "totalcalories", "hr_average", "hr_min", "hr_max"])
ACTIVITY_METRICS = ["wi_steps", "wi_distance_km", "wi_elevation", "wi_cal_active", "wi_cal_total", "wi_active_s",
                    "wi_moderate_s", "wi_intense_s", "wi_hr_avg", "wi_hr_min", "wi_hr_max"]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # NaN


def local_time(timestamp: Any, zone: str | None = None) -> datetime | None:
    """Heure locale d'un instant Withings (secondes UTC), dans le fuseau donné par Withings si on le connaît."""
    seconds = _number(timestamp)
    if seconds is None:
        return None
    if zone:
        try:
            from zoneinfo import ZoneInfo

            return datetime.fromtimestamp(seconds, ZoneInfo(zone)).replace(tzinfo=None)
        except Exception:  # fuseau inconnu de ce système (Windows sans base de fuseaux) : heure du PC
            pass
    return datetime.fromtimestamp(seconds)


def group_day(group: dict, zone: str | None = None) -> str | None:
    moment = local_time(group.get("date"), group.get("timezone") or zone)
    return moment.date().isoformat() if moment else None


def measures(group: dict) -> dict[int, float]:
    """Valeurs d'un groupe de mesures : valeur × 10^unité, par code."""
    out: dict[int, float] = {}
    for item in group.get("measures") or []:
        value, unit, kind = _number(item.get("value")), _number(item.get("unit")), item.get("type")
        if value is None or unit is None or not isinstance(kind, int):
            continue
        out[kind] = value * (10 ** int(unit))
    return out


def real(group: dict) -> bool:
    """Une vraie mesure (catégorie 1), pas un objectif fixé par l'utilisateur (catégorie 2)."""
    return int(group.get("category") or 1) == 1


def height_of(group: dict) -> float | None:
    value = measures(group).get(HEIGHT) if real(group) else None
    return value if value and 0.8 <= value <= 2.5 else None


def daily_from_groups(groups: list[dict], height: float | None = None) -> dict[str, float]:
    """Les métriques d'une journée à partir de ses groupes de mesures."""
    last: dict[str, float] = {}
    sums: dict[str, list[float]] = defaultdict(list)
    for group in sorted(groups, key=lambda g: _number(g.get("date")) or 0):
        if not real(group):
            continue
        for kind, value in measures(group).items():
            spec = MEASURES.get(kind)
            if not spec:
                continue
            key, how = spec
            if how == "avg":
                sums[key].append(value)
            else:
                last[key] = value
    out = dict(last)
    out.update({key: sum(values) / len(values) for key, values in sums.items()})
    weight = out.get("wi_weight_kg")
    if weight and out.get("wi_water_kg"):
        out["wi_water_pct"] = 100 * out["wi_water_kg"] / weight
    if weight and height:
        out["wi_bmi"] = weight / (height * height)
    return {key: round(value, 3) for key, value in out.items()}


# ------------------------------------------------------------------ sommeil
def _hour(moment: datetime | None, *, evening: bool = False) -> float | None:
    """Heure décimale ; pour le coucher, après minuit compte au-delà de 24 (comme chez Garmin)."""
    if not moment:
        return None
    value = moment.hour + moment.minute / 60
    if evening and value < 12:
        value += 24
    return round(value, 3)


def sleep_day(item: dict) -> str | None:
    """Jour d'une nuit : celui du réveil."""
    end = local_time(item.get("enddate"), item.get("timezone"))
    if end:
        return end.date().isoformat()
    day = item.get("date")
    return str(day)[:10] if day else None


def parse_sleep(item: dict) -> tuple[str | None, dict[str, float]]:
    data = item.get("data") or {}
    n = lambda key: _number(data.get(key))  # noqa: E731
    deep, light, rem = n("deepsleepduration"), n("lightsleepduration"), n("remsleepduration")
    total = n("total_sleep_time")
    if total is None and any(v is not None for v in (deep, light, rem)):
        total = sum(v or 0 for v in (deep, light, rem))
    efficiency = n("sleep_efficiency")
    if efficiency is not None and efficiency <= 1:
        efficiency *= 100
    hrv = [v for v in (n("rmssd_start_avg"), n("rmssd_end_avg")) if v]
    zone = item.get("timezone")
    values = {
        "wi_sleep_s": total, "wi_inbed_s": n("total_timeinbed"), "wi_deep_s": deep, "wi_light_s": light,
        "wi_rem_s": rem, "wi_awake_s": n("wakeupduration") if n("wakeupduration") is not None else n("waso"),
        "wi_wake_count": n("wakeupcount"), "wi_sleep_latency_s": n("sleep_latency"),
        "wi_sleep_eff_pct": efficiency, "wi_sleep_score": n("sleep_score"),
        "wi_sleep_hr": n("hr_average") or None, "wi_sleep_hr_min": n("hr_min") or None,
        "wi_sleep_resp": n("rr_average") or None, "wi_snoring_s": n("snoring"), "wi_out_of_bed": n("out_of_bed_count"),
        "wi_sleep_hrv": sum(hrv) / len(hrv) if hrv else None,
        "wi_bed_h": _hour(local_time(item.get("startdate"), zone), evening=True),
        "wi_rise_h": _hour(local_time(item.get("enddate"), zone)),
    }
    return sleep_day(item), {k: v for k, v in values.items() if v is not None}


def main_sleep(items: list[dict]) -> dict[str, float]:
    """Plusieurs résumés pour un même jour : on garde la nuit principale (la plus longue)."""
    best: dict[str, float] = {}
    for item in items:
        _, values = parse_sleep(item)
        if values.get("wi_sleep_s", 0) >= best.get("wi_sleep_s", -1):
            best = values
    return best


# ------------------------------------------------------------------ activité
def parse_activity(item: dict) -> tuple[str | None, dict[str, float]]:
    n = lambda key: _number(item.get(key))  # noqa: E731
    distance = n("distance")
    values = {
        "wi_steps": n("steps"), "wi_distance_km": distance / 1000 if distance is not None else None,
        "wi_elevation": n("elevation"), "wi_cal_active": n("calories"), "wi_cal_total": n("totalcalories"),
        "wi_active_s": n("active"), "wi_moderate_s": n("moderate"), "wi_intense_s": n("intense"),
    }
    if n("hr_average"):  # Withings envoie 0 quand la FC n'a pas été mesurée
        values.update(wi_hr_avg=n("hr_average"), wi_hr_min=n("hr_min") or None, wi_hr_max=n("hr_max") or None)
    day = item.get("date")
    return (str(day)[:10] if day else None), {k: v for k, v in values.items() if v is not None}
