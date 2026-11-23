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


# ------------------------------------------------------------------ séances toutes faites (l'Atelier)
# Des points de départ, à reprendre, modifier et enregistrer sous un autre nom. Les noms sont ceux des exercices
# conseillés (bibliothèque) : chacun se range du bon côté de l'équilibre avant / arrière. « 3 » séries est adapté
# au niveau des réglages (2 pour un débutant, 4 pour un confirmé) par l'interface.
def _ex(nom: str, reps: str, series: int = 3, recup_s: int = 45) -> dict:
    return {"nom": nom, "series": series, "reps": reps, "recup_s": recup_s}


TEMPLATES: list[dict] = [
    {"id": "tpl-express", "titre": "Renfo coureur express", "duree_min": 20,
     "pour": "Deux fois par semaine, après un footing ou à la maison : l'essentiel du coureur en 20 minutes.",
     "consigne": "Enchaîne sans traîner : la qualité d'exécution d'abord.",
     "exercices": [_ex("Pont fessier", "15"), _ex("Squat", "12"), _ex("Élévations des mollets sur une jambe", "15 par jambe"),
                   _ex("Bird dog", "10 par côté"), _ex("Planche", "30 s", recup_s=30)]},
    {"id": "tpl-arriere", "titre": "Chaîne postérieure", "duree_min": 30,
     "pour": "Fessiers, ischios, dos et mollets : ce qui manque le plus souvent aux coureurs.",
     "consigne": "Dos plat sur les mouvements de hanche ; descentes lentes.",
     "exercices": [_ex("Pont fessier sur une jambe", "10 par jambe"), _ex("Soulevé de terre roumain", "10"),
                   _ex("Rowing inversé", "10"), _ex("Superman", "10, tenir 3 s"),
                   _ex("Élévations des mollets genoux fléchis", "15")]},
    {"id": "tpl-gainage", "titre": "Gainage du coureur", "duree_min": 20,
     "pour": "Le bassin tenu à chaque foulée, et le dos qui ne s'affaisse pas en fin de course.",
     "consigne": "Respire pendant les maintiens ; arrête la série si le dos se creuse.",
     "exercices": [_ex("Planche", "45 s", recup_s=30), _ex("Dead bug", "10 par côté"), _ex("Bird dog", "10 par côté"),
                   _ex("Planche latérale", "30 s par côté", recup_s=30), _ex("Planche inversée", "30 s", recup_s=30)]},
    {"id": "tpl-pieds", "titre": "Pieds, chevilles et mollets", "duree_min": 20,
     "pour": "Tendon d'Achille, voûte plantaire et tibias : la prévention des blessures de fond.",
     "consigne": "Pieds nus si possible ; descentes en 3 secondes.",
     "exercices": [_ex("Élévations des mollets sur une jambe", "15 par jambe"),
                   _ex("Élévations des mollets genoux fléchis", "15"), _ex("Élévations des orteils", "20"),
                   _ex("Équilibre sur une jambe", "30 s par jambe", recup_s=30), _ex("Fente arrière", "10 par jambe")]},
    {"id": "tpl-trail", "titre": "Trail : cuisses et descentes", "duree_min": 30,
     "pour": "Quadriceps et fessiers pour encaisser les descentes et relancer en montée.",
     "consigne": "Genoux dans l'axe des pieds ; contrôle la descente de chaque répétition.",
     "exercices": [_ex("Squat", "15"), _ex("Fente arrière", "10 par jambe"), _ex("Step-up", "10 par jambe"),
                   _ex("Squat bulgare", "8 par jambe"), _ex("Chaise contre le mur", "45 s", recup_s=30),
                   _ex("Pont fessier", "15")]},
    {"id": "tpl-haut", "titre": "Haut du corps et posture", "duree_min": 25,
     "pour": "Le haut du dos et les épaules qui tiennent la posture quand la fatigue arrive.",
     "consigne": "Serre les omoplates sur les tirages ; corps gainé sur les pompes.",
     "exercices": [_ex("Rowing inversé", "12"), _ex("Pompes", "10"), _ex("Tirage horizontal à l'élastique", "15"),
                   _ex("Oiseau", "12"), _ex("Planche", "30 s", recup_s=30)]},
    {"id": "tpl-halteres", "titre": "Avec haltères", "duree_min": 35,
     "pour": "À la salle ou à la maison avec deux haltères : force de base pour courir plus solide.",
     "consigne": "Charge qui laisse 2 répétitions en réserve à la fin de chaque série.",
     "exercices": [_ex("Soulevé de terre roumain", "10", recup_s=60), _ex("Squat", "12 (goblet)", recup_s=60),
                   _ex("Rowing haltère un bras", "10 par bras"), _ex("Développé militaire", "10"),
                   _ex("Hip thrust", "10", recup_s=60), _ex("Planche", "45 s", recup_s=30)]},
]


def templates(settings: dict | None = None) -> list[dict]:
    """Les séances toutes faites, au niveau et au matériel des réglages (séries ; exercices sans le matériel)."""
    conf = renfo.settings_of(settings)
    series = renfo.LEVELS[conf["niveau"]][1]
    out = []
    for t in TEMPLATES:
        exercises = [{**e, "series": series if e["series"] == 3 else e["series"]} for e in t["exercices"]]
        missing = [e["nom"] for e in exercises if not renfo.has_gear(e["nom"], conf["materiel"])]
        out.append({**t, "exercices": exercises, "materiel_manquant": missing,
                    "echauffement": conf["echauffement"], "etirements": conf["etirements"]})
    return out


def composed_balance(session: Any, settings: dict | None = None) -> dict:
    """L'équilibre avant / arrière et les muscles d'une séance composée (les noms tels qu'écrits)."""
    items = (session or {}).get("exercices") if isinstance(session, dict) else None
    rows = []
    for e in items if isinstance(items, list) else []:
        name = _text((e or {}).get("nom"), 60) if isinstance(e, dict) else ""
        if not name:
            continue
        try:
            sets = max(1, min(10, int(e.get("series") or 1)))
        except (TypeError, ValueError):
            sets = 1
        rows.append({"category": "texte", "name": name, "sets": sets})
    target = renfo.target_of(settings)
    muscles: dict[str, float] = {}
    for r in rows:
        for muscle, weight in renfo.text_muscles(r["name"]).items():
            muscles[muscle] = muscles.get(muscle, 0.0) + r["sets"] * weight
    return {"equilibre": renfo.balance(rows, target), "cible": target,
            "muscles": [{"cle": m, "nom": renfo.MUSCLE_LABELS[m], "series": round(muscles[m], 1)}
                        for m, _ in renfo.MUSCLES if muscles.get(m)],
            "series": sum(r["sets"] for r in rows)}


def done_sessions(conn: sqlite3.Connection, limit: int = 12) -> list[dict]:
    """Les dernières séances de renfo faites (avec leurs exercices), à reprendre comme point de départ."""
    rows = conn.execute(
        "SELECT a.id, a.date, a.name, a.duration_s FROM activities a WHERE a.sport IN ('renfo', 'cardio') AND EXISTS "
        "(SELECT 1 FROM exercises e WHERE e.activity_id = a.id AND e.category NOT IN ('unknown', 'warm_up')) "
        "ORDER BY a.start_local DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        exercises = []
        for e in conn.execute("SELECT * FROM exercises WHERE activity_id = ? ORDER BY idx", (r["id"],)):
            e = dict(e)
            if e["category"] in ("unknown", "warm_up") or renfo.chain_family(e["category"], e["name"]) is None \
                    and e["category"] in renfo.LIGHT:
                continue
            info = renfo.describe(e)
            detail = info["detail"]
            if detail.get("mode") == "temps":
                reps = f"{detail['par_serie_s']} s"
            elif detail.get("par_serie"):
                reps = str(detail["par_serie"])
            else:
                reps = ""
            if info["charge_max_kg"]:
                reps = f"{reps} à {renfo._number(info['charge_max_kg'])} kg".strip()
            exercises.append({"nom": info["nom"][:60], "series": max(1, min(10, int(e["sets"] or 1))),
                              "reps": reps[:40], "recup_s": 45})
        if exercises:
            out.append({"id": r["id"], "date": r["date"], "nom": r["name"] or "Séance de renfo",
                        "duree_s": r["duration_s"], "exercices": exercises[:MAX_EXERCISES]})
    return out
