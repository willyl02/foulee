#!/usr/bin/env python3
"""Mise à jour de Foulée sur le serveur, depuis GitHub (à lancer en root).

    maj_serveur.py verifier            compare la version installée et celle de GitHub
    maj_serveur.py installer           installe la dernière version et relance l'interface
    maj_serveur.py --depuis-interface  traite la demande déposée par l'interface
                                       (c'est ce que fait le service foulee-maj)

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

BRANCH = "main"
ACTIONS = ("verifier", "installer")


class Failure(Exception):
    """Étape ratée, expliquée en français."""


class Updater:
    def __init__(self, root: Path, state_dir: Path, *, console: bool = False) -> None:
        self.root = root
        self.state_dir = state_dir
        self.console = console
        self.uv = os.environ.get("FOULEE_UV", "/usr/local/bin/uv")
        self.systemctl = os.environ.get("FOULEE_SYSTEMCTL", "systemctl")

    # ------------------------------------------------------------------ outils
    def state(self, status: str, message: str, **extra: object) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        data = {"statut": status, "message": message, "horodatage": time.time(), **extra}
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
    def compare(self) -> dict:
        self.git("fetch", "--quiet", "origin", BRANCH)
        behind = int(self.git("rev-list", "--count", f"HEAD..origin/{BRANCH}").strip() or 0)
        news = [line.strip() for line in self.git("log", "--format=%s", f"HEAD..origin/{BRANCH}").splitlines() if line.strip()]
        return {"installee": self.version_at("HEAD"), "disponible": self.version_at(f"origin/{BRANCH}"),
                "retard": behind, "nouveautes": news[:20]}

    def verify(self) -> None:
        self.state("en_cours", "Recherche d'une nouvelle version sur GitHub…")
        info = self.compare()
        if info["retard"]:
            plural = "s" if info["retard"] > 1 else ""
            message = f"Version {info['disponible']} disponible ({info['retard']} changement{plural})."
        else:
            message = f"Foulée est à jour (version {info['installee']})."
        self.state("verifie", message, **info)

    def install(self) -> None:
        self.state("en_cours", "Récupération de la nouvelle version…")
        before = self.version_at("HEAD")
        self.git("fetch", "--quiet", "origin", BRANCH)
        self.git("merge", "--ff-only", "--quiet", f"origin/{BRANCH}")
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
        if action not in ACTIONS:
            self.state("erreur", f"Demande inconnue : « {action[:40]} ».")
            return 1
        return self.do(action)

    def do(self, action: str) -> int:
        try:
            self.verify() if action == "verifier" else self.install()
        except Failure as exc:
            self.state("erreur", str(exc))
            return 1
        except Exception as exc:  # noqa: BLE001 - toute erreur doit apparaître dans les Réglages
            self.state("erreur", f"Erreur inattendue : {exc}")
            return 1
        return 0


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    state_dir = Path(os.environ.get("FOULEE_MAJ") or "/var/lib/foulee/maj")
    if "--depuis-interface" in argv:
        return Updater(root, state_dir).from_interface()
    actions = [arg for arg in argv if arg in ACTIONS]
    if len(actions) != 1:
        print(__doc__)
        return 2
    return Updater(root, state_dir, console="--console" in argv).do(actions[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
