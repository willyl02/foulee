"""Ménage avant la désinstallation (lancé par le désinstalleur de Windows).

- ferme l'application si elle tourne ;
- retire Foulée de Claude Desktop, si l'entrée lance cette installation-ci ;
- retire le lancement à l'ouverture de session ;
- sur demande (« effacer mes données »), efface la base, les fichiers FIT, les journaux,
  la configuration et les secrets (clé Garmin, jeton GitHub), ceux de tous les profils.

Seuls les fichiers créés par Foulée sont effacés : si tu as rangé tes données dans un
dossier à toi, le reste de son contenu n'est jamais touché.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import config

LOG = logging.getLogger("foulee.desinstallation")

DATA_FILES = ("foulee.db", "foulee.db-wal", "foulee.db-shm", "foulee-demo.db", "foulee-demo.db-wal",
              "foulee-demo.db-shm", "sync.lock", "sync-demo.lock", "profil.jpg", "profil-demo.jpg",
              "utilisateurs.json", "utilisateurs-demo.json")
PROFILE_DIRS = ("profils", "profils-demo")  # un sous-dossier par profil (autre que le principal)
DATA_PATTERNS = ("diagnostic-*.txt",)
DATA_DIRS = {"fit": ("*.fit",), "fit-demo": ("*.fit",), "logs": ("*.log", "*.log.*")}
BASE_FILES = ("config.json", "config.json.tmp", "app.json", "app.json.tmp", "app.lock", "garmin-jeton.json",
              "acces-reseau.json", "garmin-cle.dpapi", "garmin-cle.txt", "github-jeton.dpapi", "github-jeton.txt")
BASE_PATTERNS = ("garmin-jeton-p*.json", "garmin-cle-p*.dpapi", "garmin-cle-p*.txt")  # ceux des autres profils


def _remove(path: Path, removed: list[str]) -> None:
    try:
        path.unlink()
        removed.append(str(path))
    except FileNotFoundError:
        pass
    except OSError as exc:
        LOG.warning("Impossible d'effacer %s : %s", path, exc)


def erase_data_folder(folder: Path) -> list[str]:
    """Efface les fichiers de Foulée d'un dossier de données, puis le dossier s'il est vide."""
    removed: list[str] = []
    if not folder.is_dir():
        return removed
    for name in DATA_FILES:
        _remove(folder / name, removed)
    for pattern in DATA_PATTERNS:
        for path in folder.glob(pattern):
            _remove(path, removed)
    for sub in PROFILE_DIRS:
        parent = folder / sub
        if parent.is_dir():
            for child in parent.iterdir():
                if child.is_dir():
                    removed += erase_data_folder(child)
            try:
                parent.rmdir()
            except OSError:
                pass
    for sub, patterns in DATA_DIRS.items():
        directory = folder / sub
        if not directory.is_dir():
            continue
        for pattern in patterns:
            for path in directory.glob(pattern):
                if path.is_file():
                    _remove(path, removed)
        try:
            directory.rmdir()  # seulement s'il est vide
        except OSError:
            pass
    try:
        folder.rmdir()
    except OSError:
        pass
    return removed


def erase_everything() -> list[str]:
    """Données (dossier choisi et dossier par défaut), configuration et secrets de Foulée."""
    from . import vault

    from . import utilisateurs

    removed: list[str] = []
    # Les clés des autres profils, tant que leur liste existe encore (vraie et démo)
    demo = config.is_demo()
    for mode in (False, True):
        config.set_demo(mode)
        for entry in utilisateurs.profiles():
            if not entry.get("principal"):
                with config.using_profile(entry):
                    if vault.delete_secret("garmin"):
                        removed.append(f"secret « garmin » du profil {entry['id']}")
    config.set_demo(demo)
    folders = [config.root_dir(), config.default_data_dir()]
    for folder in dict.fromkeys(Path(f) for f in folders):
        removed += erase_data_folder(folder)
    for name in ("garmin", "github"):
        if vault.delete_secret(name):
            removed.append(f"secret « {name} »")
    for base in dict.fromkeys([config.user_config_dir(), config.secrets_dir()]):
        for name in BASE_FILES:
            _remove(base / name, removed)
        for pattern in BASE_PATTERNS:
            for path in base.glob(pattern):
                _remove(path, removed)
        try:
            base.rmdir()
        except OSError:
            pass
    return removed


def before_uninstall(*, erase: bool = False) -> dict:
    from . import claude_desktop, desktop

    report: dict = {"application_fermee": desktop.quit_running()}
    try:
        report["claude"] = claude_desktop.write(remove=True, only_mine=True)
    except OSError as exc:
        report["claude"] = {"erreurs": [str(exc)]}
    if desktop.startup_supported():  # pragma: no cover - Windows uniquement
        try:
            desktop.set_startup(False)
        except OSError:
            pass
    if erase:
        report["effaces"] = erase_everything()
    return report
