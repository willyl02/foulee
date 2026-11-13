"""Le lien entre ce Foulée et le relais du club (coach et élèves).

Chaque profil peut se connecter à un relais : comme coach (il invite ses élèves) ou comme élève (il rejoint son
coach avec un code d'invitation). L'adresse du relais et le compte (identifiant, nom, rôle) sont gardés dans la
base du profil ; le jeton de session, lui, va dans le coffre, comme la clé Garmin, et ne repart jamais vers
l'interface ni vers Claude.

Le relais ne parle qu'en HTTPS (sauf sur la machine elle-même, pour les essais).
"""

from __future__ import annotations

import json
import logging
import platform
import sqlite3
from urllib.parse import urlsplit

import requests

from . import __version__, config, db, vault
from .relais import API_VERSION

log = logging.getLogger("foulee.coach")

TIMEOUT = 20
META_URL = "relais_adresse"
META_ACCOUNT = "relais_compte"
META_SINCE = "relais_relie_le"


class CoachError(RuntimeError):
    """Problème expliqué en français ; ``status`` = code HTTP du relais (0 : injoignable)."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


def clean_url(value: str | None) -> str:
    """« relais.mon-club.com » → « https://relais.mon-club.com » ; HTTPS obligatoire hors de la machine."""
    text = (value or "").strip().rstrip("/")
    if not text:
        raise ValueError("Indique l'adresse du relais (par exemple relais.mon-club.com).")
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    if not host or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Adresse du relais illisible : colle seulement son nom, par exemple relais.mon-club.com.")
    local = host in ("localhost", "127.0.0.1", "::1")
    if parts.scheme != "https" and not (parts.scheme == "http" and local):
        raise ValueError("Le relais doit être en HTTPS (adresse en https://).")
    path = parts.path.rstrip("/")
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}{path}"


def device_name() -> str:
    return f"Foulée {__version__} · {platform.node() or 'ordinateur'}"[:80]


# Transport HTTP, remplaçable dans les tests (le relais tourne alors dans le même processus)
def _send(method: str, url: str, *, headers: dict, payload: dict | None) -> tuple[int, dict]:
    response = requests.request(method, url, headers=headers, json=payload, timeout=TIMEOUT)
    try:
        data = response.json()
    except ValueError:
        data = {}
    return response.status_code, data if isinstance(data, dict) else {}


transport = _send


def call(base: str, method: str, path: str, *, token: str | None = None, payload: dict | None = None) -> dict:
    headers = {"Accept": "application/json", "X-Foulee-Version": __version__, "X-Foulee-Api": str(API_VERSION),
               "User-Agent": f"Foulee/{__version__}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        status, data = transport(method, f"{base}{path}", headers=headers, payload=payload)
    except requests.RequestException as exc:
        log.info("Relais injoignable (%s) : %s", base, exc)
        raise CoachError("Relais injoignable : vérifie l'adresse et ta connexion à Internet.") from None
    if status >= 400:
        detail = data.get("detail") if isinstance(data.get("detail"), str) else None
        if status == 404 and not detail:
            detail = "Cette adresse ne répond pas comme un relais Foulée."
        if status in (502, 503, 504, 530):
            detail = "Le relais ne répond pas pour l'instant (arrêté ou en cours de mise à jour) : réessaie plus tard."
        raise CoachError(detail or f"Le relais a refusé la demande (HTTP {status}).", status)
    return data


# ------------------------------------------------------------------ état local
def linked() -> bool:
    return bool(vault.get_secret("relais"))


def status(conn: sqlite3.Connection) -> dict:
    """État du lien, sans jamais le jeton."""
    if config.is_demo():
        return {"relie": False, "demo": True}
    raw = db.get_meta(conn, META_ACCOUNT)
    account = json.loads(raw) if raw else None
    url = db.get_meta(conn, META_URL)
    if not (account and url and linked()):
        return {"relie": False, "adresse": url}
    return {"relie": True, "adresse": url, "compte": account, "relie_le": db.get_meta(conn, META_SINCE)}


def light(conn: sqlite3.Connection) -> dict | None:
    """Ce que l'interface affiche dans la colonne : le rôle et le nom (ou None)."""
    info = status(conn)
    if not info.get("relie"):
        return None
    account = info["compte"]
    return {"role": account.get("role"), "nom": account.get("nom"), "coach": (account.get("coach") or {}).get("nom")}


def _save(conn: sqlite3.Connection, url: str, token: str, account: dict) -> None:
    vault.set_secret("relais", token)
    db.set_meta(conn, META_URL, url)
    db.set_meta(conn, META_ACCOUNT, json.dumps(_public(account), ensure_ascii=False))
    db.set_meta(conn, META_SINCE, db.now_iso())
    conn.commit()


def _public(account: dict) -> dict:
    keys = ("id", "identifiant", "nom", "role", "admin", "coach")
    return {key: account.get(key) for key in keys if key in account}


def forget(conn: sqlite3.Connection) -> None:
    vault.delete_secret("relais")
    for key in (META_ACCOUNT, META_SINCE):
        db.delete_meta(conn, key)
    conn.commit()  # l'adresse reste : on la repropose à la prochaine connexion


def _session(conn: sqlite3.Connection) -> tuple[str, str]:
    url, token = db.get_meta(conn, META_URL), vault.get_secret("relais")
    if not (url and token):
        raise CoachError("Ce profil n'est relié à aucun relais.", 401)
    return url, token


def _authed(conn: sqlite3.Connection, method: str, path: str, payload: dict | None = None) -> dict:
    url, token = _session(conn)
    try:
        return call(url, method, path, token=token, payload=payload)
    except CoachError as exc:
        if exc.status == 401:  # session fermée sur le relais (mot de passe changé, compte retiré…)
            forget(conn)
        raise


# ------------------------------------------------------------------ actions
def check_relay(url: str) -> dict:
    info = call(url, "GET", "/api/v1/sante")
    if info.get("service") != "foulee-relais":
        raise CoachError("Cette adresse ne répond pas comme un relais Foulée.")
    if int(info.get("api") or 0) != API_VERSION:
        raise CoachError("Ce relais n'a pas la même version que ton Foulée : mets à jour Foulée (ou le relais).")
    return info


def login(conn: sqlite3.Connection, url: str, ident: str, password: str) -> dict:
    url = clean_url(url)
    check_relay(url)
    data = call(url, "POST", "/api/v1/connexion",
                payload={"identifiant": ident, "mot_de_passe": password, "appareil": device_name()})
    _save(conn, url, data["jeton"], data["compte"])
    return status(conn)


def join(conn: sqlite3.Connection, url: str, *, code: str, ident: str, name: str, password: str) -> dict:
    url = clean_url(url)
    check_relay(url)
    data = call(url, "POST", "/api/v1/inscription",
                payload={"code": code, "identifiant": ident, "nom": name, "mot_de_passe": password,
                         "appareil": device_name()})
    _save(conn, url, data["jeton"], data["compte"])
    return status(conn)


def refresh(conn: sqlite3.Connection) -> dict:
    """Relit le compte sur le relais (nom du coach, rôle) ; une session fermée délie le profil."""
    data = _authed(conn, "GET", "/api/v1/moi")
    db.set_meta(conn, META_ACCOUNT, json.dumps(_public(data["compte"]), ensure_ascii=False))
    conn.commit()
    return status(conn)


def logout(conn: sqlite3.Connection) -> dict:
    try:
        url, token = _session(conn)
        call(url, "POST", "/api/v1/deconnexion", token=token)
    except CoachError:
        pass  # relais injoignable : on oublie quand même la session ici
    forget(conn)
    return status(conn)


def change_password(conn: sqlite3.Connection, current: str, new: str) -> None:
    _authed(conn, "POST", "/api/v1/moi/mot-de-passe", {"actuel": current, "nouveau": new})


def leave(conn: sqlite3.Connection, password: str) -> dict:
    _authed(conn, "POST", "/api/v1/moi/quitter", {"mot_de_passe": password})
    forget(conn)
    return status(conn)


def students(conn: sqlite3.Connection) -> list[dict]:
    return _authed(conn, "GET", "/api/v1/eleves")["eleves"]


def remove_student(conn: sqlite3.Connection, student_id: int) -> list[dict]:
    return _authed(conn, "DELETE", f"/api/v1/eleves/{int(student_id)}")["eleves"]


def invitations(conn: sqlite3.Connection) -> list[dict]:
    return _authed(conn, "GET", "/api/v1/invitations")["invitations"]


def create_invitation(conn: sqlite3.Connection) -> dict:
    return _authed(conn, "POST", "/api/v1/invitations")


def cancel_invitation(conn: sqlite3.Connection, code: str) -> list[dict]:
    safe = "".join(ch for ch in (code or "").upper() if ch.isalnum() or ch == "-")[:12]
    return _authed(conn, "DELETE", f"/api/v1/invitations/{safe}")["invitations"]
