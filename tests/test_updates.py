"""Mises à jour du PC par les versions publiées sur GitHub (canal stable ou bêta)."""

import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from foulee import updates, vault, web

WRITE = {"X-Foulee": "1"}
INSTALLER = b"MZ" + b"installateur factice" * 1000


def release(tag, *, prerelease=False, draft=False, assets=True, body="- Nouveauté"):
    name = f"Foulee-Setup-{tag.lstrip('v')}.exe"
    return {
        "tag_name": tag, "prerelease": prerelease, "draft": draft, "body": body,
        "published_at": "2026-11-20T10:00:00Z",
        "assets": [
            {"name": name, "url": f"https://api.github.com/assets/{tag}-exe", "size": len(INSTALLER)},
            {"name": "SHA256SUMS.txt", "url": f"https://api.github.com/assets/{tag}-sums", "size": 100},
        ] if assets else [],
    }


RELEASES = [
    release("v0.5.0", draft=True),
    release("v0.4.0b2", prerelease=True, body="## Nouveautés\n- Bouton bêta\n- **Plus rapide**\n\n---\n**Installer** : …"),
    release("v0.3.0"),
    release("v0.3.5", assets=False),
]


class FakeResponse:
    def __init__(self, status=200, json_data=None, content=b"", headers=None):
        self.status_code = status
        self._json = json_data
        self.content = content
        self.text = content.decode("utf-8", errors="replace")
        self.headers = headers or {}

    def json(self):
        return self._json

    def iter_content(self, chunk_size):
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start:start + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def github(monkeypatch):
    calls = []
    state = {"releases": RELEASES, "installer": INSTALLER, "status": 200}

    def fake_get(url, headers=None, params=None, stream=False, timeout=None):
        calls.append((url, dict(headers or {})))
        if url.endswith("/releases"):
            return FakeResponse(state["status"], state["releases"] if state["status"] == 200 else {"message": "x"})
        if url.endswith("-sums"):
            digest = hashlib.sha256(INSTALLER).hexdigest()
            return FakeResponse(content=f"{digest}  Foulee-Setup-0.4.0b2.exe\n{digest}  Foulee-Setup-0.3.0.exe\n".encode())
        if url.endswith("-exe"):
            return FakeResponse(content=state["installer"], headers={"Content-Length": str(len(state["installer"]))})
        return FakeResponse(404)

    monkeypatch.setattr(updates.requests, "get", fake_get)
    state["calls"] = calls
    return state


def test_versions_are_ordered_like_pep440():
    order = ["0.3.0", "0.4.0a1", "0.4.0b1", "v0.4.0-beta.2", "0.4.0rc1", "0.4.0", "0.4.1", "1.0"]
    keys = [updates.parse_version(v) for v in order]
    assert keys == sorted(keys)
    assert updates.parse_version("v0.4.0-beta.1") == updates.parse_version("0.4.0b1")
    assert updates.is_prerelease("0.4.0b1") and not updates.is_prerelease("0.4.0")
    with pytest.raises(ValueError):
        updates.parse_version("nightly")


def test_channels_pick_the_right_release(github):
    assert updates.pick(RELEASES, "stable")["version"] == "0.3.0"  # ni brouillon, ni bêta, ni version sans fichiers
    assert updates.pick(RELEASES, "beta")["version"] == "0.4.0b2"


def test_check_messages(github, monkeypatch):
    monkeypatch.setattr(updates, "__version__", "0.3.0")
    beta = updates.check("beta")
    assert beta["retard"] == 1 and "0.4.0b2 (bêta) disponible" in beta["message"]
    assert beta["nouveautes"] == ["Bouton bêta", "Plus rapide"]
    assert updates.check("stable")["retard"] == 0

    monkeypatch.setattr(updates, "__version__", "0.4.0b2")
    back = updates.check("stable")  # quitter la bêta : on attend la prochaine version stable
    assert back["retard"] == 0 and "bêta" in back["message"]


def test_private_repository_needs_a_token(github):
    github["status"] = 404
    with pytest.raises(updates.UpdateError, match="jeton"):
        updates.check("stable")
    github["status"] = 200
    updates.list_releases("github_pat_test")
    assert github["calls"][-1][1]["Authorization"] == "Bearer github_pat_test"


def test_download_checks_the_digest(github, tmp_path):
    best = updates.pick(RELEASES, "beta")
    path = updates.download(best, None, tmp_path)
    assert path.read_bytes() == INSTALLER
    github["installer"] = INSTALLER + b"virus"
    with pytest.raises(updates.UpdateError, match="empreinte"):
        updates.download(best, None, tmp_path)
    assert not path.exists()


def test_local_job_checks_then_installs(github, monkeypatch, tmp_path):
    monkeypatch.setattr(updates, "__version__", "0.3.0")
    launched, exits = [], []
    monkeypatch.setattr(updates, "launch_installer", lambda path: launched.append(path))
    monkeypatch.setattr(updates, "_exit_soon", lambda delay=2.0: exits.append(delay))
    job = updates.LocalJob()

    def wait(stamp):
        for _ in range(100):
            state = job.snapshot()
            if state and state["statut"] != "en_cours" and state["horodatage"] >= stamp:
                return state
            time.sleep(0.02)
        raise AssertionError(job.snapshot())

    checked = wait(job.start("verifier", "beta"))
    assert checked["statut"] == "verifie" and checked["disponible"] == "0.4.0b2"
    done = wait(job.start("installer", "beta"))
    assert done["statut"] == "termine" and launched[0].name == "Foulee-Setup-0.4.0b2.exe" and exits


def test_web_api_on_an_installed_pc(github, monkeypatch):
    monkeypatch.setattr(updates, "mode", lambda: "exe")
    monkeypatch.setattr(updates, "__version__", "0.3.0")
    client = TestClient(web.create_app())
    status = client.get("/api/maj").json()
    assert status["mode"] == "exe" and status["disponible"] and status["jeton_github"] is False

    sent = client.post("/api/maj", json={"action": "verifier"}, headers=WRITE).json()
    for _ in range(100):
        state = client.get("/api/maj").json()["etat"]
        if state and state["statut"] != "en_cours" and state["horodatage"] >= sent["horodatage"]:
            break
        time.sleep(0.02)
    assert state["statut"] == "verifie" and state["canal"] == "stable"

    github["status"] = 401
    assert client.put("/api/github-jeton", json={"jeton": "mauvais"}, headers=WRITE).status_code == 400
    assert vault.get_secret("github") is None
    github["status"] = 200
    saved = client.put("/api/github-jeton", json={"jeton": " github_pat_bon \n"}, headers=WRITE).json()
    assert saved["jeton_github"] is True and vault.get_secret("github") == "github_pat_bon"
    assert client.delete("/api/github-jeton", headers=WRITE).json()["jeton_github"] is False


def test_release_notes_come_from_the_changelog():
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "packaging" / "notes_de_version.py"
    spec = importlib.util.spec_from_file_location("notes_de_version", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from foulee import __version__

    text = module.notes(__version__)
    assert f"Foulee-Setup-{__version__}.exe" in text
    shown = updates._notes(text)  # ce que Foulée affiche dans « Au programme »
    assert shown and not any("Exécuter quand même" in line or "SHA256SUMS" in line for line in shown)
