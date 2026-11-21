"""Mes séances de renfo : composées dans Foulée (par exemple avec les exercices conseillés pour rééquilibrer),
gardées dans la base du profil, et envoyées sur la montre (par le relais du club, s'il est relié) ou en
fichier .fit.

Une séance, telle que l'interface l'envoie et la garde :
    {"id": "…", "titre": "…", "consigne": "…", "echauffement": True, "etirements": True,
     "exercices": [{"nom": "Pont fessier", "series": 3, "reps": "15", "recup_s": 45}, …]}
« reps » se lit comme le dosage de la bibliothèque : « 15 », « 10 par jambe », « 8 à 12 », ou une durée « 30 s ».
Sur la montre, chaque série est une étape « jusqu'à la touche Lap » qui dit l'exercice et ses répétitions, puis la
récup ; une série en secondes est chronométrée.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from datetime import date
from typing import Any

from . import db, renfo

META_KEY = "renfo_mes_seances"
MAX_SESSIONS = 40
MAX_EXERCISES = 20
WARMUP = {"genre": "echauffement", "nom": "Échauffement", "repetitions": 1, "duree_min": 5.0,
          "note": "mobilité des hanches, montées de genoux, gainage léger"}
STRETCH = {"genre": "calme", "nom": "Étirements", "repetitions": 1, "duree_min": 5.0, "note": "doux, sans forcer"}


class SessionError(ValueError):
    pass


def _text(value: Any, size: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:size]


def parse_dosage(dosage: str) -> tuple[int, str]:
    """« 3 × 10 par jambe » → (3, « 10 par jambe ») ; sans « × » : 3 séries."""
    match = re.match(r"\s*(\d+)\s*[×x]\s*(.+)$", dosage or "")
    if not match:
        return 3, _text(dosage, 40)
    return int(match.group(1)), _text(match.group(2), 40)


def _seconds(reps: str) -> int | None:
    """« 30 s », « 30 à 45 s », « 45 sec » : une série chronométrée (la première valeur)."""
    match = re.match(r"^(\d+)(?:\s*à\s*\d+)?\s*(s|sec|secondes?)$", reps.strip(), re.I)
    return int(match.group(1)) if match else None


def _reps_note(reps: str) -> str:
    if not reps:
        return ""
    if re.match(r"^\d+(\s*à\s*\d+)?$", reps):
        return f"{reps} répétitions"
    return reps


def clean(raw: Any) -> dict:
    """Une séance lisible et bornée (titre, exercices…) ; l'identifiant est créé au besoin."""
    if not isinstance(raw, dict):
        raise SessionError("Séance illisible.")
    title = _text(raw.get("titre"), 80)
    if not title:
        raise SessionError("Donne un nom à ta séance (par exemple « Renfo arrière »).")
    exercises = []
    for item in (raw.get("exercices") or [])[:MAX_EXERCISES]:
        if not isinstance(item, dict) or not _text(item.get("nom"), 60):
            continue
        try:
            sets = max(1, min(10, int(item.get("series") or 1)))
        except (TypeError, ValueError):
            sets = 1
        try:
            rest = max(0, min(600, int(float(item.get("recup_s") or 0))))
        except (TypeError, ValueError):
            rest = 0
        exercises.append({"nom": _text(item.get("nom"), 60), "series": sets, "reps": _text(item.get("reps"), 40),
                          "recup_s": rest})
    if not exercises:
        raise SessionError("Ajoute au moins un exercice à ta séance.")
    ident = str(raw.get("id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,24}", ident):
        ident = secrets.token_urlsafe(8)
    return {"id": ident, "titre": title, "consigne": _text(raw.get("consigne"), 500),
            "echauffement": bool(raw.get("echauffement", True)), "etirements": bool(raw.get("etirements", True)),
            "exercices": exercises}


def to_item(session: dict, day: str | None = None) -> dict:
    """La séance au format des séances proposées (titre, sport, blocs, consigne) : pour la montre ou le .fit."""
    session = clean(session)
    blocks = [dict(WARMUP)] if session["echauffement"] else []
    for e in session["exercices"]:
        block: dict[str, Any] = {"genre": "corps", "nom": e["nom"], "repetitions": e["series"]}
        seconds = _seconds(e["reps"])
        if seconds:
            block["duree_min"] = round(seconds / 60, 2)
        else:
            block["libre"] = True  # jusqu'à la touche Lap : la série finie, on appuie
            note = _reps_note(e["reps"])
            if note:
                block["note"] = note
        if e["recup_s"]:
            block["recup_min"] = round(e["recup_s"] / 60, 2)
        blocks.append(block)
    if session["etirements"]:
        blocks.append(dict(STRETCH))
    return {"titre": session["titre"], "sport": "renfo", "blocs": blocks, "consigne": session["consigne"] or None,
            "date": day or date.today().isoformat()}


# ------------------------------------------------------------------ bibliothèque et séances gardées
def library() -> list[dict]:
    """Les exercices conseillés, famille par famille (ceux de « exercices pour rééquilibrer »)."""
    out = []
    for family, exercises in renfo.EXERCISE_LIBRARY.items():
        name, chain = renfo.CHAIN_FAMILIES[family][0], renfo.CHAIN_FAMILIES[family][1]
        out.append({"famille": family, "nom": name, "chaine": chain,
                    "exercices": [{"nom": n, "materiel": m, "dosage": d, "consigne": c,
                                   "series": parse_dosage(d)[0], "reps": parse_dosage(d)[1]}
                                  for n, m, d, c in exercises]})
    return out


def saved(conn: sqlite3.Connection) -> list[dict]:
    try:
        items = json.loads(db.get_meta(conn, META_KEY) or "[]")
    except ValueError:
        return []
    out = []
    for item in items if isinstance(items, list) else []:
        try:
            out.append(clean(item))
        except SessionError:
            continue
    return out


def save(conn: sqlite3.Connection, sessions: Any) -> list[dict]:
    if not isinstance(sessions, list):
        raise SessionError("Liste de séances illisible.")
    if len(sessions) > MAX_SESSIONS:
        raise SessionError(f"{MAX_SESSIONS} séances au plus : supprime celles qui ne servent plus.")
    cleaned = [clean(s) for s in sessions]
    db.set_meta(conn, META_KEY, json.dumps(cleaned, ensure_ascii=False))
    return cleaned
