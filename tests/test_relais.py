"""Le relais du club (coach et élèves) : comptes, invitations, sessions, et le Foulée qui s'y connecte."""

import json

import pytest
from fastapi.testclient import TestClient

from foulee import coach, db, vault
from foulee.relais import store
from foulee.relais.app import create_relay_app

PASSWORD = "un-mot-de-passe-solide"


@pytest.fixture
def relay(monkeypatch):
    """Le relais tourne dans le même processus ; le Foulée de ce test lui parle par coach.transport."""
    client = TestClient(create_relay_app())

    def send(method, url, *, headers, payload):
        path = url.split("://", 1)[1].split("/", 1)[1]
        response = client.request(method, "/" + path, headers=headers, json=payload)
        return response.status_code, response.json() if response.content else {}

    monkeypatch.setattr(coach, "transport", send)
    with store.session() as conn:
        store.create_account(conn, ident="william", name="William L.", password=PASSWORD, role="coach", admin=True)
    return client


def login(client, ident="william", password=PASSWORD):
    return client.post("/api/v1/connexion", json={"identifiant": ident, "mot_de_passe": password, "appareil": "test"})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_password_hash_never_stored_in_clear(relay):
    with store.session() as conn:
        row = store.find(conn, "william")
    assert PASSWORD not in row["mot_de_passe"] and row["mot_de_passe"].startswith("scrypt$")
    assert store.check_password(PASSWORD, row["mot_de_passe"])
    assert not store.check_password("mauvais-mot-de-passe", row["mot_de_passe"])


def test_health_and_unknown_routes(relay):
    data = relay.get("/api/v1/sante").json()
    assert data["service"] == "foulee-relais" and data["api"] == 1
    assert relay.get("/api/v1/sante").headers["x-foulee-api"] == "1"
    assert relay.get("/docs").status_code == 404
    assert relay.get("/api/v1/eleves").status_code == 401


def test_login_and_token_only_as_fingerprint(relay):
    res = login(relay)
    assert res.status_code == 200
    token = res.json()["jeton"]
    assert res.json()["compte"]["role"] == "coach" and res.json()["compte"]["admin"] is True
    with store.session() as conn:
        stored = [row[0] for row in conn.execute("SELECT empreinte FROM sessions")]
    assert token not in stored and len(stored) == 1
    assert relay.get("/api/v1/moi", headers=auth(token)).json()["compte"]["identifiant"] == "william"
    relay.post("/api/v1/deconnexion", headers=auth(token))
    assert relay.get("/api/v1/moi", headers=auth(token)).status_code == 401


def test_wrong_password_then_lockout(relay):
    for _ in range(5):
        assert login(relay, password="faux-mot-de-passe").status_code == 401
    res = login(relay)
    assert res.status_code == 429 and "15 minutes" in res.json()["detail"]
    assert login(relay, ident="inconnu").status_code in (401, 429)


def test_invitation_join_and_group(relay):
    coach_token = login(relay).json()["jeton"]
    code = relay.post("/api/v1/invitations", headers=auth(coach_token)).json()["invitation"]["code"]
    assert len(code) == 9 and code[4] == "-"
    res = relay.post("/api/v1/inscription", json={"code": code.lower().replace("-", " "), "identifiant": "Marie.D",
                                                  "nom": "Marie D.", "mot_de_passe": PASSWORD})
    assert res.status_code == 200, res.text
    student = res.json()["compte"]
    assert student["identifiant"] == "marie.d" and student["role"] == "eleve"
    assert student["coach"]["nom"] == "William L."
    # Code à usage unique
    again = relay.post("/api/v1/inscription", json={"code": code, "identifiant": "paul", "nom": "Paul",
                                                    "mot_de_passe": PASSWORD})
    assert again.status_code == 400 and "invitation" in again.json()["detail"]
    group = relay.get("/api/v1/eleves", headers=auth(coach_token)).json()["eleves"]
    assert [s["identifiant"] for s in group] == ["marie.d"]
    assert relay.get("/api/v1/invitations", headers=auth(coach_token)).json()["invitations"] == []
    # Un élève n'a pas accès aux pages du coach
    student_token = res.json()["jeton"]
    assert relay.get("/api/v1/eleves", headers=auth(student_token)).status_code == 403
    # Le coach retire l'élève : son compte et ses sessions disparaissent
    relay.delete(f"/api/v1/eleves/{student['id']}", headers=auth(coach_token))
    assert relay.get("/api/v1/moi", headers=auth(student_token)).status_code == 401


def test_join_validations(relay):
    coach_token = login(relay).json()["jeton"]
    code = relay.post("/api/v1/invitations", headers=auth(coach_token)).json()["invitation"]["code"]
    short = relay.post("/api/v1/inscription", json={"code": code, "identifiant": "paul", "nom": "Paul",
                                                    "mot_de_passe": "court"})
    assert short.status_code == 400 and "trop court" in short.json()["detail"]
    taken = relay.post("/api/v1/inscription", json={"code": code, "identifiant": "william", "nom": "W",
                                                    "mot_de_passe": PASSWORD})
    assert taken.status_code == 400 and "déjà pris" in taken.json()["detail"]
    # Les refus n'ont pas consommé le code
    assert relay.get("/api/v1/invitations", headers=auth(coach_token)).json()["invitations"][0]["code"] == code


def test_password_change_closes_other_sessions(relay):
    first = login(relay).json()["jeton"]
    second = login(relay).json()["jeton"]
    res = relay.post("/api/v1/moi/mot-de-passe", headers=auth(first),
                     json={"actuel": PASSWORD, "nouveau": "nouveau-mot-de-passe"})
    assert res.status_code == 200
    assert relay.get("/api/v1/moi", headers=auth(first)).status_code == 200
    assert relay.get("/api/v1/moi", headers=auth(second)).status_code == 401
    assert login(relay, password="nouveau-mot-de-passe").status_code == 200


def test_disabled_account(relay):
    token = login(relay).json()["jeton"]
    with store.session() as conn:
        store.set_active(conn, store.find(conn, "william")["id"], False)
    assert relay.get("/api/v1/moi", headers=auth(token)).status_code == 401
    assert login(relay).status_code == 403


# ---------------------------------------------------------------- côté Foulée
def test_clean_url():
    assert coach.clean_url("relais.mon-club.com/") == "https://relais.mon-club.com"
    assert coach.clean_url("http://127.0.0.1:8770") == "http://127.0.0.1:8770"
    with pytest.raises(ValueError, match="HTTPS"):
        coach.clean_url("http://relais.mon-club.com")
    with pytest.raises(ValueError):
        coach.clean_url("https://moi:secret@relais.mon-club.com")


def test_foulee_coach_and_student_end_to_end(relay):
    url = "https://relais.test"
    with db.session() as conn:
        info = coach.login(conn, url, "william", PASSWORD)
        assert info["relie"] and info["compte"]["role"] == "coach"
        assert coach.light(conn) == {"role": "coach", "nom": "William L.", "coach": None, "meme_club": False}
        # Le jeton est dans le coffre, jamais dans la base ni dans l'état renvoyé à l'interface
        token = vault.get_secret("relais")
        assert token and token not in json.dumps(info)
        assert token not in json.dumps([dict(r) for r in conn.execute("SELECT * FROM meta")])
        invitation = coach.create_invitation(conn)["invitation"]
        assert coach.invitations(conn)[0]["code"] == invitation["code"]
        coach.logout(conn)
        assert not coach.status(conn)["relie"] and vault.get_secret("relais") is None
        # Le même PC, cette fois en élève
        info = coach.join(conn, url, code=invitation["code"], ident="marie", name="Marie", password=PASSWORD)
        assert info["compte"]["role"] == "eleve" and info["compte"]["coach"]["nom"] == "William L."
        assert coach.light(conn)["coach"] == "William L."
        coach.leave(conn, PASSWORD)
        assert not coach.status(conn)["relie"]
        with store.session() as relay_conn:
            assert store.find(relay_conn, "marie") is None


def test_foulee_forgets_closed_session(relay):
    with db.session() as conn:
        coach.login(conn, "https://relais.test", "william", PASSWORD)
        with store.session() as relay_conn:
            relay_conn.execute("DELETE FROM sessions")
        with pytest.raises(coach.CoachError) as err:
            coach.students(conn)
        assert err.value.status == 401
        assert not coach.status(conn)["relie"]


def test_web_endpoints_require_local_for_login(relay, monkeypatch):
    from foulee import access
    from foulee.web import create_app

    client = TestClient(create_app())
    headers = {"X-Foulee": "1"}
    res = client.post("/api/coach/connexion", headers=headers,
                      json={"adresse": "https://relais.test", "identifiant": "william", "mot_de_passe": PASSWORD})
    assert res.status_code == 200, res.text
    assert res.json()["compte"]["role"] == "coach"
    assert client.get("/api/bootstrap").json()["coach"]["role"] == "coach"
    group = client.get("/api/coach/groupe").json()
    assert group == {"eleves": [], "invitations": []}
    code = client.post("/api/coach/invitations", headers=headers).json()["invitation"]["code"]
    assert client.get("/api/coach/groupe").json()["invitations"][0]["code"] == code
    bad = client.post("/api/coach/connexion", headers=headers,
                      json={"adresse": "https://relais.test", "identifiant": "william", "mot_de_passe": "faux-faux-faux"})
    assert bad.status_code == 401
    # Depuis le réseau local (pas la machine) : la connexion, qui range un secret, est refusée
    monkeypatch.setattr(access, "is_local_client", lambda host: False)
    monkeypatch.setattr(access, "is_enabled", lambda: True)
    monkeypatch.setattr(access, "cookie_valid", lambda value: True)
    remote = TestClient(create_app())
    res = remote.post("/api/coach/connexion", headers=headers,
                      json={"adresse": "https://relais.test", "identifiant": "william", "mot_de_passe": PASSWORD})
    assert res.status_code == 403


def test_cli_creates_admin(monkeypatch, capsys):
    from foulee import cli

    answers = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    assert cli.main(["relais", "admin", "w.lequin", "--nom", "William"]) == 0
    assert "créé" in capsys.readouterr().out
    with store.session() as conn:
        row = store.find(conn, "w.lequin")
    assert row["admin"] == 1 and row["role"] == "coach"
    assert cli.main(["relais", "admin", "autre", "--nom", "X"]) == 1  # déjà un administrateur
    assert cli.main(["relais", "comptes"]) == 0
    assert "w.lequin" in capsys.readouterr().out
