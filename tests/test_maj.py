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
    monkeypatch.setattr(web, "__version__", "0.3.0")  # version stable installée
    client = TestClient(web.create_app())
    assert client.get("/api/bootstrap").json()["maj"] is True
    status = client.get("/api/maj").json()
    assert (status["mode"], status["disponible"], status["canal"], status["etat"], status["en_attente"]) == \
        ("serveur", True, "stable", None, False)

    assert client.post("/api/maj", json={"action": "rm -rf /"}, headers=WRITE).status_code == 400
    sent = client.post("/api/maj", json={"action": "verifier"}, headers=WRITE).json()
    assert sent["ok"] and (folder / "demande").read_text() == "verifier:stable"
    assert client.get("/api/maj").json()["en_attente"] is True

    # Le canal bêta se choisit dans les Réglages et accompagne la demande
    assert client.put("/api/settings", json={"canal_maj": "nightly"}, headers=WRITE).status_code == 400
    client.put("/api/settings", json={"canal_maj": "beta"}, headers=WRITE)
    client.post("/api/maj", json={"action": "installer"}, headers=WRITE)
    assert (folder / "demande").read_text() == "installer:beta"

    (folder / "etat.json").write_text(json.dumps({"statut": "verifie", "message": "À jour", "horodatage": 1.0}))
    assert client.get("/api/maj").json()["etat"]["statut"] == "verifie"


def test_no_update_button_without_the_service(monkeypatch):
    monkeypatch.delenv("FOULEE_MAJ", raising=False)
    client = TestClient(web.create_app())
    assert client.get("/api/bootstrap").json()["maj"] is False
    status = client.get("/api/maj").json()
    assert status["disponible"] is False and status["mode"] == "dev"
    assert client.post("/api/maj", json={"action": "verifier"}, headers=WRITE).status_code == 404


# ------------------------------------------------------- côté service (root)
def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false",
                    *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def project(tmp_path):
    """Un dépôt « GitHub » en 0.2.0 et une installation restée en 0.1.0."""
    if sys.platform == "win32":
        pytest.skip("service de mise à jour du serveur : Linux uniquement")
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


def write_version(repo: Path, version: str, message: str) -> None:
    (repo / "foulee" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    git(repo, "commit", "-qam", message)


def test_beta_channel_and_no_downgrade(project):
    origin, install, state = project
    git(origin, "checkout", "-q", "-b", "beta")
    write_version(origin, "0.3.0b1", "Foulée 0.3.0b1 : essai")
    git(origin, "checkout", "-q", "main")

    beta = run_updater(install, state, "verifier", "--canal", "beta")
    assert beta["disponible"] == "0.3.0b1" and beta["retard"] >= 1 and beta["canal"] == "beta"
    assert run_updater(install, state, "installer", "--canal", "beta")["statut"] == "termine"
    assert '"0.3.0b1"' in (install / "foulee" / "__init__.py").read_text()

    # Retour au canal stable : la 0.2.0 est plus ancienne que la bêta, on ne redescend pas
    stable = run_updater(install, state, "verifier", "--canal", "stable")
    assert stable["retard"] == 0 and stable["en_avance"] and "bêta" in stable["message"]
    refused = run_updater(install, state, "installer", "--canal", "stable")
    assert refused["statut"] == "erreur" and "jamais en arrière" in refused["message"]

    # La version stable rattrape la bêta : on repasse sur main
    write_version(origin, "0.3.0", "Foulée 0.3.0")
    assert run_updater(install, state, "verifier", "--canal", "stable")["retard"] >= 1
    assert run_updater(install, state, "installer", "--canal", "stable")["statut"] == "termine"
    assert '"0.3.0"' in (install / "foulee" / "__init__.py").read_text()
    head = subprocess.run(["git", "-C", str(install), "rev-parse", "--abbrev-ref", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert head == "main"


def test_missing_beta_branch_is_explained(project):
    origin, install, state = project
    missing = run_updater(install, state, "verifier", "--canal", "beta")
    assert missing["statut"] == "erreur" and "n'existe pas encore" in missing["message"]


def test_channel_is_read_without_leaving_files_behind(tmp_path, monkeypatch):
    """Le service de mise à jour tourne en root : il lit le canal sans créer de fichier à côté de la base."""
    import importlib.util

    from foulee import db

    monkeypatch.setenv("FOULEE_DATA", str(tmp_path / "donnees"))
    with db.session() as conn:
        db.set_setting(conn, "canal_maj", "beta")
        conn.commit()
    spec = importlib.util.spec_from_file_location("maj_serveur", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    before = sorted(p.name for p in (tmp_path / "donnees").iterdir())
    assert module.configured_channel() == "beta"
    assert sorted(p.name for p in (tmp_path / "donnees").iterdir()) == before

    # Jamais choisi : le canal suit la version installée (bêta → bêtas)
    monkeypatch.setenv("FOULEE_DATA", str(tmp_path / "vide"))
    for version, expected in (("0.4.0", "stable"), ("0.4.0b2", "beta")):
        root = tmp_path / version
        (root / "foulee").mkdir(parents=True)
        (root / "foulee" / "__init__.py").write_text(f'__version__ = "{version}"\n')
        assert module.configured_channel(root) == expected


def test_a_beta_install_follows_betas_until_told_otherwise(monkeypatch):
    monkeypatch.setattr(web, "__version__", "0.4.0b1")
    client = TestClient(web.create_app())
    assert client.get("/api/maj").json()["canal"] == "beta"
    client.put("/api/settings", json={"canal_maj": "stable"}, headers=WRITE)
    assert client.get("/api/maj").json()["canal"] == "stable"
