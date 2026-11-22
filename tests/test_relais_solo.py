"""0.8.3b16 : les comptes « sans coach » sur le relais, pour envoyer les séances de l'Atelier sur sa montre.
Un compte solo ne voit rien d'autre sur le relais, ne partage rien, et devient élève avec un code d'invitation."""

import sqlite3
from datetime import date, timedelta

from fastapi.testclient import TestClient

from foulee import atelier, coach, db
from foulee.relais import store
from foulee.web import create_app
from test_atelier import RUN
from test_relais_garmin import ADDRESS, PASSWORD, accept, fake, relay, token  # noqa: F401

HEADERS = {"X-Foulee": "1"}


def solo(client, ident="paul", name="Paul S."):
    res = client.post("/api/v1/inscription", json={"solo": True, "identifiant": ident, "nom": name,
                                                   "mot_de_passe": PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": "Bearer " + res.json()["jeton"]}, res.json()["compte"]


def test_solo_account_only_reaches_its_watch(relay, fake):
    assert relay.get("/api/v1/sante").json()["solo"] is True
    paul, account = solo(relay)
    assert account["role"] == "solo" and "coach" not in account
    assert relay.get("/api/v1/moi", headers=paul).json()["compte"]["role"] == "solo"
    # rien du suivi de groupe : élèves, partage, conversations, notifications, calendrier
    for method, path in (("GET", "/api/v1/eleves"), ("PUT", "/api/v1/partage"), ("GET", "/api/v1/fils"),
                         ("GET", "/api/v1/notifications"), ("GET", "/api/v1/moi/coach"), ("GET", "/api/v1/moi/calendrier"),
                         ("POST", "/api/v1/invitations"), ("GET", "/api/v1/groupe")):
        res = relay.request(method, path, headers=paul, json={} if method != "GET" else None)
        assert res.status_code == 403, (path, res.status_code)
    # sa montre : relier, envoyer sa séance (avec ses allures), délier
    assert relay.get("/api/v1/garmin", headers=paul).json()["relie"] is False
    day = (date.today() + timedelta(days=1)).isoformat()
    first = relay.post("/api/v1/garmin/perso", headers=paul, json={**atelier.to_item(RUN, day), "vma_kmh": 15})
    assert first.json()["a_relier"] is True
    accept(relay, fake, first.json()["adresse"])
    sent = relay.post("/api/v1/garmin/perso", headers=paul, json={**atelier.to_item(RUN, day), "vma_kmh": 15}).json()
    assert sent["envoi"]["date"] == day and len(fake.workouts) == 1
    assert relay.delete("/api/v1/garmin", headers=paul).json()["relie"] is False


def test_solo_account_joins_a_coach_later(relay, fake):
    sophie = token(relay, "sophie")
    paul, account = solo(relay)
    bad = relay.post("/api/v1/moi/rejoindre", headers=paul, json={"code": "ABCD-EFGH"})
    assert bad.status_code == 400 and "invitation" in bad.json()["detail"]
    code = relay.post("/api/v1/invitations", headers=sophie).json()["invitation"]["code"]
    done = relay.post("/api/v1/moi/rejoindre", headers=paul, json={"code": code}).json()["compte"]
    assert done["role"] == "eleve" and done["coach"]["nom"] == "Sophie R." and done["id"] == account["id"]
    assert relay.get("/api/v1/moi/coach", headers=paul).status_code == 200      # le suivi du coach, maintenant
    assert any(e["id"] == account["id"] for e in relay.get("/api/v1/eleves", headers=sophie).json()["eleves"])
    assert relay.post("/api/v1/moi/rejoindre", headers=paul, json={"code": code}).status_code == 400
    # un compte sans coach se supprime lui-même
    other, _ = solo(relay, "lea", "Léa")
    assert relay.post("/api/v1/moi/quitter", headers=other, json={"mot_de_passe": PASSWORD}).json()["ok"] is True
    assert relay.get("/api/v1/moi", headers=other).status_code == 401


def test_solo_sign_up_can_be_closed_or_capped(relay, monkeypatch):
    monkeypatch.setenv("FOULEE_RELAIS_SOLO", "0")
    assert relay.get("/api/v1/sante").json()["solo"] is False
    res = relay.post("/api/v1/inscription", json={"solo": True, "identifiant": "zoe", "nom": "Zoé", "mot_de_passe": PASSWORD})
    assert res.status_code == 400 and "sans coach" in res.json()["detail"]
    monkeypatch.setenv("FOULEE_RELAIS_SOLO", "1")
    monkeypatch.setenv("FOULEE_RELAIS_SOLO_MAX", "1")
    solo(relay, "zoe", "Zoé")
    res = relay.post("/api/v1/inscription", json={"solo": True, "identifiant": "max", "nom": "Max", "mot_de_passe": PASSWORD})
    assert res.status_code == 400 and "nombre" in res.json()["detail"]


def test_old_relay_database_learns_the_solo_role(tmp_path, monkeypatch):
    monkeypatch.setenv("FOULEE_DATA", str(tmp_path))
    store._SOLO_READY.clear()
    old = store.SCHEMA.replace("CHECK (role IN ('coach', 'eleve', 'solo'))", "CHECK (role IN ('coach', 'eleve'))")
    conn = sqlite3.connect(tmp_path / "relais.db")
    conn.executescript(old)
    conn.execute("INSERT INTO comptes(identifiant, nom, role, admin, mot_de_passe, cree_le) VALUES "
                 "('sophie', 'Sophie R.', 'coach', 1, 'x', '2026-11-01 10:00:00')")
    conn.execute("INSERT INTO comptes(identifiant, nom, role, coach_id, mot_de_passe, cree_le) VALUES "
                 "('lucas', 'Lucas B.', 'eleve', 1, 'x', '2026-11-02 10:00:00')")
    conn.execute("INSERT INTO sessions(empreinte, compte_id, cree_le, vu_le) VALUES ('e1', 2, 'a', 'b')")
    conn.commit()
    conn.close()
    with store.session() as conn:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'comptes'").fetchone()["sql"]
        assert "'solo'" in sql
        assert [r["identifiant"] for r in conn.execute("SELECT identifiant FROM comptes ORDER BY id")] == ["sophie", "lucas"]
        store.register_solo(conn, ident="paul", name="Paul", password=PASSWORD)
        # les liens vers les comptes tiennent toujours : effacer un élève efface ses sessions
        conn.execute("DELETE FROM comptes WHERE identifiant = 'lucas'")
        assert conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"] == 0
    store._SOLO_READY.clear()


def test_foulee_links_without_a_coach(relay, fake):
    with db.session() as conn:
        info = coach.join_solo(conn, ADDRESS, ident="paul", name="Paul S.", password=PASSWORD)
        assert info["compte"]["role"] == "solo" and coach.light(conn) is None   # pas de page « Mon coach »
        assert coach.exchange(conn) == {"fait": False}                        # rien n'est partagé
    client = TestClient(create_app())
    assert client.get("/api/atelier").json()["montre"] is True
    assert client.get("/api/renfo/seances").json()["montre"] is True
    day = (date.today() + timedelta(days=3)).isoformat()
    first = client.post("/api/atelier/seance/montre", headers=HEADERS, json={"seance": RUN, "date": day}).json()
    accept(relay, fake, first["adresse"])
    sent = client.post("/api/atelier/seance/montre", headers=HEADERS, json={"seance": RUN, "date": day}).json()
    assert sent["envoi"]["date"] == day
    # le jour où il a un coach
    code = relay.post("/api/v1/invitations", headers=token(relay, "sophie")).json()["invitation"]["code"]
    after = client.post("/api/coach/rejoindre", headers=HEADERS, json={"code": code}).json()
    assert after["compte"]["role"] == "eleve" and after["compte"]["coach"]["nom"] == "Sophie R."
    with db.session() as conn:
        assert coach.light(conn)["role"] == "eleve"
