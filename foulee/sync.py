"""Chef d'orchestre des synchros.

Une seule synchro à la fois (verrou), quelle que soit son origine : bouton de
l'interface, tâche planifiée Windows ou demande à Claude.

Les sources sont déclarées dans ``SOURCES`` (Garmin, Withings, Strava, calendrier : une entrée ici et un
module à côté de ``garmin/``). Garmin est de la partie dès qu'une clé est enregistrée (ou quand
rien d'autre n'est branché) ; Withings et Strava quand leur compte est connecté (Réglages) ; le
calendrier d'entraînement quand son lien est enregistré.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date, datetime
from typing import Callable

from . import calendrier, config, db, vault
from .garmin import sync as garmin_sync
from .strava import client as strava_client
from .strava import sync as strava_sync
from .withings import client as withings_client
from .withings import sync as withings_sync

LOG = logging.getLogger("foulee.sync")
Progress = Callable[[str, float | None], None]

SOURCES = {
    "garmin": garmin_sync.run,
    "withings": withings_sync.run,
    "strava": strava_sync.run,
    "calendrier": calendrier.run,
}
LABELS = {"garmin": "Garmin", "withings": "Withings", "strava": "Strava", "calendrier": "Calendrier"}
SETTINGS_SECTIONS = {"garmin": "cle", "withings": "withings", "strava": "strava",  # où la réparer dans les Réglages
                     "calendrier": "calendrier"}
DATA_SOURCES = ("garmin", "withings", "strava")  # le calendrier ne donne que des séances prévues

# Synchro automatique (Réglages → Synchro et calculs) : un délai par source, en minutes. 3 heures est un bon
# compromis ; en dessous de 30 minutes on solliciterait Garmin et Withings pour rien, au-delà de 12 heures
# les données arriveraient trop tard. Pour une donnée tout de suite : « Synchroniser ».
DEFAULT_INTERVAL = 180
MIN_INTERVAL, MAX_INTERVAL = 30, 720
RETRY_AFTER_FAILURE = 30 * 60  # après un échec, pas plus d'un essai par demi-heure


def active_sources() -> list[str]:
    """Les sources de la synchro du profil courant : Garmin s'il a une clé, Withings et Strava si leur compte est
    connecté, le calendrier si son lien est enregistré. Sans aucune source de données, Garmin quand même : sa
    synchro dit qu'il manque la clé."""
    names = ["garmin"] if vault.has_key() else []
    if withings_client.connected():
        names.append("withings")
    if strava_client.connected():
        names.append("strava")
    names = names or ["garmin"]
    if calendrier.linked():
        names.append("calendrier")
    return names


def can_sync() -> bool:
    """Le profil courant a-t-il de quoi synchroniser : une clé Garmin, un compte Withings ou Strava connecté, ou le
    lien d'un calendrier d'entraînement ?"""
    return bool(vault.has_key() or withings_client.connected() or strava_client.connected() or calendrier.linked())


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
                    _settle(conn, name)
                except Exception as exc:  # on note l'échec d'une source sans bloquer les autres
                    if isinstance(exc, calendrier.CalendarError):
                        LOG.warning("Synchro calendrier en échec : %s", exc)  # (message sans le lien, secret)
                    else:
                        LOG.exception("Synchro %s en échec", name)
                    results[name] = {"erreur": str(exc)}
                    failed += 1
                    _settle(conn, name, exc)
            # Échec si rien n'a marché ; partiel si une source (ou un de ses flux) a échoué
            status = "echec" if names and failed == len(names) else "partiel" if failed or partial else "ok"
            finished = _log(conn, started, results, status)
            # Le calendrier seul ne compte pas comme une synchro des données (premier import, « dernière synchro »)
            if status != "echec" and any(name in DATA_SOURCES for name in results):
                db.set_meta(conn, "last_sync", finished)
            conn.commit()
            if status != "echec":
                from . import coach  # élève relié à un coach : son extrait part, ses séances proposées arrivent

                coach.exchange_quietly(conn)
    progress("Synchro terminée", 1.0)
    return {"statut": status, "debut": started, "fin": finished, "sources": results}


REFUSAL_KEYS = {"garmin": KEY_REFUSED, "withings": withings_sync.REFUSED, "strava": strava_sync.REFUSED,
                "calendrier": calendrier.REFUSED}


def _settle(conn, name: str, exc: Exception | None = None) -> None:
    """Après la synchro d'une source : un succès efface son refus éventuel ; un refus net (clé rejetée par Garmin,
    accès retiré chez Withings ou Strava, lien du calendrier qui ne répond plus) est noté, pour l'interface
    (« remplace ta clé », « reconnecte ton compte », « colle le nouveau lien ») et pour mettre la synchro
    automatique de cette source en pause."""
    key = REFUSAL_KEYS.get(name)
    if key is None:
        return
    if exc is None:
        db.delete_meta(conn, key)
    elif getattr(exc, "key_rejected" if name == "garmin" else "access_refused", False):
        _note_refusal(conn, key, exc)  # (le cache Strava est déjà effacé)


def _log(conn, started: str, results: dict, status: str) -> str:
    finished = db.now_iso()
    conn.execute(
        "INSERT INTO sync_log(started_at, finished_at, source, status, summary) VALUES (?, ?, ?, ?, ?)",
        (started, finished, ",".join(results), status, json.dumps(results, ensure_ascii=False)),
    )
    return finished


def refresh_calendar(conn, feed: tuple[list, dict] | None = None) -> dict:
    """Relit le calendrier tout de suite (lien tout juste collé, bouton « Actualiser ») : même journal, même
    pastille et même état qu'une synchro, sans attendre celle qui tourne peut-être (Garmin, premier import…).
    ``feed`` : le calendrier déjà lu (événements, infos), pour ne pas le télécharger deux fois."""
    started = db.now_iso()
    try:
        result = calendrier.apply(conn, *feed) if feed else calendrier.run(conn)
    except Exception as exc:
        conn.rollback()
        _settle(conn, "calendrier", exc)
        _log(conn, started, {"calendrier": {"erreur": str(exc)}}, "echec")
        conn.commit()
        raise
    _settle(conn, "calendrier")
    _log(conn, started, {"calendrier": result}, "ok")
    conn.commit()
    return result


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


def intervals(settings: dict) -> dict[str, int]:
    """Le délai de synchro automatique de chaque source, en minutes (borné, 3 heures par défaut)."""
    chosen = settings.get("synchro_auto") if isinstance(settings.get("synchro_auto"), dict) else {}
    out = {}
    for name in SOURCES:
        try:
            minutes = int(chosen.get(name) or DEFAULT_INTERVAL)
        except (TypeError, ValueError):
            minutes = DEFAULT_INTERVAL
        out[name] = min(MAX_INTERVAL, max(MIN_INTERVAL, minutes))
    return out


def _timestamp(text: str | None) -> float | None:
    try:
        return datetime.fromisoformat(text).timestamp() if text else None
    except (TypeError, ValueError):
        return None


def due_sources(conn, now: float | None = None) -> list[str]:
    """Les sources du profil courant dont la synchro automatique est due, d'après le délai choisi pour chacune
    et l'heure de sa dernière synchro réussie (journal des synchros).

    Rien avant le premier import (il se décide sur la page d'accueil), sauf le calendrier ; rien pour une clé ou
    un accès refusés (il faut passer par les Réglages), et pas plus d'un essai par demi-heure après un échec."""
    from .strava import vue as strava_vue
    from .withings import vue as withings_vue  # (import tardif : withings.vue importe les vues)

    if config.is_demo() or not can_sync():
        return []
    last_sync = db.get_meta(conn, "last_sync")
    now = time.time() if now is None else now
    every = intervals(db.get_settings(conn))
    history = _history(conn)
    due = []
    for name in active_sources():
        if last_sync is None and name != "calendrier":
            continue
        refusal = {"garmin": key_refused, "withings": withings_vue.refused, "strava": strava_vue.refused,
                   "calendrier": calendrier.refused}.get(name)
        if name == "garmin" and not vault.has_key() or (refusal and refusal(conn)):
            continue
        runs = [(when, res[name]) for when, res in history if isinstance(res.get(name), dict)]
        ok = next((when for when, res in runs if not res.get("erreur")), None)
        if ok is None and name == "garmin":
            ok = last_sync  # journal d'avant la 0.6 : la dernière synchro réussie, toutes sources confondues
        ok_at = _timestamp(ok)
        if ok_at is not None and now - ok_at < every[name] * 60 - 120:
            continue
        failed_at = _timestamp(runs[0][0]) if runs and runs[0][1].get("erreur") else None
        if failed_at is not None and now - failed_at < RETRY_AFTER_FAILURE:
            continue
        due.append(name)
    return due


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
    """Pastilles de l'en-tête : une par source branchée sur le profil (Garmin dès qu'il a une clé, ou quand aucune
    autre source de données n'est branchée ; Withings et Strava quand leur compte est connecté ; le calendrier
    quand son lien est enregistré ; une autre source plus tard : une entrée de plus dans ``SOURCES`` et ``LABELS``).

    État « ok » : la dernière synchro de la source a abouti (même avec des alertes dans le journal) ;
    « ko » : elle n'a pas abouti, ou la clé (l'accès) manque ou est refusée ; « attente » : pas encore
    de synchro. Jamais de clé, de jeton ni de lien dans la réponse : seulement l'état et le message d'erreur."""
    from .strava import cache as strava_cache
    from .strava import vue as strava_vue
    from .withings import vue as withings_vue  # (import tardif : withings.vue importe les vues)

    demo = config.is_demo()
    names = []
    if withings_vue.families(conn) if demo else (withings_client.connected() or withings_vue.refused(conn)):
        names.append("withings")
    if strava_cache.path().exists() if demo else (strava_client.connected() or strava_vue.refused(conn)):
        names.append("strava")
    if demo or vault.has_key() or key_refused(conn) or not names:
        names.insert(0, "garmin")
    if calendrier.status(conn)["lie"] if demo else calendrier.linked():
        names.append("calendrier")
    history = [] if demo else _history(conn)
    refusals = {"garmin": key_refused, "withings": withings_vue.refused, "strava": strava_vue.refused,
                "calendrier": calendrier.refused}
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
        refusal = refusals[name](conn)
        if demo:
            item.update(etat="ok", texte="Mode démo : données fictives, pas de synchro.")
        elif name == "garmin" and not vault.has_key():
            item.update(etat="ko", texte="Aucune clé API Garmin : la synchro est en pause.", bloque=True)
        elif refusal:
            text = {"garmin": "Garmin refuse ta clé API : la synchro est en pause.",
                    "withings": "Withings n'accepte plus l'accès de Foulée : reconnecte ton compte.",
                    "strava": "Strava n'accepte plus l'accès de Foulée : reconnecte ton compte.",
                    "calendrier": "Le lien du calendrier ne répond plus (publication annulée ?) : colle le nouveau "
                                  "lien dans les Réglages."}[name]
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
