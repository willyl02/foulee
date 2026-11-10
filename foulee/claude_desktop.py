"""Claude Desktop : où il range sa configuration, et comment y ajouter (ou retirer) Foulée.

Claude Desktop lance lui-même le serveur MCP de Foulée, d'après son fichier
claude_desktop_config.json. Selon la version installée, ce fichier n'est pas au même
endroit : la version « paquet » de Windows (Microsoft Store / MSIX) lit
%LOCALAPPDATA%\\Claude-Data\\claude_<paquet>\\, les autres %APPDATA%\\Claude. On écrit
dans tous les fichiers existants : c'est sans risque, et on est sûr de toucher le bon.

Claude Desktop réécrit ce fichier quand il se ferme : il vaut mieux qu'il soit
fermé pendant la modification.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CLAUDE_DATA = "Claude-Data"
SERVER_NAME = "foulee"


def config_paths() -> list[Path]:
    """Emplacements possibles du fichier de configuration, le plus probable d'abord."""
    paths: list[Path] = []
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        appdata = os.environ.get("APPDATA")
        if local:
            paths += [folder / "claude_desktop_config.json"
                      for folder in sorted((Path(local) / CLAUDE_DATA).glob("claude_*")) if folder.is_dir()]
        if appdata:
            paths.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
        if local:
            paths += [package / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
                      for package in sorted((Path(local) / "Packages").glob("Claude_*"))]
    elif sys.platform == "darwin":
        paths.append(Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
    else:
        paths.append(Path.home() / ".config" / "Claude" / "claude_desktop_config.json")
    return paths


def config_targets() -> list[Path]:
    """Fichiers à modifier : ceux qui existent, plus celui de la version « paquet » s'il n'existe pas encore."""
    candidates = config_paths()
    targets = [p for p in candidates if p.exists() or p.parent.parent.name == CLAUDE_DATA]
    return targets or candidates[:1]


def is_installed() -> bool:
    """Claude Desktop semble installé (un de ses dossiers existe)."""
    return any(path.parent.exists() for path in config_paths())


def python_for_mcp() -> str:
    """Interpréteur à lancer pour le serveur MCP : python.exe, jamais pythonw.exe ni Foulee.exe
    (programmes sans console : le serveur MCP a besoin de ses entrées-sorties)."""
    executable = Path(sys.executable)
    if executable.name.lower() in ("pythonw.exe", "foulee.exe") and executable.with_name("python.exe").exists():
        return str(executable.with_name("python.exe"))
    return str(executable)


def mcp_entry() -> dict:
    env = {"PYTHONUTF8": "1"}
    # Le dossier des données se retrouve tout seul (réglages de Foulée) ; on ne le fige
    # que s'il est lui-même imposé par l'environnement.
    if os.environ.get("FOULEE_DATA"):
        env["FOULEE_DATA"] = os.environ["FOULEE_DATA"]
    return {"command": python_for_mcp(), "args": ["-m", "foulee", "mcp"], "env": env}


def run_quiet(command: list[str], timeout: float = 30) -> str:
    """Lance une commande Windows sans fenêtre et renvoie sa sortie ("" en cas d'échec)."""
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")


def is_running() -> bool:
    if sys.platform != "win32":
        return False
    return "claude.exe" in run_quiet(["tasklist", "/FI", "IMAGENAME eq claude.exe", "/NH"]).lower()


def close() -> None:
    """Ferme Claude Desktop (et Claude Code s'il tourne sous le même nom)."""
    if sys.platform == "win32":
        run_quiet(["taskkill", "/IM", "claude.exe", "/F"])


def read_config(path: Path) -> tuple[dict, str] | None:
    """(contenu, texte d'origine) ; None si le fichier n'est pas un objet JSON valide."""
    raw = path.read_text(encoding="utf-8-sig").strip() if path.exists() else ""  # tolère un BOM
    if not raw:
        return {}, ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return (data, raw) if isinstance(data, dict) else None


def _save(path: Path, data: dict, raw: str) -> str | None:
    """Écrit le fichier (UTF-8 sans BOM, que Claude Desktop exige) ; renvoie la sauvegarde éventuelle."""
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if raw:
        backup = path.with_name(f"{path.name}.sauvegarde-{datetime.now():%Y%m%d-%H%M%S}")
        backup.write_text(raw, encoding="utf-8")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(backup) if backup else None


def status() -> dict:
    entry = mcp_entry()
    files = []
    for path in config_paths():
        if not path.exists():
            continue
        loaded = read_config(path)
        servers = (loaded[0].get("mcpServers") or {}) if loaded else {}
        current = servers.get(SERVER_NAME) if isinstance(servers, dict) else None
        command = current.get("command") if isinstance(current, dict) else None
        files.append({
            "chemin": str(path), "valide": loaded is not None, "foulee": bool(current), "commande": command,
            "a_jour": bool(command) and same_path(command, entry["command"]) and current.get("args") == entry["args"],
        })
    return {
        "systeme": sys.platform, "installe": is_installed(), "ouvert": is_running(),
        "fichiers": files, "connecte": any(f["a_jour"] for f in files), "entree": entry,
    }


def write(*, remove: bool = False, only_mine: bool = False) -> dict:
    """Ajoute (ou retire) Foulée dans chaque fichier de configuration. Ne touche jamais un JSON invalide.

    only_mine (désinstallation) : ne retire l'entrée que si elle lance cette installation-ci.
    """
    entry = mcp_entry()
    report: dict = {"modifies": [], "sauvegardes": [], "erreurs": []}
    for path in config_targets():
        if remove and not path.exists():
            continue
        loaded = read_config(path)
        if loaded is None:
            report["erreurs"].append(f"{path} n'est pas un JSON valide : je n'y touche pas.")
            continue
        data, raw = loaded
        servers = data.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            report["erreurs"].append(f"{path} : la rubrique « mcpServers » a une forme inattendue, je n'y touche pas.")
            continue
        if remove:
            current = servers.get(SERVER_NAME)
            if current is None:
                continue
            command = current.get("command") if isinstance(current, dict) else None
            if only_mine and not (command and same_path(command, entry["command"])):
                continue  # une autre installation de Foulée : on n'y touche pas
            del servers[SERVER_NAME]
        else:
            servers[SERVER_NAME] = entry
        backup = _save(path, data, raw)
        report["modifies"].append(str(path))
        if backup:
            report["sauvegardes"].append(backup)
    return report


def same_path(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def retarget_data_dir(old: Path, new: Path) -> list[str]:
    """Après un changement de dossier des données, corrige les entrées qui figeaient l'ancien."""
    changed = []
    for path in config_paths():
        loaded = read_config(path) if path.exists() else None
        if not loaded:
            continue
        data, raw = loaded
        entry = (data.get("mcpServers") or {}).get(SERVER_NAME) if isinstance(data.get("mcpServers"), dict) else None
        env = entry.get("env") if isinstance(entry, dict) else None
        if isinstance(env, dict) and env.get("FOULEE_DATA") and same_path(env["FOULEE_DATA"], old):
            env.pop("FOULEE_DATA")  # Foulée retrouvera seul le nouveau dossier
            _save(path, data, raw)
            changed.append(str(path))
    return changed
