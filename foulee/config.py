"""Chemins et paramètres d'exécution de Foulée.

Tout ce qui touche au disque passe par ici, pour qu'il n'y ait qu'un seul
endroit à lire quand on se demande « où est rangé quoi ? ».

Dossier des données, par ordre de priorité :
1. la variable d'environnement FOULEE_DATA (le serveur s'en sert) ;
2. le dossier choisi dans les Réglages, noté dans le fichier de configuration
   de l'utilisateur (config.json) ;
3. le dossier par défaut : ``data`` à côté du code pour une installation
   « développeur » (dossier décompressé), sinon %LOCALAPPDATA%\\Foulee\\donnees
   sous Windows (installation par le .exe) et ~/.local/share/foulee ailleurs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "Foulée"
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
STATIC_DIR = PACKAGE_DIR / "static"
DEFAULT_PORT = 8770
CONFIG_FILE = "config.json"


def is_demo() -> bool:
    """Le mode démo travaille sur une base séparée remplie de données fictives."""
    return os.environ.get("FOULEE_DEMO", "") == "1"


def set_demo(enabled: bool) -> None:
    os.environ["FOULEE_DEMO"] = "1" if enabled else "0"


def is_packaged() -> bool:
    """Installé comme une application (le .exe) plutôt que lancé depuis le dossier du projet."""
    return not (PROJECT_ROOT / "pyproject.toml").exists()


def _local_base() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "Foulee"
    return Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "foulee"


# --------------------------------------------------- configuration utilisateur
def user_config_dir() -> Path:
    """Dossier du fichier de configuration (jamais synchronisé par OneDrive sous Windows)."""
    path = Path(os.environ["FOULEE_CONFIG"]) if os.environ.get("FOULEE_CONFIG") else _local_base()
    path.mkdir(parents=True, exist_ok=True)
    return path


_config_cache: tuple[float, dict] | None = None


def load_user_config() -> dict:
    """Contenu de config.json ({} s'il n'existe pas ou s'il est illisible)."""
    global _config_cache
    path = user_config_dir() / CONFIG_FILE
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return {}
    if _config_cache and _config_cache[0] == stamp:
        return dict(_config_cache[1])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    data = data if isinstance(data, dict) else {}
    _config_cache = (stamp, data)
    return dict(data)


def save_user_config(changes: dict) -> dict:
    """Met à jour config.json (une valeur None retire la clé) et renvoie le nouveau contenu."""
    global _config_cache
    data = load_user_config()
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    path = user_config_dir() / CONFIG_FILE
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
    _config_cache = None
    return data


# ------------------------------------------------------------------ données
def default_data_dir() -> Path:
    if not is_packaged():
        return PROJECT_ROOT / "data"
    if sys.platform == "win32":
        return _local_base() / "donnees"
    return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "foulee"


def data_dir_source() -> str:
    """D'où vient le dossier des données : « env », « reglages » ou « defaut »."""
    if os.environ.get("FOULEE_DATA"):
        return "env"
    return "reglages" if load_user_config().get("dossier_donnees") else "defaut"


def data_dir() -> Path:
    """Dossier des données (base SQLite, fichiers FIT, journaux) ; créé au besoin."""
    chosen = os.environ.get("FOULEE_DATA") or load_user_config().get("dossier_donnees")
    path = Path(chosen) if chosen else default_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def secrets_dir() -> Path:
    """Dossier local (jamais synchronisé) pour le jeton temporaire Garmin.

    Windows : %LOCALAPPDATA%\\Foulee — le dossier « Local » n'est pas itinérant
    et n'est pas synchronisé par OneDrive.
    """
    path = Path(os.environ["FOULEE_SECRETS"]) if os.environ.get("FOULEE_SECRETS") else _local_base()
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
