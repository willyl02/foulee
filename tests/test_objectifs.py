"""Objectifs : un principal et des secondaires, leur gestion (API), la vue « Objectifs » et ce que voit le coach."""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from foulee import coach, db, objectifs, views
from foulee.relais import club as relay

HEADERS = {"X-Foulee": "1"}
TODAY = date.today()


def _in(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


@pytest.fixture
def web():
    from foulee.web import create_app

    return TestClient(create_app())


# --------------------------------------------------------------------- contrôles
def test_a_goal_is_checked_and_tidied():
    goal = objectifs.clean_goal({"nom": "  10 km de Reims ", "date": "2027-02-07", "distance_km": "10",
                                 "temps_cible": "38:30", "d_plus_m": "45", "note": "partir prudemment"})
    assert goal == {"nom": "10 km de Reims", "date": "2027-02-07", "distance_km": 10.0, "temps_cible": "38:30",
                    "d_plus_m": 45, "note": "partir prudemment"}
    assert objectifs.clean_goal({"nom": "Semi", "distance_km": 21.0975, "temps_cible": "1:25"})["temps_cible"] == "1:25:00"
    assert objectifs.clean_goal({"nom": "Semi", "distance_km": 21.0975, "temps_cible": "1:25:0"})["temps_cible"] == "1:25:00"
    assert objectifs.clean_goal({})["nom"] == ""  # pas d'objectif principal : permis
    for bad, message in [({"nom": "", "date": "2027-01-01"}, "nom"), ({"nom": "X", "date": "07/02/2027"}, "Date"),
                         ({"nom": "X", "temps_cible": "vite"}, "illisible"), ({"nom": "X", "distance_km": 5000}, "1 000"),
                         ({"nom": "X", "distance_km": 10, "temps_cible": "0:10:00"}, "trop rapide"),
                         ({"nom": "X", "d_plus_m": -3}, "Dénivelé")]:
        with pytest.raises(objectifs.GoalError, match=message):
            objectifs.clean_goal(bad)


def test_riegel_and_distance_guess():
    assert round(objectifs.riegel(2310, 10, 21.0975)) == 5097  # 38:30 au 10 km ≈ 1:24:57 au semi
    assert objectifs.guess_distance("COURSE — Semi de Paris") == 21.0975
    assert objectifs.guess_distance("Marathon de Reims") == 42.195
    assert objectifs.guess_distance("Les 10 km de Château") == 10
    assert objectifs.guess_distance("Trail des Crêtes 25 km") == 25
    assert objectifs.guess_distance("Cross du club") is None


# ------------------------------------------------------------------------- API
def test_manage_goals_through_the_api(web):
    assert web.put("/api/objectifs/principal", headers=HEADERS,
                   json={"nom": "Semi de Paris", "date": _in(60), "distance_km": 21.0975, "temps_cible": "1:25:00"}
                   ).status_code == 200
    res = web.post("/api/objectifs", headers=HEADERS,
                   json={"nom": "10 km de Reims", "date": _in(25), "distance_km": 10, "temps_cible": "38:30"}).json()
    assert res["principal"]["nom"] == "Semi de Paris" and res["objectif"]["nom"] == "Semi de Paris"
    ten = res["secondaires"][0]
    assert ten["nom"] == "10 km de Reims" and ten["jours_restants"] == 25 and ten["avant_principal_jours"] == 35
    assert ten["allure_cible"] == "3:51 /km" and ten["equivalence"]["temps"] == "1:24:57"
    assert ten["equivalence"]["ecart_s"] < 0  # plus rapide que le temps visé au semi
    web.post("/api/objectifs", headers=HEADERS, json={"nom": "Trail des Crêtes", "date": _in(90), "distance_km": 25,
                                                       "d_plus_m": 900})
    res = web.post("/api/objectifs", headers=HEADERS, json={"nom": "Cross", "date": _in(10)}).json()
    assert [g["nom"] for g in res["secondaires"]] == ["Cross", "10 km de Reims", "Trail des Crêtes"]  # par date
    trail = next(g for g in res["secondaires"] if g["nom"] == "Trail des Crêtes")
    assert trail["equivalence"] is None and "avant_principal_jours" not in trail or trail["avant_principal_jours"] is None

    # l'objectif de l'Accueil : le principal, et les secondaires dessous
    home = web.get("/api/objective").json()
    assert home["nom"] == "Semi de Paris" and len(home["secondaires"]) == 3

    # modifier, promouvoir, retirer
    cross = next(g for g in res["secondaires"] if g["nom"] == "Cross")
    res = web.put(f"/api/objectifs/{cross['id']}", headers=HEADERS, json={"nom": "Cross départemental", "date": _in(11)}).json()
    assert any(g["nom"] == "Cross départemental" and g["jours_restants"] == 11 for g in res["secondaires"])
    res = web.post(f"/api/objectifs/{ten['id']}/principal", headers=HEADERS).json()
    assert res["principal"]["nom"] == "10 km de Reims" and res["objectif"]["temps_cible"] == "38:30"
    assert "Semi de Paris" in [g["nom"] for g in res["secondaires"]]  # l'ancien principal reste un objectif
    res = web.delete(f"/api/objectifs/{cross['id']}", headers=HEADERS).json()
    assert "Cross départemental" not in [g["nom"] for g in res["secondaires"]]
    res = web.delete("/api/objectifs/principal", headers=HEADERS).json()
    assert res["principal"] is None and res["objectif"]["nom"] == ""
    res = web.post("/api/objectifs", headers=HEADERS, json={"nom": "Marathon", "date": _in(200), "distance_km": 42.195,
                                                            "principal": True}).json()
    assert res["principal"]["nom"] == "Marathon"

    # refus expliqués
    assert web.post("/api/objectifs", headers=HEADERS, json={"nom": ""}).status_code == 400
    assert web.put("/api/objectifs/inconnu", headers=HEADERS, json={"nom": "X"}).status_code == 404
    assert "temps visé" in web.post("/api/objectifs", headers=HEADERS,
                                    json={"nom": "X", "temps_cible": "bof"}).json()["detail"].lower()
    assert web.post("/api/objectifs", json={"nom": "Sans en-tête"}).status_code == 403


def test_past_goals_find_the_race_of_the_day(web):
    race_day = (TODAY - timedelta(days=20)).isoformat()
    with db.session() as conn:
        rows = [("garmin:1", race_day, "course", "10 km de Reims", 10080, 2290),  # la course
                ("garmin:2", race_day, "course", "Échauffement", 2500, 900),
                ("garmin:3", race_day, "velo", "Retour à vélo", 9900, 1500)]
        for aid, day, sport, name, dist, dur in rows:
            conn.execute("INSERT INTO activities(id, source, source_id, start_local, date, sport, name, distance_m, "
                         "duration_s, moving_s) VALUES (?, 'garmin', ?, ?, ?, ?, ?, ?, ?, ?)",
                         (aid, aid[7:], f"{day}T10:00:00", day, sport, name, dist, dur, dur))
    web.put("/api/objectifs/principal", headers=HEADERS,
            json={"nom": "Semi de Paris", "date": _in(40), "distance_km": 21.0975, "temps_cible": "1:25:00"})
    web.post("/api/objectifs", headers=HEADERS,
             json={"nom": "10 km de Reims", "date": race_day, "distance_km": 10, "temps_cible": "38:30"})
    web.post("/api/objectifs", headers=HEADERS, json={"nom": "Trail sans séance", "date": _in(-5), "distance_km": 30})
    data = web.get("/api/objectifs").json()
    assert [g["nom"] for g in data["passes"]] == ["Trail sans séance", "10 km de Reims"] and not data["secondaires"]
    ten = data["passes"][1]
    assert ten["resultat"]["seance_id"] == "garmin:1" and ten["resultat"]["temps"] == "38:10"
    assert ten["resultat"]["ecart_s"] == -40  # 38:10 sur 10,08 km : 40 s de mieux que 38:30 à distance égale
    assert ten["equivalence"]["vers"] == "Semi de Paris"
    assert data["passes"][0]["resultat"] is None

    # l'objectif principal passé : il rejoint les passés, et la page propose le suivant
    web.put("/api/objectifs/principal", headers=HEADERS, json={"nom": "10 km de Reims (principal)", "date": race_day,
                                                                 "distance_km": 10, "temps_cible": "38:30"})
    web.post("/api/objectifs", headers=HEADERS, json={"nom": "Semi de Paris", "date": _in(40), "distance_km": 21.0975})
    data = web.get("/api/objectifs").json()
    assert data["principal"] is None and data["principal_passe"]["resultat"]["temps"] == "38:10"
    assert data["suivant"] == data["secondaires"][0]["id"]


def test_races_of_the_calendar_are_offered(web):
    with db.session() as conn:
        for day, title in ((_in(12), "COURSE — Les 10 km de Château"), (_in(30), "COURSE — Semi de Paris"),
                           (_in(3), "Fractionné 10 × 400")):
            conn.execute("INSERT INTO calendar_events(date, all_day, title, kind) VALUES (?, 1, ?, ?)",
                         (day, title, "seance" if "Fraction" in title else "course"))
    web.put("/api/objectifs/principal", headers=HEADERS, json={"nom": "Semi de Paris", "date": _in(30)})
    offered = web.get("/api/objectifs").json()["calendrier"]
    assert offered == [{"date": _in(12), "nom": "Les 10 km de Château", "lieu": None, "distance_km": 10.0,
                        "dans_jours": 12}]  # le semi est déjà l'objectif, la séance n'est pas une course


def test_settings_export_keeps_secondary_goals(web):
    web.post("/api/objectifs", headers=HEADERS, json={"nom": "10 km", "date": _in(20), "distance_km": 10})
    with db.session() as conn:
        from foulee import reglages

        exported = reglages.export(conn, with_views=False)
    assert exported["reglages"]["objectifs_secondaires"][0]["nom"] == "10 km"


# ------------------------------------------------------------------- les vues
def test_the_goals_view(web):
    boot = web.get("/api/bootstrap").json()
    view = next(v for v in boot["vues"] if v["id"] == "objectifs")
    assert view["name"] == "Objectifs" and [t["type"] for t in view["spec"]["tuiles"]][:2] == ["objectifs", "fractions"]
    assert not any(v["id"] == "cap-semi" for v in boot["vues"])


def test_the_old_marathon_view_becomes_the_goals_view():
    with db.session() as conn:  # une base d'avant la 0.8.1b4, avec « Cap semi de Paris » d'origine
        conn.execute("DELETE FROM views WHERE id = 'objectifs'")
        old = {"tuiles": [views._tile("objectif", 4, 2), views._tile("fractions", 8, 2, periode="120"),
                          views._tile("charge", 6, 2)]}
        conn.execute("INSERT INTO views(id, name, icon, position, spec, builtin) VALUES ('cap-semi', "
                     "'Cap semi de Paris', 'flag', 5, ?, 1)", (json.dumps(old),))
        db.delete_meta(conn, "vue_objectifs")
    with db.session() as conn:
        rows = {r["id"]: r for r in conn.execute("SELECT * FROM views")}
        assert "cap-semi" not in rows and rows["objectifs"]["name"] == "Objectifs" and rows["objectifs"]["position"] == 5
        tiles = json.loads(rows["objectifs"]["spec"])["tuiles"]
        assert [(t["type"], t["w"], t["h"]) for t in tiles] == [("objectifs", 12, 3), ("fractions", 12, 2), ("charge", 6, 2)]
        db.delete_meta(conn, "vue_objectifs")  # une seule fois : rien ne bouge au passage suivant
    with db.session() as conn:
        assert [r["id"] for r in conn.execute("SELECT id FROM views WHERE id LIKE 'objectifs%'")] == ["objectifs"]


def test_a_renamed_or_deleted_view_is_respected():
    with db.session() as conn:
        conn.execute("DELETE FROM views WHERE id = 'objectifs'")
        old = {"tuiles": [views._tile("objectif", 4, 2)]}
        conn.execute("INSERT INTO views(id, name, icon, position, spec, builtin) VALUES ('cap-semi', 'Mon marathon', "
                     "'flag', 5, ?, 1)", (json.dumps(old),))
        db.delete_meta(conn, "vue_objectifs")
    with db.session() as conn:
        assert conn.execute("SELECT name FROM views WHERE id = 'objectifs'").fetchone()["name"] == "Mon marathon"
        conn.execute("DELETE FROM views WHERE id = 'objectifs'")  # supprimée : elle revient une fois, après Entraînement
        db.delete_meta(conn, "vue_objectifs")
    with db.session() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM views ORDER BY position")]
        assert ids.index("objectifs") == ids.index("entrainement") + 1


# --------------------------------------------------------------------- le coach
def test_the_coach_sees_the_secondary_goals():
    with db.session() as conn:
        db.set_setting(conn, "objectif", {"nom": "Semi de Paris", "date": _in(50), "distance_km": 21.0975,
                                          "temps_cible": "1:25:00", "d_plus_m": None, "note": "perso"})
        db.set_setting(conn, "objectifs_secondaires", [
            {"id": "a", "nom": "10 km de Reims", "date": _in(20), "distance_km": 10, "temps_cible": "38:30",
             "d_plus_m": None, "note": "dossard 42"},
            {"id": "b", "nom": "Passé", "date": _in(-3), "distance_km": 5}])
        snap = coach.snapshot(conn, {"objectif": True})
    assert snap["profil"]["objectif"]["nom"] == "Semi de Paris" and "note" not in snap["profil"]["objectif"]
    assert snap["profil"]["objectifs"] == [{"nom": "10 km de Reims", "date": _in(20), "distance_km": 10,
                                            "temps_cible": "38:30", "d_plus_m": None}]
    clean = relay.clean_share(snap)
    assert clean["profil"]["objectifs"][0]["nom"] == "10 km de Reims"
    assert relay._upcoming_goals(clean["profil"], TODAY)[0]["dans_jours"] == 20
    main = {**clean["profil"]["objectif"], "dans_jours": 50}
    assert relay._next_goal(main, clean["profil"], TODAY)["nom"] == "10 km de Reims"  # la course la plus proche
