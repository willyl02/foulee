"""Envoyer les séances du coach sur la montre des élèves : la Training API de Garmin, par le relais.

Le relais est « l'application Foulée » inscrite au programme développeur de Garmin (Connect Developer –
Starter). Son Client Secret ne quitte jamais la machine du relais (``foulee relais garmin`` l'y range, dans
un fichier que seul Foulée lit) : ni le dépôt, ni les Foulée des élèves ne le connaissent.

Le parcours d'un élève :
1. « Envoyer sur ma montre » : s'il n'est pas encore relié, le relais prépare l'autorisation (OAuth 2.0 avec
   PKCE) et renvoie l'adresse de Garmin ; l'élève s'y connecte, chez Garmin, et accepte. Il ne tape jamais son
   mot de passe Garmin ailleurs que chez Garmin.
2. Garmin le renvoie sur ``/garmin/retour`` : le relais échange le code contre ses jetons, les range
   **chiffrés** dans sa base (la clé est à part, dans le dossier des secrets), et envoie aussitôt la séance
   qui attendait.
3. Les fois suivantes, la séance part directement : créée dans son compte Garmin Connect, planifiée à sa date
   (aujourd'hui si elle est passée) ; la montre la récupère à sa synchro.

Le coach peut aussi l'envoyer pour l'élève, si celui-ci l'a permis (c'est le réglage par défaut une fois
relié). Une séance renvoyée remplace la précédente ; une séance supprimée par le coach disparaît du calendrier
Garmin. Délier (ou quitter le groupe) retire l'autorisation chez Garmin et efface les jetons du relais.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import logging
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit

import requests

from .. import garmin_training, vault
from ..workout_fit import WorkoutError
from . import store

log = logging.getLogger("foulee.relais.garmin")

AUTHORIZE_URL = "https://connect.garmin.com/oauth2Confirm"
TOKEN_URL = "https://connectapi.garmin.com/di-oauth2-service/oauth/token"   # selon la note PKCE de Garmin
API_URL = "https://apis.garmin.com"
CALLBACK_PATH = "/garmin/retour"
PENDING_MINUTES = 15          # le temps de s'identifier chez Garmin et d'accepter
REFRESH_MARGIN = 600          # Garmin : renouveler le jeton au moins 10 minutes avant qu'il expire
TIMEOUT = 20
PERMISSION = "WORKOUT_IMPORT"



class GarminError(store.RelayError):
    """Refus expliqué en français ; ``status`` : le code HTTP à renvoyer à Foulée."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class NeedLink(Exception):
    """L'élève doit (re)lier son compte Garmin : ``url`` est l'adresse d'autorisation de Garmin."""

    def __init__(self, url: str, reason: str = "") -> None:
        super().__init__(reason or "Relie ton compte Garmin Connect.")
        self.url = url
        self.reason = reason


# ------------------------------------------------------------------ réglages
def _url(name: str, default: str) -> str:
    return (os.environ.get(name) or default).rstrip("/")


def app_settings() -> dict | None:
    """L'appli Garmin du club (Client ID, Client Secret, adresse publique du relais), si elle est réglée."""
    raw = vault.get_secret("relais-garmin-appli")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not all(data.get(k) for k in ("client_id", "client_secret", "adresse")):
        return None
    return data


def clean_address(value: str | None) -> str:
    """« relais.mon-club.com » → « https://relais.mon-club.com » (HTTPS : Garmin l'exige)."""
    text = (value or "").strip().rstrip("/")
    if text.endswith(CALLBACK_PATH):
        text = text[: -len(CALLBACK_PATH)]
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment or parts.username:
        raise GarminError("Adresse publique du relais illisible : par exemple https://relais.mon-club.com")
    port = f":{parts.port}" if parts.port else ""
    return f"https://{parts.hostname.lower()}{port}{parts.path.rstrip('/')}"


def save_app(client_id: str, client_secret: str, address: str) -> dict:
    client_id, client_secret = (client_id or "").strip(), (client_secret or "").strip()
    if not client_id or len(client_id) > 200 or not client_secret or len(client_secret) > 500:
        raise GarminError("Client ID ou Client Secret manquant.")
    data = {"client_id": client_id, "client_secret": client_secret, "adresse": clean_address(address)}
    vault.set_secret("relais-garmin-appli", json.dumps(data))
    return {"client_id": client_id, "adresse": data["adresse"], "retour": redirect_uri(data)}


def redirect_uri(settings: dict) -> str:
    return settings["adresse"] + CALLBACK_PATH


def configured() -> bool:
    return app_settings() is not None


def _settings() -> dict:
    settings = app_settings()
    if settings is None:
        raise GarminError("L'envoi vers les montres n'est pas encore branché sur ce relais : son administrateur doit "
                          "y enregistrer l'appli Garmin du club (commande « foulee relais garmin »).", 503)
    return settings


# ------------------------------------------------------- chiffrement des jetons
def _cipher():
    from cryptography.fernet import Fernet

    key = vault.get_secret("relais-garmin-cle")
    if not key:
        key = Fernet.generate_key().decode()
        vault.set_secret("relais-garmin-cle", key)
    return Fernet(key.encode())


def _seal(tokens: dict) -> str:
    return _cipher().encrypt(json.dumps(tokens).encode()).decode()


def _open(sealed: str) -> dict | None:
    from cryptography.fernet import InvalidToken

    try:
        return json.loads(_cipher().decrypt(sealed.encode()))
    except (InvalidToken, ValueError):
        return None


# ------------------------------------------------------------- appels à Garmin
def _http(method: str, url: str, *, headers: dict, form: dict | None = None,
          body: Any = None) -> tuple[int, Any]:
    response = requests.request(method, url, headers=headers, data=form, json=body, timeout=TIMEOUT)
    try:
        data = response.json() if response.content else None
    except ValueError:
        data = response.text[:300]
    return response.status_code, data


transport = _http  # remplacé par un faux Garmin dans les tests


def _call(method: str, url: str, **kwargs) -> tuple[int, Any]:
    try:
        return transport(method, url, **kwargs)
    except requests.RequestException as exc:
        log.warning("Garmin injoignable : %s", exc)
        raise GarminError("Garmin ne répond pas pour l'instant : réessaie dans quelques minutes.", 502) from None


def _token_request(params: dict) -> dict:
    settings = _settings()
    status, data = _call("POST", _url("FOULEE_GARMIN_TOKEN_URL", TOKEN_URL),
                         headers={"Accept": "application/json"},
                         form={**params, "client_id": settings["client_id"], "client_secret": settings["client_secret"]})
    if status >= 400 or not isinstance(data, dict) or not data.get("access_token"):
        reason = _reason(data)
        log.warning("Jetons Garmin refusés (HTTP %s) %s", status, reason)
        hint = (" L'appli Garmin enregistrée sur le relais (Client ID ou Client Secret) ne correspond pas à celle du "
                "portail : son administrateur peut le vérifier avec « foulee relais garmin tester »."
                if status == 401 or "client" in reason.lower() else "")
        raise GarminError(f"Garmin a refusé l'autorisation (HTTP {status}{' : ' + reason if reason else ''}).{hint}",
                          401 if status in (400, 401) else 502)
    stamp = datetime.now().timestamp()
    return {"access": data["access_token"], "refresh": data.get("refresh_token"),
            "expire": stamp + int(data.get("expires_in") or 86400),
            "refresh_expire": stamp + int(data.get("refresh_token_expires_in") or 90 * 86400)}


def _reason(data: Any) -> str:
    """Le motif d'un refus de Garmin (« invalid_client »…), jamais rien d'autre de sa réponse."""
    if isinstance(data, dict):
        text = " ".join(str(data.get(k) or "") for k in ("error", "error_description", "message")).strip()
    else:
        text = str(data or "").strip()
    return " ".join(text.split())[:160]


def check_app() -> dict:
    """« foulee relais garmin tester » : Garmin reconnaît-il le Client ID et le Client Secret enregistrés ?

    On demande un jeton avec un jeton de renouvellement bidon : des identifiants faux sont refusés comme tels
    (401, invalid_client) ; des identifiants justes, pour le jeton seulement (400, invalid_grant)."""
    settings = _settings()
    status, data = _call("POST", _url("FOULEE_GARMIN_TOKEN_URL", TOKEN_URL), headers={"Accept": "application/json"},
                         form={"grant_type": "refresh_token", "refresh_token": "essai-foulee",
                               "client_id": settings["client_id"], "client_secret": settings["client_secret"]})
    reason = _reason(data)
    ok = status != 401 and "client" not in reason.lower()
    return {"ok": ok, "http": status, "motif": reason, "client_id": settings["client_id"],
            "secret": len(settings["client_secret"]), "retour": redirect_uri(settings)}


def _api(method: str, path: str, access: str, body: Any = None) -> tuple[int, Any]:
    return _call(method, _url("FOULEE_GARMIN_API_URL", API_URL) + path,
                 headers={"Authorization": f"Bearer {access}", "Accept": "application/json"}, body=body)


# --------------------------------------------------------------- autorisation
def _verifier() -> str:
    return secrets.token_urlsafe(72)[:96]  # 43 à 128 caractères : lettres, chiffres, « - » et « _ »


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def authorize_url(conn: sqlite3.Connection, account_id: int, proposal_id: int | None = None,
                  vma: float | None = None) -> str:
    """Prépare l'autorisation (et la séance qui attend), et renvoie l'adresse de Garmin."""
    settings = _settings()
    limit = (store.local_now() - timedelta(minutes=PENDING_MINUTES)).isoformat(sep=" ")
    conn.execute("DELETE FROM garmin_attentes WHERE cree_le < ? OR compte_id = ?", (limit, account_id))
    state, verifier = secrets.token_urlsafe(24), _verifier()
    conn.execute("INSERT INTO garmin_attentes(etat, compte_id, verificateur, proposition_id, vma_kmh, cree_le) "
                 "VALUES (?,?,?,?,?,?)", (state, account_id, verifier, proposal_id, vma, store.now()))
    query = {"response_type": "code", "client_id": settings["client_id"], "code_challenge": _challenge(verifier),
             "code_challenge_method": "S256", "redirect_uri": redirect_uri(settings), "state": state}
    return f"{_url('FOULEE_GARMIN_AUTHORIZE_URL', AUTHORIZE_URL)}?{urlencode(query)}"


def link_row(conn: sqlite3.Connection, account_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM garmin_liens WHERE compte_id = ?", (account_id,)).fetchone()


def _store_tokens(conn: sqlite3.Connection, account_id: int, tokens: dict) -> None:
    conn.execute("UPDATE garmin_liens SET jetons = ? WHERE compte_id = ?", (_seal(tokens), account_id))
    conn.commit()  # un jeton de renouvellement ne sert qu'une fois : le nouveau ne doit pas se perdre


def _access(conn: sqlite3.Connection, account_id: int, *, force: bool = False) -> str:
    """Un jeton d'accès valable (renouvelé s'il expire bientôt). Sans lien utilisable : NeedLink."""
    row = link_row(conn, account_id)
    tokens = _open(row["jetons"]) if row else None
    if not tokens:
        if row:
            forget(conn, account_id)
        raise NeedLink(authorize_url(conn, account_id))
    if force or tokens["expire"] - REFRESH_MARGIN <= datetime.now().timestamp():
        try:
            tokens = _token_request({"grant_type": "refresh_token", "refresh_token": tokens.get("refresh") or ""})
        except GarminError as exc:
            if exc.status != 401:
                raise
            forget(conn, account_id)  # autorisation retirée chez Garmin, ou plus de 90 jours sans envoi
            raise NeedLink(authorize_url(conn, account_id),
                           "Ton autorisation Garmin a expiré ou a été retirée : relie à nouveau ton compte.") from None
        _store_tokens(conn, account_id, tokens)
    return tokens["access"]


def complete(conn: sqlite3.Connection, state: str | None, code: str | None, error: str | None) -> dict:
    """Retour de Garmin (après « Accepter » ou « Refuser ») : relie le compte, puis envoie la séance qui attendait.

    Renvoie ce que la page de retour affiche : {"ok", "titre", "texte"}.
    """
    pending = conn.execute("SELECT * FROM garmin_attentes WHERE etat = ?", (state or "",)).fetchone() \
        if state else None
    limit = (store.local_now() - timedelta(minutes=PENDING_MINUTES)).isoformat(sep=" ")
    if pending is None or pending["cree_le"] < limit:
        return {"ok": False, "titre": "Lien expiré",
                "texte": "Cette autorisation a expiré ou a déjà servi. Reviens dans Foulée et clique de nouveau sur "
                         "« Envoyer sur ma montre »."}
    conn.execute("DELETE FROM garmin_attentes WHERE etat = ?", (pending["etat"],))
    if error or not code:
        return {"ok": False, "titre": "Compte Garmin non relié",
                "texte": "Tu as refusé l'accès chez Garmin : rien n'a été relié, rien n'a été envoyé. Tu pourras le "
                         "faire plus tard depuis « Envoyer sur ma montre »."}
    account_id = pending["compte_id"]
    tokens = _token_request({"grant_type": "authorization_code", "code": code,
                             "code_verifier": pending["verificateur"], "redirect_uri": redirect_uri(_settings())})
    status, data = _api("GET", "/wellness-api/rest/user/id", tokens["access"])
    user = str((data or {}).get("userId") or "") if isinstance(data, dict) else ""
    if status >= 400 or not user:
        raise GarminError(f"Garmin n'a pas donné ton identifiant (HTTP {status}) : réessaie dans un instant.", 502)
    status, granted = _api("GET", "/wellness-api/rest/user/permissions", tokens["access"])
    if status < 400 and isinstance(granted, list) and PERMISSION not in granted:
        _api("DELETE", "/wellness-api/rest/user/registration", tokens["access"])
        return {"ok": False, "titre": "Autorisation incomplète",
                "texte": "Garmin n'a pas donné à Foulée le droit d'ajouter des entraînements à ton compte. "
                         "Recommence depuis « Envoyer sur ma montre », et laisse cochée l'autorisation des "
                         "entraînements (« Workout import ») sur la page de Garmin."}
    # Un compte Garmin ne se relie qu'à un seul compte du relais : l'ancien lien est remplacé
    conn.execute("DELETE FROM garmin_liens WHERE garmin_user = ? AND compte_id != ?", (user, account_id))
    conn.execute("INSERT INTO garmin_liens(compte_id, garmin_user, jetons, relie_le) VALUES (?,?,?,?) "
                 "ON CONFLICT(compte_id) DO UPDATE SET garmin_user = excluded.garmin_user, jetons = excluded.jetons, "
                 "relie_le = excluded.relie_le", (account_id, user, _seal(tokens), store.now()))
    conn.commit()
    log.info("Compte %s relié à Garmin", account_id)
    done = {"ok": True, "titre": "Compte Garmin relié",
            "texte": "C'est fait : les prochaines séances partiront directement sur ta montre."}
    if pending["proposition_id"]:
        row = conn.execute("SELECT * FROM propositions WHERE id = ? AND eleve_id = ?",
                           (pending["proposition_id"], account_id)).fetchone()
        if row is not None:
            try:
                sent = send(conn, row, pending["vma_kmh"], by="eleve")
            except (GarminError, NeedLink, WorkoutError) as exc:
                done["texte"] += f" La séance « {row['titre']} » n'est pas partie : {exc} Réessaie depuis Foulée."
            else:
                done["texte"] = (f"Ton compte est relié, et la séance « {row['titre']} » est dans ton calendrier "
                                 f"Garmin Connect pour le {_day_label(sent['date'])}. Synchronise ta montre "
                                 f"(appli Garmin Connect ouverte) : elle l'y trouvera.")
    return done


def forget(conn: sqlite3.Connection, account_id: int) -> None:
    conn.execute("DELETE FROM garmin_liens WHERE compte_id = ?", (account_id,))
    conn.execute("DELETE FROM garmin_envois WHERE compte_id = ?", (account_id,))


def unlink(conn: sqlite3.Connection, account_id: int) -> None:
    """Délier : l'autorisation est retirée chez Garmin (si Garmin répond), et les jetons effacés du relais."""
    row = link_row(conn, account_id)
    if row is None:
        return
    tokens = _open(row["jetons"])
    if tokens and configured():
        try:
            access = _access(conn, account_id)
            _api("DELETE", "/wellness-api/rest/user/registration", access)
        except (GarminError, NeedLink) as exc:
            log.info("Retrait chez Garmin impossible pour %s : %s", account_id, exc)
    forget(conn, account_id)
    log.info("Compte %s délié de Garmin", account_id)


def unlink_all(conn: sqlite3.Connection, account_id: int) -> None:
    """Avant d'effacer un compte (et, pour un coach, ses élèves) : chacun est délié de Garmin."""
    ids = [account_id] + [r["id"] for r in conn.execute("SELECT id FROM comptes WHERE coach_id = ?", (account_id,))]
    for linked in ids:
        if link_row(conn, linked) is not None:
            unlink(conn, linked)


# ---------------------------------------------------------------------- envoi
def _day_label(day: str) -> str:
    months = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
              "novembre", "décembre")
    value = date.fromisoformat(day)
    return f"{value.day} {months[value.month - 1]}"


def _item(row: sqlite3.Row) -> dict:
    content = json.loads(row["contenu"])
    return {"id": row["id"], "date": row["date"], "titre": row["titre"], "sport": row["sport"],
            "blocs": content.get("blocs", []), "consigne": content.get("consigne")}


def _shared_vma(conn: sqlite3.Connection, student_id: int) -> float | None:
    from . import club

    content, _ = club.shared(conn, student_id)
    return content.get("profil", {}).get("vma_kmh")


def _with_retry(conn: sqlite3.Connection, account_id: int, method: str, path: str, body: Any = None):
    """Un appel à la Training API ; jeton renouvelé une fois si Garmin le refuse."""
    status, data = _api(method, path, _access(conn, account_id), body)
    if status == 401:
        status, data = _api(method, path, _access(conn, account_id, force=True), body)
    if status == 401:
        forget(conn, account_id)
        raise NeedLink(authorize_url(conn, account_id), "Garmin ne reconnaît plus ton autorisation : relie à nouveau "
                                                       "ton compte.")
    if status == 403:
        forget(conn, account_id)
        raise NeedLink(authorize_url(conn, account_id), "Foulée n'a pas le droit d'ajouter des entraînements à ton "
                                                       "compte Garmin : relie-le à nouveau en laissant cochée "
                                                       "l'autorisation des entraînements.")
    if status == 429:
        raise GarminError("Garmin limite le nombre d'envois : réessaie dans quelques minutes.", 429)
    return status, data


def _remove_remote(conn: sqlite3.Connection, sent: sqlite3.Row) -> None:
    """Retire de Garmin une séance déjà envoyée (planification, puis séance) ; déjà partie : pas une erreur."""
    if sent["schedule_id"]:
        _with_retry(conn, sent["compte_id"], "DELETE", f"/training-api/schedule/{sent['schedule_id']}")
    if sent["workout_id"]:
        _with_retry(conn, sent["compte_id"], "DELETE", f"/training-api/workout/v2/{sent['workout_id']}")


def send(conn: sqlite3.Connection, row: sqlite3.Row, vma: float | None, *, by: str) -> dict:
    """Envoie une séance proposée sur le compte Garmin de son élève (et remplace l'envoi précédent)."""
    student_id = row["eleve_id"]
    if link_row(conn, student_id) is None:
        raise NeedLink(authorize_url(conn, student_id, row["id"], vma))
    vma = vma or _shared_vma(conn, student_id)
    workout = garmin_training.build(_item(row), vma)
    previous = conn.execute("SELECT * FROM garmin_envois WHERE proposition_id = ?", (row["id"],)).fetchone()
    if previous is not None:
        _remove_remote(conn, previous)
    status, data = _with_retry(conn, student_id, "POST", "/workoutportal/workout/v2", workout)
    if status == 400 and garmin_training.has_zones(workout):  # zones de FC refusées : la zone reste écrite
        workout = garmin_training.build(_item(row), vma, zones=False)
        status, data = _with_retry(conn, student_id, "POST", "/workoutportal/workout/v2", workout)
    workout_id = data.get("workoutId") if isinstance(data, dict) else None
    if status >= 400 or not workout_id:
        log.warning("Séance refusée par Garmin (HTTP %s) : %s", status, str(data)[:300])
        raise GarminError(f"Garmin a refusé la séance (HTTP {status}).", 502)
    day = max(row["date"], store.local_now().date().isoformat())
    status, data = _with_retry(conn, student_id, "POST", "/training-api/schedule/",
                               {"workoutId": workout_id, "date": day})
    if status >= 400:
        _with_retry(conn, student_id, "DELETE", f"/training-api/workout/v2/{workout_id}")
        raise GarminError(f"Garmin n'a pas pu planifier la séance au {_day_label(day)} (HTTP {status}).", 502)
    schedule = data.get("scheduleId") if isinstance(data, dict) else data
    schedule_id = int(schedule) if isinstance(schedule, (int, float, str)) and str(schedule).isdigit() else None
    stamp = store.now()
    conn.execute("INSERT INTO garmin_envois(proposition_id, compte_id, workout_id, schedule_id, date, envoye_le, par, "
                 "version, vma_kmh, erreur) VALUES (?,?,?,?,?,?,?,?,?,NULL) ON CONFLICT(proposition_id) DO UPDATE SET "
                 "workout_id = excluded.workout_id, schedule_id = excluded.schedule_id, date = excluded.date, "
                 "envoye_le = excluded.envoye_le, par = excluded.par, version = excluded.version, "
                 "vma_kmh = excluded.vma_kmh, erreur = NULL",
                 (row["id"], student_id, int(workout_id), schedule_id, day, stamp, by, row["modifie_le"], vma))
    log.info("Séance %s envoyée sur le compte Garmin de %s (%s)", row["id"], student_id, by)
    return {"date": day, "envoye_le": stamp, "par": by}


def withdraw(conn: sqlite3.Connection, proposal_id: int) -> None:
    """Le coach supprime une séance : elle quitte aussi le calendrier Garmin de l'élève (si Garmin répond)."""
    sent = conn.execute("SELECT * FROM garmin_envois WHERE proposition_id = ?", (proposal_id,)).fetchone()
    if sent is None:
        return
    try:
        _remove_remote(conn, sent)
    except (GarminError, NeedLink) as exc:
        log.info("Séance %s non retirée de Garmin : %s", proposal_id, exc)
    conn.execute("DELETE FROM garmin_envois WHERE proposition_id = ?", (proposal_id,))


def follow_update(conn: sqlite3.Connection, proposal_id: int) -> None:
    """Le coach modifie une séance déjà envoyée : elle est renvoyée (ou marquée « à renvoyer » si ça échoue)."""
    sent = conn.execute("SELECT * FROM garmin_envois WHERE proposition_id = ?", (proposal_id,)).fetchone()
    row = conn.execute("SELECT * FROM propositions WHERE id = ?", (proposal_id,)).fetchone()
    if sent is None or row is None:
        return
    try:
        send(conn, row, sent["vma_kmh"], by=sent["par"])
    except (GarminError, NeedLink, WorkoutError) as exc:
        message = exc.reason if isinstance(exc, NeedLink) and exc.reason else str(exc)
        conn.execute("UPDATE garmin_envois SET erreur = ? WHERE proposition_id = ?", (message[:300], proposal_id))


# ------------------------------------------------------------- ce que voit Foulée
def sent_map(conn: sqlite3.Connection, student_id: int) -> dict[int, dict]:
    rows = conn.execute("SELECT g.*, p.modifie_le FROM garmin_envois g JOIN propositions p ON p.id = g.proposition_id "
                        "WHERE g.compte_id = ?", (student_id,)).fetchall()
    return {r["proposition_id"]: {"date": r["date"], "envoye_le": r["envoye_le"], "par": r["par"],
                                  "a_jour": r["version"] == r["modifie_le"] and not r["erreur"],
                                  "erreur": r["erreur"]} for r in rows}


def decorate(conn: sqlite3.Connection, student_id: int, items: list[dict]) -> None:
    """Ajoute à chaque séance proposée son envoi sur la montre (« montre »)."""
    sent = sent_map(conn, student_id)
    for item in items:
        item["montre"] = sent.get(item["id"])


def status(conn: sqlite3.Connection, account: sqlite3.Row) -> dict:
    row = link_row(conn, account["id"])
    return {"disponible": configured(), "relie": row is not None, "relie_le": row["relie_le"] if row else None,
            "coach_peut_envoyer": bool(row["coach_peut_envoyer"]) if row else True}


def student_flags(conn: sqlite3.Connection, student_id: int) -> dict:
    """Pour le coach : l'élève est-il relié, et le laisse-t-il envoyer ?"""
    row = link_row(conn, student_id)
    return {"relie": row is not None, "coach_peut_envoyer": bool(row and row["coach_peut_envoyer"])}


def set_coach_allowed(conn: sqlite3.Connection, account_id: int, allowed: bool) -> None:
    conn.execute("UPDATE garmin_liens SET coach_peut_envoyer = ? WHERE compte_id = ?", (int(allowed), account_id))


def student_send(conn: sqlite3.Connection, student: sqlite3.Row, proposal_id: int, vma: Any) -> dict:
    """« Envoyer sur ma montre » : envoyée, ou l'adresse de Garmin pour relier le compte d'abord."""
    row = conn.execute("SELECT * FROM propositions WHERE id = ? AND eleve_id = ?",
                       (proposal_id, student["id"])).fetchone()
    if row is None:
        raise GarminError("Séance introuvable : ton coach l'a peut-être supprimée.", 404)
    try:
        vma_value = float(vma) if vma not in (None, "") else None
    except (TypeError, ValueError):
        vma_value = None
    if vma_value is not None and not 8 <= vma_value <= 30:
        vma_value = None
    try:
        return {"envoi": send(conn, row, vma_value, by="eleve")}
    except NeedLink as need:
        # la séance attend la fin de la liaison : elle part dès le retour de Garmin
        url = authorize_url(conn, student["id"], proposal_id, vma_value)
        return {"a_relier": True, "adresse": url, "raison": need.reason or None}
    except WorkoutError as exc:
        raise GarminError(str(exc)) from None


def coach_send(conn: sqlite3.Connection, coach: sqlite3.Row, proposal_ids: list[Any]) -> dict:
    """Le coach envoie des séances proposées sur la montre de ses élèves (ceux qui sont reliés et le permettent)."""
    ids = [int(i) for i in proposal_ids if str(i).isdigit()][:60]
    if not ids:
        raise GarminError("Aucune séance à envoyer.")
    _settings()
    result = {"envoyees": [], "non_reliees": [], "refusees": [], "erreurs": []}
    for proposal_id in dict.fromkeys(ids):
        row = conn.execute("SELECT p.*, c.nom AS eleve_nom FROM propositions p JOIN comptes c ON c.id = p.eleve_id "
                           "WHERE p.id = ? AND p.coach_id = ?", (proposal_id, coach["id"])).fetchone()
        if row is None:
            continue
        name = row["eleve_nom"]
        link = link_row(conn, row["eleve_id"])
        if link is None:
            result["non_reliees"].append(name)
            continue
        if not link["coach_peut_envoyer"]:
            result["refusees"].append(name)
            continue
        try:
            send(conn, row, None, by="coach")
            result["envoyees"].append(name)
        except NeedLink:
            result["non_reliees"].append(name)
        except (GarminError, WorkoutError) as exc:
            result["erreurs"].append(f"{name} : {exc}")
    return result


# ------------------------------------------------------------------ page de retour
def page(result: dict) -> str:
    """La page que l'élève voit dans son navigateur au retour de Garmin."""
    color = "#1f8a4c" if result.get("ok") else "#d3263a"
    mark = "✓" if result.get("ok") else "!"
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<meta name="referrer" content="no-referrer"><title>Foulée · Garmin Connect</title>
<style>:root{{color-scheme:light dark;--ink:#15201b;--muted:#5d6a64;--page:#f2f5f3;--card:#fcfdfc;--hair:#dce3df}}
@media (prefers-color-scheme:dark){{:root{{--ink:#e8eeeb;--muted:#a7b3ad;--page:#101614;--card:#182020;--hair:#2a3532}}}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px 16px;background:var(--page);
color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:480px;background:var(--card);border:1px solid var(--hair);border-radius:14px;padding:28px 26px}}
.brand{{display:flex;align-items:center;gap:10px;font-weight:600;font-size:19px;margin-bottom:18px}}
.mark{{display:inline-grid;place-items:center;width:30px;height:30px;border-radius:50%;background:{color};color:#fff;
font-weight:700;margin-right:8px;vertical-align:-6px}}h1{{font-size:21px;margin:0 0 10px}}p{{margin:0 0 12px;color:var(--muted)}}
</style></head><body><main>
<div class="brand"><svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="7"
fill="#182020"/><rect x="8" y="6" width="5.5" height="20" rx="1.2" fill="#fff"/><rect x="8" y="6" width="16.5"
height="5.5" rx="1.2" fill="#fff"/><rect x="8" y="14.5" width="12.5" height="5.5" rx="1.2" fill="#d3263a"/></svg>Foulée</div>
<h1><span class="mark">{mark}</span>{html.escape(result.get("titre") or "")}</h1>
<p>{html.escape(result.get("texte") or "")}</p>
<p>Tu peux fermer cette page et revenir dans Foulée.</p></main></body></html>"""
