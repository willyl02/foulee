"""Accès à l'API de Strava, en lecture seule : autorisation OAuth 2.0, jetons, appels, quota.

Strava ne donne son API qu'aux « applis » créées par un abonné Strava (règles du 1er juin 2026). Le
profil principal crée donc la sienne (strava.com/settings/api) et colle dans Foulée son Client ID et son
Client Secret : une appli pour toute l'installation, chaque profil y connecte son propre compte Strava
(jusqu'à 10 athlètes une fois l'appli passée à 10 dans les réglages API de Strava).

Lecture seule, garantie par Strava lui-même : Foulée ne demande que les droits « read » et
« activity:read_all ». Un jeton sans « activity:write » ne peut rien créer ni modifier chez Strava.
Les seuls envois (POST) servent à l'autorisation : échanger le code contre les jetons, les renouveler
et, à la déconnexion, révoquer l'accès de Foulée.

1. Foulée ouvre la page « Autoriser » de Strava ;
2. Strava renvoie le navigateur vers ce Foulée (``/strava/retour``) : 127.0.0.1 et localhost sont
   toujours acceptés, un serveur doit être inscrit comme « Authorization Callback Domain » de l'appli ;
3. Foulée échange le code contre un jeton d'accès (6 heures) et un jeton de renouvellement.

Le Client Secret et les jetons vont dans le coffre (``vault``), jamais à l'interface ni à Claude.
Les adresses de Strava peuvent être remplacées par des variables d'environnement (FOULEE_STRAVA_API,
FOULEE_STRAVA_OAUTH) : c'est ce que font les tests, avec un faux Strava.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlsplit

import requests

from .. import __version__, config, vault

LOG = logging.getLogger("foulee.strava")

SETTINGS_PAGE = "https://www.strava.com/settings/api"
APPS_PAGE = "https://www.strava.com/settings/apps"
SCOPE = "read,activity:read_all"   # lecture seule : jamais « activity:write »
APP_SECRET = "strava-appli"        # Client ID et Client Secret : un exemplaire pour l'installation
TOKENS = "strava"                  # jetons : un exemplaire par profil
REFRESH_MARGIN = 600               # renouvelle le jeton d'accès 10 minutes avant son expiration
TIMEOUT = 40
NEW_BASE_FROM = date(2027, 3, 1)   # Strava change d'adresse (api-v3.strava.com, ouverte le 4 janvier 2027)

# Quota de lecture de Strava (en-têtes X-ReadRateLimit-*) : par défaut 100 appels par quart d'heure
# et 1 000 par jour pour une appli à un athlète, partagés par tous les profils connectés à l'appli.
DEFAULT_LIMITS = (100, 1000)
QUOTA_FILE = "strava-quota.json"


def api_url() -> str:
    custom = os.environ.get("FOULEE_STRAVA_API")
    if custom:
        return custom.rstrip("/")
    return "https://api-v3.strava.com" if date.today() >= NEW_BASE_FROM else "https://www.strava.com/api/v3"


def oauth_url() -> str:
    return os.environ.get("FOULEE_STRAVA_OAUTH", "https://www.strava.com/oauth").rstrip("/")


def activity_link(strava_id: Any) -> str:
    return f"https://www.strava.com/activities/{int(strava_id)}"


class StravaError(Exception):
    """Erreur Strava expliquée en français.

    ``status`` : code HTTP (None si Strava n'a pas répondu) ; ``detail`` : message de Strava, sans secret
    ni jeton ; ``access_refused`` : Strava n'accepte plus l'accès de Foulée (il faut reconnecter le compte) ;
    ``rate_limited`` : quota de Strava atteint pour ce quart d'heure ou cette journée.
    """

    def __init__(self, message: str, status: int | None = None, *, detail: str = "", access_refused: bool = False,
                 rate_limited: bool = False):
        super().__init__(message)
        self.status = status
        self.detail = detail
        self.access_refused = access_refused
        self.rate_limited = rate_limited

    @property
    def passing(self) -> bool:
        """Panne passagère (réseau, serveur, quota) : la prochaine synchro reprendra."""
        return self.status is None or self.rate_limited or self.status >= 500


# ------------------------------------------------------------------ coffre
def _read(name: str) -> dict[str, Any]:
    raw = vault.get_secret(name)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _write(name: str, data: dict[str, Any]) -> str:
    clean = {k: v for k, v in data.items() if v not in (None, "")}
    if not clean:
        vault.delete_secret(name)
        return ""
    return vault.set_secret(name, json.dumps(clean, separators=(",", ":")))


def load_app() -> dict[str, Any]:
    """Client ID et Client Secret de l'appli Strava de l'installation (vide si rien n'est enregistré)."""
    return _read(APP_SECRET)


def has_app() -> bool:
    data = load_app()
    return bool(data.get("client_id") and data.get("client_secret"))


def load() -> dict[str, Any]:
    """Jetons du profil courant (vide si son compte Strava n'est pas connecté)."""
    return _read(TOKENS)


def connected() -> bool:
    return has_app() and bool(load().get("refresh_token"))


CLIENT_ID = re.compile(r"\d{1,10}")
CLIENT_SECRET = re.compile(r"[0-9a-fA-F]{40}")


def clean_client_id(text: Any) -> str:
    value = re.sub(r"\s+", "", str(text or "").strip().strip("\"'«»"))
    if not value:
        raise ValueError("Client ID vide : copie-le depuis la page « Mon appli API » de Strava.")
    if not CLIENT_ID.fullmatch(value):
        raise ValueError("Le Client ID de Strava est un nombre (par exemple 123456) : recopie-le depuis la page "
                         "« Mon appli API » de Strava.")
    return value


def clean_client_secret(text: Any) -> str:
    value = re.sub(r"\s+", "", str(text or "").strip().strip("\"'«»"))
    if not value:
        raise ValueError("Client Secret vide : sur la page « Mon appli API » de Strava, clique sur « afficher », "
                         "puis copie-le.")
    if not CLIENT_SECRET.fullmatch(value):
        raise ValueError("Ce texte ne ressemble pas à un Client Secret de Strava (40 lettres et chiffres, de 0 à 9 "
                         "et de a à f) : sur la page « Mon appli API », clique sur « afficher » puis recopie-le.")
    return value.lower()


def set_app(client_id: str, client_secret: str) -> str:
    """Enregistre l'appli Strava de l'installation. Une autre appli : les jetons de chaque profil ne valent plus
    rien, ils seront redemandés à la connexion."""
    previous = load_app()
    changed = previous.get("client_id") != client_id or previous.get("client_secret") != client_secret
    where = _write(APP_SECRET, {"client_id": client_id, "client_secret": client_secret,
                                "changee_le": int(time.time()) if changed else previous.get("changee_le")})
    return where


def forget_app() -> None:
    vault.delete_secret(APP_SECRET)


def app_changed_after(tokens: dict[str, Any]) -> bool:
    """Les jetons du profil datent-ils d'avant le changement d'appli ? (ils ne valent alors plus rien)"""
    changed = int(load_app().get("changee_le") or 0)
    return bool(changed and int(tokens.get("obtenus_le") or 0) and int(tokens["obtenus_le"]) < changed)


def forget_tokens() -> None:
    vault.delete_secret(TOKENS)


def _store_tokens(body: dict[str, Any], *, first: bool = False) -> dict[str, Any]:
    access, refresh = body.get("access_token"), body.get("refresh_token")
    if not access or not refresh:
        raise StravaError("Strava n'a pas renvoyé les jetons attendus : relance la connexion.")
    data = {} if first else load()
    athlete = body.get("athlete") if isinstance(body.get("athlete"), dict) else {}
    data.update(access_token=access, refresh_token=refresh,
                expires_at=int(body.get("expires_at") or (time.time() + int(body.get("expires_in") or 21600))))
    if first:
        data.update(athlete_id=str(athlete.get("id") or ""), scope=str(body.get("scope") or ""),
                    obtenus_le=int(time.time()))
    _write(TOKENS, data)
    return data


# ------------------------------------------------------------- autorisation
def redirect_uri(origin: str) -> str:
    return f"{origin.rstrip('/')}/strava/retour"


def callback_domain(origin: str) -> str:
    """Ce qu'il faut inscrire dans « Authorization Callback Domain » de l'appli Strava pour cette adresse."""
    return (urlsplit(origin).hostname or "").lower()


def callback_free(origin: str) -> bool:
    """127.0.0.1 et localhost : Strava les accepte toujours, quel que soit le domaine inscrit dans l'appli."""
    return callback_domain(origin) in ("127.0.0.1", "localhost")


def origin_problem(origin: str, host: str | None) -> str | None:
    """L'adresse de ce Foulée, telle que le navigateur la voit, doit correspondre à la requête."""
    try:
        parts = urlsplit(origin)
    except ValueError:
        return "adresse illisible"
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "adresse illisible"
    if parts.netloc.lower() != str(host or "").lower():
        return "l'adresse ne correspond pas à celle de cette page"
    return None


def authorize_url(client_id: str, origin: str, state: str) -> str:
    query = urlencode({"client_id": client_id, "redirect_uri": redirect_uri(origin), "response_type": "code",
                       "approval_prompt": "auto", "scope": SCOPE, "state": state})
    return f"{oauth_url()}/authorize?{query}"


def granted(scope: str | None) -> tuple[bool, bool]:
    """(séances lisibles, séances « Moi uniquement » comprises) d'après les droits accordés."""
    parts = set(re.split(r"[\s,]+", str(scope or "").strip()))
    return bool(parts & {"activity:read", "activity:read_all"}), "activity:read_all" in parts


# ------------------------------------------------------------------ appels
def scrub(text: Any, secrets: tuple[str, ...] = ()) -> str:
    """Message lisible, sans Secret, jeton ni code."""
    value = str(text or "")
    for secret in secrets:
        if secret and len(secret) >= 6:
            value = value.replace(secret, "[masqué]")
    value = re.sub(r"\b[0-9a-fA-F]{32,}\b", "[masqué]", value)
    value = " ".join(value.split())
    return value if len(value) <= 200 else value[:199] + "…"


def _strava_message(response: requests.Response, secrets: tuple[str, ...]) -> str:
    try:
        payload = response.json()
    except ValueError:
        return scrub(response.text, secrets)[:160]
    if isinstance(payload, dict):
        parts = [str(payload.get("message") or "")]
        for error in payload.get("errors") or []:
            if isinstance(error, dict):
                parts.append(" ".join(str(error.get(k) or "") for k in ("resource", "field", "code")).strip())
        return scrub(" — ".join(p for p in parts if p), secrets)
    return ""


def _post_oauth(path: str, data: dict[str, Any], *, secrets: tuple[str, ...], auth: tuple[str, str] | None = None
                ) -> dict[str, Any]:
    url = f"{oauth_url()}/{path.lstrip('/')}"
    headers = {"User-Agent": f"Foulee/{__version__}", "Accept": "application/json"}
    last: StravaError | None = None
    for attempt in range(3):
        if attempt:
            time.sleep(1.5 * attempt)
        try:
            response = requests.post(url, data=data, headers=headers, auth=auth, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last = StravaError(f"Strava injoignable ({scrub(type(exc).__name__)}) : vérifie la connexion à Internet.")
            continue
        if response.status_code >= 500 or response.status_code == 429:
            last = StravaError(f"Strava ne répond pas (HTTP {response.status_code}) : réessaie plus tard.",
                               response.status_code, rate_limited=response.status_code == 429)
            continue
        if response.status_code >= 400:
            detail = _strava_message(response, secrets)
            raise StravaError(f"Strava refuse (HTTP {response.status_code}){f' : « {detail} »' if detail else ''}.",
                              response.status_code, detail=detail, access_refused=True)
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError:
            raise StravaError(f"Réponse inattendue de Strava (HTTP {response.status_code}).") from None
        return payload if isinstance(payload, dict) else {}
    raise last or StravaError("Strava ne répond pas : réessaie plus tard.")


def exchange_code(code: str) -> dict[str, Any]:
    """Échange le code reçu après « Autoriser » contre les jetons, et les range dans le coffre."""
    app = load_app()
    client_id, secret = app.get("client_id"), app.get("client_secret")
    if not client_id or not secret:
        raise StravaError("L'appli Strava n'est pas encore enregistrée (étape 2).")
    try:
        body = _post_oauth("token", {"client_id": client_id, "client_secret": secret, "code": code,
                                     "grant_type": "authorization_code"}, secrets=(secret, code))
    except StravaError as exc:
        said = f" (« {exc.detail} »)" if exc.detail else ""
        raise StravaError(f"Strava refuse de terminer la connexion{said}. Vérifie le Client ID et le Client Secret "
                          "recopiés à l'étape 2, puis relance la connexion.", exc.status, detail=exc.detail) from exc
    return _store_tokens(body, first=True)


def revoke() -> bool:
    """Retire l'accès de Foulée chez Strava (le compte n'apparaît plus dans « Mes applis » de Strava).
    Renvoie False si Strava n'a pas pu être joint : les jetons sont oubliés de toute façon."""
    app, tokens = load_app(), load()
    token = tokens.get("refresh_token") or tokens.get("access_token")
    if not (app.get("client_id") and app.get("client_secret") and token):
        return True
    try:
        _post_oauth("revoke", {"token": token, "token_type_hint": "refresh_token"},
                    secrets=(app["client_secret"], str(token)), auth=(str(app["client_id"]), str(app["client_secret"])))
        return True
    except StravaError as exc:
        LOG.warning("Révocation Strava impossible : %s", exc)
        return False


# ------------------------------------------------------------------- quota
def _window(at: float) -> tuple[int, str]:
    stamp = datetime.fromtimestamp(at, timezone.utc)
    return int(at // 900), stamp.date().isoformat()  # quart d'heure (0, 15, 30, 45) et jour UTC de Strava


def _quota_path():
    return config.root_dir() / QUOTA_FILE


def quota() -> dict[str, int]:
    """Dernier quota connu (partagé par les profils et les processus) : appels faits et limites."""
    try:
        data = json.loads(_quota_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    now = time.time()
    window, day = _window(now)
    at = float(data.get("at") or 0)
    used15 = int(data.get("used15") or 0) if at and _window(at)[0] == window else 0
    used_day = int(data.get("used_day") or 0) if at and _window(at)[1] == day else 0
    return {"used15": used15, "limit15": int(data.get("limit15") or DEFAULT_LIMITS[0]),
            "used_day": used_day, "limit_day": int(data.get("limit_day") or DEFAULT_LIMITS[1])}


def _note_quota(response: requests.Response) -> None:
    def pair(name: str) -> tuple[int, int] | None:
        raw = response.headers.get(f"X-ReadRateLimit-{name}") or response.headers.get(f"X-RateLimit-{name}")
        try:
            a, b = (int(x) for x in str(raw).split(",")[:2])
        except (TypeError, ValueError):
            return None
        return a, b

    usage, limit = pair("Usage"), pair("Limit")
    if not usage:
        return
    data = {"at": time.time(), "used15": usage[0], "used_day": usage[1]}
    if limit:
        data.update(limit15=limit[0], limit_day=limit[1])
    else:
        known = quota()
        data.update(limit15=known["limit15"], limit_day=known["limit_day"])
    try:
        _quota_path().write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def can_spend(calls: int = 1, *, reserve15: int = 20, reserve_day: int = 150) -> bool:
    """Reste-t-il de quoi faire ``calls`` appels en gardant une réserve (pour ouvrir une séance, pour les autres
    profils) ? Les détails et les courbes passent après l'essentiel."""
    q = quota()
    return (q["limit15"] - q["used15"] - calls >= reserve15) and (q["limit_day"] - q["used_day"] - calls >= reserve_day)


class StravaSession:
    """Les appels d'une synchro (ou d'une séance ouverte) : jeton renouvelé au besoin, compteur d'appels."""

    def __init__(self, *, pause: float = 0.15) -> None:
        self.app = load_app()
        self.data = load()
        if not (self.app.get("client_id") and self.app.get("client_secret")):
            raise StravaError("L'appli Strava de Foulée n'est pas enregistrée : Réglages → Strava.")
        if not self.data.get("refresh_token"):
            raise StravaError("Compte Strava non connecté : Réglages → Strava.")
        if app_changed_after(self.data):
            raise StravaError("L'appli Strava a changé depuis ta connexion : reconnecte ton compte, Réglages → Strava.",
                              access_refused=True)
        self.pause = pause
        self.calls = 0

    def _secrets(self) -> tuple[str, ...]:
        return (str(self.app.get("client_secret") or ""), str(self.data.get("access_token") or ""),
                str(self.data.get("refresh_token") or ""))

    def refresh(self) -> None:
        try:
            body = _post_oauth("token", {"client_id": self.app["client_id"], "client_secret": self.app["client_secret"],
                                         "grant_type": "refresh_token", "refresh_token": self.data["refresh_token"]},
                               secrets=self._secrets())
        except StravaError as exc:
            if exc.passing:
                raise
            said = f" (« {exc.detail} »)" if exc.detail else ""
            raise StravaError(f"Strava refuse de renouveler l'accès de Foulée{said} : reconnecte ton compte, "
                              "Réglages → Strava.", exc.status, detail=exc.detail, access_refused=True) from exc
        self.data = _store_tokens(body)

    def token(self) -> str:
        if not self.data.get("access_token") or time.time() > int(self.data.get("expires_at") or 0) - REFRESH_MARGIN:
            self.refresh()
        return str(self.data["access_token"])

    def get(self, path: str, **params: Any) -> Any:
        """GET sur l'API de Strava (seule méthode employée pour les données)."""
        url = f"{api_url()}/{path.lstrip('/')}"
        clean = {k: v for k, v in params.items() if v is not None}
        for attempt in range(3):
            if self.calls:
                time.sleep(self.pause)
            self.calls += 1
            headers = {"User-Agent": f"Foulee/{__version__}", "Accept": "application/json",
                       "Authorization": f"Bearer {self.token()}"}
            try:
                response = requests.get(url, params=clean, headers=headers, timeout=TIMEOUT)
            except requests.RequestException as exc:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise StravaError(f"Strava injoignable ({scrub(type(exc).__name__)}) : vérifie la connexion à Internet."
                                  ) from None
            _note_quota(response)
            if response.status_code == 401 and attempt == 0:
                self.data["access_token"] = None  # jeton refusé avant l'heure : on le renouvelle une fois
                continue
            if response.status_code == 429:
                raise StravaError("Quota de Strava atteint (appels limités par quart d'heure et par jour) : la "
                                  "prochaine synchro reprendra là où celle-ci s'est arrêtée.", 429, rate_limited=True)
            if response.status_code >= 500:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise StravaError(f"Strava ne répond pas (HTTP {response.status_code}) : réessaie plus tard.",
                                  response.status_code)
            if response.status_code == 404:
                return None
            if response.status_code >= 400:
                detail = _strava_message(response, self._secrets())
                refused = response.status_code in (401, 403)
                raise StravaError(
                    (f"Strava n'accepte plus l'accès de Foulée (HTTP {response.status_code}) : reconnecte ton compte, "
                     "Réglages → Strava." if refused else f"Strava refuse la demande (HTTP {response.status_code}).")
                    + (f" « {detail} »" if detail else ""), response.status_code, detail=detail,
                    access_refused=refused)
            try:
                return response.json()
            except ValueError:
                raise StravaError(f"Réponse inattendue de Strava (HTTP {response.status_code}).") from None
        raise StravaError("Strava refuse le jeton d'accès : reconnecte ton compte, Réglages → Strava.",
                          401, access_refused=True)
