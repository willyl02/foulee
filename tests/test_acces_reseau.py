"""Accès par le réseau local : fermé par défaut, puis protégé par un mot de passe."""

import sys

import pytest
from fastapi.testclient import TestClient

from foulee import access, web

PASSWORD = "foulée-maison-2026"
LAN_HOST = {"Host": "192.168.0.19:8770"}


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(access, "ITERATIONS", 1000)  # les tests n'ont pas besoin d'une empreinte lente
    monkeypatch.setenv("FOULEE_ECOUTE", "0.0.0.0")
    monkeypatch.setenv("FOULEE_HOTES", "foulee.tail1234.ts.net")
    return web.create_app()


def local_client(app):
    """Comme Tailscale : la connexion arrive par la machine elle-même."""
    return TestClient(app, client=("127.0.0.1", 50000))


def lan_client(app, ip="192.168.0.50"):
    return TestClient(app, client=(ip, 50000), follow_redirects=False)


def write(client, method, path, **kwargs):
    headers = {"X-Foulee": "1", **LAN_HOST, **kwargs.pop("headers", {})}
    return client.request(method, path, headers=headers, **kwargs)


def test_lan_is_closed_until_a_password_is_chosen(app):
    lan = lan_client(app)
    page = lan.get("/", headers=LAN_HOST)
    assert page.status_code == 403 and "désactivé" in page.text
    assert lan.get("/api/bootstrap", headers=LAN_HOST).status_code == 403
    assert "désactivé" in lan.get("/connexion", headers=LAN_HOST).text
    # Par Tailscale (machine elle-même) : aucun mot de passe
    assert local_client(app).get("/api/bootstrap", headers={"Host": "foulee.tail1234.ts.net"}).json()["acces"] == "local"


def test_password_login_and_cookie(app):
    local = local_client(app)
    assert local.put("/api/acces-reseau", json={"mot_de_passe": "court"}, headers={"X-Foulee": "1"}).status_code == 400
    status = local.put("/api/acces-reseau", json={"mot_de_passe": PASSWORD}, headers={"X-Foulee": "1"}).json()
    assert status["actif"] and status["ecoute"] and status["depuis"] == "local"
    assert "empreinte" not in status and PASSWORD not in str(status)

    lan = lan_client(app)
    redirect = lan.get("/", headers=LAN_HOST)
    assert redirect.status_code == 303 and redirect.headers["location"] == "/connexion"
    assert lan.get("/api/bootstrap", headers=LAN_HOST).status_code == 401
    assert 'type="password"' in lan.get("/connexion", headers=LAN_HOST).text

    assert write(lan, "POST", "/api/connexion", json={"mot_de_passe": "mauvais-mot"}).status_code == 401
    ok = write(lan, "POST", "/api/connexion", json={"mot_de_passe": PASSWORD})
    assert ok.status_code == 200
    cookie = ok.headers["set-cookie"]
    assert "httponly" in cookie.lower() and "samesite=strict" in cookie.lower()

    boot = lan.get("/api/bootstrap", headers=LAN_HOST)
    assert boot.status_code == 200 and boot.json()["acces"] == "reseau"
    assert lan.get("/", headers=LAN_HOST).status_code == 200
    # Depuis le réseau local, on ne change pas le mot de passe
    assert write(lan, "PUT", "/api/acces-reseau", json={"mot_de_passe": "autre-mot-de-passe"}).status_code == 403
    assert write(lan, "DELETE", "/api/acces-reseau").status_code == 403

    # Changer le mot de passe (par Tailscale) déconnecte tout le monde
    local.put("/api/acces-reseau", json={"mot_de_passe": "nouveau-mot-de-passe"}, headers={"X-Foulee": "1"})
    assert lan.get("/api/bootstrap", headers=LAN_HOST).status_code == 401

    # Couper l'accès referme le réseau local
    assert local.delete("/api/acces-reseau", headers={"X-Foulee": "1"}).json()["actif"] is False
    assert lan.get("/api/bootstrap", headers=LAN_HOST).status_code == 403


def test_too_many_wrong_passwords_lock_the_address(app):
    access.set_password(PASSWORD)
    lan = lan_client(app, ip="192.168.0.66")
    for _ in range(access.MAX_FAILURES):
        assert write(lan, "POST", "/api/connexion", json={"mot_de_passe": "essai-au-hasard"}).status_code == 401
    assert write(lan, "POST", "/api/connexion", json={"mot_de_passe": PASSWORD}).status_code == 429
    # Une autre adresse n'est pas bloquée
    assert write(lan_client(app, ip="192.168.0.67"), "POST", "/api/connexion", json={"mot_de_passe": PASSWORD}).status_code == 200


def test_host_header_rules(app):
    access.set_password(PASSWORD)
    lan = lan_client(app)
    assert lan.get("/connexion", headers={"Host": "192.168.0.19:8770"}).status_code == 200
    assert lan.get("/connexion", headers={"Host": "pirate.example"}).status_code == 403  # « DNS rebinding »
    assert local_client(app).get("/", headers={"Host": "[::1]:8770"}).status_code == 200
    assert web.host_name("Foulee.Tail1234.ts.net.:443") == "foulee.tail1234.ts.net"


def test_cookie_signature_and_expiry(monkeypatch):
    monkeypatch.setattr(access, "ITERATIONS", 1000)
    access.set_password(PASSWORD)
    cookie = access.make_cookie(now=1_000_000)
    assert access.cookie_valid(cookie, now=1_000_100)
    assert not access.cookie_valid(cookie, now=1_000_000 + access.SESSION_DAYS * 86400 + 1)
    expiry, signature = cookie.split(".")
    assert not access.cookie_valid(f"{int(expiry) + 3600}.{signature}", now=1_000_100)  # date trafiquée
    assert not access.cookie_valid("n'importe quoi")
    assert access.check_password(PASSWORD) and not access.check_password(PASSWORD.upper())
    if sys.platform != "win32":  # Windows : droits hérités du dossier de l'utilisateur
        assert access.path().stat().st_mode & 0o077 == 0  # lisible par le seul propriétaire
