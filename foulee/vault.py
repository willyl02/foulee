"""Rangement de tes secrets : la clé API Garmin, l'accès à Withings (ClientID, Secret et jetons
de ton appli Withings), l'accès à Strava (Client ID et Client Secret de l'appli Strava de
l'installation, jetons de chaque profil), le lien de publication du calendrier d'entraînement
(quiconque le connaît lit le calendrier) et le jeton GitHub éventuel (pour chercher les mises à
jour tant que le dépôt de Foulée est privé).

- Windows : Gestionnaire d'identification Windows (entrée « Foulee »), chiffré
  avec ta session. Si la clé était trop longue pour lui, repli automatique sur
  un fichier chiffré par DPAPI : même protection, seule ta session Windows
  peut le relire.
- Autres systèmes (le serveur, les tests) : fichier lisible par toi seul
  (FOULEE_COFFRE=fichier impose ce mode, y compris sous Windows : tests).
- La variable d'environnement GARMIN_PERSONAL_API_KEY, si elle existe, passe
  avant tout le reste (pour le profil principal seulement).

Profils : chaque profil a sa clé Garmin, rangée sous un nom suffixé par son identifiant
(« garmin-personal-api-key-p1a2b3 », « garmin-cle-p1a2b3.txt ») ; le profil principal
garde les noms d'avant les profils. Le jeton GitHub reste celui de l'installation.

Ni l'interface web ni Claude ne lisent jamais la clé : seul le connecteur
Garmin l'utilise, pour l'échanger contre un jeton temporaire.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import config

SERVICE = "Foulee"
USERNAME = "garmin-personal-api-key"
ENV_VAR = "GARMIN_PERSONAL_API_KEY"

# Secrets rangés par Foulée : nom → (entrée du Gestionnaire d'identification, nom de fichier, variable d'environnement)
SECRETS = {
    "garmin": (USERNAME, "garmin-cle", ENV_VAR),
    "github": ("github-jeton", "github-jeton", "FOULEE_GITHUB_TOKEN"),  # dépôt privé : vérifier les mises à jour
    "withings": ("withings-acces", "withings-acces", None),  # ClientID, Secret et jetons de l'appli Withings
    "strava-appli": ("strava-appli", "strava-appli", None),  # Client ID et Client Secret de l'appli Strava
    "strava": ("strava-acces", "strava-acces", None),        # jetons Strava du profil
    "calendrier": ("calendrier-lien", "calendrier-lien", None),  # lien de publication du calendrier (iCal)
}
# un exemplaire par profil (l'appli Strava : un pour l'installation)
PER_PROFILE = {"garmin", "withings", "strava", "calendrier"}


def _entry(name: str) -> tuple[str, str, str | None]:
    """(entrée du Gestionnaire d'identification, nom de fichier, variable d'environnement) du profil courant."""
    username, stem, env_var = SECRETS[name]
    suffix = config.profile_suffix() if name in PER_PROFILE else ""
    if suffix:  # autre profil que le principal : ni la même entrée, ni la variable d'environnement
        return f"{username}{suffix}", f"{stem}{suffix}", None
    return username, stem, env_var


def _windows_store() -> bool:
    """Gestionnaire d'identification Windows (sinon : fichier protégé)."""
    return sys.platform == "win32" and os.environ.get("FOULEE_COFFRE") != "fichier"


def _dpapi_file(name: str = "garmin") -> Path:
    return config.secrets_dir() / f"{_entry(name)[1]}.dpapi"


def _plain_file(name: str = "garmin") -> Path:
    return config.secrets_dir() / f"{_entry(name)[1]}.txt"


# ------------------------------------------------------------------ DPAPI
def _dpapi(data: bytes, *, protect: bool) -> bytes:  # pragma: no cover - Windows uniquement
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    if protect:
        func = crypt32.CryptProtectData
        func.argtypes = [
            ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        ok = func(ctypes.byref(blob_in), "Foulee", None, None, None, flags, ctypes.byref(blob_out))
    else:
        func = crypt32.CryptUnprotectData
        func.argtypes = [
            ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        ok = func(ctypes.byref(blob_in), None, None, None, None, flags, ctypes.byref(blob_out))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


# ----------------------------------------------------------------- public
def get_secret(name: str) -> str | None:
    username, _file, env_var = _entry(name)
    env = os.environ.get(env_var, "").strip() if env_var else ""
    if env:
        return env
    if _windows_store():  # pragma: no cover - Windows uniquement
        try:
            import keyring

            value = keyring.get_password(SERVICE, username)
            if value:
                return value.strip()
        except Exception:
            pass
        path = _dpapi_file(name)
        if path.exists():
            try:
                return _dpapi(path.read_bytes(), protect=False).decode("utf-8").strip()
            except OSError:
                return None
        return None
    path = _plain_file(name)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        return value or None
    return None


def set_secret(name: str, value: str) -> str:
    """Range un secret et renvoie une phrase décrivant où il est."""
    username = _entry(name)[0]
    value = value.strip()
    if not value:
        raise ValueError("Valeur vide")
    if _windows_store():  # pragma: no cover - Windows uniquement
        try:
            import keyring

            keyring.set_password(SERVICE, username, value)
            if _dpapi_file(name).exists():
                _dpapi_file(name).unlink()
            return "Gestionnaire d'identification Windows (entrée « Foulee »)"
        except Exception:
            _dpapi_file(name).write_bytes(_dpapi(value.encode("utf-8"), protect=True))
            return f"fichier chiffré par Windows (DPAPI) : {_dpapi_file(name)}"
    path = _plain_file(name)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(value)
    return f"fichier protégé : {path}"


def delete_secret(name: str) -> bool:
    username = _entry(name)[0]
    removed = False
    if _windows_store():  # pragma: no cover - Windows uniquement
        try:
            import keyring

            keyring.delete_password(SERVICE, username)
            removed = True
        except Exception:
            pass
        if _dpapi_file(name).exists():
            _dpapi_file(name).unlink()
            removed = True
    elif _plain_file(name).exists():
        _plain_file(name).unlink()
        removed = True
    return removed


def get_key() -> str | None:
    return get_secret("garmin")


def set_key(key: str) -> str:
    return set_secret("garmin", key)


def delete_key() -> bool:
    removed = delete_secret("garmin")
    token = config.token_cache_file()
    if token.exists():
        token.unlink()
    return removed


def has_key() -> bool:
    return bool(get_key())
