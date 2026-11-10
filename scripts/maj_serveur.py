#!/usr/bin/env python3
"""Mise à jour de Foulée sur le serveur, depuis GitHub (à lancer en root).

    maj_serveur.py verifier [--canal beta]   compare la version installée et celle de GitHub
    maj_serveur.py installer [--canal beta]  installe la dernière version et relance l'interface
    maj_serveur.py --depuis-interface        traite la demande déposée par l'interface
                                             (c'est ce que fait le service foulee-maj)

Canal « stable » : branche main du dépôt ; canal « beta » : branche beta. On ne
redescend jamais de version : en quittant la bêta, on attend que la version stable
la rattrape.

Où il en est s'écrit dans etat.json (dossier FOULEE_MAJ), que les Réglages affichent.
Le script n'utilise que la bibliothèque standard de Python : il continue de tourner
pendant que le code et les bibliothèques de Foulée sont remplacés.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ACTIONS = ("verifier", "installer")
BRANCHES = {"stable": "main", "beta": "beta"}
_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-.]?(a|alpha|b|beta|rc)[-.]?(\d+)?)?$", re.IGNORECASE)
_PRE_RANK = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "rc": 2}


def version_key(text: str) -> tuple:
    """« 0.4.0b1 » → (0, 4, 0, 1, 1) ; une version finale passe après ses pré-versions."""
    match = _VERSION.match(text.strip())
    if not match:
        return (0, 0, 0, 0, 0)
    major, minor, patch = int(match[1]), int(match[2]), int(match[3] or 0)
    if match[4]:
        return major, minor, patch, _PRE_RANK[match[4].lower()], int(match[5] or 0)
    return major, minor, patch, 9, 0


class Failure(Exception):
    """Étape ratée, expliquée en français."""


class Updater:
    def __init__(self, root: Path, state_dir: Path, *, console: bool = False, channel: str = "stable") -> None:
        self.root = root
        self.state_dir = state_dir
        self.console = console
        self.channel = channel if channel in BRANCHES else "stable"
        self.branch = BRANCHES[self.channel]
        self.uv = os.environ.get("FOULEE_UV", "/usr/local/bin/uv")
        self.systemctl = os.environ.get("FOULEE_SYSTEMCTL", "systemctl")

    # ------------------------------------------------------------------ outils
    def state(self, status: str, message: str, **extra: object) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        data = {"statut": status, "message": message, "horodatage": time.time(), "canal": self.channel, **extra}
        temporary = self.state_dir / "etat.json.tmp"
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.chmod(temporary, 0o644)
        os.replace(temporary, self.state_dir / "etat.json")
        if self.console:
            print(message, flush=True)

    def run(self, *command: str, env: dict | None = None) -> str:
        try:
            result = subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True, timeout=900)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Failure(f"« {' '.join(command[:2])} » impossible : {exc}") from exc
        if result.returncode != 0:
            lines = [line for line in (result.stderr or result.stdout).splitlines() if line.strip()]
            raise Failure(f"« {' '.join(command[:3])} » a échoué : {' / '.join(lines[-3:]) or result.returncode}")
        return result.stdout

    def git(self, *args: str) -> str:
        return self.run("git", "-C", str(self.root), *args)

    def version_at(self, ref: str) -> str:
        match = re.search(r'__version__\s*=\s*"([^"]+)"', self.git("show", f"{ref}:foulee/__init__.py"))
        return match.group(1) if match else "?"

    # ----------------------------------------------------------------- actions
    def fetch(self) -> str:
        """Récupère la branche du canal ; renvoie la référence distante à suivre."""
        try:
            self.git("fetch", "--quiet", "origin", self.branch)
        except Failure as exc:
            if "couldn't find remote ref" in str(exc).lower() or "not found" in str(exc).lower():
                raise Failure(f"La branche « {self.branch} » n'existe pas encore sur GitHub.") from exc
            raise
        return f"origin/{self.branch}"

    def compare(self) -> dict:
        remote = self.fetch()
        installed, available = self.version_at("HEAD"), self.version_at(remote)
        behind = int(self.git("rev-list", "--count", f"HEAD..{remote}").strip() or 0)
        ahead = int(self.git("rev-list", "--count", f"{remote}..HEAD").strip() or 0)
        if version_key(available) < version_key(installed):
            behind = 0  # jamais de retour en arrière (ex. : on quitte la bêta)
        elif ahead and version_key(available) == version_key(installed):
            behind = 0  # autre branche, même version : rien à installer
        news = [line.strip() for line in self.git("log", "--format=%s", f"HEAD..{remote}").splitlines() if line.strip()]
        return {"installee": installed, "disponible": available, "retard": behind,
                "nouveautes": news[:20] if behind else [], "en_avance": version_key(available) < version_key(installed)}

    def verify(self) -> None:
        self.state("en_cours", "Recherche d'une nouvelle version sur GitHub…")
        info = self.compare()
        if info["retard"]:
            plural = "s" if info["retard"] > 1 else ""
            kind = " (bêta)" if self.channel == "beta" else ""
            message = f"Version {info['disponible']}{kind} disponible ({info['retard']} changement{plural})."
        elif info["en_avance"]:
            message = (f"Tu utilises une bêta ({info['installee']}) : tu repasseras sur la version stable dès "
                       f"qu'elle sera plus récente (actuelle : {info['disponible']}).")
        else:
            message = f"Foulée est à jour (version {info['installee']})."
        self.state("verifie", message, **info)

    def install(self) -> None:
        self.state("en_cours", "Récupération de la nouvelle version…")
        before = self.version_at("HEAD")
        remote = self.fetch()
        if version_key(self.version_at(remote)) < version_key(before):
            raise Failure(f"La version {self.version_at(remote)} est plus ancienne que la tienne ({before}) : "
                          "Foulée ne revient jamais en arrière.")
        # Se place sur la branche du canal (main ou beta), au niveau de GitHub
        self.git("checkout", "--quiet", "-B", self.branch, remote)
        after = self.version_at("HEAD")
        self.state("en_cours", "Mise à jour des bibliothèques…", installee=before, disponible=after)
        env = {**os.environ, "UV_PYTHON_INSTALL_DIR": os.environ.get("UV_PYTHON_INSTALL_DIR", "/opt/uv/python"),
               "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", "/opt/uv/cache")}
        self.run(self.uv, "sync", "--no-dev", "--compile-bytecode", "--quiet", env=env)
        self.run(str(self.root / ".venv" / "bin" / "python"), "-m", "compileall", "-q", str(self.root / "foulee"))
        # Réglages système de la nouvelle version (nouveaux services, nouvelles options)
        self.state("en_cours", "Réglage des services…", installee=before, disponible=after)
        self.run("bash", str(self.root / "scripts" / "configurer-serveur.sh"))
        self.state("termine", f"Foulée {after} est installé. L'interface redémarre…", installee=after, precedente=before)
        self.run(self.systemctl, "restart", "foulee-web.service")

    def from_interface(self) -> int:
        request = self.state_dir / "demande"
        try:
            action = request.read_text(encoding="utf-8").strip().lower()
        except FileNotFoundError:
            return 0
        request.unlink(missing_ok=True)  # sinon le service se relancerait en boucle
        action, _, channel = action.partition(":")
        if action not in ACTIONS or (channel and channel not in BRANCHES):
            self.state("erreur", f"Demande inconnue : « {action[:40]} ».")
            return 1
        self.channel = channel or "stable"
        self.branch = BRANCHES[self.channel]
        return self.do(action)

    def do(self, action: str) -> int:
        try:
            self.verify() if action == "verifier" else self.install()
        except Failure as exc:
            self.state("erreur", str(exc))
            return 1
        except Exception as exc:  # toute erreur doit apparaître dans les Réglages
            self.state("erreur", f"Erreur inattendue : {exc}")
            return 1
        return 0


def configured_channel() -> str:
    """Canal choisi dans les Réglages de Foulée (lu directement dans sa base)."""
    import sqlite3

    database = Path(os.environ.get("FOULEE_DATA") or "/var/lib/foulee") / "foulee.db"
    if not database.exists():
        return "stable"
    try:
        # immutable=1 : root ne crée aucun fichier à côté de la base (des -wal/-shm appartenant à root
        # empêcheraient l'utilisateur foulee de l'ouvrir ensuite)
        with sqlite3.connect(f"file:{database}?mode=ro&immutable=1", uri=True) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'canal_maj'").fetchone()
        value = json.loads(row[0]) if row else "stable"
    except (sqlite3.Error, ValueError):
        value = "stable"
    return value if value in BRANCHES else "stable"


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    state_dir = Path(os.environ.get("FOULEE_MAJ") or "/var/lib/foulee/maj")
    if "--depuis-interface" in argv:
        return Updater(root, state_dir).from_interface()
    actions = [arg for arg in argv if arg in ACTIONS]
    if "--canal" in argv and argv.index("--canal") + 1 < len(argv):
        channel = argv[argv.index("--canal") + 1]
    else:
        channel = configured_channel()
    if len(actions) != 1 or channel not in BRANCHES:
        print(__doc__)
        return 2
    return Updater(root, state_dir, console="--console" in argv, channel=channel).do(actions[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
