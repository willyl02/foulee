"""Chef d'orchestre des synchros.

Une seule synchro à la fois (verrou), quelle que soit son origine : bouton de
l'interface, tâche planifiée Windows ou demande à Claude.

Les sources sont déclarées dans ``SOURCES`` (Garmin, Withings ; Strava plus tard : une
entrée ici et un module à côté de ``garmin/``). Garmin est toujours de la partie ; Withings
seulement quand le compte est connecté (Réglages → Withings).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date
from typing import Callable

from . import config, db, vault
from .garmin import sync as garmin_sync
from .withings import client as withings_client
from .withings import sync as withings_sync

LOG = logging.getLogger("foulee.sync")
Progress = Callable[[str, float | None], None]

SOURCES = {
    "garmin": garmin_sync.run,
    "withings": withings_sync.run,
}
LABELS = {"garmin": "Garmin", "withings": "Withings"}
SETTINGS_SECTIONS = {"garmin": "cle", "withings": "withings"}  # où la réparer dans les Réglages


def active_sources() -> list[str]:
    """Les sources de la synchro du profil courant : Garmin, plus Withings si son compte est connecté."""
    names = ["garmin"]
    if withings_client.connected():
        names.append("withings")
    return names


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
            names = [name for name in (sources or active_sources()) if name in SOURCES]
            failed, partial = 0, False
            for name in names:
                try:
                    results[name] = SOURCES[name](conn, since=since, fit_days=fit_days, with_fit=with_fit,
                                                  progress=progress)
                    if results[name].get("erreurs"):
                        partial = True
                    if name == "garmin":
                        db.delete_meta(conn, KEY_REFUSED)
                    if name == "withings":
                        db.delete_meta(conn, withings_sync.REFUSED)
                except Exception as exc:  # on note l'échec d'une source sans bloquer les autres
                    LOG.exception("Synchro %s en échec", name)
                    results[name] = {"erreur": str(exc)}
                    failed += 1
                    if name == "garmin" and getattr(exc, "key_rejected", False):
                        # L'interface affichera « Garmin refuse ta clé : remplace-la »
                        _note_refusal(conn, KEY_REFUSED, exc)
                    if name == "withings" and getattr(exc, "access_refused", False):
                        # « Withings n'accepte plus l'accès de Foulée : reconnecte ton compte »
                        _note_refusal(conn, withings_sync.REFUSED, exc)
            # Échec si rien n'a marché ; partiel si une source (ou un de ses flux) a échoué
            status = "echec" if names and failed == len(names) else "partiel" if failed or partial else "ok"
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


def _note_refusal(conn, key: str, exc: Exception) -> None:
    raw = db.get_meta(conn, key)
    try:
        previous = json.loads(raw) if raw else {}
    except ValueError:
        previous = {}
    db.set_meta(conn, key, json.dumps({
        "depuis": previous.get("depuis") or db.now_iso(),
        "statut": getattr(exc, "status", None), "detail": getattr(exc, "detail", ""),
    }, ensure_ascii=False))


def key_refused(conn) -> dict | None:
    """Depuis quand Garmin refuse la clé enregistrée (None si tout va bien)."""
    raw = db.get_meta(conn, KEY_REFUSED)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def _history(conn, limit: int = 120) -> list[tuple[str, dict]]:
    """Les dernières synchros, de la plus récente à la plus ancienne : (fin, résultat de chaque source)."""
    out = []
    for row in conn.execute("SELECT finished_at, summary FROM sync_log ORDER BY id DESC LIMIT ?", (limit,)):
        try:
            results = json.loads(row["summary"] or "{}")
        except ValueError:
            continue
        if isinstance(results, dict):
            out.append((row["finished_at"], results))
    return out


def connections(conn) -> list[dict]:
    """Pastilles de l'en-tête : une par source branchée sur le profil (Garmin toujours, Withings s'il est
    connecté ; une autre source plus tard : une entrée de plus dans ``SOURCES`` et ``LABELS``).

    État « ok » : la dernière synchro de la source a abouti (même avec des alertes dans le journal) ;
    « ko » : elle n'a pas abouti, ou la clé (l'accès) manque ou est refusée ; « attente » : pas encore
    de synchro. Jamais de clé ni de jeton dans la réponse : seulement l'état et le message d'erreur."""
    from .withings import vue as withings_vue  # (import tardif : withings.vue importe les vues)

    demo = config.is_demo()
    names = ["garmin"]
    if withings_vue.families(conn) if demo else (withings_client.connected() or withings_vue.refused(conn)):
        names.append("withings")
    history = [] if demo else _history(conn)
    out = []
    for name in names:
        runs = [(when, res[name]) for when, res in history if isinstance(res.get(name), dict)]
        last = runs[0] if runs else None
        item: dict = {
            "cle": name, "nom": LABELS.get(name, name.capitalize()), "reglages": SETTINGS_SECTIONS.get(name),
            "derniere": last[0] if last else None,
            "derniere_reussie": next((when for when, res in runs if not res.get("erreur")), None),
            "erreur": None, "alertes": 0, "bloque": False,  # bloque : rien à faire sans passer par les Réglages
        }
        refusal = key_refused(conn) if name == "garmin" else withings_vue.refused(conn)
        if demo:
            item.update(etat="ok", texte="Mode démo : données fictives, pas de synchro.")
        elif name == "garmin" and not vault.has_key():
            item.update(etat="ko", texte="Aucune clé API Garmin : la synchro est en pause.", bloque=True)
        elif refusal:
            text = ("Garmin refuse ta clé API : la synchro est en pause." if name == "garmin"
                    else "Withings n'accepte plus l'accès de Foulée : reconnecte ton compte.")
            item.update(etat="ko", texte=text, depuis=refusal.get("depuis"), bloque=True)
        elif last is None:
            item.update(etat="attente", texte="Pas encore synchronisé.")
        elif last[1].get("erreur"):
            item.update(etat="ko", texte="La dernière synchro n'a pas abouti.", erreur=str(last[1]["erreur"])[:300])
        else:
            item.update(etat="ok", texte="Connexion OK.", alertes=len(last[1].get("erreurs") or []))
        out.append(item)
    return out


def last_sync_info(conn) -> dict:
    row = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
    info = {"derniere_reussie": db.get_meta(conn, "last_sync"), "en_cours": is_running()}
    if row:
        info["derniere"] = {"fin": row["finished_at"], "statut": row["status"],
                            "resume": json.loads(row["summary"] or "{}")}
    return info
