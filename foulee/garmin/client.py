"""Accès à l'API personnelle Garmin, par-dessus le client Python officiel de Garmin.

Ce module ajoute ce dont une synchro a besoin :
- un rythme modéré entre deux appels (Garmin ne publie pas de limite) ;
- des nouvelles tentatives en cas d'erreur passagère (429, 5xx, réseau) ;
- le renouvellement du jeton si Garmin le rejette en cours de route ;
- des messages d'erreur compréhensibles.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests
from garmin_personal_api import GarminPersonalApiClient, PersonalApiAuthenticator
from garmin_personal_api.errors import GarminPersonalApiError, HttpError

from .. import config, vault

LOG = logging.getLogger("foulee.garmin")

KEY_PAGE = "https://connect.garmin.com/app/settings/personalApiToken"


class GarminError(Exception):
    """Erreur Garmin expliquée en français.

    ``detail`` : extrait de la réponse de Garmin, sans clé ni jeton.
    ``key_rejected`` : Garmin a refusé la clé elle-même (HTTP 400, 401 ou 403 à l'échange).
    """

    def __init__(self, message: str, status: int | None = None, *, detail: str = "", key_rejected: bool = False):
        super().__init__(message)
        self.status = status
        self.detail = detail
        self.key_rejected = key_rejected


_SECRETS = (
    re.compile(r"GCDC_[A-Za-z0-9._~+/=:-]*"),                      # une clé API
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"),  # un jeton JWT
)


def garmin_detail(text: str | None, secret: str | None = None, limit: int = 200) -> str:
    """Extrait lisible d'une réponse de Garmin, débarrassé de toute clé ou de tout jeton."""
    if not text:
        return ""
    if re.search(r"<\s*(html|body|head|div|p)\b", text, re.I):
        text = re.sub(r"<(script|style)\b.*?</\1\s*>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]*>", " ", text)
    if secret:
        text = text.replace(secret, "[clé masquée]")
    for pattern in _SECRETS:
        text = pattern.sub("[masqué]", text)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class GarminSession:
    def __init__(self, api_key: str | None = None, *, pause: float = 0.4, timeout: float = 40):
        key = "".join((api_key or vault.get_key() or "").split())
        if not key:
            raise GarminError("Aucune clé API Garmin enregistrée. Lance d'abord « foulee setup ».")
        self._key = key
        self.pause = pause
        self.calls = 0
        self._last_call = 0.0
        self.auth = PersonalApiAuthenticator(bearer_token_cache_file=config.token_cache_file(), timeout=timeout)
        try:
            token = self._obtain()
        except BaseException:
            self.auth.close()
            raise
        self.token_expires_at = token.expires_at
        self.client = GarminPersonalApiClient(token.access_token, timeout=timeout)

    def close(self) -> None:
        self.client.close()
        self.auth.close()

    def __enter__(self) -> "GarminSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------ jetons
    def _obtain(self, force: bool = False):
        try:
            return self.auth.obtain_token(self._key, force_refresh=force)
        except HttpError as exc:
            status = exc.status_code
            detail = garmin_detail(exc.response_text, self._key)
            quoted = f" Réponse de Garmin : « {detail} »." if detail else ""
            LOG.info("Échange de la clé refusé : HTTP %s%s", status, f" ({detail})" if detail else "")
            if status in (400, 401, 403):
                raise GarminError(
                    f"Garmin a refusé la clé API (HTTP {status}).{quoted} Si elle fonctionnait jusqu'ici, "
                    "elle a sans doute expiré ou été supprimée : crée-en une nouvelle dans Garmin Connect "
                    "(page « API personnelle »), puis lance Configurer-cle-Garmin.cmd.",
                    status, detail=detail, key_rejected=True,
                ) from exc
            if status == 429:
                raise GarminError("Garmin limite les demandes (HTTP 429) : réessaie dans quelques minutes.",
                                  status, detail=detail) from exc
            raise GarminError(f"Échange de la clé impossible (HTTP {status}).{quoted}", status, detail=detail) from exc
        except GarminPersonalApiError as exc:
            raise GarminError("Réponse inattendue de Garmin lors de l'échange de la clé : "
                              f"{garmin_detail(str(exc), self._key)}") from exc
        except requests.RequestException as exc:
            raise GarminError(f"Impossible de joindre Garmin ({exc.__class__.__name__}) : vérifie la connexion "
                              "Internet, un éventuel proxy ou l'analyse HTTPS de ton antivirus.") from exc
        except UnicodeError as exc:
            raise GarminError("La clé contient des caractères qui ne peuvent pas venir de Garmin : "
                              "recopie-la depuis Garmin Connect.") from exc

    def _throttle(self) -> None:
        wait = self.pause - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    # ------------------------------------------------------------- appels
    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        delay = 2.0
        last_error: Exception | None = None
        for attempt in range(5):
            self._throttle()
            self.calls += 1
            try:
                return getattr(self.client, method)(*args, **kwargs)
            except HttpError as exc:
                last_error = exc
                if exc.status_code == 401 and attempt == 0:
                    token = self._obtain(force=True)
                    self.client.update_bearer_token(token.access_token)
                    continue
                if exc.status_code in (429, 502, 503, 504) or (exc.status_code == 500 and attempt < 2):
                    LOG.info("Garmin HTTP %s sur %s, nouvel essai dans %.0f s", exc.status_code, method, delay)
                    time.sleep(delay)
                    delay *= 2
                    continue
                if exc.status_code in (204, 404):
                    return None
                detail = garmin_detail(exc.response_text, self._key)
                raise GarminError(
                    f"Garmin a répondu HTTP {exc.status_code} pour {method}" + (f" : « {detail} »." if detail else "."),
                    exc.status_code, detail=detail,
                ) from exc
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(delay)
                delay *= 2
        raise GarminError(f"Garmin ne répond pas ({method}) après plusieurs tentatives : {last_error}")

    def download_activity(self, activity_id: str | int) -> bytes | None:
        """Fichier d'origine (ZIP). Repli sur l'en-tête Accept que Garmin préfère en cas de 406."""
        try:
            return self.call("download_activity", activity_id)
        except GarminError as exc:
            if exc.status != 406:
                raise
        self._throttle()
        token = self._obtain()
        response = requests.get(
            f"{self.client.base_url}/download-service/files/activity/{int(activity_id)}",
            headers={"Authorization": f"Bearer {token.access_token}", "Accept": "application/x-zip-compressed"},
            timeout=self.client.timeout,
        )
        if response.status_code == 404:
            return None
        if not response.ok:
            raise GarminError(f"Téléchargement du fichier impossible (HTTP {response.status_code}).",
                              response.status_code)
        return response.content


def check_key(api_key: str) -> dict:
    """Vérifie une clé. L'échange contre un jeton fait foi ; la lecture du profil confirme l'accès aux données."""
    with GarminSession(api_key, pause=0) as session:
        info = {
            "ok": True,
            "jeton_expire": time.strftime("%d/%m/%Y %H:%M", time.localtime(session.token_expires_at)),
            "systeme": None,
            "profil_erreur": None,
        }
        try:
            profile = session.call("get_user_profile_settings") or {}
        except GarminError as exc:
            info["profil_erreur"] = str(exc)
        else:
            if isinstance(profile, dict):
                info["systeme"] = profile.get("measurementSystem")
        return info
