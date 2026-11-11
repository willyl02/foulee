"""Changer le dossier des données de Foulée (base, fichiers FIT, journaux).

Trois façons de faire :
- « déplacer » : copier les données actuelles dans un nouveau dossier, puis s'en servir ;
- « utiliser » : passer sur un dossier qui contient déjà des données Foulée (un disque
  externe, une ancienne installation…) et les utiliser là où elles sont ;
- « importer » : copier ici les données d'un autre dossier (ancienne installation,
  sauvegarde), tant que Foulée n'a encore rien importé de son côté.

L'ancien dossier n'est jamais effacé : on le supprime soi-même une fois rassuré.
La base est copiée par la sauvegarde intégrée de SQLite, qui donne une copie
cohérente même si Claude ou l'interface la lisent au même moment.

Le dossier est celui de l'installation : il contient aussi les autres profils
(« profils/<id> ») et leur liste (« utilisateurs.json »), qui le suivent.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import uuid
from contextlib import closing
from pathlib import Path

from . import config

MODES = ("deplacer", "utiliser", "importer")
DB_NAME = "foulee.db"
DATA_TABLES = ("raw", "daily", "activities")  # une base sans rien dedans n'a pas de « données »


class DataDirError(Exception):
    """Changement impossible, expliqué en français."""


def _resolve(path: str | Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(str(_resolve(a))) == os.path.normcase(str(_resolve(b)))


def _inside(child: Path, parent: Path) -> bool:
    child_text = os.path.normcase(str(_resolve(child)))
    parent_text = os.path.normcase(str(_resolve(parent))).rstrip("\\/")
    return child_text.startswith(parent_text + os.sep)


def program_dir() -> Path | None:
    """Dossier du programme installé par le .exe : il est remplacé à chaque mise à jour."""
    return Path(sys.prefix).parent if config.is_packaged() else None


def in_onedrive(path: Path) -> bool:
    """Le dossier est-il synchronisé par OneDrive (tes données de santé partiraient dans le cloud) ?"""
    roots = [os.environ.get(name) for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")]
    if any(root and (_same(path, Path(root)) or _inside(path, Path(root))) for root in roots):
        return True
    return any(part.lower().startswith("onedrive") for part in _resolve(path).parts)


def folder_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def summary(folder: Path) -> dict | None:
    """Ce que contient la base d'un dossier (None : pas de base, ou base vide)."""
    database = folder / DB_NAME
    if not database.is_file():
        return None
    try:
        with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=5)) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if not any(conn.execute(f"SELECT EXISTS(SELECT 1 FROM {t})").fetchone()[0]
                       for t in DATA_TABLES if t in tables):
                return None
            count = lambda sql: conn.execute(sql).fetchone()[0] if {"activities", "daily"} <= tables else 0  # noqa: E731
            return {
                "seances": count("SELECT COUNT(*) FROM activities"),
                "valeurs": count("SELECT COUNT(*) FROM daily"),
                "debut": count("SELECT MIN(date) FROM daily"),
                "fin": count("SELECT MAX(date) FROM daily"),
            }
    except sqlite3.Error:
        return {"illisible": True}  # par prudence, on la traite comme une base pleine


def describe() -> dict:
    current = config.root_dir()
    source = config.data_dir_source()
    return {
        "chemin": str(current), "source": source, "modifiable": source != "env",
        "defaut": str(config.default_data_dir()), "est_defaut": _same(current, config.default_data_dir()),
        "base": (current / DB_NAME).exists(), "contenu": summary(current),
        "taille": folder_size(current), "onedrive": in_onedrive(current),
    }


def inspect(target_text: str) -> dict:
    """Ce qu'on peut dire d'un dossier avant de s'en servir, et ce qu'on peut y faire."""
    if not target_text or not os.path.isabs(os.path.expanduser(target_text)):
        return {"chemin": target_text, "probleme": "Indique un chemin complet, par exemple D:\\Sport\\Foulee.",
                "modes": []}
    target = _resolve(target_text)
    current = config.root_dir()
    exists = target.is_dir()
    modes = {mode: _problem(target, current, mode) for mode in MODES}
    return {
        "chemin": str(target), "existe": exists,
        "contenu": summary(target) if exists else None,
        "vide": exists and not any(target.iterdir()),
        "onedrive": in_onedrive(target),
        "modes": [mode for mode, problem in modes.items() if problem is None],
        "refus": {mode: problem for mode, problem in modes.items() if problem},
        "probleme": _problem(target, current, None),
    }


def _problem(target: Path, current: Path, mode: str | None) -> str | None:
    if _same(target, current):
        return "C'est déjà le dossier utilisé."
    if _inside(target, current) or _inside(current, target):
        return "Le nouveau dossier ne peut pas être à l'intérieur de l'actuel, ni l'inverse."
    program = program_dir()
    if program and (_same(target, program) or _inside(target, program)):
        return "C'est le dossier du programme : il est remplacé à chaque mise à jour. Choisis-en un autre."
    if target.exists() and not target.is_dir():
        return "Ce chemin désigne un fichier, pas un dossier."
    content = summary(target)
    if mode == "deplacer" and content:
        return ("Ce dossier contient déjà des données Foulée : choisis « Utiliser » pour t'en servir, "
                "ou un autre dossier.")
    if mode in ("utiliser", "importer") and not content:
        return "Ce dossier ne contient pas de données Foulée (fichier foulee.db)."
    if mode in ("utiliser", "importer") and content.get("illisible"):
        return "La base de ce dossier est illisible (abîmée, ou d'un autre programme)."
    if mode == "importer" and summary(current):
        return ("Foulée a déjà des données ici : l'import remplacerait tout. Choisis plutôt « Utiliser », "
                "ou repars d'une installation vide.")
    return None


def _check_writable(target: Path) -> None:
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / f".foulee-essai-{uuid.uuid4().hex[:8]}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise DataDirError(f"Impossible d'écrire dans ce dossier : {exc.strerror or exc}.") from exc


def _verify_db(path: Path) -> dict:
    try:
        with closing(sqlite3.connect(path)) as conn:
            check = conn.execute("PRAGMA quick_check").fetchone()[0]
            activities = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
            daily = conn.execute("SELECT COUNT(*) FROM daily").fetchone()[0]
    except sqlite3.Error as exc:
        raise DataDirError(f"La base {path} est illisible : {exc}.") from exc
    if check != "ok":
        raise DataDirError(f"La base {path} est abîmée ({check}).")
    return {"seances": activities, "valeurs": daily}


def _copy_database(source: Path, destination: Path) -> dict:
    """Copie cohérente de la base (sauvegarde SQLite), puis vérification de la copie.

    Si la destination existe déjà (base vide créée au premier démarrage), elle est
    remplacée de l'intérieur : ceux qui l'ont ouverte voient directement le nouveau contenu.
    """
    existed = destination.exists()
    try:
        with closing(sqlite3.connect(source, timeout=15)) as src, \
                closing(sqlite3.connect(destination, timeout=15)) as dst:
            src.backup(dst)
        return _verify_db(destination)
    except (sqlite3.Error, DataDirError) as exc:
        if not existed:
            for suffix in ("", "-wal", "-shm"):
                Path(f"{destination}{suffix}").unlink(missing_ok=True)
        raise DataDirError(f"Copie de la base impossible : {exc}") from exc


def _copy_tree(source: Path, target: Path) -> tuple[int, int]:
    files = size = 0
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        destination = target / item.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.stat().st_size == item.stat().st_size:
            continue
        shutil.copy2(item, destination)
        files += 1
        size += item.stat().st_size
    return files, size


PROFILE_FILES = ("profil.jpg", "utilisateurs.json")  # photo du principal, liste des profils


def _copy_profile(source: Path, target: Path) -> tuple[dict | None, int, int]:
    """Base, fichiers FIT et photo d'un profil : (rapport de la base, fichiers FIT, octets copiés)."""
    target.mkdir(parents=True, exist_ok=True)
    base = _copy_database(source / DB_NAME, target / DB_NAME) if (source / DB_NAME).exists() else None
    fit_files, size = _copy_tree(source / "fit", target / "fit") if (source / "fit").is_dir() else (0, 0)
    size += (target / DB_NAME).stat().st_size if (target / DB_NAME).exists() else 0
    for name in PROFILE_FILES:
        if (source / name).is_file():
            shutil.copy2(source / name, target / name)
            size += (source / name).stat().st_size
    return base, fit_files, size


def _copy_data(source: Path, target: Path) -> dict:
    report: dict = {}
    base, fit_files, size = _copy_profile(source, target)
    if base:
        report["base"] = base
    profiles = 0
    if (source / "profils").is_dir():  # les autres profils suivent le dossier de l'installation
        for folder in sorted((source / "profils").iterdir()):
            if folder.is_dir():
                _base, files, copied = _copy_profile(folder, target / "profils" / folder.name)
                fit_files += files
                size += copied
                profiles += 1
    report["fichiers_fit"] = fit_files
    report["octets_copies"] = size
    if profiles:
        report["profils"] = profiles
    return report


def change(target_text: str, mode: str) -> dict:
    """Déplace les données, passe sur un dossier existant ou importe ses données, et retient ce choix."""
    from . import claude_desktop, sync

    if mode not in MODES:
        raise DataDirError("Mode inconnu : « deplacer », « utiliser » ou « importer ».")
    if config.data_dir_source() == "env" and mode != "importer":
        raise DataDirError("Le dossier est imposé par la variable FOULEE_DATA (serveur) : change-la à sa source.")
    if not target_text or not os.path.isabs(os.path.expanduser(target_text)):
        raise DataDirError("Indique un chemin complet, par exemple D:\\Sport\\Foulee.")
    from . import utilisateurs

    for entry in utilisateurs.profiles():
        with config.using_profile(entry):
            if sync.is_running():
                raise DataDirError("Une synchro est en cours : réessaie quand elle sera terminée.")
    current = _resolve(config.root_dir())
    target = _resolve(target_text)
    problem = _problem(target, current, mode)
    if problem:
        raise DataDirError(problem)

    report: dict = {"ancien": str(current), "nouveau": str(target), "mode": mode}
    if mode == "importer":  # les données viennent ici ; le dossier utilisé ne change pas
        report.update(_copy_data(target, current))
        report["nouveau"] = str(current)
        report["source"] = str(target)
        return report
    _check_writable(target)
    if mode == "deplacer":
        report.update(_copy_data(current, target))
    else:
        report["base"] = _verify_db(target / DB_NAME)

    default = config.default_data_dir()
    config.save_user_config({"dossier_donnees": None if _same(target, default) else str(target)})
    report["claude"] = claude_desktop.retarget_data_dir(current, target)
    report["onedrive"] = in_onedrive(target)
    return report


def previous_installs() -> list[dict]:
    """Données Foulée laissées ailleurs sur ce PC (ancienne installation, ancien dossier par défaut)."""
    candidates = [Path.home() / "Foulee" / "data", config.default_data_dir()]
    if config.is_packaged():
        candidates.append(Path(os.environ.get("USERPROFILE") or Path.home()) / "Foulee" / "data")
    current = config.root_dir()
    found, seen = [], set()
    for folder in candidates:
        key = os.path.normcase(str(_resolve(folder)))
        if key in seen or _same(folder, current) or not folder.is_dir():
            continue
        seen.add(key)
        content = summary(folder)
        if content and not content.get("illisible"):
            found.append({"chemin": str(_resolve(folder)), "contenu": content, "taille": folder_size(folder)})
    return found


def pick_folder(initial: str | None = None) -> str | None:
    """Ouvre la fenêtre « Choisir un dossier » de Windows, sur la machine qui fait tourner Foulée."""
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # sinon la fenêtre s'ouvre derrière le navigateur
    try:
        chosen = filedialog.askdirectory(parent=root, initialdir=initial or str(Path.home()),
                                         title="Dossier des données de Foulée", mustexist=False)
    finally:
        root.destroy()
    return os.path.normpath(chosen) if chosen else None
