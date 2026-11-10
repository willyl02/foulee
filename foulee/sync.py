"""Chef d'orchestre des synchros.

Une seule synchro à la fois (verrou), quelle que soit son origine : bouton de
l'interface, tâche planifiée Windows ou demande à Claude.

Les sources sont déclarées dans ``SOURCES`` : ajouter Withings ou Strava plus
tard, ce sera ajouter une entrée ici et un module à côté de ``garmin/``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date
from typing import Callable

from . import config, db
from .garmin import sync as garmin_sync

LOG = logging.getLogger("foulee.sync")
Progress = Callable[[str, float | None], None]

SOURCES = {
    "garmin": garmin_sync.run,
}


class SyncBusy(Exception):
    pass


KEY_REFUSED = "cle_refusee"


def _pid_alive(pid: int) -> bool:
    """Le processus existe-t-il encore ? (une synchro coupée net laisse son verrou derrière elle)"""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # accès refusé : le processus existe
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock_path():
    return config.data_dir() / ("sync-demo.lock" if config.is_demo() else "sync.lock")


def _lock_held(path) -> bool:
    """Le verrou est-il tenu par une synchro vivante (processus présent, verrou de moins de 2 heures) ?"""
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return False
    if age >= 7200:
        return False
    try:
        pid = int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return age < 60  # verrou en train d'être écrit
    return _pid_alive(pid)


class _Lock:
    """Verrou par fichier. Libéré d'office si son processus a disparu ou au bout de 2 heures."""

    def __init__(self) -> None:
        self.path = _lock_path()

    def __enter__(self) -> "_Lock":
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _lock_held(self.path):
                raise SyncBusy("Une synchro est déjà en cours.") from None
            LOG.info("Verrou de synchro abandonné : je le retire")
            self.path.unlink(missing_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as handle:
            handle.write(str(os.getpid()))
        return self

    def __exit__(self, *exc: object) -> None:
        self.path.unlink(missing_ok=True)


def is_running() -> bool:
    return _lock_held(_lock_path())


def run(*, since: date | None = None, fit_days: int | None = None, with_fit: bool = True,
        progress: Progress | None = None, sources: list[str] | None = None) -> dict:
    """Lance la synchro de toutes les sources (ou de celles demandées)."""
    progress = progress or (lambda message, fraction=None: None)
    if config.is_demo():
        return {"statut": "demo", "message": "Mode démo : pas de synchro, les données sont fictives."}
    results: dict = {}
    with _Lock():
        with db.session() as conn:
            started = db.now_iso()
            status = "ok"
            for name in sources or list(SOURCES):
                try:
                    results[name] = SOURCES[name](conn, since=since, fit_days=fit_days, with_fit=with_fit,
                                                  progress=progress)
                    if results[name].get("erreurs"):
                        status = "partiel"
                    if name == "garmin":
                        db.delete_meta(conn, KEY_REFUSED)
                except Exception as exc:  # on note l'échec d'une source sans bloquer les autres
                    LOG.exception("Synchro %s en échec", name)
                    results[name] = {"erreur": str(exc)}
                    status = "echec"
                    if name == "garmin" and getattr(exc, "key_rejected", False):
                        # L'interface affichera « Garmin refuse ta clé : remplace-la »
                        previous = key_refused(conn) or {}
                        db.set_meta(conn, KEY_REFUSED, json.dumps({
                            "depuis": previous.get("depuis") or db.now_iso(),
                            "statut": getattr(exc, "status", None), "detail": getattr(exc, "detail", ""),
                        }, ensure_ascii=False))
            finished = db.now_iso()
            conn.execute(
                "INSERT INTO sync_log(started_at, finished_at, source, status, summary) VALUES (?, ?, ?, ?, ?)",
                (started, finished, ",".join(results), status, json.dumps(results, ensure_ascii=False)),
            )
            if status != "echec":
                db.set_meta(conn, "last_sync", finished)
            conn.commit()
    progress("Synchro terminée", 1.0)
    return {"statut": status, "debut": started, "fin": finished, "sources": results}


def key_refused(conn) -> dict | None:
    """Depuis quand Garmin refuse la clé enregistrée (None si tout va bien)."""
    raw = db.get_meta(conn, KEY_REFUSED)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def last_sync_info(conn) -> dict:
    row = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
    info = {"derniere_reussie": db.get_meta(conn, "last_sync"), "en_cours": is_running()}
    if row:
        info["derniere"] = {"fin": row["finished_at"], "statut": row["status"],
                            "resume": json.loads(row["summary"] or "{}")}
    return info
