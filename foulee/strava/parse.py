"""Réponses de Strava → lignes de Foulée : séances, tours, courbes, et exercices notés dans la description.

Strava donne ses séances en unités SI (mètres, secondes, m/s). Son type de sport (``sport_type``) est rangé
dans les familles de Foulée (course, trail, vélo…), comme ceux de Garmin.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

# Familles de Foulée pour les types de sport de Strava
SPORT_TYPES = {
    "course": {"Run", "VirtualRun", "Wheelchair"},
    "trail": {"TrailRun"},
    "velo": {"Ride", "MountainBikeRide", "GravelRide", "EBikeRide", "EMountainBikeRide", "VirtualRide", "Velomobile",
             "Handcycle"},
    "marche": {"Walk"},
    "rando": {"Hike", "Snowshoe"},
    "natation": {"Swim"},
    "renfo": {"WeightTraining", "RockClimbing"},
    "cardio": {"Workout", "Crossfit", "HighIntensityIntervalTraining", "Elliptical", "StairStepper", "Rowing",
               "VirtualRow"},
    "souplesse": {"Yoga", "Pilates", "PhysicalTherapy"},
}
STEP_FAMILIES = ("course", "trail", "marche", "rando")  # cadence de Strava par jambe : ×2 en pas par minute
GARMIN_EXTERNAL = re.compile(r"^garmin_(?:ping|push)_(\d+)", re.I)


def sport_family(sport_type: str | None) -> str:
    key = str(sport_type or "")
    for family, names in SPORT_TYPES.items():
        if key in names:
            return family
    low = key.lower()
    if "trail" in low:
        return "trail"
    if "run" in low:
        return "course"
    if "ride" in low or "bike" in low:
        return "velo"
    if "swim" in low:
        return "natation"
    return "autre"


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _positive(value: Any) -> float | None:
    number = _num(value)
    return number if number is not None and number > 0 else None


def _local(text: Any) -> str | None:
    """« 2026-11-05T20:48:33Z » (heure locale que Strava marque Z) → « 2026-11-05 20:48:33 »."""
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None).isoformat(sep=" ")
    except ValueError:
        return None


def garmin_id(external_id: Any) -> str | None:
    """« garmin_push_24979762351 » → « 24979762351 » : la séance vient de Garmin Connect (numéro Garmin)."""
    match = GARMIN_EXTERNAL.match(str(external_id or ""))
    return match.group(1) if match else None


def summary_row(item: dict) -> dict | None:
    """Séance de la liste de Strava (SummaryActivity) → ligne du cache, colonnes de la table ``activities``."""
    if not isinstance(item, dict) or item.get("id") is None:
        return None
    start_local = _local(item.get("start_date_local"))
    if not start_local:
        return None
    strava_id = int(item["id"])
    sport_type = str(item.get("sport_type") or item.get("type") or "")
    family = sport_family(sport_type)
    cadence = _positive(item.get("average_cadence"))
    if cadence and family in STEP_FAMILIES:
        cadence *= 2
    device = str(item.get("device_name") or "").strip() or None
    extra = {k: v for k, v in {
        "strava_id": strava_id, "appareil": device, "kudos": item.get("kudos_count"),
        "prive": bool(item.get("private")) or item.get("visibility") == "only_me",
        "manuelle": bool(item.get("manual")), "home_trainer": bool(item.get("trainer")),
        "type_strava": sport_type, "puissance_capteur": item.get("device_watts"),
    }.items() if v not in (None, "", False)}
    moving, elapsed = _positive(item.get("moving_time")), _positive(item.get("elapsed_time"))
    return {
        "id": f"strava:{strava_id}", "source": "strava", "source_id": str(strava_id),
        "start_local": start_local, "start_utc": _local(item.get("start_date")), "date": start_local[:10],
        "sport": family, "type_key": sport_type or None, "name": str(item.get("name") or "").strip() or None,
        "duration_s": moving or elapsed, "moving_s": moving, "elapsed_s": elapsed,
        "distance_m": _positive(item.get("distance")), "elev_gain_m": _positive(item.get("total_elevation_gain")),
        "avg_hr": _positive(item.get("average_heartrate")) if item.get("has_heartrate", True) else None,
        "max_hr": _positive(item.get("max_heartrate")) if item.get("has_heartrate", True) else None,
        "avg_speed": _positive(item.get("average_speed")), "max_speed": _positive(item.get("max_speed")),
        "avg_cadence": cadence, "avg_power": _positive(item.get("average_watts")),
        "start_lat": _num((item.get("start_latlng") or [None, None])[0]) if item.get("start_latlng") else None,
        "start_lon": _num((item.get("start_latlng") or [None, None])[1]) if item.get("start_latlng") else None,
        "extra": json.dumps(extra, ensure_ascii=False, separators=(",", ":")),
        # colonnes propres au cache
        "strava_id": strava_id, "external_id": str(item.get("external_id") or "") or None,
        "garmin_id": garmin_id(item.get("external_id")), "device_name": device,
        "polyline": ((item.get("map") or {}).get("summary_polyline") or None) if isinstance(item.get("map"), dict)
        else None,
    }


def detail_fields(item: dict, family: str) -> dict:
    """Ce que seul le détail d'une séance donne (DetailedActivity) : description, calories, tours."""
    if not isinstance(item, dict):
        return {"description": None, "calories": None, "laps": [], "device_name": None}
    laps = []
    for index, lap in enumerate(item.get("laps") or []):
        if not isinstance(lap, dict):
            continue
        cadence = _positive(lap.get("average_cadence"))
        if cadence and family in STEP_FAMILIES:
            cadence *= 2
        laps.append({
            "idx": index, "start_s": None, "duration_s": _positive(lap.get("moving_time")),
            "elapsed_s": _positive(lap.get("elapsed_time")), "distance_m": _positive(lap.get("distance")),
            "avg_hr": _positive(lap.get("average_heartrate")), "max_hr": _positive(lap.get("max_heartrate")),
            "avg_speed": _positive(lap.get("average_speed")), "max_speed": _positive(lap.get("max_speed")),
            "avg_cadence": cadence, "avg_power": _positive(lap.get("average_watts")),
            "elev_gain_m": _positive(lap.get("total_elevation_gain")), "elev_loss_m": None, "intensity": None,
        })
    # Le départ de chaque tour : la somme des durées des tours d'avant
    clock = 0.0
    for lap in laps:
        lap["start_s"] = round(clock, 1)
        clock += lap["elapsed_s"] or lap["duration_s"] or 0
    if len(laps) < 2:
        laps = []  # un seul tour = la séance entière : rien à montrer
    description = str(item.get("description") or "").strip() or None
    return {"description": description, "calories": _positive(item.get("calories")), "laps": laps,
            "device_name": str(item.get("device_name") or "").strip() or None}


def streams(payload: Any, family: str) -> dict | None:
    """Courbes de Strava (``key_by_type``) → courbes de Foulée (t, hr, spd, alt, cad, pwr, dist, lat, lon, temp)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("time"), dict):
        return None

    def data(key: str) -> list | None:
        entry = payload.get(key)
        values = entry.get("data") if isinstance(entry, dict) else None
        return values if isinstance(values, list) else None

    times = data("time") or []
    n = len(times)
    if n < 2:
        return None
    out: dict[str, list] = {"t": [float(t) for t in times]}
    simple = {"heartrate": "hr", "velocity_smooth": "spd", "altitude": "alt", "watts": "pwr", "distance": "dist",
              "temp": "temp"}
    for key, name in simple.items():
        values = data(key)
        if values and len(values) == n:
            out[name] = [_num(v) for v in values]
    cadence = data("cadence")
    if cadence and len(cadence) == n:
        factor = 2 if family in STEP_FAMILIES else 1
        out["cad"] = [(_num(v) or 0) * factor if _num(v) is not None else None for v in cadence]
    latlng = data("latlng")
    if latlng and len(latlng) == n:
        out["lat"] = [p[0] if isinstance(p, list) and len(p) == 2 else None for p in latlng]
        out["lon"] = [p[1] if isinstance(p, list) and len(p) == 2 else None for p in latlng]
    return out


def decode_polyline(text: str | None) -> list[tuple[float, float]]:
    """Tracé résumé de Strava (« polyline » encodée de Google) → points (latitude, longitude)."""
    points: list[tuple[float, float]] = []
    if not text:
        return points
    index = lat = lon = 0
    length = len(text)
    try:
        while index < length:
            values = []
            for _ in range(2):
                shift = result = 0
                while True:
                    byte = ord(text[index]) - 63
                    index += 1
                    result |= (byte & 0x1F) << shift
                    shift += 5
                    if byte < 0x20:
                        break
                values.append(~(result >> 1) if result & 1 else result >> 1)
            lat += values[0]
            lon += values[1]
            points.append((lat / 1e5, lon / 1e5))
    except IndexError:
        return points
    return points


# --------------------------------------------------- exercices de la description
# Strava garde les exercices d'une séance de musculation pour son appli et son connecteur Claude : son API ne
# les donne pas (elle ne sait que les recevoir). Foulée lit donc ceux que la description énumère, comme le font
# les applis de musculation (Hevy, Strong…) ou une note écrite à la main. Les noms restent tels qu'écrits.
LB = 0.45359237
_WEIGHT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|kgs|lb|lbs)\b", re.I)
_SET_LINE = re.compile(r"^(?:(?:set|série|serie)\s*\d+\s*[:.)\-]?|\d{1,2}\s*[:.)]|[-•*–])\s*(?P<rest>.+)$", re.I)
_WEIGHT_X_REPS = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(kg|kgs|lb|lbs)\s*[x×*]\s*(\d+)", re.I)
_REPS_X_WEIGHT = re.compile(r"^(\d+)\s*(?:reps?|rép\w*)?\s*[x×*@à]\s*(\d+(?:[.,]\d+)?)\s*(kg|kgs|lb|lbs)\b", re.I)
_REPS = re.compile(r"^(\d+)\s*(?:reps?|rép\w*|fois)\b", re.I)
_TIME = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(s|sec|secs|secondes?|min|mn)\b", re.I)
_INLINE = re.compile(r"^(?P<name>[^\d|:]{2,60}?)\s*[:\-–|]?\s*(?P<sets>\d{1,2})\s*[x×*]\s*(?P<amount>\d+(?:[.,]\d+)?)"
                     r"\s*(?P<unit>secondes?|secs?|s|min|mn|reps?|rép\w*)?\b", re.I)
_NOISE = re.compile(r"(https?://|www\.|logged with|enregistré avec|#\w)", re.I)


def _kg(value: str, unit: str) -> float:
    number = float(value.replace(",", "."))
    return round(number * LB, 2) if unit.lower().startswith("lb") else number


def _clean_name(text: str) -> str:
    name = re.sub(r"\s+", " ", text).strip(" :-–|•*\t")
    return name[:1].upper() + name[1:] if name else name


def _seconds(amount: float, unit: str) -> float:
    return amount * (60 if unit.lower() in ("min", "mn") else 1)


def exercises_from_text(text: str | None) -> list[dict]:
    """Exercices énumérés dans une description, au format de la table ``exercises`` (catégorie « texte »).

    Formats lus : « Bench Press (Barbell) » suivi de « Set 1: 60 kg x 10 » (Hevy), « 1: 60 kg × 10 » (Strong),
    ou une ligne par exercice : « Squat 4x10 @ 65 kg », « Pompes : 3 x 15 », « Gainage 3 x 45 s ».
    Les noms restent tels qu'écrits (en anglais le plus souvent) : ce sont ceux que tout le monde emploie.
    """
    if not text:
        return []
    found: dict[str, dict] = {}

    def add(name: str, *, sets: int, reps: int = 0, duration: float = 0.0, weights: list[tuple[float, int]] = ()):
        entry = found.setdefault(name.lower(), {"category": "texte", "name": name, "sets": 0, "reps": 0,
                                                "duration_s": 0.0, "max_kg": 0.0, "volume_kg": 0.0})
        entry["sets"] += sets
        entry["reps"] += reps
        entry["duration_s"] += duration
        for kg, count in weights:
            entry["max_kg"] = max(entry["max_kg"], kg)
            entry["volume_kg"] += kg * count

    def one_set(name: str, rest: str) -> bool:
        rest = rest.strip()
        match = _WEIGHT_X_REPS.match(rest)
        if match:
            kg, reps = _kg(match.group(1), match.group(2)), int(match.group(3))
            add(name, sets=1, reps=reps, weights=[(kg, reps)])
            return True
        match = _REPS_X_WEIGHT.match(rest)
        if match:
            reps, kg = int(match.group(1)), _kg(match.group(2), match.group(3))
            add(name, sets=1, reps=reps, weights=[(kg, reps)])
            return True
        match = _REPS.match(rest)
        if match:
            add(name, sets=1, reps=int(match.group(1)))
            return True
        match = _TIME.match(rest)
        if match:
            add(name, sets=1, duration=_seconds(float(match.group(1).replace(",", ".")), match.group(2)))
            return True
        return False

    current: str | None = None
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line or _NOISE.search(line):
            continue
        set_line = _SET_LINE.match(line)
        if current and set_line and one_set(current, set_line.group("rest")):
            continue
        inline = _INLINE.match(line)
        if inline:
            name = _clean_name(inline.group("name"))
            sets, amount = int(inline.group("sets")), float(inline.group("amount").replace(",", "."))
            unit = (inline.group("unit") or "").lower()
            if name and 0 < sets <= 20 and amount > 0:
                if unit and not unit.startswith(("rep", "rép")):
                    add(name, sets=sets, duration=sets * _seconds(amount, unit))
                else:
                    reps = int(amount)
                    weight = _WEIGHT.search(line[inline.end():])
                    weights = [(_kg(weight.group(1), weight.group(2)), reps)] * sets if weight else []
                    add(name, sets=sets, reps=sets * reps, weights=weights)
                current = None
                continue
        # Une ligne de texte seule (sans chiffre) annonce l'exercice dont les séries suivent
        if not re.search(r"\d", line) and 2 <= len(line) <= 60 and not line.endswith((".", "!", "?", ":")):
            current = _clean_name(line)
        elif not set_line:
            current = None
    out = []
    for entry in found.values():
        if entry["sets"] <= 0:
            continue
        entry.update(idx=len(out), duration_s=round(entry["duration_s"], 1), max_kg=round(entry["max_kg"], 2),
                     volume_kg=round(entry["volume_kg"], 1))
        out.append(entry)
    return out
