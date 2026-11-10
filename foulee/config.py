"""Chemins et paramètres d'exécution de Foulée.

Tout ce qui touche au disque passe par ici, pour qu'il n'y ait qu'un seul
endroit à lire quand on se demande « où est rangé quoi ? ».
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Foulée"
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
STATIC_DIR = PACKAGE_DIR / "static"
DEFAULT_PORT = 8770


def is_demo() -> bool:
    """Le mode démo travaille sur une base séparée remplie de données fictives."""
    return os.environ.get("FOULEE_DEMO", "") == "1"


def set_demo(enabled: bool) -> None:
    os.environ["FOULEE_DEMO"] = "1" if enabled else "0"


def data_dir() -> Path:
    """Dossier des données (base SQLite, fichiers FIT, journaux).

    Par défaut : le sous-dossier ``data`` du projet. On peut le déplacer avec
    la variable d'environnement ``FOULEE_DATA``.
    """
    path = Path(os.environ.get("FOULEE_DATA") or (PROJECT_ROOT / "data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def secrets_dir() -> Path:
    """Dossier local (jamais synchronisé) pour le jeton temporaire Garmin.

    Windows : %LOCALAPPDATA%\\Foulee — le dossier « Local » n'est pas itinérant
    et n'est pas synchronisé par OneDrive.
    """
    override = os.environ.get("FOULEE_SECRETS")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / "Foulee"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        path = Path(base) / "foulee"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / ("foulee-demo.db" if is_demo() else "foulee.db")


def fit_dir() -> Path:
    path = data_dir() / ("fit-demo" if is_demo() else "fit")
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def token_cache_file() -> Path:
    return secrets_dir() / "garmin-jeton.json"
