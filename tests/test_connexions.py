"""Pastilles de connexion : l'état de chaque source (vert, rouge, gris) d'après le journal des synchros."""

import json

import pytest
from fake_withings import FakeWithings
from fastapi.testclient import TestClient
from test_withings import RELAY, authorize, wait_for_sync

from foulee import config, db, sync, vault, web
from foulee.garmin.client import GarminError


def states() -> dict:
    with db.session(readonly=True) as conn:
        return {c["cle"]: c for c in sync.connections(conn)}


def garmin_ok(conn, **kwargs) -> dict:
    return {"seances_nouvelles": 0, "erreurs": []}


def garmin_down(conn, **kwargs) -> dict:
    raise GarminError("Impossible de joindre Garmin (ConnectError) : vérifie la connexion à Internet.")


def test_without_key_garmin_is_red_and_withings_absent():
    c = states()
    assert set(c) == {"garmin"}  # pas de compte Withings : pas de pastille
    assert c["garmin"]["etat"] == "ko" and c["garmin"]["bloque"] and "Aucune clé" in c["garmin"]["texte"]


def test_key_but_no_sync_yet_is_grey():
    vault.set_key("cle-de-test")
    assert states()["garmin"]["etat"] == "attente"


def test_ok_then_failure_then_partial(monkeypatch):
    vault.set_key("cle-de-test")
    monkeypatch.setitem(sync.SOURCES, "garmin", garmin_ok)
    sync.run()
    first = states()["garmin"]
    assert first["etat"] == "ok" and first["derniere_reussie"] == first["derniere"] and first["erreur"] is None

    monkeypatch.setitem(sync.SOURCES, "garmin", garmin_down)
    sync.run()
    down = states()["garmin"]
    assert down["etat"] == "ko" and "Impossible de joindre Garmin" in down["erreur"] and not down["bloque"]
    assert down["derniere_reussie"] == first["derniere_reussie"]  # la dernière réussite reste affichée

    # Synchro aboutie avec un flux en échec : vert, l'alerte est signalée dans le détail
    monkeypatch.setitem(sync.SOURCES, "garmin", lambda conn, **kw: {"erreurs": ["Sommeil : HTTP 500"]})
    sync.run()
    partial = states()["garmin"]
    assert partial["etat"] == "ok" and partial["alertes"] == 1


def test_refused_key_is_red_until_a_sync_works(monkeypatch):
    vault.set_key("cle-de-test")

    def refused(conn, **kwargs):
        raise GarminError("Garmin refuse la clé API (HTTP 404).", 404, key_rejected=True)

    monkeypatch.setitem(sync.SOURCES, "garmin", refused)
    sync.run()
    c = states()["garmin"]
    assert c["etat"] == "ko" and c["bloque"] and c["depuis"] and "refuse ta clé" in c["texte"]
    monkeypatch.setitem(sync.SOURCES, "garmin", garmin_ok)
    sync.run()
    assert states()["garmin"]["etat"] == "ok"


def test_each_source_has_its_own_state(monkeypatch):
    with FakeWithings(days=10, relay=RELAY) as fake:
        monkeypatch.setenv("FOULEE_WITHINGS_API", fake.url)
        monkeypatch.setenv("FOULEE_WITHINGS_COMPTE", fake.url)
        monkeypatch.setenv("FOULEE_WITHINGS_RELAIS", RELAY)
        vault.set_key("cle-de-test")
        monkeypatch.setitem(sync.SOURCES, "garmin", garmin_down)
        http = TestClient(web.create_app())
        authorize(http, fake)
        wait_for_sync(http)  # premier import : Withings seul
        assert states()["garmin"]["etat"] == "attente"
        sync.run()  # les deux sources : Garmin injoignable, Withings à jour
        c = states()
        assert c["garmin"]["etat"] == "ko" and c["withings"]["etat"] == "ok"
        assert c["withings"]["reglages"] == "withings" and c["garmin"]["reglages"] == "cle"

        fake.revoked = True
        fake.expire_access()
        monkeypatch.setitem(sync.SOURCES, "garmin", garmin_ok)
        sync.run()
        c = states()
        assert c["garmin"]["etat"] == "ok"
        assert c["withings"]["etat"] == "ko" and c["withings"]["bloque"] and "reconnecte" in c["withings"]["texte"]

        # L'interface les reçoit au démarrage et à chaque relecture de l'état de la synchro
        boot = http.get("/api/bootstrap").json()
        assert [x["cle"] for x in boot["connexions"]] == ["garmin", "withings"]
        polled = http.get("/api/sync").json()
        assert {x["cle"]: x["etat"] for x in polled["connexions"]} == {"garmin": "ok", "withings": "ko"}
        # jamais de jeton ni de Secret dans ce qui part vers l'interface
        assert fake.refresh not in json.dumps(boot["connexions"]) and fake.access not in json.dumps(polled)


def test_demo_is_green():
    from foulee import demo

    demo.build(days=40, second_profile=False)
    try:
        c = states()
        assert {k: v["etat"] for k, v in c.items()} == {"garmin": "ok", "withings": "ok"}
        assert "démo" in c["garmin"]["texte"]
    finally:
        config.set_demo(False)


def test_claude_sees_the_connections(monkeypatch):
    from foulee import mcp_server

    vault.set_key("cle-de-test")
    monkeypatch.setitem(sync.SOURCES, "garmin", garmin_down)
    sync.run()
    connexions = mcp_server.statut()["connexions"]
    assert connexions[0]["nom"] == "Garmin" and connexions[0]["etat"] == "ko"
    assert "Impossible de joindre Garmin" in connexions[0]["erreur"]


@pytest.mark.parametrize("summary", ["pas du json", "[]", None])
def test_unreadable_journal_lines_are_skipped(summary):
    vault.set_key("cle-de-test")
    with db.session() as conn:
        conn.execute("INSERT INTO sync_log(started_at, finished_at, source, status, summary) VALUES (?, ?, ?, ?, ?)",
                     ("2026-11-12 10:00:00", "2026-11-12 10:01:00", "garmin", "ok", summary))
    assert states()["garmin"]["etat"] == "attente"
