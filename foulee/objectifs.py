"""Objectifs : un objectif principal et des objectifs secondaires (courses de préparation, autres rendez-vous).

L'objectif principal reste rangé sous ``objectif`` dans les réglages (le compte à rebours, l'allure cible,
la tuile des fractions rapides, ce que voit le coach en dépendent) ; les autres sous ``objectifs_secondaires``,
chacun avec son identifiant. Un objectif passé reste dans la liste : la vue « Objectifs » le range dans
« Passés », avec la séance du jour retrouvée (temps réalisé face au temps visé).

Pour comparer deux objectifs de distances différentes, l'équivalence de Riegel (T2 = T1 × (D2 / D1)^1,06) :
le temps visé sur un 10 km correspond à quel temps sur le semi ? Une estimation, pas une prédiction.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import date
from typing import Any

from . import analysis, metrics

MAX_SECONDARY = 30
RIEGEL = 1.06
PRINCIPAL = "principal"
RESULT_TOLERANCE = 0.25  # la séance du jour doit faire la distance de l'objectif à 25 % près
PLAUSIBLE_KMH = 26  # au-delà, « 1:25 » ne peut pas être des minutes:secondes : ce sont des heures:minutes
MAX_KMH = 30  # un temps visé plus rapide que ça n'est pas une faute de frappe qu'on corrige : on le signale


class GoalError(ValueError):
    """Objectif refusé, avec un message en français."""


def _hms(seconds: float | None) -> str | None:
    if not seconds:
        return None
    seconds = round(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def clean_goal(value: Any, *, keep_id: bool = False) -> dict:
    """Un objectif contrôlé : nom, date, distance, dénivelé, temps visé, note (tout est facultatif sauf le nom
    dès qu'autre chose est rempli)."""
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise GoalError("Objectif illisible.")
    name = str(value.get("nom") or "").strip()[:80]
    day = str(value.get("date") or "").strip()[:10]
    if day:
        try:
            date.fromisoformat(day)
        except ValueError:
            raise GoalError(f"Date de l'objectif illisible : « {day} » (AAAA-MM-JJ).") from None
    distance = value.get("distance_km")
    if distance in ("", None):
        distance = None
    else:
        try:
            distance = round(float(distance), 4)
        except (TypeError, ValueError):
            raise GoalError("Distance de l'objectif : un nombre de kilomètres.") from None
        if not 0.1 <= distance <= 1000:
            raise GoalError("Distance de l'objectif : entre 0,1 et 1 000 km.")
    climb = value.get("d_plus_m")
    if climb in ("", None):
        climb = None
    else:
        try:
            climb = round(float(climb))
        except (TypeError, ValueError):
            raise GoalError("Dénivelé positif : un nombre de mètres.") from None
        if not 0 <= climb <= 30000:
            raise GoalError("Dénivelé positif : entre 0 et 30 000 m.")
    target = str(value.get("temps_cible") or "").strip()[:10]
    if target:
        seconds = target_seconds(target, distance)
        if seconds is None:
            raise GoalError("Temps visé illisible : h:mm:ss, par exemple 1:25:00 (ou mm:ss : 38:30).")
        if distance and distance * 3600 / seconds > MAX_KMH:
            raise GoalError(f"Temps visé trop rapide pour {distance:g} km : vérifie-le (h:mm:ss).")
        target = _hms(seconds)
    note = str(value.get("note") or "").strip()[:200]
    if not name and (day or distance or target):
        raise GoalError("Donne un nom à l'objectif (la course, l'épreuve…).")
    goal = {"nom": name, "date": day, "distance_km": distance, "temps_cible": target, "d_plus_m": climb,
            "note": note}
    if keep_id:
        goal["id"] = re.sub(r"[^a-z0-9]", "", str(value.get("id") or "").lower())[:16] or uuid.uuid4().hex[:8]
    return goal


def target_seconds(text: str, distance_km: float | None = None) -> int | None:
    """« 1:25:00 » → 5100 s ; « 38:30 » → 2310 s. Deux nombres se lisent minutes:secondes, sauf si l'allure
    devient impossible pour la distance : « 1:25 » sur un semi, c'est 1 h 25."""
    text = str(text or "").strip()
    if not re.fullmatch(r"\d{1,3}(:\d{1,2}){1,2}", text):
        return None
    seconds = analysis.parse_hms(text)
    if not seconds:
        return None
    if text.count(":") == 1 and distance_km and distance_km * 3600 / seconds > PLAUSIBLE_KMH:
        seconds *= 60
    return seconds


def clean_secondaries(value: Any) -> list[dict]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise GoalError("Objectifs secondaires : une liste.")
    goals, seen = [], set()
    for raw in value[:MAX_SECONDARY]:
        goal = clean_goal(raw, keep_id=True)
        if not goal["nom"]:
            continue
        while goal["id"] in seen:
            goal["id"] = uuid.uuid4().hex[:8]
        seen.add(goal["id"])
        goals.append(goal)
    return goals


def riegel(seconds: float, from_km: float, to_km: float) -> float:
    return seconds * (to_km / from_km) ** RIEGEL


def describe(goal: dict | None, settings: dict, today: date | None = None) -> dict | None:
    """Un objectif tel que l'interface le montre : compte à rebours, allure cible, part de la VMA."""
    goal = goal or {}
    if not goal.get("nom"):
        return None
    today = today or date.today()
    out: dict[str, Any] = {k: goal.get(k) for k in ("id", "nom", "date", "distance_km", "temps_cible", "d_plus_m",
                                                    "note")}
    if goal.get("date"):
        try:
            left = (date.fromisoformat(goal["date"]) - today).days
            out.update(jours_restants=left, semaines_restantes=round(left / 7, 1),
                       statut="a_venir" if left > 0 else "jour_j" if left == 0 else "passe")
        except ValueError:
            out["statut"] = "sans_date"
    else:
        out["statut"] = "sans_date"
    seconds = analysis.parse_hms(goal.get("temps_cible") or "")
    distance = float(goal.get("distance_km") or 0)
    if seconds and distance:
        speed = distance * 1000 / seconds
        vma = float(settings.get("vma_kmh") or 16)
        out.update(vitesse_cible=round(speed, 3), allure_cible=metrics.fmt_pace(speed),
                   vitesse_cible_kmh=round(speed * 3.6, 2), pct_vma=round(speed * 3.6 / vma * 100, 1))
    return out


def find_result(conn: sqlite3.Connection, goal: dict) -> dict | None:
    """La séance du jour de l'objectif : celle dont la distance colle le mieux (course ou trail d'abord)."""
    if not goal.get("date"):
        return None
    rows = conn.execute("SELECT id, name, sport, distance_m, duration_s, moving_s, avg_speed, elev_gain_m "
                        "FROM activities WHERE date = ? AND distance_m > 0", (goal["date"],)).fetchall()
    if not rows:
        return None
    wanted = float(goal.get("distance_km") or 0) * 1000

    def score(row) -> tuple:
        running = row["sport"] in metrics.RUNNING_SPORTS
        gap = abs(row["distance_m"] - wanted) / wanted if wanted else 0.0
        return (not running, gap, -(row["distance_m"] or 0))

    best = min(rows, key=score)
    if wanted and abs(best["distance_m"] - wanted) / wanted > RESULT_TOLERANCE:
        return None
    if not wanted and best["sport"] not in metrics.RUNNING_SPORTS:
        return None
    seconds = best["duration_s"] or best["moving_s"]
    out = {"seance_id": best["id"], "nom": best["name"], "distance_km": round(best["distance_m"] / 1000, 2),
           "duree_s": round(seconds) if seconds else None, "temps": _hms(seconds),
           "allure": metrics.fmt_pace(best["distance_m"] / seconds) if seconds else None,
           "d_plus_m": round(best["elev_gain_m"]) if best["elev_gain_m"] else None}
    target = analysis.parse_hms(goal.get("temps_cible") or "")
    if target and seconds:
        # Une course plus longue ou plus courte que prévu : on compare à distance égale (Riegel)
        expected = riegel(target, wanted / 1000, best["distance_m"] / 1000) if wanted else target
        out["ecart_s"] = round(seconds - expected)
    return out


def _equivalent(goal: dict, principal: dict | None, seconds: float | None = None,
                distance_km: float | None = None) -> dict | None:
    """Le temps visé (ou réalisé) d'un objectif ramené à la distance de l'objectif principal (Riegel)."""
    if not principal or principal.get("id") == goal.get("id"):
        return None
    to_km = float(principal.get("distance_km") or 0)
    from_km = float(distance_km or goal.get("distance_km") or 0)
    seconds = seconds or analysis.parse_hms(goal.get("temps_cible") or "")
    if not (seconds and from_km and to_km) or abs(from_km - to_km) < 0.05 or not 0.2 <= from_km / to_km <= 5:
        return None
    if goal.get("d_plus_m") and goal["d_plus_m"] > 25 * from_km or \
            principal.get("d_plus_m") and principal["d_plus_m"] > 25 * to_km:
        return None  # trail vallonné : Riegel ne tient pas compte du dénivelé
    eq = riegel(seconds, from_km, to_km)
    out = {"temps": _hms(eq), "duree_s": round(eq), "vers": principal.get("nom")}
    target = analysis.parse_hms(principal.get("temps_cible") or "")
    if target:
        out["ecart_s"] = round(eq - target)  # négatif : plus rapide que le temps visé au principal
    return out


def _calendar_races(conn: sqlite3.Connection, known: list[dict], today: date) -> list[dict]:
    """Les courses à venir du calendrier qui ne sont pas encore des objectifs : à ajouter d'un clic."""
    from . import calendrier

    if not calendrier.ready(conn):
        return []
    taken = {(g.get("date"), _fold(g.get("nom"))) for g in known}
    dates = {g.get("date") for g in known}
    out = []
    for row in conn.execute("SELECT date, title, location FROM calendar_events WHERE kind = 'course' AND date >= ? "
                            "ORDER BY date LIMIT 12", (today.isoformat(),)):
        name = re.sub(r"^\s*course\s*[—–:-]+\s*", "", row["title"] or "", flags=re.IGNORECASE).strip() or row["title"]
        if (row["date"], _fold(name)) in taken or row["date"] in dates:
            continue
        out.append({"date": row["date"], "nom": name[:80], "lieu": row["location"],
                    "distance_km": guess_distance(name), "dans_jours": (date.fromisoformat(row["date"]) - today).days})
    return out


def _fold(text: Any) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def guess_distance(title: str) -> float | None:
    """« 10 km de Reims » → 10 ; « Semi de Paris » → 21,0975 ; « Marathon » → 42,195."""
    text = _fold(title)
    if re.search(r"\bsemi\b|half", text):
        return 21.0975
    if re.search(r"\bmarathon\b", text):
        return 42.195
    match = re.search(r"\b(\d{1,3})(?:[ .,](\d{1,3}))?\s*(?:km|k)\b", text)
    if match:
        value = float(f"{match.group(1)}.{match.group(2)}" if match.group(2) else match.group(1))
        return value if 0.4 <= value <= 400 else None
    return None


def overview(conn: sqlite3.Connection, settings: dict, today: date | None = None) -> dict:
    """La page « Objectifs » : le principal, les secondaires à venir, les passés (avec le résultat), et les
    courses du calendrier qui pourraient en devenir."""
    today = today or date.today()
    principal_raw = dict(settings.get("objectif") or {})
    principal_raw["id"] = PRINCIPAL
    principal = describe(principal_raw, settings, today)
    secondaries = [describe(g, settings, today) for g in settings.get("objectifs_secondaires") or []]
    secondaries = [g for g in secondaries if g]
    upcoming = sorted([g for g in secondaries if g["statut"] != "passe"],
                      key=lambda g: (g.get("date") or "9999", g["nom"]))
    past = sorted([g for g in secondaries if g["statut"] == "passe"], key=lambda g: g["date"], reverse=True)
    if principal and principal["statut"] == "passe":
        past = sorted([principal, *past], key=lambda g: g["date"], reverse=True)
    for goal in upcoming:
        goal["equivalence"] = _equivalent(goal, principal)
        if principal and principal.get("date") and goal.get("date") and principal["statut"] != "passe":
            gap = (date.fromisoformat(principal["date"]) - date.fromisoformat(goal["date"])).days
            goal["avant_principal_jours"] = gap if gap > 0 else None
    for goal in past:
        goal["resultat"] = find_result(conn, goal)
        res = goal["resultat"]
        if res and res.get("duree_s") and principal and principal["statut"] != "passe":
            goal["equivalence"] = _equivalent(goal, principal, res["duree_s"], res["distance_km"])
    known = [g for g in [principal, *secondaries] if g]
    return {
        "principal": principal if principal and principal["statut"] != "passe" else None,
        "principal_passe": principal if principal and principal["statut"] == "passe" else None,
        "secondaires": upcoming,
        "passes": past[:20],
        "calendrier": _calendar_races(conn, known, today),
        "suivant": upcoming[0]["id"] if upcoming and principal and principal["statut"] == "passe" else None,
        "vma_kmh": settings.get("vma_kmh"),
    }


# ----------------------------------------------------------------- modifications
EMPTY = {"nom": "", "date": "", "distance_km": None, "temps_cible": "", "d_plus_m": None, "note": ""}


def _lists(settings: dict) -> tuple[dict, list[dict]]:
    raw = {k: v for k, v in (settings.get("objectif") or {}).items() if k != "id"}
    try:
        principal = clean_goal(raw)
    except GoalError:  # objectif enregistré par une ancienne version, sans contrôle : on garde ce qui se lit
        principal = {**EMPTY, "nom": str(raw.get("nom") or "")[:80]}
    return principal, [dict(g) for g in settings.get("objectifs_secondaires") or []]


def add(settings: dict, payload: dict) -> dict:
    """Nouvel objectif ; ``principal`` vrai : il devient l'objectif principal (l'ancien passe en secondaire)."""
    principal, others = _lists(settings)
    goal = clean_goal(payload, keep_id=True)
    if not goal["nom"]:
        raise GoalError("Donne un nom à l'objectif (la course, l'épreuve…).")
    goal["id"] = uuid.uuid4().hex[:8]
    if payload.get("principal"):
        if principal["nom"]:
            others.append({**principal, "id": uuid.uuid4().hex[:8]})
        principal = {k: v for k, v in goal.items() if k != "id"}
    else:
        if len(others) >= MAX_SECONDARY:
            raise GoalError(f"{MAX_SECONDARY} objectifs secondaires au plus : retire d'abord les plus anciens.")
        others.append(goal)
    return {"objectif": principal, "objectifs_secondaires": clean_secondaries(others)}


def update(settings: dict, goal_id: str, payload: dict) -> dict:
    principal, others = _lists(settings)
    if goal_id == PRINCIPAL:
        goal = clean_goal(payload)
        if not goal["nom"]:
            raise GoalError("Donne un nom à l'objectif (la course, l'épreuve…).")
        return {"objectif": goal, "objectifs_secondaires": others}
    for i, g in enumerate(others):
        if g.get("id") == goal_id:
            goal = clean_goal({**payload, "id": goal_id}, keep_id=True)
            if not goal["nom"]:
                raise GoalError("Donne un nom à l'objectif (la course, l'épreuve…).")
            others[i] = goal
            return {"objectif": principal, "objectifs_secondaires": clean_secondaries(others)}
    raise LookupError("Objectif introuvable.")


def remove(settings: dict, goal_id: str) -> dict:
    principal, others = _lists(settings)
    if goal_id == PRINCIPAL:
        return {"objectif": dict(EMPTY), "objectifs_secondaires": others}
    kept = [g for g in others if g.get("id") != goal_id]
    if len(kept) == len(others):
        raise LookupError("Objectif introuvable.")
    return {"objectif": principal, "objectifs_secondaires": kept}


def promote(settings: dict, goal_id: str) -> dict:
    """Un objectif secondaire devient le principal ; l'ancien principal rejoint les secondaires (ou les passés)."""
    principal, others = _lists(settings)
    chosen = next((g for g in others if g.get("id") == goal_id), None)
    if chosen is None:
        raise LookupError("Objectif introuvable.")
    others = [g for g in others if g.get("id") != goal_id]
    if principal["nom"]:
        others.append({**principal, "id": uuid.uuid4().hex[:8]})
    return {"objectif": {k: v for k, v in chosen.items() if k != "id"},
            "objectifs_secondaires": clean_secondaries(others)}


def shared(settings: dict, today: date | None = None) -> list[dict]:
    """Les objectifs secondaires à venir, pour le coach (sans la note, qui reste personnelle)."""
    today = today or date.today()
    out = []
    for g in settings.get("objectifs_secondaires") or []:
        if g.get("nom") and g.get("date") and g["date"] >= today.isoformat():
            out.append({k: g.get(k) for k in ("nom", "date", "distance_km", "temps_cible", "d_plus_m")})
    return sorted(out, key=lambda g: g["date"])[:10]
