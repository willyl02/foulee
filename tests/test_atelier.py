"""0.8.3b15 : temps par zone d'une séance, Réglages → Renfo (objectif, cible avant / arrière, matériel…) et
l'Atelier (mes séances en blocs et de renfo, toutes faites, envoyées sur la montre avec ma VMA)."""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from foulee import analysis, atelier, coach, db, jour, reglages, renfo, renfo_seances, views
from foulee.web import create_app
from test_relais_garmin import ADDRESS, PASSWORD, accept, fake, relay, token  # noqa: F401

HEADERS = {"X-Foulee": "1"}
RUN = {"titre": "Seuil 3 × 10 min", "sport": "course", "consigne": "Réguliers",
       "blocs": [{"genre": "echauffement", "nom": "Échauffement", "duree_min": 20, "pct_vma": 65},
                 {"genre": "corps", "nom": "Seuil", "repetitions": 3, "duree_min": 10, "pct_vma": 88, "recup_min": 2},
                 {"genre": "calme", "nom": "Retour au calme", "duree_min": 10, "pct_vma": 60}]}


def _activity(conn, ident="garmin:1", sport="course", day=None, hr=(600, 1800, 900, 300, 60), pace=(1200, 1500, 600, 300, 0)):
    conn.execute(
        "INSERT INTO activities(id, source, source_id, start_local, date, sport, name, duration_s, moving_s, distance_m, "
        "avg_speed, hr_zones, pace_zones) VALUES (?, 'garmin', ?, ?, ?, ?, 'Sortie', 3660, 3600, 10000, 2.8, ?, ?)",
        (ident, ident.split(":")[1], f"{day or date.today().isoformat()} 09:00:00", day or date.today().isoformat(), sport,
         json.dumps(list(hr)) if hr else None, json.dumps(list(pace)) if pace else None))


# ------------------------------------------------------------------ temps par zone
def test_session_zone_tables():
    with db.session() as conn:
        _activity(conn)
        _activity(conn, "garmin:2", sport="velo")
        _activity(conn, "garmin:3", hr=None, pace=None)
        conn.commit()
        settings = db.get_settings(conn)
        detail = analysis.activity_detail(conn, "garmin:1", settings)
        fc, pace = detail["temps_zones"]["fc"], detail["temps_zones"]["allure"]
        assert fc["secondes"] == [600, 1800, 900, 300, 60] and fc["total"] == 3660 and len(fc["noms"]) == len(fc["bornes"]) == 5
        assert pace["secondes"][:2] == [1200, 1500] and "/km" in pace["bornes"][0]
        bike = analysis.activity_detail(conn, "garmin:2", settings)["temps_zones"]
        assert "fc" in bike and "allure" not in bike   # l'allure : course à pied seulement
        assert analysis.activity_detail(conn, "garmin:3", settings)["temps_zones"] == {}
        day = jour.day_page(conn, settings)
        by_id = {a["id"]: a for a in day["faites"]}
        assert by_id["garmin:1"]["zones_fc"]["secondes"][1] == 1800 and by_id["garmin:3"]["zones_fc"] is None


def test_zones_tile_joins_the_session_view_once():
    with db.session() as conn:
        views.ensure_default_views(conn)
        tiles = [t["type"] for t in json.loads(conn.execute("SELECT spec FROM views WHERE id = 'seance'").fetchone()["spec"])["tuiles"]]
        assert tiles.index("seance_zones") == tiles.index("seance_effet") + 1
        # une vue d'avant la b15 la reçoit une fois ; retirée ensuite, elle ne revient pas
        spec = {"tuiles": [t for t in json.loads(conn.execute("SELECT spec FROM views WHERE id = 'seance'").fetchone()["spec"])["tuiles"]
                           if t["type"] != "seance_zones"]}
        conn.execute("UPDATE views SET spec = ? WHERE id = 'seance'", (json.dumps(spec),))
        conn.execute("DELETE FROM meta WHERE key = 'vue_seance_zones'")
        conn.commit()
        views.ensure_default_views(conn)
        tiles = [t["type"] for t in json.loads(conn.execute("SELECT spec FROM views WHERE id = 'seance'").fetchone()["spec"])["tuiles"]]
        assert tiles.count("seance_zones") == 1
        conn.execute("UPDATE views SET spec = ? WHERE id = 'seance'", (json.dumps(spec),))
        conn.commit()
        views.ensure_default_views(conn)
        tiles = [t["type"] for t in json.loads(conn.execute("SELECT spec FROM views WHERE id = 'seance'").fetchone()["spec"])["tuiles"]]
        assert "seance_zones" not in tiles


# ------------------------------------------------------------------ réglages du renfo
def test_renfo_settings_are_checked():
    assert renfo.clean_settings(None) is None
    conf = renfo.clean_settings({"objectif_semaine": 9, "cible": "arriere", "niveau": "debutant", "materiel": ["banc", "elastique"],
                                 "recup_s": 60, "etirements": False, "jours": [5, 2, 2]})
    assert conf["objectif_semaine"] == 7 and conf["materiel"] == ["elastique", "banc"] and conf["jours"] == [2, 5]
    assert conf["etirements"] is False and conf["echauffement"] is True
    perso = renfo.clean_settings({"cible": "perso", "cible_bas": "1,2".replace(",", "."), "cible_haut": 2.5})
    assert (perso["cible_bas"], perso["cible_haut"]) == (1.2, 2.5)
    for bad in ({"cible": "rien"}, {"cible": "perso", "cible_bas": 2, "cible_haut": 1}, {"niveau": "pro"},
                {"materiel": ["fusée"]}, {"jours": [8]}, "x"):
        with pytest.raises(ValueError, match="Renfo"):
            renfo.clean_settings(bad)
    with db.session() as conn:
        saved, recompute = reglages.apply(conn, {"renfo": {"objectif_semaine": 3, "cible": "equilibre"}})
        assert saved["renfo"]["objectif_semaine"] == 3 and recompute is False
        # renvoyer la même VMA ne relance pas le recalcul de toutes les séances
        _, recompute = reglages.apply(conn, {"vma_kmh": saved["vma_kmh"], "renfo": saved["renfo"]})
        assert recompute is False
        _, recompute = reglages.apply(conn, {"vma_kmh": (saved["vma_kmh"] or 16) + 0.5})
        assert recompute is True


def test_balance_follows_the_chosen_target():
    rows = [{"category": "texte", "name": "Pont fessier", "sets": 3}, {"category": "texte", "name": "Squat", "sets": 3}]
    runner = renfo.balance(rows)
    assert runner["zone"] == "cible" and runner["ratio"] == 1.0        # 1:1 : bas de la cible du coureur
    back = renfo.target_of({"renfo": {"cible": "arriere"}})
    assert (back["bas"], back["haut"], back["vise"]) == (1.5, 3.0, 2.0)
    strict = renfo.balance(rows, back)
    assert strict["zone"] == "avant" and "1 : 1,5" in renfo.balance(rows + [{"category": "texte", "name": "Superman", "sets": 1}], back)["explication"]
    plan = renfo.compensation(strict, 28, 4, back)
    assert plan["cote"] == "arriere" and plan["manque_series"] == 3 and plan["cible"] == "1 : 2"
    perso = renfo.target_of({"renfo": {"cible": "perso", "cible_bas": 1.2, "cible_haut": 2.0}})
    assert perso["vise"] == 1.6 and renfo.balance_zone(3, 3, perso)[0] == "proche"
    # matériel : les exercices faisables d'abord, ceux qui demandent ce qu'on n'a pas, seulement s'il en manque
    assert renfo.has_gear("Pont fessier", []) and not renfo.has_gear("Kettlebell swing", ["halteres"])
    assert renfo.has_gear("Kettlebell swing", None)
    hips = renfo.compensation(runner | {"zone": "avant", "avant": 6, "arriere": 3}, 28, 4, None, gear=[])
    names = [e["nom"] for f in hips["familles"] for e in f["exercices"]]
    assert "Kettlebell swing" not in names and "Pont fessier" in names


def test_renfo_period_uses_settings():
    with db.session() as conn:
        reglages.apply(conn, {"renfo": {"objectif_semaine": 4, "cible": "arriere"}})
        data = renfo.period(conn, date.today() - timedelta(days=30), date.today(), settings=db.get_settings(conn))
    assert data["objectif_semaine"] == 4 and data["cible"]["profil"] == "arriere"


# ------------------------------------------------------------------ l'Atelier
def test_block_sessions_are_kept_with_distinct_names():
    session = atelier.clean(RUN)
    assert session["sport"] == "course" and len(session["id"]) >= 6 and session["blocs"][1]["repetitions"] == 3
    assert atelier.clean({**RUN, "sport": "jet-ski"})["sport"] == "course"
    with pytest.raises(atelier.SessionError, match="nom"):
        atelier.clean({**RUN, "titre": " "})
    with pytest.raises(atelier.SessionError):
        atelier.clean({**RUN, "blocs": [{"genre": "corps", "nom": "Vide"}]})
    with db.session() as conn:
        kept = atelier.save(conn, [RUN, {**RUN, "titre": "Seuil long"}])
        assert [s["titre"] for s in atelier.saved(conn)] == ["Seuil 3 × 10 min", "Seuil long"] and kept[0]["id"] != kept[1]["id"]
        with pytest.raises(atelier.SessionError, match="même nom"):
            atelier.save(conn, [RUN, {**RUN, "titre": "seuil 3 × 10 MIN"}])
    item = atelier.to_item(RUN, "2026-12-05")
    assert item["date"] == "2026-12-05" and item["sport"] == "course"


def test_next_renfo_day():
    monday = date(2026, 11, 23)
    assert atelier.next_day([], monday) == "2026-11-23"
    assert atelier.next_day([4], monday) == "2026-11-26"           # jeudi
    assert atelier.next_day([1, 4], monday) == "2026-11-23"        # aujourd'hui compte
    assert atelier.next_day([7], date(2026, 11, 29)) == "2026-11-29"


def test_templates_follow_level_and_gear():
    out = renfo_seances.templates({"renfo": {"niveau": "confirme", "materiel": []}})
    express = next(t for t in out if t["id"] == "tpl-express")
    assert {e["series"] for e in express["exercices"]} == {4} and express["materiel_manquant"] == []
    weights = next(t for t in out if t["id"] == "tpl-halteres")
    assert "Soulevé de terre roumain" in weights["materiel_manquant"]
    # chaque séance toute faite se range bien devant / derrière (pas d'exercice « perdu »)
    for t in renfo_seances.TEMPLATES:
        bal = renfo_seances.composed_balance(t)["equilibre"]
        assert bal["zone"] != "vide", t["titre"]
    gainage = renfo_seances.composed_balance(next(t for t in renfo_seances.TEMPLATES if t["id"] == "tpl-express"))
    assert gainage["equilibre"]["ratio_texte"] == "1 : 1,5" and gainage["muscles"]


def test_atelier_api_and_fit_file():
    client = TestClient(create_app())
    page = client.get("/api/atelier").json()
    assert page["seances"] == [] and len(page["modeles_renfo"]) == len(renfo_seances.TEMPLATES)
    assert page["montre"] is False and page["date_renfo"] == date.today().isoformat()
    assert all("materiel_ok" in e for f in page["bibliotheque"] for e in f["exercices"])
    kept = client.put("/api/atelier/seances", headers=HEADERS, json={"seances": [RUN]}).json()["seances"]
    assert client.get("/api/atelier").json()["seances"] == kept
    fit = client.post("/api/atelier/seance.fit", headers=HEADERS, json={"seance": RUN})
    assert fit.status_code == 200 and fit.content[8:12] == b".FIT"
    bad = client.post("/api/atelier/seance.fit", headers=HEADERS, json={"seance": {**RUN, "titre": ""}})
    assert bad.status_code == 400
    watch = client.post("/api/atelier/seance/montre", headers=HEADERS, json={"seance": RUN})
    assert watch.status_code == 409 and ".fit" in watch.json()["detail"]
    bilan = client.post("/api/atelier/renfo/bilan", headers=HEADERS, json={"seance": renfo_seances.TEMPLATES[1]}).json()
    assert bilan["equilibre"]["arriere"] > bilan["equilibre"]["avant"] and bilan["cible"]["profil"] == "coureur"


def test_done_strength_sessions_can_be_reused():
    with db.session() as conn:
        _activity(conn, "garmin:9", sport="renfo", hr=None, pace=None)
        for idx, (cat, name, sets, reps, dur, kg) in enumerate([("squat", "goblet_squat", 3, 36, 120, 16.0),
                                                                ("plank", "plank", 3, 3, 135, 0.0),
                                                                ("warm_up", None, 1, 0, 300, 0.0)]):
            conn.execute("INSERT INTO exercises(activity_id, idx, category, name, sets, reps, duration_s, max_kg, volume_kg) "
                         "VALUES ('garmin:9', ?, ?, ?, ?, ?, ?, ?, 0)", (idx, cat, name, sets, reps, dur, kg))
        conn.commit()
        (done,) = renfo_seances.done_sessions(conn)
    assert done["id"] == "garmin:9" and len(done["exercices"]) == 2
    squat, plank = done["exercices"]
    assert squat["series"] == 3 and squat["reps"] == "12 à 16 kg" and plank["reps"] == "45 s"


def test_my_run_goes_to_my_watch_with_my_paces(relay, fake):
    sophie = token(relay, "sophie")
    code = relay.post("/api/v1/invitations", headers=sophie).json()["invitation"]["code"]
    with db.session() as conn:
        coach.join(conn, ADDRESS, code=code, ident="lucas", name="Lucas B.", password=PASSWORD)
        reglages.apply(conn, {"vma_kmh": 16.0})
        conn.commit()
    day = (date.today() + timedelta(days=2)).isoformat()
    client = TestClient(create_app())
    first = client.post("/api/atelier/seance/montre", headers=HEADERS, json={"seance": RUN, "date": day}).json()
    assert first["a_relier"] is True
    accept(relay, fake, first["adresse"])
    sent = client.post("/api/atelier/seance/montre", headers=HEADERS, json={"seance": RUN, "date": day}).json()
    assert sent["envoi"]["date"] == day
    (workout,) = fake.workouts.values()
    assert workout["sport"] == "RUNNING" and workout["workoutName"] == "Seuil 3 × 10 min"
    loop = workout["segments"][0]["steps"][1]
    effort = loop["steps"][0]
    # 88 % de 16 km/h = 3,91 m/s, ± 3 % : la montre a une vraie fourchette d'allure
    assert effort["targetType"] == "PACE" and effort["targetValueLow"] == pytest.approx(3.911 * 0.97, abs=0.01)
    (schedule,) = fake.schedules.values()
    assert schedule["date"] == day
