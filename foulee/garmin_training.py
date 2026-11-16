"""Une séance proposée par le coach, au format de la Training API de Garmin (spécification V2).

Le pendant de ``workout_fit`` (le fichier .fit pour l'USB) : mêmes blocs, même lecture. Chaque bloc devient une
étape ; un bloc répété devient une boucle (``WorkoutRepeatStep`` : l'effort, la récup, N fois) ; les % de VMA
deviennent une fourchette d'allure (± 3 % de vitesse, en m/s) calculée avec la VMA de l'élève ; la zone de FC,
une cible de zone de FC. Le relais envoie ce dictionnaire à Garmin, qui range la séance dans le calendrier
Garmin Connect de l'élève ; la montre la récupère à sa synchro.
"""

from __future__ import annotations

from typing import Any

from .workout_fit import GENRE_NAMES, PACE_SPORTS, TOLERANCE, WorkoutError

PROVIDER = "Foulée"   # workoutProvider et workoutSourceId : 20 caractères au plus
MAX_STEPS = 100       # Garmin : 100 étapes au plus par séance
SPORTS = {  # famille Foulée → sport de la Training API
    "course": "RUNNING", "trail": "RUNNING", "velo": "CYCLING", "natation": "LAP_SWIMMING",
    "renfo": "STRENGTH_TRAINING", "cardio": "CARDIO_TRAINING", "souplesse": "YOGA",
    "marche": "GENERIC", "rando": "GENERIC", "autre": "GENERIC",
}
INTENSITY = {"echauffement": "WARMUP", "calme": "COOLDOWN", "corps": "ACTIVE", "libre": "ACTIVE"}


def _pace(speed_ms: float) -> str:
    seconds = round(1000 / speed_ms)
    return f"{seconds // 60}:{seconds % 60:02d} /km"


def _duration(block: dict) -> tuple[str, float | None, str | None]:
    """(durationType, durationValue, durationValueType) : le temps d'abord, comme sur la montre."""
    if block.get("duree_min"):
        return "TIME", float(round(float(block["duree_min"]) * 60)), None   # secondes
    if block.get("distance_m"):
        return "DISTANCE", float(round(float(block["distance_m"]))), "METER"
    return "OPEN", None, None                                              # jusqu'au bouton « tour »


def _target(block: dict, sport: str, vma: float | None, zones: bool) -> tuple[dict, str]:
    """La cible de l'étape, et la même en clair pour la description."""
    if block.get("pct_vma") and vma and sport in PACE_SPORTS:
        speed = vma * float(block["pct_vma"]) / 100 / 3.6
        # PACE se donne en vitesse (m/s) : « low » est la limite lente, « high » la rapide
        return ({"targetType": "PACE", "targetValue": None, "targetValueLow": round(speed * (1 - TOLERANCE), 4),
                 "targetValueHigh": round(speed * (1 + TOLERANCE), 4), "targetValueType": None},
                f"{block['pct_vma']:g} % VMA · {_pace(speed)}")
    if block.get("zone_fc"):
        zone = max(1, min(5, int(block["zone_fc"])))
        target = {"targetType": "HEART_RATE", "targetValue": zone, "targetValueLow": None, "targetValueHigh": None,
                  "targetValueType": None} if zones else {}
        return target, f"zone FC {zone}"
    return {}, f"{block['pct_vma']:g} % VMA" if block.get("pct_vma") else ""


def _open_target() -> dict:
    return {"targetType": "OPEN", "targetValue": None, "targetValueLow": None, "targetValueHigh": None,
            "targetValueType": None}


def _step(order: int, intensity: str, description: str | None, block: dict, target: dict) -> dict:
    kind, value, unit = _duration(block)
    return {"type": "WorkoutStep", "stepOrder": order, "intensity": intensity,
            "description": (description or None) and description[:512],
            "durationType": kind, "durationValue": value, "durationValueType": unit,
            **(_open_target() | target)}


def build(item: dict, vma: float | None, *, zones: bool = True) -> dict[str, Any]:
    """La séance (``item`` : titre, sport, blocs, consigne) au format de la Training API.

    ``zones`` : cibles en zone de FC (sinon la zone n'est rappelée que dans la description de l'étape).
    """
    family = item.get("sport") or "course"
    sport = SPORTS.get(family, "GENERIC")
    steps: list[dict] = []
    order = 0
    for block in item.get("blocs") or []:
        genre = block.get("genre") or "corps"
        reps = max(1, min(50, int(block.get("repetitions") or 1)))
        target, said = _target(block, family, vma, zones)
        name = block.get("nom") or GENRE_NAMES.get(genre, "Étape")
        description = " · ".join(x for x in (name, said, block.get("note")) if x)
        if reps == 1:
            order += 1
            steps.append(_step(order, INTENSITY.get(genre, "ACTIVE"), description, block, target))
            continue
        order += 1  # la boucle prend son numéro avant ses étapes, comme dans l'exemple de Garmin
        repeat = {"type": "WorkoutRepeatStep", "stepOrder": order, "repeatType": "REPEAT_UNTIL_STEPS_CMPLT",
                  "repeatValue": reps, "steps": []}
        order += 1
        repeat["steps"].append(_step(order, "INTERVAL" if genre in ("corps", "libre") else INTENSITY[genre],
                                     description, block, target))
        rest = float(block.get("recup_min") or 0)
        if rest or block.get("recup_texte"):
            order += 1
            repeat["steps"].append(_step(order, "RECOVERY", " · ".join(x for x in ("Récup", block.get("recup_texte"))
                                                                        if x),
                                         {"duree_min": rest} if rest else {}, {}))
        steps.append(repeat)
    if not steps:
        raise WorkoutError("Cette séance n'a aucun bloc.")
    if order > MAX_STEPS:
        raise WorkoutError(f"Cette séance compte {order} étapes : Garmin en accepte {MAX_STEPS} au plus.")
    workout = {"workoutName": (item.get("titre") or "Séance du coach")[:50],
               "description": (item.get("consigne") or None) and item["consigne"][:1024],
               "sport": sport, "workoutProvider": PROVIDER, "workoutSourceId": PROVIDER,
               "isSessionTransitionEnabled": False,
               "segments": [{"segmentOrder": 1, "sport": sport, "steps": steps}]}
    if sport == "LAP_SWIMMING":
        workout.update({"poolLength": 25.0, "poolLengthUnit": "METER"})
        workout["segments"][0].update({"poolLength": 25.0, "poolLengthUnit": "METER"})
    return workout


def has_zones(workout: dict) -> bool:
    """La séance vise-t-elle une zone de FC ? (si Garmin la refuse, on la renvoie sans)"""
    def walk(steps):
        for step in steps:
            if step.get("type") == "WorkoutRepeatStep":
                yield from walk(step["steps"])
            else:
                yield step
    return any(s.get("targetType") == "HEART_RATE" for seg in workout.get("segments", []) for s in walk(seg["steps"]))
