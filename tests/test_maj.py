"""Mises à jour depuis l'interface : la demande, le service root et son compte rendu."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foulee import web

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "maj_serveur.py"
WRITE = {"X-Foulee": "1"}


# ------------------------------------------------------------- côté interface
def test_interface_drops_a_request_and_reads_the_state(tmp_path, monkeypatch):
    folder = tmp_path / "maj"
    folder.mkdir()
    monkeypatch.setenv("FOULEE_MAJ", str(folder))
    client = TestClient(web.create_app())
    assert client.get("/api/bootstrap").json()["maj"] is True
    assert client.get("/api/maj").json() == {"disponible": True, "version": web.__version__, "etat": None, "en_attente": False}

    assert client.post("/api/maj", json={"action": "rm -rf /"}, headers=WRITE).status_code == 400
    sent = client.post("/api/maj", json={"action": "verifier"}, headers=WRITE).json()
    assert sent["ok"] and (folder / "demande").read_text() == "verifier"
    assert client.get("/api/maj").json()["en_attente"] is True

    (folder / "etat.json").write_text(json.dumps({"statut": "verifie", "message": "À jour", "horodatage": 1.0}))
    assert client.get("/api/maj").json()["etat"]["statut"] == "verifie"


def test_no_update_button_without_the_service(monkeypatch):
    monkeypatch.delenv("FOULEE_MAJ", raising=False)
    client = TestClient(web.create_app())
    assert client.get("/api/bootstrap").json()["maj"] is False
    assert client.get("/api/maj").json()["disponible"] is False
    assert client.post("/api/maj", json={"action": "verifier"}, headers=WRITE).status_code == 404


# ------------------------------------------------------- côté service (root)
def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false",
                    *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def project(tmp_path):
    """Un dépôt « GitHub » en 0.2.0 et une installation restée en 0.1.0."""
    origin = tmp_path / "origin"
    (origin / "foulee").mkdir(parents=True)
    (origin / "scripts").mkdir()
    (origin / "foulee" / "__init__.py").write_text('__version__ = "0.1.0"\n')
    shutil.copy(SCRIPT, origin / "scripts" / "maj_serveur.py")
    (origin / "scripts" / "configurer-serveur.sh").write_text('#!/bin/sh\ntouch "$(dirname "$0")/../services-ok"\n')
    git(origin, "init", "-q", "-b", "main")
    git(origin, "add", "-A")
    git(origin, "commit", "-qm", "Version 0.1.0")
    install = tmp_path / "install"
    git(tmp_path, "clone", "-q", str(origin), str(install))
    (install / ".venv" / "bin").mkdir(parents=True)
    (install / ".venv" / "bin" / "python").symlink_to(sys.executable)
    (origin / "foulee" / "__init__.py").write_text('__version__ = "0.2.0"\n')
    git(origin, "commit", "-qam", "Foulée 0.2.0 : accès par le réseau local")
    return origin, install, tmp_path / "etat"


def run_updater(install: Path, state: Path, *args: str) -> dict:
    env = {**os.environ, "FOULEE_MAJ": str(state), "FOULEE_UV": "true", "FOULEE_SYSTEMCTL": "true",
           "GIT_TERMINAL_PROMPT": "0"}
    subprocess.run([sys.executable, str(install / "scripts" / "maj_serveur.py"), *args], env=env,
                   capture_output=True, text=True, timeout=120)
    return json.loads((state / "etat.json").read_text(encoding="utf-8"))


def test_check_then_install_from_the_interface(project):
    origin, install, state = project
    checked = run_updater(install, state, "verifier")
    assert checked["statut"] == "verifie"
    assert (checked["installee"], checked["disponible"], checked["retard"]) == ("0.1.0", "0.2.0", 1)
    assert checked["nouveautes"] == ["Foulée 0.2.0 : accès par le réseau local"]
    assert (state / "etat.json").stat().st_mode & 0o004  # lisible par l'utilisateur foulee

    (state / "demande").write_text("installer")
    done = run_updater(install, state, "--depuis-interface")
    assert done["statut"] == "termine" and done["installee"] == "0.2.0" and done["precedente"] == "0.1.0"
    assert not (state / "demande").exists()
    assert '"0.2.0"' in (install / "foulee" / "__init__.py").read_text()
    assert (install / "services-ok").exists()  # les réglages système de la nouvelle version sont appliqués

    again = run_updater(install, state, "verifier")
    assert again["retard"] == 0 and "à jour" in again["message"]


def test_unknown_request_and_unreachable_github_are_reported(project):
    origin, install, state = project
    (state).mkdir()
    (state / "demande").write_text("rm -rf /")
    assert run_updater(install, state, "--depuis-interface")["statut"] == "erreur"

    shutil.rmtree(origin)  # GitHub injoignable
    failed = run_updater(install, state, "verifier")
    assert failed["statut"] == "erreur" and "a échoué" in failed["message"]
