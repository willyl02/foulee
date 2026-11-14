"""Relais, étapes 2 à 5 : l'accord et l'extrait partagé, les messages, les séances proposées, la vue du coach."""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from foulee import coach, config, db
from foulee.relais import club, store
from foulee.relais.app import create_relay_app

PASSWORD = "un-mot-de-passe-solide"


@pytest.fixture
def relay(monkeypatch):
    client = TestClient(create_relay_app())

    def send(method, url, *, headers, payload):
        path = url.split("://", 1)[1].split("/", 1)[1]
        response = client.request(method, "/" + path, headers=headers, json=payload)
        return response.status_code, response.json() if response.content else {}

    monkeypatch.setattr(coach, "transport", send)
    with store.session() as conn:
        store.create_account(conn, ident="sophie", name="Sophie R.", password=PASSWORD, role="coach", admin=True)
    return client


def token(client, ident):
    return {"Authorization": "Bearer " + client.post("/api/v1/connexion", json={
        "identifiant": ident, "mot_de_passe": PASSWORD}).json()["jeton"]}


def join(client, coach_headers, ident, name):
    code = client.post("/api/v1/invitations", headers=coach_headers).json()["invitation"]["code"]
    res = client.post("/api/v1/inscription", json={"code": code, "identifiant": ident, "nom": name,
                                                   "mot_de_passe": PASSWORD})
    return {"Authorization": "Bearer " + res.json()["jeton"]}, res.json()["compte"]["id"]


def session(key, day, **extra):
    return {"cle": key, "date": day.isoformat(), "debut": f"{day.isoformat()} 18:00:00", "sport": "course",
            "nom": "Seuil 3 × 10 min", "distance_m": 12400, "duree_s": 3420, "allure": "4:38 /km", "fc_moy": 158,
            "charge": 120, **extra}


def test_share_needs_accord_and_follows_it(relay):
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    today = date.today()
    payload = {"seances": [session("garmin:1", today, trace=[[49.0, 3.4], [49.01, 3.41]])],
               "jours": [{"date": today.isoformat(), "sommeil_h": 7.5, "vfc": 61, "poids_kg": 70.2}],
               "profil": {"vma_kmh": 17, "objectif": {"nom": "Semi de Reims", "date": (today + timedelta(days=30))
                                                      .isoformat(), "temps_cible": "1:35:00"}}}
    refused = relay.put("/api/v1/partage", headers=lucas, json=payload)
    assert refused.status_code == 400 and "partages" in refused.json()["detail"]
    relay.put("/api/v1/partage/accord", headers=lucas, json={"seances": True, "objectif": True, "gps": False,
                                                              "sante": True, "poids": False})
    assert relay.put("/api/v1/partage", headers=lucas, json=payload).json()["seances"] == 1
    page = relay.get(f"/api/v1/eleves/{lucas_id}/fiche", headers=sophie).json()
    assert page["seances"][0]["nom"] == "Seuil 3 × 10 min" and page["seances"][0]["trace"] is False
    assert page["jours"] == [{"date": today.isoformat(), "sommeil_h": 7.5, "vfc": 61}]  # pas le poids
    assert page["objectif"]["dans_jours"] == 30
    # Une case décochée efface tout de suite
    relay.put("/api/v1/partage/accord", headers=lucas, json={"seances": False, "objectif": True})
    page = relay.get(f"/api/v1/eleves/{lucas_id}/fiche", headers=sophie).json()
    assert page["seances"] == [] and page["jours"] == []
    with store.session() as conn:
        assert json.loads(conn.execute("SELECT contenu FROM partages").fetchone()[0])["seances"] == []


def test_clean_share_drops_old_and_unknown():
    old = date.today() - timedelta(days=40)
    cleaned = club.clean_share({"seances": [session("garmin:9", old), session("garmin:8", date.today(), pirate="x"),
                                            {"cle": "bad key!", "date": date.today().isoformat()}],
                                "profil": {"vma_kmh": 99}})
    assert [s["cle"] for s in cleaned["seances"]] == ["garmin:8"]
    assert "pirate" not in cleaned["seances"][0] and cleaned["profil"] == {}


def test_messages_threads_and_access(relay):
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    emma, emma_id = join(relay, sophie, "emma", "Emma L.")
    relay.post(f"/api/v1/fils/eleve-{lucas_id}", headers=lucas, json={"texte": "Dernier bloc dur."})
    relay.post("/api/v1/fils/groupe", headers=sophie, json={"texte": "Sortie longue dimanche 9 h"})
    # Emma ne voit pas la conversation de Lucas
    assert relay.get(f"/api/v1/fils/eleve-{lucas_id}", headers=emma).status_code == 403
    assert relay.post(f"/api/v1/fils/seance-{lucas_id}-garmin:1", headers=emma, json={"texte": "x"}).status_code == 403
    news = relay.get("/api/v1/nouveautes", headers=sophie).json()
    assert news["non_lus"] == 1
    threads = relay.get("/api/v1/fils", headers=sophie).json()["fils"]
    assert threads[0]["fil"] == "groupe"
    lucas_thread = next(t for t in threads if t["fil"] == f"eleve-{lucas_id}")
    assert lucas_thread["titre"] == "Lucas B." and lucas_thread["non_lus"] == 1
    read = relay.get(f"/api/v1/fils/eleve-{lucas_id}", headers=sophie).json()
    assert read["messages"][0]["texte"] == "Dernier bloc dur." and read["messages"][0]["auteur"]["nom"] == "Lucas B."
    assert relay.get("/api/v1/nouveautes", headers=sophie).json()["non_lus"] == 0
    assert relay.get("/api/v1/nouveautes", headers=emma).json()["non_lus"] == 1  # le message du groupe
    # Épingler : le coach seulement
    pinned = relay.get("/api/v1/fils/groupe", headers=emma).json()["messages"][0]["id"]
    assert relay.post(f"/api/v1/messages/{pinned}/epingle", headers=emma, json={}).status_code == 403
    assert relay.post(f"/api/v1/messages/{pinned}/epingle", headers=sophie, json={}).status_code == 200
    assert relay.get("/api/v1/fils/groupe", headers=emma).json()["messages"][0]["epingle"] is True
    # Retirer un élève efface ses conversations
    relay.delete(f"/api/v1/eleves/{lucas_id}", headers=sophie)
    with store.session() as conn:
        assert conn.execute("SELECT COUNT(*) FROM messages WHERE fil LIKE 'eleve-%'").fetchone()[0] == 0


def test_proposals_status_and_overview(relay):
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    today = date.today()
    blocks = [{"nom": "Échauffement", "duree_min": 20, "pct_vma": 65, "genre": "echauffement"},
              {"nom": "Seuil", "repetitions": 3, "duree_min": 10, "pct_vma": 88, "recup_min": 2}]
    res = relay.post("/api/v1/propositions", headers=sophie, json={
        "eleves": [lucas_id], "date": today.isoformat(), "titre": "Seuil 3 × 10", "sport": "course", "blocs": blocks})
    assert res.status_code == 200, res.text
    bad = relay.post("/api/v1/propositions", headers=sophie, json={"eleves": [999], "date": today.isoformat(),
                                                                   "titre": "x", "blocs": blocks})
    assert bad.status_code == 400
    relay.put("/api/v1/partage/accord", headers=lucas, json={})
    relay.put("/api/v1/partage", headers=lucas, json={"seances": [session("garmin:1", today)]})
    mine = relay.get("/api/v1/moi/coach", headers=lucas).json()
    assert mine["propositions"][0]["statut"] == "fait" and mine["coach"]["nom"] == "Sophie R."
    group = relay.get("/api/v1/groupe", headers=sophie).json()["eleves"][0]
    assert group["derniere_seance"]["nom"] == "Seuil 3 × 10 min"
    assert group["semaine"]["prevues"] == 1 and group["semaine"]["faites"] == 1
    assert len(group["bande"]) == 7
    assert next(d for d in group["bande"] if d["date"] == today.isoformat()) == {
        "date": today.isoformat(), "etat": "fait", "titre": "Seuil 3 × 10 min", "coach": True}
    detail = relay.get(f"/api/v1/eleves/{lucas_id}/seances/garmin:1", headers=sophie).json()
    assert detail["proposition"]["titre"] == "Seuil 3 × 10" and detail["fil"] == f"seance-{lucas_id}-garmin:1"
    relay.post("/api/v1/modeles", headers=sophie, json={"titre": "Seuil 3 × 10", "blocs": blocks})
    assert relay.get("/api/v1/modeles", headers=sophie).json()["modeles"][0]["blocs"][1]["repetitions"] == 3
    assert relay.post("/api/v1/propositions", headers=lucas, json={}).status_code == 403


def test_trace_mask_hides_home():
    lat0, lon0 = 49.0, 3.4
    points = [(lat0 + i * 0.001, lon0) for i in range(30)] + [(lat0 + (29 - i) * 0.001, lon0 + 0.0002)
                                                               for i in range(30)]
    streams = {"lat": [p[0] for p in points], "lon": [p[1] for p in points]}
    masked = coach.trace_points(streams, True)
    assert all(coach._haversine(tuple(p), (lat0, lon0)) > 500 for p in masked)
    assert len(coach.trace_points(streams, False)) == 60


def test_pace_and_block_text():
    assert coach.pace_for(17, 88) == "4:01 /km"
    text = coach.block_text({"nom": "Seuil", "repetitions": 3, "duree_min": 10, "pct_vma": 88, "recup_min": 2}, 17)
    assert text == "Seuil : 3 × 10 min à 88 % VMA (4:01 /km), récup 2 min"


def test_demo_student_end_to_end(relay, monkeypatch):
    """Le profil démo rejoint le coach, partage ses 4 semaines fictives et reçoit la séance proposée."""
    from foulee import demo

    sophie = token(relay, "sophie")
    code = relay.post("/api/v1/invitations", headers=sophie).json()["invitation"]["code"]
    demo.build(days=45, second_profile=False)
    assert config.is_demo()
    with db.session() as conn:
        coach.join(conn, "https://relais.test", code=code, ident="demo.eleve", name="Élève démo", password=PASSWORD)
        result = coach.set_accord(conn, {"seances": True, "objectif": True, "gps": True, "masquer": True})
        assert result["accord"]["gps"] is True and result["echange"]["envoi"]["seances"] > 5
    student = relay.get("/api/v1/groupe", headers=sophie).json()["eleves"][0]
    assert student["nom"] == "Élève démo" and student["seances_28j"] > 5
    assert student["objectif"]["nom"]
    page = relay.get(f"/api/v1/eleves/{student['id']}/fiche", headers=sophie).json()
    assert any(s["trace"] for s in page["seances"])  # tracés partagés, départ et arrivée masqués
    relay.post("/api/v1/propositions", headers=sophie, json={
        "eleves": [student["id"]], "date": (date.today() + timedelta(days=2)).isoformat(), "titre": "Seuil 3 × 10",
        "sport": "course", "blocs": [{"nom": "Seuil", "repetitions": 3, "duree_min": 10, "pct_vma": 88}]})
    with db.session() as conn:
        page = coach.my_page(conn)
        assert page["propositions"][0]["lignes"][0].startswith("Seuil : 3 × 10 min à 88 % VMA")
        rows = conn.execute("SELECT title FROM calendar_events WHERE uid LIKE 'coach:%'").fetchall()
        assert [r[0] for r in rows] == ["Seuil 3 × 10 (coach)"]  # « Mon coach » ouvert : le calendrier suit
        from foulee import calendrier

        assert calendrier.status(conn)["coach"] is True
        coach.exchange(conn)
        planned = calendrier.plan(conn, date.today(), date.today() + timedelta(days=3))
        assert [p["titre"] for p in planned if p["coach"]] == ["Seuil 3 × 10 (coach)"]
        calendrier.store(conn, [])  # relire le calendrier Garmin n'efface pas les séances du coach
        assert conn.execute("SELECT COUNT(*) FROM calendar_events WHERE uid LIKE 'coach:%'").fetchone()[0] == 1
    config.set_demo(False)
    with db.session() as conn:  # le vrai profil n'est relié à rien : le jeton de la démo est à part
        assert not coach.status(conn)["relie"]


def test_proxy_only_known_routes(relay):
    with db.session() as conn:
        for path in ("comptes", "../admin", "eleves/1/fiche/../../comptes", "invitations", "partage"):
            with pytest.raises(coach.CoachError):
                coach.proxy(conn, "GET", path)
        with pytest.raises(coach.CoachError):
            coach.proxy(conn, "PATCH", "groupe")


def test_demo_token_is_kept_apart(monkeypatch):
    from foulee import vault

    real = vault._entry("relais")
    config.set_demo(True)
    try:
        demo_entry = vault._entry("relais")
        assert demo_entry[0] == real[0] + "-demo" and demo_entry[1].endswith("-demo") and demo_entry[2] is None
    finally:
        config.set_demo(False)


def test_relay_clock_follows_the_club(monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setenv("FOULEE_RELAIS_TZ", "UTC")
    if store._zone() is None:
        pytest.skip("base des fuseaux horaires absente")
    utc = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((store.local_now() - utc).total_seconds()) < 5
