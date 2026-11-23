"""L'Atelier : les séances que je me compose moi-même, avec ou sans coach.

Deux sortes de séances :
- en blocs, pour la course et les autres sports d'endurance (échauffement, corps de séance répété avec sa récup,
  retour au calme ; en % de VMA, en zone de FC ou sans intensité) : le format des séances proposées par un coach,
  gardées ici dans la base du profil ;
- de renfo, exercice par exercice : voir renfo_seances.py (les mêmes séances que « Ma séance de renfo »).

On les reprend, on les modifie, on les enregistre sous un autre nom, et on les envoie sur la montre à la date
choisie : dans le calendrier Garmin Connect, par le relais du club (avec un compte élève relié, l'appli Garmin du
club), avec les allures calculées sur ma VMA ; sinon en fichier .fit, à copier sur la montre branchée en USB.

Une séance en blocs, telle que l'interface l'envoie et la garde :
    {"id": "…", "titre": "Seuil 3 × 10 min", "sport": "course", "consigne": "…",
     "blocs": [{"genre": "echauffement", "nom": "Échauffement", "duree_min": 20, "pct_vma": 65}, …]}
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from datetime import date
from typing import Any

from . import db

META_KEY = "atelier_seances"
MAX_SESSIONS = 60
SPORTS = ("course", "trail", "velo", "natation", "cardio", "souplesse", "marche", "rando", "autre")


class SessionError(ValueError):
    pass


def _text(value: Any, size: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:size]


def clean(raw: Any) -> dict:
    """Une séance en blocs lisible et bornée ; l'identifiant est créé au besoin."""
    from .relais.club import clean_blocks  # les règles des séances du coach (durées, % VMA, zones, récup)
    from .relais.store import RelayError

    if not isinstance(raw, dict):
        raise SessionError("Séance illisible.")
    title = _text(raw.get("titre"), 80)
    if not title:
        raise SessionError("Donne un nom à ta séance (par exemple « Seuil 3 × 10 min »).")
    sport = raw.get("sport") if raw.get("sport") in SPORTS else "course"
    try:
        blocks = clean_blocks(raw.get("blocs"))
    except RelayError as exc:
        raise SessionError(str(exc)) from None
    ident = str(raw.get("id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,24}", ident) or ident.startswith("ex-"):
        ident = secrets.token_urlsafe(8)
    return {"id": ident, "titre": title, "sport": sport, "consigne": _text(raw.get("consigne"), 1500),
            "blocs": blocks}


def to_item(session: Any, day: str | None = None) -> dict:
    """La séance au format des séances proposées (titre, sport, blocs, consigne, date) : pour la montre ou le .fit."""
    session = clean(session)
    return {"titre": session["titre"], "sport": session["sport"], "blocs": session["blocs"],
            "consigne": session["consigne"] or None, "date": day or date.today().isoformat()}


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
    titles = [s["titre"].lower() for s in cleaned]
    if len(set(titles)) != len(titles):
        raise SessionError("Deux de tes séances ont le même nom : donne-leur des noms différents.")
    db.set_meta(conn, META_KEY, json.dumps(cleaned, ensure_ascii=False))
    return cleaned


def next_day(days: list[int], today: date | None = None) -> str:
    """Le prochain jour choisi (1 = lundi … 7 = dimanche), aujourd'hui compris ; aujourd'hui sans jour choisi."""
    today = today or date.today()
    if not days:
        return today.isoformat()
    from datetime import timedelta

    for shift in range(7):
        day = today + timedelta(days=shift)
        if day.isoweekday() in days:
            return day.isoformat()
    return today.isoformat()
