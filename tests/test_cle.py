"""Clé Garmin depuis l'interface : la remplacer, et savoir quand Garmin la refuse."""

import pytest
from fake_garmin import FakeGarmin
from fastapi.testclient import TestClient

from foulee import db, sync, vault, web

WRITE = {"X-Foulee": "1"}
KEY = "GCDC_0f1e2d3c-test.4b5a6978-cle.SecretDeTest"


@pytest.fixture
def garmin(monkeypatch):
    with FakeGarmin(days=5, activities=1) as fake:
        monkeypatch.setenv("GARMIN_PERSONAL_API_BASE_URL", fake.url)
        yield fake


def test_replace_the_key_from_the_settings(garmin):
    client = TestClient(web.create_app())
    assert client.get("/api/cle").json()["enregistree"] is False

    garbage = client.put("/api/cle", json={"cle": "\x16"}, headers=WRITE)
    assert garbage.status_code == 400 and "ne peut pas être une clé" in garbage.json()["detail"]
    assert garmin.requests == []  # rien n'est parti chez Garmin

    refused = client.put("/api/cle", json={"cle": "GCDC_refuse-0000.1111.secret"}, headers=WRITE)
    assert refused.status_code == 400 and "HTTP 401" in refused.json()["detail"]
    assert "GCDC_refuse-0000.1111.secret" not in refused.text

    ok = client.put("/api/cle", json={"cle": f"  {KEY[:20]}\n{KEY[20:]}  "}, headers=WRITE)
    assert ok.status_code == 200
    body = ok.json()
    assert body["enregistree"] and body["enregistree_le"] and "commence bien par GCDC_" in body["lu"]
    assert KEY not in ok.text
    assert vault.get_key() == KEY

    assert client.delete("/api/cle", headers=WRITE).json()["enregistree"] is False
    assert vault.get_key() is None


def test_key_cannot_travel_over_the_local_network(garmin, monkeypatch):
    from foulee import access

    monkeypatch.setattr(access, "ITERATIONS", 1000)
    access.set_password("mot-de-passe-maison")
    app = web.create_app()
    lan = TestClient(app, client=("192.168.0.50", 50000))
    login = lan.post("/api/connexion", json={"mot_de_passe": "mot-de-passe-maison"},
                     headers={**WRITE, "Host": "192.168.0.19"})
    assert login.status_code == 200
    blocked = lan.put("/api/cle", json={"cle": KEY}, headers={**WRITE, "Host": "192.168.0.19"})
    assert blocked.status_code == 403 and vault.get_key() is None


def test_sync_remembers_a_refused_key_until_it_is_replaced(garmin):
    vault.set_key("GCDC_refuse-ancienne-cle")
    result = sync.run()
    assert result["statut"] == "echec"
    client = TestClient(web.create_app())
    refused = client.get("/api/bootstrap").json()["cle_refusee"]
    assert refused and refused["statut"] == 401 and refused["depuis"]

    sync.run()  # un second échec garde la date du premier
    with db.session(readonly=True) as conn:
        assert sync.key_refused(conn)["depuis"] == refused["depuis"]

    assert client.put("/api/cle", json={"cle": KEY}, headers=WRITE).status_code == 200
    assert client.get("/api/bootstrap").json()["cle_refusee"] is None
    assert sync.run()["statut"] in ("ok", "partiel")
