"""Saisie d'une clé secrète dans la console, sans l'afficher ni l'abîmer.

Coller dans une invite masquée est piégeux : comme rien ne s'affiche, on colle
souvent deux fois ; Ctrl+V peut arriver comme un caractère de contrôle ; une
sélection à la souris emporte des retours à la ligne et l'invite s'arrête au
premier. Foulée lit donc de préférence la clé dans le presse-papiers de Windows,
la nettoie, puis décrit ce qu'elle a lu (longueur, début attendu) sans jamais la
montrer.
"""

from __future__ import annotations

import subprocess
import sys
import time

GARMIN_PREFIX = "GCDC_"
CF_UNICODETEXT = 13

# Caractères invisibles qu'une page web ou un gestionnaire de mots de passe peut glisser dans une copie
_INVISIBLES = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)
_QUOTES = "\"'`«»“”‘’"


# ------------------------------------------------------------------ nettoyage
def normalize_key(raw: str) -> tuple[str, list[str]]:
    """Clé nettoyée et liste des corrections faites (sans rien révéler de la clé)."""
    notes: list[str] = []
    text = raw.translate(_INVISIBLES)
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        notes.append(f"{len(lines)} morceaux recollés")
    key = "".join(text.split())
    unquoted = key.strip(_QUOTES)
    if unquoted != key:
        notes.append("guillemets retirés")
        key = unquoted
    half = len(key) // 2
    if half and len(key) % 2 == 0 and key[:half] == key[half:]:
        key = key[:half]
        notes.append("clé présente deux fois, un seul exemplaire gardé")
    return key, notes


def looks_like_garmin_key(key: str) -> bool:
    return key.startswith(GARMIN_PREFIX)


def describe_key(key: str) -> str:
    """Ce qu'on peut dire d'une clé sans la dévoiler : sa longueur et son début attendu."""
    start = (f"commence bien par {GARMIN_PREFIX}" if looks_like_garmin_key(key)
             else f"ne commence pas par {GARMIN_PREFIX} comme une clé Garmin")
    return f"{len(key)} caractère{'s' if len(key) > 1 else ''}, {start}"


def key_problem(key: str) -> str | None:
    """Raison pour laquelle ce texte ne peut pas être une clé ; None s'il est plausible."""
    if not key:
        return "aucun texte"
    if key.count(GARMIN_PREFIX) > 1:
        return f"{key.count(GARMIN_PREFIX)} clés à la suite (une seule suffit)"
    odd = sum(1 for ch in key if not 0x21 <= ord(ch) <= 0x7E)
    if odd:
        return (f"{odd} caractère{'s' if odd > 1 else ''} impossible{'s' if odd > 1 else ''} dans une clé "
                "(accent, symbole ou caractère de contrôle)")
    return None


# -------------------------------------------------------------- presse-papiers
def clipboard_available() -> bool:
    return sys.platform == "win32"


def _win32():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    return ctypes, user32, kernel32


def _open_clipboard(user32) -> bool:
    # Une autre application peut tenir le presse-papiers un court instant
    for _ in range(20):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.05)
    return False


def _read_clipboard_win32() -> str | None:
    ctypes, user32, kernel32 = _win32()
    if not _open_clipboard(user32):
        return None
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _read_clipboard_powershell() -> str | None:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-Clipboard -Raw"],
            capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def read_clipboard() -> str | None:
    """Texte du presse-papiers ; "" s'il ne contient pas de texte ; None s'il est illisible."""
    if not clipboard_available():
        return None
    try:
        text = _read_clipboard_win32()
    except Exception:  # API Windows indisponible ou refusée : on passe par PowerShell
        text = None
    return text if text is not None else _read_clipboard_powershell()


def clear_clipboard() -> bool:
    if not clipboard_available():
        return False
    try:
        _, user32, _ = _win32()
        if not _open_clipboard(user32):
            return False
        try:
            return bool(user32.EmptyClipboard())
        finally:
            user32.CloseClipboard()
    except Exception:
        return False


# ---------------------------------------------------------------------- console
def drain_console_input() -> None:
    """Jette ce qui reste dans le tampon du clavier (fin d'un collage, second collage)."""
    if sys.platform != "win32":
        return
    try:
        import msvcrt

        time.sleep(0.05)
        while msvcrt.kbhit():
            msvcrt.getwch()
    except Exception:
        pass
