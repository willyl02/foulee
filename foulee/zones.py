"""Zones de fréquence cardiaque et d'allure : méthodes de calcul, valeurs par défaut, contrôles.

Zones FC (réglage « zones_fc ») : cinq zones, décrites par leurs planchers.
- garmin       : les zones de ta montre, relues chez Garmin à chaque synchro ;
- pct_max      : en % de la FC max (Garmin par défaut : 50, 60, 70, 80, 90) ;
- pct_reserve  : en % de la FC de réserve (Karvonen : repos + % × (max − repos)) ;
- pct_seuil    : en % de la FC au seuil lactique (lue chez Garmin ou saisie) ;
- bornes       : quatre bornes en bpm, comme le curseur de Strava (la zone 1 part de zéro).

Zones d'allure (réglage « zones_allure ») : cinq zones, décrites par quatre vitesses.
- pct_vma      : en % de la VMA (réglage historique « zones_allure_pct_vma ») ;
- pct_seuil    : en % de la vitesse au seuil (allure saisie, ou lue chez Garmin) ;
- bornes       : quatre allures en min/km.
"""

from __future__ import annotations

import math
import re
from typing import Any

HR_METHODS = {
    "garmin": "Zones Garmin (celles de ta montre)",
    "pct_max": "% de la FC max",
    "pct_reserve": "% de la FC de réserve (Karvonen)",
    "pct_seuil": "% de la FC au seuil lactique",
    "bornes": "Bornes personnalisées (comme Strava)",
}
HR_DEFAULT_PCT = {
    "pct_max": [50, 60, 70, 80, 90],
    "pct_reserve": [50, 60, 70, 80, 90],
    "pct_seuil": [70, 85, 90, 95, 100],
}
HR_ZONE_NAMES = ["Z1 Échauffement", "Z2 Facile", "Z3 Aérobie", "Z4 Seuil", "Z5 Maximum"]

PACE_METHODS = {
    "pct_vma": "% de la VMA",
    "pct_seuil": "% de la vitesse au seuil",
    "bornes": "Allures personnalisées",
}
PACE_DEFAULT_PCT = {"pct_vma": [70, 80, 88, 95], "pct_seuil": [75, 85, 95, 102]}
PACE_ZONE_NAMES = ["Récup / EF", "Endurance active", "Seuil / semi", "Allure 10 km", "VMA"]


class ZoneError(ValueError):
    pass


def _round(value: float) -> int:
    """Arrondi au plus proche, 0,5 vers le haut : comme l'interface (Math.round)."""
    return int(math.floor(value + 0.5))


# ------------------------------------------------------------------ outils
def parse_pace(value: Any) -> float | None:
    """« 4:05 » ou 245 (secondes par km) → secondes par km."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if value > 0 else None
    match = re.fullmatch(r"\s*(\d{1,2})[:'’](\d{2})\s*(?:/\s*km)?\s*", str(value))
    if not match:
        raise ZoneError(f"Allure illisible « {value} » (format 4:05).")
    return int(match[1]) * 60 + int(match[2])


def _numbers(values: Any, count: int, low: float, high: float, label: str) -> list[float]:
    if not isinstance(values, list) or len(values) != count:
        raise ZoneError(f"{label} : il faut {count} valeurs.")
    result = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ZoneError(f"{label} : « {value} » n'est pas un nombre.") from None
        if not low <= number <= high:
            raise ZoneError(f"{label} : {number:g} sort des valeurs possibles ({low:g} à {high:g}).")
        result.append(int(number) if number.is_integer() else round(number, 1))
    if any(b <= a for a, b in zip(result, result[1:])):
        raise ZoneError(f"{label} : chaque valeur doit dépasser la précédente.")
    return result


# ------------------------------------------------------------------ FC
def clean_hr(data: Any) -> dict:
    data = data if isinstance(data, dict) else {}
    method = data.get("methode") or "auto"
    if method not in HR_METHODS and method != "auto":
        raise ZoneError(f"Méthode de zones FC inconnue : {method}.")
    clean: dict[str, Any] = {"methode": method, "pct": None, "seuil": None, "bornes": None}
    if data.get("pct") is not None:
        clean["pct"] = _numbers(data["pct"], 5, 20, 130, "Zones FC en %")
    if data.get("seuil") not in (None, ""):
        try:
            seuil = float(data["seuil"])
        except (TypeError, ValueError):
            raise ZoneError("FC au seuil illisible.") from None
        if not 100 <= seuil <= 220:
            raise ZoneError("FC au seuil : entre 100 et 220 bpm.")
        clean["seuil"] = round(seuil)
    if data.get("bornes") is not None:
        clean["bornes"] = [int(round(v)) for v in _numbers(data["bornes"], 4, 60, 230, "Bornes des zones FC")]
    return clean


def hr_floors(config: dict | None, hr_max: float, hr_rest: float, garmin: dict | None,
              max_from_settings: bool = False) -> dict:
    """Planchers des cinq zones FC selon la méthode choisie (et ce que Garmin a fourni)."""
    config = config or {}
    method = config.get("methode") or "auto"
    garmin = garmin or {}
    lthr = config.get("seuil") or garmin.get("lthr")
    if method == "auto":
        # Comportement historique : zones Garmin, sauf FC max imposée dans les réglages
        method = "garmin" if garmin.get("floors") and not max_from_settings else "pct_max"
    if method == "garmin" and not garmin.get("floors"):
        method = "pct_max"
    if method == "pct_seuil" and not lthr:
        method = "pct_max"
    pct = config.get("pct") or HR_DEFAULT_PCT.get(method)
    if method == "garmin":
        floors = [float(f) for f in garmin["floors"]]
    elif method == "bornes" and config.get("bornes"):
        floors = [0.0] + [float(b) for b in config["bornes"]]
    elif method == "pct_reserve":
        floors = [_round(hr_rest + (hr_max - hr_rest) * p / 100) for p in pct]
    elif method == "pct_seuil":
        floors = [_round(lthr * p / 100) for p in pct]
    else:
        method = "pct_max"
        pct = config.get("pct") if config.get("methode") == "pct_max" and config.get("pct") else HR_DEFAULT_PCT["pct_max"]
        floors = [_round(hr_max * p / 100) for p in pct]
    return {"methode": method, "floors": [float(f) for f in floors], "pct": pct if method.startswith("pct") else None,
            "seuil": lthr, "noms": HR_ZONE_NAMES}


def hr_bounds_text(floors: list[float]) -> list[str]:
    floors = [int(f) for f in floors]
    first = f"< {floors[1]} bpm" if floors[0] <= 0 else f"{floors[0]}–{floors[1] - 1} bpm"
    return [first] + [f"{floors[i]}–{floors[i + 1] - 1} bpm" for i in range(1, 4)] + [f"≥ {floors[4]} bpm"]


# ----------------------------------------------------------------- allure
def clean_pace(data: Any) -> dict:
    data = data if isinstance(data, dict) else {}
    method = data.get("methode") or "pct_vma"
    if method not in PACE_METHODS:
        raise ZoneError(f"Méthode de zones d'allure inconnue : {method}.")
    clean: dict[str, Any] = {"methode": method, "pct": None, "seuil": None, "bornes": None}
    if data.get("pct") is not None:
        clean["pct"] = _numbers(data["pct"], 4, 30, 140, "Zones d'allure en %")
    if data.get("seuil") not in (None, ""):
        seuil = parse_pace(data["seuil"])
        if not seuil or not 120 <= seuil <= 600:
            raise ZoneError("Allure au seuil : entre 2:00 et 10:00 /km.")
        clean["seuil"] = round(seuil)
    if data.get("bornes") is not None:
        raw = data["bornes"]
        if not isinstance(raw, list) or len(raw) != 4:
            raise ZoneError("Il faut quatre allures pour séparer cinq zones.")
        secs = [parse_pace(v) for v in raw]
        if any(s is None or not 120 <= s <= 900 for s in secs):
            raise ZoneError("Allures des zones : entre 2:00 et 15:00 /km.")
        if any(b >= a for a, b in zip(secs, secs[1:])):
            raise ZoneError("Allures des zones : de la plus lente (zone 1) à la plus rapide (zone 5).")
        clean["bornes"] = [round(s) for s in secs]
    return clean


def pace_bounds(config: dict | None, vma_kmh: float, legacy_pct: list | None = None,
                garmin_threshold_speed: float | None = None) -> dict:
    """Quatre vitesses (m/s) qui séparent les cinq zones d'allure."""
    config = config or {}
    method = config.get("methode") or "pct_vma"
    threshold = None
    if config.get("seuil"):
        threshold = 1000 / float(config["seuil"])
    elif garmin_threshold_speed:
        threshold = float(garmin_threshold_speed)
    if method == "bornes" and config.get("bornes"):
        speeds = [1000 / float(s) for s in config["bornes"]]
        pct = None
    elif method == "pct_seuil" and threshold:
        pct = config.get("pct") or PACE_DEFAULT_PCT["pct_seuil"]
        speeds = [threshold * p / 100 for p in pct]
    else:
        method = "pct_vma"
        pct = (config.get("pct") if config.get("methode") == "pct_vma" else None) or legacy_pct or PACE_DEFAULT_PCT["pct_vma"]
        speeds = [vma_kmh * float(p) / 100 / 3.6 for p in pct]
    return {"methode": method, "vitesses": speeds, "pct": pct, "seuil_vitesse": threshold, "noms": PACE_ZONE_NAMES}
