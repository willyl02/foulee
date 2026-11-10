"""Rangement de ta clé API Garmin.

- Windows : Gestionnaire d'identification Windows (entrée « Foulee »), chiffré
  avec ta session. Si la clé était trop longue pour lui, repli automatique sur
  un fichier chiffré par DPAPI : même protection, seule ta session Windows
  peut le relire.
- Autres systèmes (utile pour les tests) : fichier lisible par toi seul.
- La variable d'environnement GARMIN_PERSONAL_API_KEY, si elle existe, passe
  avant tout le reste.

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


def _dpapi_file() -> Path:
    return config.secrets_dir() / "garmin-cle.dpapi"


def _plain_file() -> Path:
    return config.secrets_dir() / "garmin-cle.txt"


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
def get_key() -> str | None:
    env = os.environ.get(ENV_VAR, "").strip()
    if env:
        return env
    if sys.platform == "win32":  # pragma: no cover - Windows uniquement
        try:
            import keyring

            value = keyring.get_password(SERVICE, USERNAME)
            if value:
                return value.strip()
        except Exception:
            pass
        path = _dpapi_file()
        if path.exists():
            try:
                return _dpapi(path.read_bytes(), protect=False).decode("utf-8").strip()
            except OSError:
                return None
        return None
    path = _plain_file()
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        return value or None
    return None


def set_key(key: str) -> str:
    """Range la clé et renvoie une phrase décrivant où elle est."""
    key = key.strip()
    if not key:
        raise ValueError("Clé vide")
    if sys.platform == "win32":  # pragma: no cover - Windows uniquement
        try:
            import keyring

            keyring.set_password(SERVICE, USERNAME, key)
            if _dpapi_file().exists():
                _dpapi_file().unlink()
            return "Gestionnaire d'identification Windows (entrée « Foulee »)"
        except Exception:
            _dpapi_file().write_bytes(_dpapi(key.encode("utf-8"), protect=True))
            return f"fichier chiffré par Windows (DPAPI) : {_dpapi_file()}"
    path = _plain_file()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(key)
    return f"fichier protégé : {path}"


def delete_key() -> bool:
    removed = False
    if sys.platform == "win32":  # pragma: no cover - Windows uniquement
        try:
            import keyring

            keyring.delete_password(SERVICE, USERNAME)
            removed = True
        except Exception:
            pass
        if _dpapi_file().exists():
            _dpapi_file().unlink()
            removed = True
    elif _plain_file().exists():
        _plain_file().unlink()
        removed = True
    token = config.token_cache_file()
    if token.exists():
        token.unlink()
    return removed


def has_key() -> bool:
    return bool(get_key())
