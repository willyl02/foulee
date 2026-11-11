"""Accès à l'API de Withings : autorisation OAuth 2.0, jetons, appels.

Chaque utilisateur crée sa propre « appli » sur le tableau de bord développeur de Withings
(gratuit) et colle dans Foulée son ClientID et son Secret. Ensuite :

1. Foulée ouvre la page d'autorisation de Withings (account.withings.com) ;
2. après « Autoriser », Withings renvoie le navigateur vers la page relais de Foulée, sur
   GitHub Pages (Withings refuse les adresses locales comme 127.0.0.1), qui le renvoie
   aussitôt vers ce Foulée-ci (``/withings/retour``) avec un code valable 30 secondes ;
3. Foulée échange ce code contre un jeton d'accès (3 heures) et un jeton de renouvellement
   (un an, remplacé à chaque renouvellement : on garde toujours le dernier reçu).

Le Secret et les jetons vont dans le coffre (``vault``), comme la clé Garmin : un exemplaire
par profil, jamais montré à l'interface ni à Claude.

Les adresses de Withings et de la page relais peuvent être remplacées par des variables
d'environnement (FOULEE_WITHINGS_API, FOULEE_WITHINGS_COMPTE, FOULEE_WITHINGS_RELAIS) :
c'est ce que font les tests, avec un faux Withings.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from typing import Any
from urllib.parse import urlencode, urlsplit

import requests

from .. import __version__, vault

LOG = logging.getLogger("foulee.withings")

DASHBOARD = "https://developer.withings.com/dashboard/"
RELAY = "https://willyl02.github.io/foulee/withings/"
SCOPES = "user.info,user.metrics,user.activity,user.sleepevents"
SECRET = "withings"
CODE_LIFETIME = 30           # secondes : délai pour échanger le code reçu
REFRESH_MARGIN = 300         # renouvelle le jeton d'accès 5 minutes avant son expiration
TIMEOUT = 40

# Codes « status » de Withings (la réponse HTTP vaut 200 même en cas d'erreur)
TOKEN_REFUSED = {100, 101, 102, 200, 401}          # jeton d'accès invalide ou expiré
ACCESS_WITHDRAWN = {214, 277, 2553, 2554, 2555}    # appli ou autorisation retirée
TOO_MANY = {601}


def api_url() -> str:
    return os.environ.get("FOULEE_WITHINGS_API", "https://wbsapi.withings.net").rstrip("/")


def account_url() -> str:
    return os.environ.get("FOULEE_WITHINGS_COMPTE", "https://account.withings.com").rstrip("/")


def relay_url() -> str:
    return os.environ.get("FOULEE_WITHINGS_RELAIS", RELAY)


class WithingsError(Exception):
    """Erreur Withings expliquée en français.

    ``status`` : code « status » de la réponse de Withings (None si Withings n'a pas répondu) ;
    ``http`` : code HTTP quand la réponse n'en est pas une (panne, page d'erreur) ;
    ``detail`` : message de Withings, sans secret ni jeton ;
    ``access_refused`` : Withings n'accepte plus l'accès de Foulée (il faut reconnecter le compte).
    """

    def __init__(self, message: str, status: int | None = None, *, detail: str = "", access_refused: bool = False,
                 http: int | None = None):
        super().__init__(message)
        self.status = status
        self.detail = detail
        self.access_refused = access_refused
        self.http = http

    @property
    def passing(self) -> bool:
        """Panne passagère (réseau, serveur, trop de demandes) : à réessayer plus tard, rien à reconnecter."""
        return self.status is None or self.status in TOO_MANY or self.status == 522


# ------------------------------------------------------------------ coffre
def load() -> dict[str, Any]:
    """ClientID, Secret et jetons du profil courant (vide si rien n'est enregistré)."""
    raw = vault.get_secret(SECRET)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, Any]) -> str:
    clean = {k: v for k, v in data.items() if v not in (None, "")}
    if not clean:
        vault.delete_secret(SECRET)
        return ""
    return vault.set_secret(SECRET, json.dumps(clean, separators=(",", ":")))


def has_app() -> bool:
    data = load()
    return bool(data.get("client_id") and data.get("client_secret"))


def connected() -> bool:
    data = load()
    return bool(data.get("client_id") and data.get("client_secret") and data.get("refresh_token"))


CREDENTIAL = re.compile(r"[A-Za-z0-9._~+/=-]{16,256}")
HEX_PIECES = re.compile(r"[0-9A-Fa-f]+(?:\s+[0-9A-Fa-f]+)+")  # suite hexadécimale coupée en morceaux


def clean_credential(text: str, label: str) -> str:
    """ClientID ou Secret collé : espaces, guillemets et retours à la ligne autour retirés, forme vérifiée.

    Une copie coupée en deux lignes est recollée : le navigateur change parfois le retour à la ligne en espace.
    """
    value = str(text or "").strip().strip("\"'«»").strip()
    value = re.sub(r"\s+", "", value) if HEX_PIECES.fullmatch(value) else re.sub(r"[\r\n\t]+", "", value)
    if not value:
        raise ValueError(f"{label} vide : copie-le depuis le tableau de bord de Withings.")
    if not CREDENTIAL.fullmatch(value):
        raise ValueError(f"Ce texte ne ressemble pas à un {label} de Withings (une longue suite de lettres et de "
                         "chiffres) : recopie-le avec le bouton de copie du tableau de bord.")
    return value


def set_app(client_id: str, client_secret: str) -> str:
    """Enregistre l'appli Withings. Une autre appli que la précédente : les anciens jetons ne valent plus rien."""
    data = load()
    if data.get("client_id") != client_id or data.get("client_secret") != client_secret:
        data = {}
    data.update(client_id=client_id, client_secret=client_secret)
    return _save(data)


def disconnect(*, forget_app: bool = False) -> None:
    """Oublie les jetons (et l'appli si demandé) : la synchro Withings s'arrête."""
    if forget_app:
        vault.delete_secret(SECRET)
        return
    data = load()
    for key in ("access_token", "refresh_token", "expires_at", "userid"):
        data.pop(key, None)
    _save(data)


def _store_tokens(body: dict[str, Any]) -> None:
    access, refresh = body.get("access_token"), body.get("refresh_token")
    if not access or not refresh:
        raise WithingsError("Withings n'a pas renvoyé les jetons attendus : relance la connexion.")
    data = load()
    data.update(access_token=access, refresh_token=refresh,
                expires_at=int(time.time()) + int(body.get("expires_in") or 10800),
                userid=str(body.get("userid") or data.get("userid") or ""))
    _save(data)


# ----------------------------------------------------------- page relais
def make_state(nonce: str, origin: str) -> str:
    """Le « state » de l'autorisation : un nonce à usage unique et l'adresse de ce Foulée (pour la page relais)."""
    raw = json.dumps({"n": nonce, "r": origin}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def read_state(state: str) -> dict[str, str]:
    try:
        text = str(state or "")
        data = json.loads(base64.urlsafe_b64decode((text + "=" * (-len(text) % 4)).encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("state illisible") from exc
    if not isinstance(data, dict) or not isinstance(data.get("n"), str) or not isinstance(data.get("r"), str):
        raise ValueError("state incomplet")
    return data


LOCAL_SUFFIXES = (".ts.net", ".local", ".lan", ".home", ".home.arpa", ".internal", ".intranet")


def relay_accepts(host: str) -> bool:
    """Exactement la règle de la page relais (docs/withings/index.html) : la machine elle-même,
    le réseau de la maison ou Tailscale."""
    name = str(host or "").strip().lower().strip("[]")
    if name in ("localhost", "::1") or name.endswith(".localhost"):
        return True
    match = re.fullmatch(r"(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})", name)
    if match:
        a, b = int(match[1]), int(match[2])
        return a in (127, 10) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31) or (a == 100 and 64 <= b <= 127)
    if ":" in name:
        return re.match(r"(fc|fd|fe8|fe9|fea|feb)", name) is not None
    if "." not in name:
        return bool(name)
    return name.endswith(LOCAL_SUFFIXES)


def origin_problem(origin: str, host: str) -> str | None:
    """Adresse de ce Foulée, telle que le navigateur la voit : doit correspondre à la requête et à la page relais."""
    try:
        parts = urlsplit(origin)
    except ValueError:
        return "adresse illisible"
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "adresse illisible"
    if parts.netloc.lower() != str(host or "").lower():
        return "l'adresse ne correspond pas à celle de cette page"
    if not relay_accepts(parts.hostname):
        return (f"la page relais ne renvoie que vers un Foulée de la maison (ce PC, ton serveur, Tailscale), "
                f"pas vers « {parts.hostname} »")
    return None


def authorize_url(client_id: str, state: str) -> str:
    query = urlencode({"response_type": "code", "client_id": client_id, "scope": SCOPES,
                       "redirect_uri": relay_url(), "state": state})
    return f"{account_url()}/oauth2_user/authorize2?{query}"


# ------------------------------------------------------------------ appels
def scrub(text: Any, secrets: tuple[str, ...] = ()) -> str:
    """Message lisible, sans Secret, jeton ni code."""
    value = str(text or "")
    for secret in secrets:
        if secret and len(secret) >= 6:
            value = value.replace(secret, "[masqué]")
    value = re.sub(r"\b[0-9a-fA-F]{24,}\b", "[masqué]", value)
    value = " ".join(value.split())
    return value if len(value) <= 200 else value[:199] + "…"


def _message(status: int | None, error: str) -> str:
    said = f" : « {error} »" if error else ""
    if status in TOKEN_REFUSED or status in ACCESS_WITHDRAWN:
        return f"Withings n'accepte plus l'accès de Foulée (code {status}){said}. Reconnecte ton compte : Réglages → Withings."
    if status in TOO_MANY:
        return "Trop de demandes à Withings d'un coup : la prochaine synchro reprendra là où celle-ci s'est arrêtée."
    return f"Withings a répondu par une erreur (code {status}){said}."


def _post(path: str, data: dict[str, Any], *, token: str | None = None, secrets: tuple[str, ...] = (),
          pause: float = 2.0) -> dict[str, Any]:
    """Un appel à Withings (POST), avec deux nouvelles tentatives en cas d'erreur passagère."""
    url = f"{api_url()}/{path.lstrip('/')}"
    headers = {"User-Agent": f"Foulee/{__version__}", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    last: WithingsError | None = None
    for attempt in range(3):
        if attempt:
            time.sleep(pause * attempt)
        try:
            response = requests.post(url, data=data, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last = WithingsError(f"Withings injoignable ({scrub(type(exc).__name__)}) : vérifie la connexion à Internet.")
            continue
        if response.status_code >= 500:
            last = WithingsError(f"Withings ne répond pas (HTTP {response.status_code}) : réessaie plus tard.",
                                 http=response.status_code)
            continue
        try:
            payload = response.json()
        except ValueError:
            raise WithingsError(f"Réponse inattendue de Withings (HTTP {response.status_code}).",
                                detail=scrub(response.text, secrets), http=response.status_code) from None
        status = payload.get("status") if isinstance(payload, dict) else None
        if status == 0:
            body = payload.get("body")
            return body if isinstance(body, dict) else {}
        error = scrub(payload.get("error") if isinstance(payload, dict) else "", secrets)
        last = WithingsError(_message(status, error), status, detail=error,
                             access_refused=status in TOKEN_REFUSED or status in ACCESS_WITHDRAWN)
        if status in TOO_MANY or status == 522:  # trop de demandes, délai dépassé : on réessaie un peu plus tard
            continue
        raise last
    raise last or WithingsError("Withings ne répond pas : réessaie plus tard.")


def exchange_code(code: str) -> dict[str, Any]:
    """Échange le code reçu après « Autoriser » contre les jetons, et les range dans le coffre."""
    app = load()
    client_id, secret = app.get("client_id"), app.get("client_secret")
    if not client_id or not secret:
        raise WithingsError("Enregistre d'abord le ClientID et le Secret de ton appli Withings (étape 2).")
    try:
        body = _post("v2/oauth2", {
            "action": "requesttoken", "grant_type": "authorization_code", "client_id": client_id,
            "client_secret": secret, "code": code, "redirect_uri": relay_url(),
        }, secrets=(secret, code), pause=0.5)
    except WithingsError as exc:
        said = f" (« {exc.detail} »)" if exc.detail else ""
        raise WithingsError(
            f"Withings refuse de terminer la connexion{said}. Vérifie le ClientID et le Secret recopiés à l'étape 2, "
            f"et que l'adresse enregistrée dans ton appli Withings est exactement {relay_url()}. "
            "Puis relance la connexion : l'autorisation ne vaut que 30 secondes.", exc.status, detail=exc.detail) from exc
    _store_tokens(body)
    return {"userid": str(body.get("userid") or ""), "scope": body.get("scope") or ""}


class WithingsSession:
    """Les appels d'une synchro : jeton d'accès renouvelé au besoin, rythme modéré, compteur d'appels."""

    def __init__(self, *, pause: float = 0.3) -> None:
        self.data = load()
        if not (self.data.get("client_id") and self.data.get("client_secret") and self.data.get("refresh_token")):
            raise WithingsError("Compte Withings non connecté : Réglages → Withings.")
        self.pause = pause
        self.calls = 0
        self.answered = False

    def _secrets(self) -> tuple[str, ...]:
        return tuple(str(self.data.get(k) or "") for k in ("client_secret", "access_token", "refresh_token"))

    def refresh(self) -> None:
        try:
            body = _post("v2/oauth2", {
                "action": "requesttoken", "grant_type": "refresh_token", "client_id": self.data["client_id"],
                "client_secret": self.data["client_secret"], "refresh_token": self.data["refresh_token"],
            }, secrets=self._secrets())
        except WithingsError as exc:
            if exc.passing:
                raise  # passager : on réessaiera à la prochaine synchro
            said = f" (« {exc.detail} »)" if exc.detail else ""
            raise WithingsError(f"Withings refuse de renouveler l'accès de Foulée{said} : reconnecte ton compte, "
                                "Réglages → Withings.", exc.status, detail=exc.detail, access_refused=True) from exc
        _store_tokens(body)
        self.data = load()

    def token(self) -> str:
        expires = int(self.data.get("expires_at") or 0)
        if not self.data.get("access_token") or time.time() > expires - REFRESH_MARGIN:
            self.refresh()
        return str(self.data["access_token"])

    def call(self, path: str, action: str, **params: Any) -> dict[str, Any]:
        data = {"action": action, **{k: v for k, v in params.items() if v is not None}}
        for attempt in (0, 1):
            if self.calls:
                time.sleep(self.pause)
            self.calls += 1
            try:
                body = _post(path, data, token=self.token(), secrets=self._secrets())
            except WithingsError as exc:
                if attempt == 0 and exc.status in TOKEN_REFUSED:
                    self.data["access_token"] = None  # jeton refusé avant l'heure : on le renouvelle une fois
                    continue
                raise
            self.answered = True
            return body
        raise WithingsError("Withings refuse le jeton d'accès : reconnecte ton compte.", access_refused=True)
