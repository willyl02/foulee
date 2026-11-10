"""Application de bureau : Foulée tourne en arrière-plan, avec son icône près de l'horloge.

C'est ce que lancent le menu Démarrer et le raccourci du Bureau (« foulee app ») :
- l'interface tourne dans ce processus, sur http://127.0.0.1:8770 (ce PC seulement) ;
- l'icône près de l'horloge : Ouvrir Foulée, Synchroniser maintenant, Lancer au
  démarrage de Windows, Quitter ;
- la synchro se fait toute seule : au démarrage si la dernière date de plus de
  3 heures, puis toutes les 3 heures (la mise en veille est prise en compte) ;
- une seule copie à la fois : relancer Foulée ouvre simplement l'interface.

Ailleurs que sous Windows (ou avec --sans-icone), même chose sans l'icône.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import __version__, config

LOG = logging.getLogger("foulee.app")

MUTEX_NAME = "Local\\Foulee-app"
INSTANCE_FILE = "app.json"
SYNC_EVERY = 3 * 3600          # une synchro toutes les 3 heures…
RETRY_AFTER_FAILURE = 30 * 60  # …et pas plus d'un essai par demi-heure quand ça échoue
CHECK_EVERY = 10 * 60          # on regarde l'heure régulièrement : la mise en veille fausse les minuteries
FIRST_CHECK_DELAY = 60
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
RUN_VALUE = "Foulee"


# ------------------------------------------------------------ une seule copie
def mutex_name() -> str:
    """Nom du verrou système ; propre au dossier de configuration quand il est imposé (tests)."""
    custom = os.environ.get("FOULEE_CONFIG")
    if not custom:
        return MUTEX_NAME
    return f"{MUTEX_NAME}-{hashlib.sha1(os.path.abspath(custom).encode()).hexdigest()[:12]}"


class SingleInstance:
    """Verrou système : un « mutex » nommé sous Windows, un fichier verrouillé ailleurs."""

    def __init__(self) -> None:
        self._handle = None
        self._file = None

    def acquire(self) -> bool:
        if sys.platform == "win32":  # pragma: no cover - Windows uniquement
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            handle = kernel32.CreateMutexW(None, False, mutex_name())
            if not handle:
                return True  # impossible de vérifier : on ne bloque pas
            if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
                kernel32.CloseHandle(ctypes.c_void_p(handle))
                return False
            self._handle = handle
            return True
        import fcntl

        handle = open(config.user_config_dir() / "app.lock", "w")  # reste ouvert : le verrou dure autant que l'appli
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._file = handle
        return True

    def release(self) -> None:
        if self._handle:  # pragma: no cover - Windows uniquement
            import ctypes

            ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(self._handle))
            self._handle = None
        if self._file:
            self._file.close()
            self._file = None


def instance_file() -> Path:
    return config.user_config_dir() / INSTANCE_FILE


def read_instance() -> dict | None:
    """Où tourne la copie déjà lancée (numéro de processus, port)."""
    try:
        data = json.loads(instance_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("port"), int) else None


def write_instance(port: int) -> None:
    path = instance_file()
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"pid": os.getpid(), "port": port, "version": __version__,
                                     "depuis": time.time()}), encoding="utf-8")
    os.replace(temporary, path)


def clear_instance() -> None:
    info = read_instance()
    if info and info.get("pid") == os.getpid():
        instance_file().unlink(missing_ok=True)


def url_for(port: int, page: str = "") -> str:
    return f"http://127.0.0.1:{port}/{page}"


# ------------------------------------------------------------------- réseau
def bind_socket(preferred: int, tries: int = 20) -> socket.socket:
    """Réserve un port sur 127.0.0.1 : le port habituel, sinon un des suivants s'il est pris."""
    ports = [preferred] if preferred == 0 else range(preferred, preferred + tries)
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows : personne d'autre sur ce port
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            sock.close()
            continue
        return sock
    raise OSError(f"Aucun port libre entre {preferred} et {preferred + tries - 1} : un autre programme les occupe.")


class WebServer:
    """L'interface (uvicorn) dans un fil d'exécution à part."""

    def __init__(self, app, sock: socket.socket) -> None:
        import uvicorn

        # log_config=None : les messages vont dans le journal de Foulée (pas de console ici)
        self.server = uvicorn.Server(uvicorn.Config(app, log_config=None, log_level="warning", access_log=False,
                                                    proxy_headers=False, lifespan="off"))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [sock]}, name="foulee-web",
                                       daemon=True)

    def start(self, timeout: float = 30) -> None:
        self.thread.start()
        deadline = time.monotonic() + timeout
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("L'interface n'a pas pu démarrer (voir le journal app.log).")
            time.sleep(0.05)

    def stop(self) -> None:
        self.server.should_exit = True
        if self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(10)


# ------------------------------------------------- démarrage avec Windows
def gui_executable() -> str:
    """Programme à lancer sans fenêtre noire : Foulee.exe (installé), sinon pythonw.exe."""
    executable = Path(sys.executable)
    for name in ("Foulee.exe", "pythonw.exe"):
        candidate = executable.with_name(name)
        if candidate.exists():
            return str(candidate)
    return str(executable)


def launch_command(*extra: str) -> str:
    return subprocess.list2cmdline([gui_executable(), "-m", "foulee", "app", *extra])


def startup_supported() -> bool:
    return sys.platform == "win32"


def startup_enabled() -> bool:  # pragma: no cover - Windows uniquement
    """Foulée se lance-t-il à l'ouverture de session (et Windows ne l'a-t-il pas désactivé) ?"""
    if not startup_supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, RUN_VALUE)
    except OSError:
        return False
    if not value:
        return False
    try:  # désactivé depuis le Gestionnaire des tâches (onglet « Démarrage ») ?
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as key:
            state, _kind = winreg.QueryValueEx(key, RUN_VALUE)
        return not (isinstance(state, bytes) and state and state[0] % 2 == 1)
    except OSError:
        return True


def set_startup(enabled: bool) -> None:  # pragma: no cover - Windows uniquement
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, launch_command("--demarrage"))
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass
    try:  # on efface aussi un éventuel « désactivé » du Gestionnaire des tâches
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE)
    except OSError:
        pass


# ---------------------------------------------------------- synchro auto
def _parse(stamp: str | None) -> float | None:
    try:
        return datetime.fromisoformat(stamp).timestamp() if stamp else None
    except ValueError:
        return None


class AutoSync:
    """Synchro toutes les 3 heures, d'après l'heure de la dernière synchro réussie.

    Elle ne démarre qu'après une première synchro réussie : le premier import est un choix
    (date de début, ou reprise des données d'une ancienne installation).
    """

    def __init__(self, start: Callable[[], bool], wait_result: Callable[[], dict], notify: Callable[[str], None],
                 *, every: float = SYNC_EVERY, check_every: float = CHECK_EVERY,
                 first_delay: float = FIRST_CHECK_DELAY, clock: Callable[[], float] = time.time) -> None:
        self.start, self.wait_result, self.notify = start, wait_result, notify
        self.every, self.check_every, self.first_delay, self.clock = every, check_every, first_delay, clock
        self.last_attempt: float | None = None
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._loop, name="foulee-synchro-auto", daemon=True)

    def due(self) -> bool:
        from . import db, sync, vault

        if config.is_demo() or not vault.has_key():
            return False
        now = self.clock()
        if self.last_attempt and now - self.last_attempt < RETRY_AFTER_FAILURE:
            return False
        with db.session(readonly=True) as conn:
            if sync.key_refused(conn):
                return False  # Garmin refuse la clé : on attend qu'elle soit remplacée
            last = _parse(db.get_meta(conn, "last_sync"))
        if last is None:
            # Jamais synchronisé ici : le premier import (ou la reprise d'une ancienne installation)
            # se décide sur la page d'accueil, jamais tout seul
            return False
        return now - last >= self.every - 120

    def tick(self) -> dict | None:
        """Une vérification : lance la synchro si elle est due et renvoie son résultat."""
        if not self.due() or not self.start():
            return None
        from . import db, sync

        self.last_attempt = self.clock()
        state = self.wait_result()
        if (state.get("resultat") or {}).get("statut") in ("ok", "partiel"):
            self.last_attempt = None
        else:
            with db.session(readonly=True) as conn:
                refused = sync.key_refused(conn)
            if refused:
                self.notify("Garmin refuse ta clé API : remplace-la dans les Réglages de Foulée.")
        return state

    def _loop(self) -> None:
        if self.stopped.wait(self.first_delay):
            return
        while True:
            try:
                self.tick()
            except Exception:  # la synchro auto ne doit jamais arrêter l'application
                LOG.exception("Synchro automatique impossible")
            if self.stopped.wait(self.check_every):
                return

    def begin(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stopped.set()


# --------------------------------------------------------------- l'appli
def show_error(message: str) -> None:
    """Message visible même sans console (lancement depuis le menu Démarrer)."""
    LOG.error(message)
    if sys.platform == "win32":  # pragma: no cover - Windows uniquement
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "Foulée", 0x10 | 0x40000)  # erreur, premier plan
    else:
        print(message, file=sys.stderr)


def tray_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception:  # bibliothèque absente ou cassée : l'interface reste utilisable
        LOG.exception("Icône près de l'horloge indisponible")
        return False
    return True


class DesktopApp:
    def __init__(self, *, port: int = config.DEFAULT_PORT, open_browser: bool = True, tray: bool = True,
                 after_update: bool = False) -> None:
        self.preferred_port = port
        self.open_browser = open_browser
        self.tray = tray
        self.after_update = after_update
        self.port: int | None = None
        self.web: WebServer | None = None
        self.icon = None
        self.job = None
        self.autosync: AutoSync | None = None
        self._stopped = threading.Event()
        self._stop_lock = threading.Lock()

    # -------------------------------------------------------------- actions
    def url(self, page: str = "") -> str:
        return url_for(self.port or self.preferred_port, page)

    def open_ui(self, page: str = "") -> None:
        webbrowser.open(self.url(page))

    def notify(self, message: str) -> None:
        LOG.info("Notification : %s", message)
        if self.icon is not None:
            try:
                self.icon.notify(message, "Foulée")
            except Exception:  # notifications coupées dans Windows : sans importance
                LOG.debug("Notification impossible", exc_info=True)

    def can_sync(self) -> bool:
        from . import vault

        return bool(self.job) and not config.is_demo() and vault.has_key() and not self.job.snapshot()["en_cours"]

    def wait_for_sync(self, timeout: float = 4 * 3600) -> dict:
        deadline = time.monotonic() + timeout
        while self.job.snapshot()["en_cours"] and time.monotonic() < deadline and not self._stopped.is_set():
            time.sleep(1)
        return self.job.snapshot()

    def sync_now(self) -> None:
        """Bouton « Synchroniser maintenant » : lance la synchro et en donne le résultat."""
        from . import vault

        if not vault.has_key():
            self.notify("Ajoute d'abord ta clé API Garmin dans Foulée.")
            self.open_ui()
            return
        if not self.job.start():
            self.notify("Une synchro est déjà en cours.")
            return

        def report() -> None:
            state = self.wait_for_sync()
            self.notify(sync_summary(state))

        threading.Thread(target=report, name="foulee-synchro-bouton", daemon=True).start()

    def toggle_startup(self) -> None:  # pragma: no cover - Windows uniquement
        try:
            set_startup(not startup_enabled())
        except OSError as exc:
            self.notify(f"Réglage impossible : {exc}")

    def stop(self) -> None:
        """Arrête tout proprement (menu Quitter, mise à jour, désinstallation)."""
        with self._stop_lock:
            if self._stopped.is_set():
                return
            self._stopped.set()
        LOG.info("Arrêt de Foulée")
        if self.autosync:
            self.autosync.stop()
        if self.web:
            self.web.stop()
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                LOG.debug("Icône déjà fermée", exc_info=True)

    # ------------------------------------------------------------- démarrage
    def run(self) -> int:
        from . import updates
        from .web import create_app

        sock = bind_socket(self.preferred_port)
        self.port = sock.getsockname()[1]
        os.environ["FOULEE_ECOUTE"] = "127.0.0.1"
        os.environ["FOULEE_PORT"] = str(self.port)
        app = create_app()
        app.state.quit = self.stop
        self.job = app.state.sync_job
        self.web = WebServer(app, sock)
        self.web.start()
        write_instance(self.port)
        LOG.info("Foulée %s prêt sur %s", __version__, self.url())
        updates.set_exit_hook(self.stop)
        self.autosync = AutoSync(self.job.start, self.wait_for_sync, self.notify)
        self.autosync.begin()
        if self.open_browser:
            self.open_ui()
        try:
            if self.tray and tray_available():
                try:
                    self._run_tray()  # rend la main quand on quitte
                except Exception:  # session sans bureau, Explorer redémarré… : on continue sans icône
                    LOG.exception("Icône près de l'horloge impossible : Foulée continue sans elle")
                    self.icon = None
            while not self._stopped.wait(0.5):
                pass
        finally:
            self.stop()
            clear_instance()
        return 0

    def _run_tray(self) -> None:  # pragma: no cover - Windows uniquement
        import pystray

        from .icon import draw

        menu = pystray.Menu(
            pystray.MenuItem("Ouvrir Foulée", lambda icon, item: self.open_ui(), default=True),
            pystray.MenuItem("Synchroniser maintenant", lambda icon, item: self.sync_now(),
                             enabled=lambda item: self.can_sync()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Lancer au démarrage de Windows", lambda icon, item: self.toggle_startup(),
                             checked=lambda item: startup_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quitter Foulée", lambda icon, item: self.stop()),
        )
        self.icon = pystray.Icon("Foulee", draw(64), f"Foulée {__version__}", menu)

        def ready(icon) -> None:
            icon.visible = True
            if self.after_update:
                self.notify(f"Foulée {__version__} est installé.")

        self.icon.run(setup=ready)


def sync_summary(state: dict) -> str:
    """Résultat d'une synchro en une phrase."""
    if state.get("erreur"):
        return f"Synchro impossible : {state['erreur']}"
    result = state.get("resultat") or {}
    garmin = (result.get("sources") or {}).get("garmin") or {}
    if "erreur" in garmin:
        return f"Synchro impossible : {garmin['erreur']}"
    new = garmin.get("seances_nouvelles", 0)
    if new:
        return f"Synchro terminée : {new} nouvelle{'s' if new > 1 else ''} séance{'s' if new > 1 else ''}."
    return "Synchro terminée : tout est à jour."


def quit_running(timeout: float = 15) -> bool:
    """Demande à la copie qui tourne de se fermer (installateur, désinstallation). True si plus rien ne tourne."""
    from .sync import _pid_alive

    info = read_instance()
    if not info or not _pid_alive(int(info.get("pid") or 0)):
        return True
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url_for(info["port"], "api/app/quitter"), data=b"", method="POST",
                                     headers={"X-Foulee": "1"})
    try:
        opener.open(request, timeout=5).close()
    except OSError as exc:
        LOG.warning("Demande d'arrêt sans réponse : %s", exc)
    pid = int(info["pid"])
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        current = read_instance()
        if current is None or current.get("pid") != pid:
            # L'application a terminé son arrêt (elle efface app.json en dernier) : le processus suit
            end = time.monotonic() + 3
            while time.monotonic() < end and _pid_alive(pid):
                time.sleep(0.2)
            return True
        time.sleep(0.3)
    return False


def main(*, port: int, at_login: bool, after_update: bool, no_browser: bool, no_tray: bool) -> int:
    instance = SingleInstance()
    if not instance.acquire():
        # Déjà lancé : on se contente d'ouvrir l'interface de la copie qui tourne
        if not (at_login or after_update or no_browser):
            info = read_instance()
            webbrowser.open(url_for(info["port"] if info else port))
        return 0
    try:
        return DesktopApp(port=port, open_browser=not (at_login or after_update or no_browser),
                          tray=not no_tray, after_update=after_update).run()
    except Exception as exc:
        LOG.exception("Foulée n'a pas pu démarrer")
        show_error(f"Foulée n'a pas pu démarrer :\n\n{exc}\n\nDétails dans {config.log_dir() / 'app.log'}")
        return 1
    finally:
        instance.release()
