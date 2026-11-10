"""Horaires de travail : postes (matin, soir, nuit, journée…), cycle et congés.

Le réglage « horaires » décrit qui travaille quand :

    {
      "actif": true,
      "modele": "bureau" | "2x8" | "3x8" | "5x8" | "perso",
      "postes": [{"id": "matin", "nom": "Matin", "debut": "05:00", "fin": "13:00"}, …],
      "cycle": {
        "unite": "semaine",                 # cycle fait de semaines (bureau, 2x8, 3x8…)
        "semaines": [[7 codes], …],         # une ligne par semaine du cycle, du lundi au dimanche
        "ancrage": "parite" | "AAAA-MM-JJ", # parité ISO (semaines impaires = 1re ligne) ou lundi de la 1re ligne
        # ou bien
        "unite": "jour",                    # cycle fait de jours (5x8…)
        "jours": [codes…],                  # la suite des jours du cycle
        "debut": "AAAA-MM-JJ"               # date du 1er jour du cycle
      },
      "conges": [{"du": "AAAA-MM-JJ", "au": "AAAA-MM-JJ", "nom": "Été"}],
      "jours_ouvres": true                  # comparer seulement les jours travaillés
    }

Un code de jour est l'identifiant d'un poste, ou "" pour un jour de repos.

L'ancien réglage « postes » (semaines impaires du matin, paires du soir) se lit
toujours : il devient un modèle 2x8 ancré sur la parité des semaines ISO.
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from datetime import date, timedelta
from typing import Any

MODELES = {
    "bureau": "Horaires de bureau",
    "2x8": "En décalé : matin / soir (2x8)",
    "3x8": "3x8 : matin / après-midi / nuit",
    "5x8": "5x8 : cycle continu",
    "perso": "Personnalisé",
}
REPOS = "repos"  # groupe des jours de repos, quand on les compare à part

_M, _S, _N, _J = "matin", "soir", "nuit", "journee"
WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _week(code: str, days: int = 5) -> list[str]:
    return [code] * days + [""] * (7 - days)


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def preset(modele: str, today: date | None = None) -> dict:
    """Horaires types, à ajuster ensuite (heures, ordre des semaines, congés…)."""
    today = today or date.today()
    monday = _monday(today).isoformat()
    morning = {"id": _M, "nom": "Matin", "debut": "05:00", "fin": "13:00"}
    if modele == "bureau":
        postes = [{"id": _J, "nom": "Journée", "debut": "08:30", "fin": "17:30"}]
        cycle = {"unite": "semaine", "semaines": [_week(_J)], "ancrage": monday}
    elif modele == "3x8":
        postes = [morning, {"id": "apres-midi", "nom": "Après-midi", "debut": "13:00", "fin": "21:00"},
                  {"id": _N, "nom": "Nuit", "debut": "21:00", "fin": "05:00"}]
        cycle = {"unite": "semaine", "semaines": [_week(_M), _week("apres-midi"), _week(_N)], "ancrage": monday}
    elif modele == "5x8":
        postes = [morning, {"id": "apres-midi", "nom": "Après-midi", "debut": "13:00", "fin": "21:00"},
                  {"id": _N, "nom": "Nuit", "debut": "21:00", "fin": "05:00"}]
        cycle = {"unite": "jour", "jours": [_M, _M, "apres-midi", "apres-midi", _N, _N, "", "", "", ""],
                 "debut": today.isoformat()}
    else:  # 2x8, et point de départ du modèle personnalisé
        postes = [morning, {"id": _S, "nom": "Soir", "debut": "13:00", "fin": "21:00"}]
        cycle = {"unite": "semaine", "semaines": [_week(_M), _week(_S)], "ancrage": "parite"}
    return {"actif": True, "modele": modele if modele in MODELES else "2x8", "postes": postes, "cycle": cycle,
            "conges": [], "jours_ouvres": True}


def from_legacy(postes: dict | None) -> dict:
    """Ancien réglage « postes » (parité des semaines ISO) → horaires 2x8 équivalents."""
    postes = postes or {}
    odd = postes.get("impaires") if postes.get("impaires") in (_M, _S) else _M
    even = _S if odd == _M else _M
    result = preset("2x8")
    result["cycle"]["semaines"] = [_week(odd), _week(even)]
    result["actif"] = postes.get("actif", True) is not False
    result["jours_ouvres"] = postes.get("jours_ouvres", True) is not False
    leaves = []
    for week in postes.get("semaines_exclues") or []:
        match = re.fullmatch(r"(\d{4})-W(\d{2})", str(week).strip().upper())
        if not match:
            continue
        try:
            monday = date.fromisocalendar(int(match[1]), int(match[2]), 1)
        except ValueError:
            continue
        leaves.append({"du": monday.isoformat(), "au": (monday + timedelta(days=6)).isoformat(),
                       "nom": f"Semaine {int(match[2])}"})
    result["conges"] = leaves
    return result


# ------------------------------------------------------------------ validation
class ScheduleError(ValueError):
    pass


def _clock(text: Any, label: str) -> str:
    value = str(text or "").strip()
    match = re.fullmatch(r"(\d{1,2})[:h](\d{2})", value)
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        raise ScheduleError(f"{label} : heure illisible « {value} » (format 05:30).")
    return f"{int(match[1]):02d}:{match[2]}"


def _day(text: Any, label: str) -> date:
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        raise ScheduleError(f"{label} : date illisible « {text} » (format AAAA-MM-JJ).") from None


def clean(data: Any) -> dict:
    """Vérifie et normalise des horaires reçus de l'interface ou de Claude."""
    if not isinstance(data, dict):
        raise ScheduleError("Horaires illisibles.")
    modele = data.get("modele") if data.get("modele") in MODELES else "perso"
    postes, ids = [], set()
    for index, raw in enumerate(data.get("postes") or []):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("nom") or "").strip()[:30] or f"Poste {index + 1}"
        ident = re.sub(r"[^a-z0-9-]+", "-", str(raw.get("id") or name).lower()).strip("-")[:20] or f"poste-{index + 1}"
        if ident in ids or ident == REPOS:
            raise ScheduleError(f"Deux postes portent le même identifiant « {ident} ».")
        ids.add(ident)
        postes.append({"id": ident, "nom": name, "debut": _clock(raw.get("debut"), name),
                       "fin": _clock(raw.get("fin"), name)})
    if not postes:
        raise ScheduleError("Il faut au moins un poste (par exemple « Journée »).")
    if len(postes) > 8:
        raise ScheduleError("Huit postes au plus.")

    def code(value: Any) -> str:
        value = str(value or "").strip()
        if value and value not in ids:
            raise ScheduleError(f"Le cycle utilise un poste inconnu : « {value} ».")
        return value

    raw_cycle = data.get("cycle") if isinstance(data.get("cycle"), dict) else {}
    if raw_cycle.get("unite") == "jour":
        days = [code(v) for v in (raw_cycle.get("jours") or [])]
        if not 1 <= len(days) <= 42:
            raise ScheduleError("Un cycle compte de 1 à 42 jours.")
        cycle = {"unite": "jour", "jours": days, "debut": _day(raw_cycle.get("debut"), "Début du cycle").isoformat()}
    else:
        weeks = []
        for row in raw_cycle.get("semaines") or []:
            if not isinstance(row, list) or len(row) != 7:
                raise ScheduleError("Chaque semaine du cycle compte 7 jours, du lundi au dimanche.")
            weeks.append([code(v) for v in row])
        if not 1 <= len(weeks) <= 8:
            raise ScheduleError("Un cycle compte de 1 à 8 semaines.")
        anchor = raw_cycle.get("ancrage") or "parite"
        if anchor == "parite":
            if len(weeks) != 2:
                raise ScheduleError("La parité des semaines (paires / impaires) ne vaut que pour un cycle de 2 semaines.")
        else:
            anchor = _monday(_day(anchor, "Semaine n° 1 du cycle")).isoformat()
        cycle = {"unite": "semaine", "semaines": weeks, "ancrage": anchor}

    leaves = []
    for raw in data.get("conges") or []:
        if not isinstance(raw, dict):
            continue
        start = _day(raw.get("du"), "Congés")
        end = _day(raw.get("au") or raw.get("du"), "Congés")
        if end < start:
            start, end = end, start
        leaves.append({"du": start.isoformat(), "au": end.isoformat(), "nom": str(raw.get("nom") or "").strip()[:40]})
    if len(leaves) > 200:
        raise ScheduleError("Deux cents périodes de congés au plus.")
    leaves.sort(key=lambda item: item["du"])
    return {"actif": data.get("actif", True) is not False, "modele": modele, "postes": postes, "cycle": cycle,
            "conges": leaves, "jours_ouvres": data.get("jours_ouvres", True) is not False}


def effective(settings: dict) -> dict:
    """Horaires en vigueur : le réglage « horaires », sinon l'ancien réglage « postes » converti."""
    value = settings.get("horaires")
    if isinstance(value, dict) and value.get("postes"):
        try:
            return clean(value)
        except ScheduleError:
            pass
    return from_legacy(settings.get("postes"))


# --------------------------------------------------------------------- calculs
class Schedule:
    """Horaires prêts à interroger, jour par jour."""

    def __init__(self, horaires: dict):
        self.h = horaires
        self.postes = {p["id"]: p for p in horaires["postes"]}
        self.cycle = horaires["cycle"]
        self.leaves = [(date.fromisoformat(c["du"]), date.fromisoformat(c["au"]), c.get("nom") or "")
                       for c in horaires.get("conges") or []]

    @classmethod
    def of(cls, settings: dict) -> "Schedule":
        return cls(settings["horaires"] if isinstance(settings.get("horaires"), dict) and
                   "cycle" in settings["horaires"] else effective(settings))

    @property
    def active(self) -> bool:
        return bool(self.h.get("actif", True))

    def leave(self, day: date) -> str | None:
        """Nom des congés qui couvrent ce jour (« » s'ils n'ont pas de nom), ou None."""
        for start, end, name in self.leaves:
            if start <= day <= end:
                return name
        return None

    def week_index(self, day: date) -> int:
        weeks = self.cycle["semaines"]
        if self.cycle.get("ancrage") == "parite":
            return 0 if day.isocalendar()[1] % 2 == 1 else 1
        anchor = date.fromisoformat(self.cycle["ancrage"])
        return ((_monday(day) - anchor).days // 7) % len(weeks)

    def code(self, day: date) -> str:
        """Poste prévu par le cycle ce jour-là ("" = repos), congés non compris."""
        if self.cycle["unite"] == "jour":
            days = self.cycle["jours"]
            start = date.fromisoformat(self.cycle["debut"])
            return days[(day - start).days % len(days)]
        return self.cycle["semaines"][self.week_index(day)][day.weekday()]

    def week_shift(self, day: date) -> str | None:
        """Poste principal de la semaine du cycle (cycles en semaines seulement)."""
        if self.cycle["unite"] != "semaine":
            return None
        codes = [c for c in self.cycle["semaines"][self.week_index(day)] if c]
        return Counter(codes).most_common(1)[0][0] if codes else None

    def shift_of(self, day: date, include_rest: bool | None = None) -> str | None:
        """Groupe de comparaison d'un jour : un poste, « repos », ou None (congés, horaires coupés).

        include_rest : None = suivre le réglage « jours_ouvres ». Un jour de repos compte alors
        pour le poste de sa semaine (cycle en semaines) ou dans le groupe « repos » (cycle en jours).
        """
        if not self.active or self.leave(day) is not None:
            return None
        code = self.code(day)
        if code:
            return code
        if include_rest is None:
            include_rest = not self.h.get("jours_ouvres", True)
        if not include_rest:
            return None
        return self.week_shift(day) if self.cycle["unite"] == "semaine" else REPOS

    def groups(self, include_rest: bool | None = None) -> list[dict]:
        """Groupes comparables : les postes utilisés par le cycle, plus « repos » s'il y a lieu."""
        codes = self.cycle["jours"] if self.cycle["unite"] == "jour" else [c for w in self.cycle["semaines"] for c in w]
        used = [p for p in self.h["postes"] if p["id"] in codes]
        result = [{"id": p["id"], "nom": p["nom"], "debut": p["debut"], "fin": p["fin"]} for p in used]
        if include_rest is None:
            include_rest = not self.h.get("jours_ouvres", True)
        if include_rest and self.cycle["unite"] == "jour" and "" in codes:
            result.append({"id": REPOS, "nom": "Repos", "debut": None, "fin": None})
        return result

    def day(self, day: date) -> dict:
        """Ce que dit le planning d'un jour : poste et horaires, repos ou congés."""
        info: dict[str, Any] = {"date": day.isoformat(), "poste": None, "nom": None, "debut": None, "fin": None,
                                "repos": False, "conges": None, "actif": self.active}
        if not self.active:
            return info
        leave = self.leave(day)
        if leave is not None:
            info.update(conges=leave or "Congés", nom="Congés")
            return info
        code = self.code(day)
        if not code:
            info.update(repos=True, nom="Repos")
            return info
        poste = self.postes[code]
        info.update(poste=code, nom=poste["nom"], debut=poste["debut"], fin=poste["fin"])
        if self.cycle["unite"] == "semaine":
            info["semaine_cycle"] = self.week_index(day) + 1
        return info

    def label(self, group: str | None) -> str:
        if group == REPOS:
            return "Repos"
        poste = self.postes.get(group or "")
        return poste["nom"] if poste else "–"


def describe(horaires: dict, today: date | None = None) -> dict:
    """Résumé lisible (pour Claude et l'en-tête de l'interface)."""
    today = today or date.today()
    plan = Schedule(horaires)
    return {
        "modele": MODELES.get(horaires.get("modele"), horaires.get("modele")),
        "actif": plan.active,
        "postes": horaires["postes"],
        "aujourdhui": plan.day(today),
        "prochains_jours": [plan.day(today + timedelta(days=i)) for i in range(1, 8)],
        "conges_a_venir": [c for c in horaires.get("conges") or [] if c["au"] >= today.isoformat()][:5],
        "comparaison": "jours travaillés seulement" if horaires.get("jours_ouvres", True)
                       else "tous les jours (repos compris)",
    }


def with_effective(settings: dict) -> dict:
    """Copie des réglages où « horaires » est toujours rempli (et valide)."""
    result = copy.copy(settings)
    result["horaires"] = effective(settings)
    return result
