"""Réglages › Foulée sur ton téléphone : Tailscale relaie l'interface du PC (avec un faux « tailscale »)."""

import json
import sys

import pytest
from fastapi.testclient import TestClient

from foulee import config, telephone

NAME = "mon-pc.tail1234.ts.net"
HEADERS = {"X-Foulee": "1"}
FAKE = """#!{python}
import json, os, pathlib, sys
state = pathlib.Path(os.environ["FAKE_TS_STATE"])
data = json.loads(state.read_text())
args = sys.argv[1:]
data.setdefault("appels", []).append(args)
if args[:2] == ["status", "--json"]:
    print(json.dumps(data["status"]))
elif args[:3] == ["serve", "status", "--json"]:
    print(json.dumps(data["serve"]))
elif args[:1] == ["serve"]:
    if data.get("refus"):
        state.write_text(json.dumps(data))
        print("Access denied: serve config denied")
        sys.exit(1)
    if "off" in args:
        data["serve"] = {{}}
    else:
        data["serve"] = {{"TCP": {{"443": {{"HTTPS": True}}}},
                         "Web": {{"{name}:443": {{"Handlers": {{"/": {{"Proxy": "http://127.0.0.1:" + args[-1]}}}}}}}}}}
state.write_text(json.dumps(data))
"""


@pytest.fixture
def tailscale(tmp_path, monkeypatch):
    """Un faux Tailscale : connecté, HTTPS activé, sans relais au départ."""
    script = tmp_path / "tailscale.py"
    script.write_text(FAKE.format(python=sys.executable, name=NAME))
    if sys.platform == "win32":  # Windows ne lance pas un script Python directement : un petit .cmd le fait
        exe = tmp_path / "tailscale.cmd"
        exe.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
    else:
        exe = script
        exe.chmod(0o755)
    state = tmp_path / "etat.json"
    data = {"status": {"BackendState": "Running", "Self": {"DNSName": NAME + "."}, "CertDomains": [NAME]}, "serve": {}}
    state.write_text(json.dumps(data))
    monkeypatch.setenv("FOULEE_TAILSCALE", str(exe))
    monkeypatch.setenv("FAKE_TS_STATE", str(state))
    monkeypatch.delenv("FOULEE_PORT", raising=False)

    def change(**values):
        current = json.loads(state.read_text())
        for key, value in values.items():
            if key in ("BackendState", "CertDomains"):
                current["status"][key] = value
            else:
                current[key] = value
        state.write_text(json.dumps(current))
        return current

    change.read = lambda: json.loads(state.read_text())
    return change


def test_without_tailscale(monkeypatch, tmp_path):
    monkeypatch.setenv("FOULEE_TAILSCALE", str(tmp_path / "absent"))
    info = telephone.status()
    assert info["installe"] is False and info["telechargement"].startswith("https://tailscale.com")
    with pytest.raises(telephone.PhoneError, match="Installe d'abord Tailscale"):
        telephone.enable()


def test_each_missing_step_is_explained(tailscale):
    tailscale(BackendState="NeedsLogin")
    info = telephone.status()
    assert info["installe"] and not info["connecte"] and info["nom"] is None
    with pytest.raises(telephone.PhoneError, match="pas connecté"):
        telephone.enable()
    tailscale(BackendState="Running", CertDomains=[])
    info = telephone.status()
    assert info["connecte"] and info["nom"] == NAME and info["https"] is False
    with pytest.raises(telephone.PhoneError, match="HTTPS"):
        telephone.enable()
    assert telephone.allowed_host() is None


def test_enable_relays_foulee_and_accepts_the_name(tailscale):
    from foulee.web import create_app

    web = TestClient(create_app())
    remote = {"host": NAME}
    assert web.get("/api/bootstrap", headers=remote).status_code == 403  # nom pas encore accepté
    info = web.put("/api/telephone", headers=HEADERS, json={"actif": True}).json()
    assert info["actif"] and info["autorise"] and info["adresse"] == f"https://{NAME}/"
    assert ["serve", "--bg", "--yes", "8770"] in tailscale.read()["appels"]
    assert config.load_user_config()[telephone.CONFIG_KEY] == NAME
    assert web.get("/api/bootstrap", headers=remote).status_code == 200
    qr = web.get("/api/telephone/qr.svg")
    assert qr.status_code == 200 and qr.headers["content-type"].startswith("image/svg+xml") and b"<svg" in qr.content and b"xmlns" in qr.content

    info = web.put("/api/telephone", headers=HEADERS, json={"actif": False}).json()
    assert not info["actif"] and not info["autorise"]
    assert ["serve", "--https=443", "off"] in tailscale.read()["appels"]
    assert telephone.CONFIG_KEY not in config.load_user_config()
    assert web.get("/api/bootstrap", headers=remote).status_code == 403
    assert web.get("/api/telephone/qr.svg").status_code == 404


def test_a_relay_set_by_hand_is_kept(tailscale):
    """Déjà fait à la main dans PowerShell (tailscale serve --bg 8770) : Foulée accepte juste le nom."""
    tailscale(serve={"Web": {f"{NAME}:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8770"}}}}})
    info = telephone.status()
    assert info["actif"] and not info["autorise"]
    assert telephone.enable()["autorise"]
    assert not [a for a in tailscale.read()["appels"] if a[:1] == ["serve"] and "status" not in a]


def test_another_port_or_a_refusal(tailscale, monkeypatch):
    tailscale(serve={"Web": {f"{NAME}:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:9999"}}}}})
    assert telephone.status()["actif"] is False  # relaie autre chose que Foulée
    tailscale(refus=True)
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(telephone.PhoneError, match="Tailscale a refusé"):
        telephone.enable()
    assert telephone.allowed_host() is None
