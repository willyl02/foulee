"""Une séance proposée par le coach, en fichier d'entraînement FIT (le format natif des montres Garmin).

Le fichier se copie dans le dossier ``GARMIN/NewFiles`` de la montre, branchée en USB : elle l'importe dans
ses entraînements. Chaque bloc devient une étape ; un bloc répété devient une boucle (l'effort, la récup, et
« répéter N fois »). Les % de VMA deviennent une fourchette d'allure, calculée avec la VMA de l'élève.
"""

from __future__ import annotations

import re
import unicodedata
import zlib
from datetime import datetime, timezone
from typing import Any

from garmin_fit_sdk import Decoder, Encoder, Stream
from garmin_fit_sdk.profile import Profile

MESG = Profile["mesg_num"]
PACE_SPORTS = {"course", "trail", "marche"}  # une allure n'a de sens qu'à pied
TOLERANCE = 0.03   # fourchette d'allure : ± 3 % de vitesse autour de la cible
SPORTS = {   # famille Foulée → (sport, sous-sport) FIT
    "course": ("running", "generic"), "trail": ("running", "trail"), "velo": ("cycling", "generic"),
    "natation": ("swimming", "lap_swimming"), "renfo": ("training", "strength_training"),
    "cardio": ("training", "cardio_training"), "souplesse": ("training", "yoga"),
    "marche": ("walking", "generic"), "autre": ("generic", "generic"),
}
INTENSITY = {"echauffement": "warmup", "calme": "cooldown", "corps": "active", "libre": "active"}
GENRE_NAMES = {"echauffement": "Échauffement", "calme": "Retour au calme", "corps": "Effort", "libre": "Libre"}


class WorkoutError(ValueError):
    pass


def _pace(speed_ms: float) -> str:
    seconds = round(1000 / speed_ms)
    return f"{seconds // 60}:{seconds % 60:02d} /km"


def _duration(block: dict) -> tuple[str, int]:
    if block.get("duree_min"):
        return "time", round(float(block["duree_min"]) * 60 * 1000)        # millisecondes
    if block.get("distance_m"):
        return "distance", round(float(block["distance_m"]) * 100)          # centimètres
    return "open", 0                                                         # jusqu'au bouton « tour »


def _target(block: dict, sport: str, vma: float | None) -> tuple[dict, str]:
    """La cible de l'étape, et la même en clair pour la note."""
    if block.get("pct_vma") and vma and sport in PACE_SPORTS:
        speed = vma * float(block["pct_vma"]) / 100 / 3.6
        low, high = speed * (1 - TOLERANCE), speed * (1 + TOLERANCE)
        return ({"target_type": "speed", "target_value": 0,
                 "custom_target_value_low": round(low * 1000), "custom_target_value_high": round(high * 1000)},
                f"{block['pct_vma']:g} % VMA · {_pace(speed)}")
    if block.get("zone_fc"):
        zone = max(1, min(5, int(block["zone_fc"])))
        return {"target_type": "heart_rate", "target_value": zone}, f"zone FC {zone}"
    text = f"{block['pct_vma']:g} % VMA" if block.get("pct_vma") else ""
    return {"target_type": "open"}, text


def steps_for(item: dict, vma: float | None) -> list[dict]:
    sport = item.get("sport") or "course"
    steps: list[dict] = []
    for block in item.get("blocs") or []:
        genre = block.get("genre") or "corps"
        reps = max(1, min(50, int(block.get("repetitions") or 1)))
        kind, value = _duration(block)
        target, said = _target(block, sport, vma)
        first = len(steps)
        notes = " · ".join(x for x in (said, block.get("note")) if x)
        steps.append({"wkt_step_name": (block.get("nom") or GENRE_NAMES.get(genre, "Étape"))[:32],
                      "duration_type": kind, "duration_value": value, **target,
                      "intensity": INTENSITY.get(genre, "active"), **({"notes": notes[:80]} if notes else {})})
        if reps > 1:
            rest = float(block.get("recup_min") or 0)
            if rest or block.get("recup_texte"):
                steps.append({"wkt_step_name": "Récup", "intensity": "recovery", "target_type": "open",
                              "duration_type": "time" if rest else "open",
                              "duration_value": round(rest * 60 * 1000) if rest else 0,
                              **({"notes": block["recup_texte"][:80]} if block.get("recup_texte") else {})})
            steps.append({"duration_type": "repeat_until_steps_cmplt", "duration_value": first,
                          "target_type": "open", "target_value": reps})
    if not steps:
        raise WorkoutError("Cette séance n'a aucun bloc.")
    return steps


def build(item: dict, vma: float | None, *, created: datetime | None = None) -> bytes:
    """Le fichier FIT d'une séance proposée (``item`` : titre, sport, blocs, consigne)."""
    sport, sub_sport = SPORTS.get(item.get("sport") or "course", SPORTS["autre"])
    steps = steps_for(item, vma)
    created = created or datetime.now(timezone.utc)
    encoder = Encoder()
    encoder.write_mesg({"mesg_num": MESG["FILE_ID"], "type": "workout", "manufacturer": "development",
                        "product": 0, "serial_number": zlib.crc32(str(item.get("id", item.get("titre"))).encode()) or 1,
                        "time_created": created})
    workout = {"mesg_num": MESG["WORKOUT"], "sport": sport, "sub_sport": sub_sport,
               "wkt_name": (item.get("titre") or "Séance du coach")[:40], "num_valid_steps": len(steps)}
    if sport == "swimming":
        workout.update({"pool_length": 25, "pool_length_unit": "metric"})
    if item.get("consigne"):
        workout["wkt_description"] = item["consigne"][:120]
    encoder.write_mesg(workout)
    for index, step in enumerate(steps):
        encoder.write_mesg({"mesg_num": MESG["WORKOUT_STEP"], "message_index": index, **step})
    return encoder.close()


def decode(data: bytes) -> dict[str, list[dict[str, Any]]]:
    """Relit un fichier (pour les tests, et pour vérifier ce qu'on donne à la montre)."""
    check = Decoder(Stream.from_byte_array(bytearray(data)))
    if not check.is_fit() or not check.check_integrity():
        raise WorkoutError("Fichier FIT invalide.")
    messages, errors = Decoder(Stream.from_byte_array(bytearray(data))).read(convert_datetimes_to_dates=False)
    if errors:
        raise WorkoutError(f"Fichier FIT illisible : {errors[0]}")
    return messages


def file_name(item: dict) -> str:
    """« 2026-11-14-seuil-3-x-10-min.fit » : sans accents ni espaces, pour toutes les montres."""
    title = unicodedata.normalize("NFKD", item.get("titre") or "seance").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()[:40] or "seance"
    return f"{item.get('date', '')}-{slug}.fit".lstrip("-")
