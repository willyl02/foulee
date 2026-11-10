"""Retours : où signaler un bug, proposer une idée ou poser une question.

Tout passe par les « issues » (sujets) GitHub du dépôt de Foulée : chaque sujet a sa page et sa
discussion, consultables par tous quand le dépôt est public, et l'auteur de Foulée reçoit un e-mail
de GitHub à chaque nouveau sujet. L'interface prépare le titre, le message et les informations
techniques, puis ouvre la page de GitHub : rien ne part sans un clic de l'utilisateur.

Une adresse e-mail s'y ajoute (CONTACT_EMAIL), pour qui n'a pas de compte GitHub. Elle est publiée
avec le code et l'installateur : c'est l'adresse que l'auteur a choisi d'afficher (novembre 2026), à
remplacer par une adresse dédiée avant une diffusion plus large. Vide : GitHub seulement.
"""

from __future__ import annotations

import threading
import time

import requests

from . import updates

CONTACT_EMAIL = "william.lequin@gmail.com"  # affichée dans le formulaire de retours (vide : GitHub seulement)
VISIBILITY_TTL = 3600      # on redemande à GitHub au plus une fois par heure
_cache: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def info() -> dict:
    """Adresses utiles : le dépôt, ses sujets, la page « nouveau sujet », l'e-mail éventuel."""
    repo = updates.repo()
    base = f"https://github.com/{repo}"
    return {"depot": repo, "url": base, "issues": f"{base}/issues", "nouveau": f"{base}/issues/new",
            "email": CONTACT_EMAIL.strip() or None}


def visibility(*, refresh: bool = False) -> str:
    """« public », « prive » (la page ne s'ouvre que pour les personnes invitées) ou « inconnu ».

    Sans jeton : on veut savoir ce que voit quelqu'un qui n'est pas invité. GitHub répond 404 pour un
    dépôt privé comme pour un dépôt qui n'existe pas.
    """
    repo = updates.repo()
    with _lock:
        cached = _cache.get(repo)
        if cached and not refresh and time.monotonic() - cached[1] < VISIBILITY_TTL:
            return cached[0]
    try:
        response = requests.get(f"{updates.API}/repos/{repo}", headers=updates._headers(None), timeout=6)
        if response.status_code == 200:
            state = "prive" if response.json().get("private") else "public"
        elif response.status_code == 404:
            state = "prive"
        else:  # limite de requêtes atteinte, panne : on redemandera plus tard
            state = "inconnu"
    except (requests.RequestException, ValueError):
        state = "inconnu"
    if state != "inconnu":
        with _lock:
            _cache[repo] = (state, time.monotonic())
    return state
