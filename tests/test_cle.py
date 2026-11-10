"""Clé Garmin depuis l'interface : la remplacer, et savoir quand Garmin la refuse."""

import datetime as dt
import json

import pytest
from fake_garmin import DELETED_KEY_ID, FakeGarmin
from fastapi.testclient import TestClient

from foulee import config, db, sync, vault, web

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


def test_a_deleted_key_stops_the_sync_at_once(garmin):
    """Clé supprimée ou régénérée dans Garmin Connect : l'échange répond 404 (vu en 0.4.0). Avant, chaque
    flux réessayait, la synchro passait pour « partielle » et la date de dernière synchro avançait."""
    vault.set_key(KEY)
    assert sync.run(since=garmin.today - dt.timedelta(days=3))["statut"] == "ok"
    with db.session() as conn:
        db.set_meta(conn, "last_sync", "2026-01-01 08:00:00")
    garmin.deleted_keys.add(KEY)
    garmin.revoked = True  # le jeton gardé en cache ne vaut plus rien non plus
    before = len(garmin.requests)

    result = sync.run()
    assert result["statut"] == "echec"
    error = result["sources"]["garmin"]["erreur"]
    assert "ne connaît plus cette clé" in error and "Réglages → Clé API Garmin" in error
    assert len(garmin.requests) - before == 2  # une lecture refusée, un échange refusé : on s'arrête là
    assert not config.token_cache_file().exists()
    with db.session(readonly=True) as conn:
        assert db.get_meta(conn, "last_sync") == "2026-01-01 08:00:00"  # pas de fausse synchro réussie
        assert sync.key_refused(conn)["statut"] == 404
        journal = conn.execute("SELECT group_concat(summary) AS s FROM sync_log").fetchone()["s"]
    assert DELETED_KEY_ID not in journal and DELETED_KEY_ID not in json.dumps(result)

    client = TestClient(web.create_app())
    assert client.get("/api/bootstrap").json()["cle_refusee"]["statut"] == 404
    replaced = client.put("/api/cle", json={"cle": KEY}, headers=WRITE)  # la même : toujours inconnue
    assert replaced.status_code == 400 and "HTTP 404" in replaced.json()["detail"]
    assert DELETED_KEY_ID not in replaced.text and KEY not in replaced.text


def test_nothing_answered_is_a_failure_not_a_partial_sync(garmin, monkeypatch):
    from foulee.garmin import client as garmin_client

    monkeypatch.setattr(garmin_client.time, "sleep", lambda seconds: None)
    vault.set_key(KEY)
    garmin.fail_status = 503
    result = sync.run()
    assert result["statut"] == "echec" and "Aucune donnée" in result["sources"]["garmin"]["erreur"]
    with db.session(readonly=True) as conn:
        assert db.get_meta(conn, "last_sync") is None
        assert sync.key_refused(conn) is None  # panne de Garmin : la clé n'y est pour rien
        assert db.get_sync_state(conn, "garmin", "activities") is None  # rien de sauté la prochaine fois

    garmin.fail_status = None
    assert sync.run()["statut"] == "ok"


def test_garmin_messages_never_carry_the_key_or_its_id():
    from foulee.garmin.client import garmin_detail

    text = (f'{{"message":"Personal API Key with ID {DELETED_KEY_ID} does not exist."}} '
            f"echo {KEY} / 0f1e2d3c-test / SecretDeTest / eyJhbGciOi.eyJleHAiOjF9.sig")
    shown = garmin_detail(text, KEY, limit=500)
    for secret in (DELETED_KEY_ID, KEY, "SecretDeTest", "0f1e2d3c-test", "eyJhbGciOi"):
        assert secret not in shown
    assert "does not exist" in shown and "[identifiant masqué]" in shown


def test_old_sync_journal_is_cleaned(monkeypatch):
    with db.session() as conn:
        conn.execute("DELETE FROM meta WHERE key = 'journal_masque'")
        conn.execute("INSERT INTO sync_log(status, summary) VALUES ('partiel', ?)",
                     (json.dumps({"erreurs": [f"Personal API Key with ID {DELETED_KEY_ID} does not exist."]}),))
        conn.commit()
    with db.session() as conn:  # chaque ouverture en écriture passe par db.init
        summary = conn.execute("SELECT summary FROM sync_log").fetchone()["summary"]
    assert DELETED_KEY_ID not in summary and "identifiant masqué" in summary
