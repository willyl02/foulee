"""Renfo : exercices lus dans le résumé de Garmin Connect, noms en français, muscles, API, vues, Claude, démo."""

import copy
import datetime as dt
import json

import pytest
from fake_garmin import FakeGarmin
from fastapi.testclient import TestClient

from foulee import config, db, renfo, sync, vault, views

# Résumé d'une séance tel que Garmin le donne (charges en grammes, durées en millisecondes)
LEGS = [
    {"category": "SQUAT", "subCategory": "GOBLET_SQUAT", "reps": 30, "volume": 480000.0, "duration": 96000.0,
     "sets": 3, "maxWeight": 16000.0},
    {"category": "LUNGE", "subCategory": "DUMBBELL_LUNGE", "reps": 24, "volume": 192000.0, "duration": 74000.0,
     "sets": 3, "maxWeight": 8000.0},
    {"category": "PLANK", "subCategory": "SIDE_PLANK", "reps": 0, "volume": 0.0, "duration": 80000.0, "sets": 2,
     "maxWeight": None},
    {"category": "WARM_UP", "subCategory": None, "reps": 0, "volume": 0, "duration": 60000, "sets": 0},
]


def lighter(sets: list[dict], kg: float) -> list[dict]:
    """La même séance, une semaine plus tôt, avec des charges plus légères."""
    out = copy.deepcopy(sets)
    for e in out:
        if e.get("maxWeight"):
            e["maxWeight"] -= kg * 1000
            e["volume"] = e["maxWeight"] * e["reps"]
    return out


def strength(n: int, day: dt.date, sets: list[dict]) -> dict:
    start = dt.datetime(day.year, day.month, day.day, 18, 0)
    return {
        "activityId": 60_000_000 + n, "activityName": f"Renfo {n}",
        "startTimeLocal": start.strftime("%Y-%m-%d %H:%M:%S"),
        "startTimeGMT": (start - dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "activityType": {"typeId": 13, "typeKey": "strength_training"},
        "duration": 1800.0, "movingDuration": 1700.0, "elapsedDuration": 1850.0,
        "averageHR": 96.0, "maxHR": 131.0, "calories": 180.0,
        "totalSets": sum(e["sets"] for e in sets), "activeSets": sum(e["sets"] for e in sets),
        "totalReps": sum(e["reps"] for e in sets), "summarizedExerciseSets": sets,
    }


@pytest.fixture
def garmin(monkeypatch):
    with FakeGarmin(days=40, activities=4) as fake:
        fake.activities.append(strength(1, fake.today - dt.timedelta(days=2), LEGS))
        fake.activities.append(strength(2, fake.today - dt.timedelta(days=9), lighter(LEGS, 2)))
        fake.activities.append(strength(3, fake.today - dt.timedelta(days=16), []))  # séance sans détail
        monkeypatch.setenv("GARMIN_PERSONAL_API_BASE_URL", fake.url)
        vault.set_key("cle-de-test")
        sync.run(since=fake.today - dt.timedelta(days=35))
        yield fake


# ------------------------------------------------------------------ lecture du résumé de Garmin
def test_parse_summary_units():
    exercises = renfo.parse_summary({"summarizedExerciseSets": LEGS})
    assert len(exercises) == 3  # l'entrée sans série est écartée
    assert exercises[0] == {"category": "squat", "name": "goblet_squat", "sets": 3, "reps": 30, "duration_s": 96.0,
                            "max_kg": 16.0, "volume_kg": 480.0}
    assert exercises[2]["max_kg"] == 0.0 and exercises[2]["reps"] == 0
    assert renfo.totals(exercises) == {"sets": 8, "reps": 54, "volume": 672.0, "sets_effort": 250}
    assert renfo.parse_summary({}) == [] and renfo.parse_summary({"summarizedExerciseSets": "?"}) == []
    assert renfo.totals([]) == {}


def test_reading_each_exercise():
    squat, lunge, plank = (renfo.describe(e) for e in renfo.parse_summary({"summarizedExerciseSets": LEGS}))
    assert squat["detail"] == {"mode": "reps", "par_serie": 10, "texte": None}
    assert plank["detail"] == {"mode": "temps", "par_serie_s": 40, "texte": None}  # 2 × 40 s
    uneven = renfo.describe({"category": "push_up", "name": "push_up", "sets": 10, "reps": 64, "duration_s": 300.0,
                             "max_kg": 0.0, "volume_kg": 0.0})
    assert uneven["detail"]["texte"] == "64 répétitions" and uneven["charge_max_kg"] is None
    assert squat["nom"] == "Squat goblet" and squat["charge_max_kg"] == 16.0 and squat["tonnage_kg"] == 480.0
    assert [m["cle"] for m in squat["muscles"] if m["role"] == "principal"] == ["quadriceps", "fessiers"]


# ------------------------------------------------------------------ noms en français
@pytest.mark.parametrize("category, name, expected", [
    # les exercices de William (séance du programme S2-1)
    ("plank", "side_plank", "Planche latérale"),
    ("banded_exercises", "ankle_dorsiflexion_with_band", "Flexion dorsale de cheville avec élastique"),
    ("calf_raise", "single_leg_standing_calf_raise", "Élévation des mollets debout sur une jambe"),
    ("squat", "weighted_wall_squat", "Chaise lestée"),
    ("hip_raise", "swiss_ball_hip_raise_and_leg_curl", "Pont et leg curl sur swiss ball"),
    ("plank", "swiss_ball_plank", "Planche sur swiss ball"),
    ("lunge", "dumbbell_lunge", "Fente avec haltères"),
    ("calf_raise", "weighted_standing_calf_raise", "Élévation des mollets debout lestée"),
    ("plyo", "lateral_leap_and_hop", "Bonds latéraux"),
    # accords et précisions
    ("lunge", "alternating_dumbbell_lunge", "Fente alternée avec haltères"),
    ("plank", "straight_arm_plank_with_shoulder_touch", "Planche bras tendus avec touché d'épaule"),
    ("hip_raise", "marching_hip_raise", "Pont fessier en marchant"),
    ("leg_raise", "hanging_single_leg_raise", "Relevé d'une jambe suspendu"),
    ("calf_raise", "3_way_weighted_calf_raise", "Élévation des mollets dans 3 directions lestée"),
    ("hip_swing", "kettlebell_swing", "Swing kettlebell"),
    # pas de traduction : la famille en français, puis le nom de Garmin
    ("plyo", "side_to_side_shuffle_jump", "Pliométrie (side to side shuffle jump)"),
    ("core", None, "Abdos et gainage"),
    ("nouvelle_famille", "foo_bar", "Nouvelle famille (foo bar)"),
])
def test_exercise_names(category, name, expected):
    assert renfo.exercise_name(category, name) == expected


def test_every_garmin_exercise_has_a_name_and_muscles():
    """Les 1 846 exercices du profil FIT de Garmin : jamais d'erreur, toujours un nom, des muscles connus."""
    from garmin_fit_sdk import Profile

    types = Profile["types"]
    names = [(k[:-len("_exercise_name")], v) for k in types if k.endswith("_exercise_name") for v in types[k].values()]
    assert len(names) > 1800
    translated = 0
    for category, name in names:
        label = renfo.exercise_name(category, name)
        assert label and "_" not in label
        translated += renfo._translate(name) is not None
        muscles = renfo.exercise_muscles(category, name)
        assert set(muscles) <= set(renfo.MUSCLE_LABELS) and set(muscles.values()) <= {renfo.P, renfo.S}
    assert translated / len(names) > 0.5  # garde-fou : la traduction ne recule pas


def test_muscles():
    assert renfo.exercise_muscles("plank", "side_plank") == {"obliques": 1.0, "abdos": 0.5, "abducteurs": 0.5}
    assert renfo.exercise_muscles("banded_exercises", "ankle_dorsiflexion_with_band") == {"mollets": 1.0}
    assert renfo.exercise_muscles("hip_raise", "kettlebell_swing") == {"fessiers": 1.0, "ischios": 1.0,
                                                                      "lombaires": 0.5}
    # échauffement et étirements : au plus ½
    assert renfo.exercise_muscles("warm_up", "stretch_hamstring") == {"ischios": 0.5}
    assert renfo.exercise_muscles("unknown", None) == {}


# ------------------------------------------------------------------ synchro, séance, période
def test_sync_stores_exercises_and_session_detail(garmin):
    from foulee import analysis

    with db.session() as conn:
        rows = conn.execute("SELECT activity_id, category, name, sets FROM exercises ORDER BY activity_id, idx").fetchall()
        assert len(rows) == 6 and {r["activity_id"] for r in rows} == {"garmin:60000001", "garmin:60000002"}
        extra = json.loads(conn.execute("SELECT extra FROM activities WHERE id = 'garmin:60000001'").fetchone()[0])
        assert {k: extra[k] for k in ("sets", "reps", "volume", "sets_effort")} == {
            "sets": 8, "reps": 54, "volume": 672.0, "sets_effort": 250}
        detail = analysis.activity_detail(conn, "garmin:60000001", db.get_settings(conn))["renfo"]
        assert [e["nom"] for e in detail["exercices"]] == ["Squat goblet", "Fente avec haltères", "Planche latérale"]
        assert detail["series"] == 8 and detail["tonnage_kg"] == 672.0 and detail["effort_s"] == 250
        assert detail["muscles"]["quadriceps"] == 6.0 and detail["muscles"]["obliques"] == 2.0
        assert detail["muscles"]["ischios"] == 3.0  # ½ × 3 séries de squat + ½ × 3 de fente
        empty = analysis.activity_detail(conn, "garmin:60000003", db.get_settings(conn))["renfo"]
        assert empty["exercices"] == [] and empty["series"] == 0  # séance de renfo sans détail
        assert analysis.activity_detail(conn, "garmin:50000000", db.get_settings(conn))["renfo"] is None  # une course


def test_period_progression_and_regularity(garmin):
    with db.session() as conn:
        data = renfo.period(conn, garmin.today - dt.timedelta(days=29), garmin.today)
    assert data["nb_seances"] == 3 and data["series"] == 16
    squat = next(e for e in data["exercices"] if e["nom"] == "Squat goblet")
    assert squat["seances"] == 2 and [h["charge_kg"] for h in squat["historique"]] == [14.0, 16.0]
    assert squat["derniere"] == (garmin.today - dt.timedelta(days=2)).isoformat()
    assert len(data["semaines"]) == 12 and sum(w["seances"] for w in data["semaines"]) == 3
    assert data["semaines"][-1]["debut"] == (garmin.today - dt.timedelta(days=garmin.today.weekday())).isoformat()
    assert "pectoraux" not in data["muscles"] and data["muscles"]["fessiers"] == 12.0


def test_corrections_in_garmin_connect_replace_the_exercises(garmin):
    """Exercice changé dans l'appli Garmin Connect : la synchro suivante remplace l'ancien, sans doublon."""
    fixed = copy.deepcopy(LEGS)
    fixed[1]["subCategory"] = "WALKING_LUNGE"
    garmin.activities[4]["summarizedExerciseSets"] = fixed
    sync.run()
    with db.session() as conn:
        names = [r["name"] for r in conn.execute(
            "SELECT name FROM exercises WHERE activity_id = 'garmin:60000001' ORDER BY idx")]
    assert names == ["goblet_squat", "walking_lunge", "side_plank"]


def test_web_api_and_views(garmin):
    from foulee.web import create_app

    client = TestClient(create_app())
    data = client.get("/api/renfo").json()
    assert data["nb_seances"] == 3 and data["noms_muscles"]["ischios"] == "Ischio-jambiers"
    assert client.get("/api/renfo", params={"semaines": 500}).json()["semaines"].__len__() == 52
    detail = client.get("/api/activities/garmin:60000001", params={"fetch": 0}).json()
    assert detail["renfo"]["exercices"][0]["detail"]["par_serie"] == 10
    listed = client.get("/api/activities", params={"sport": "renfo"}).json()
    assert {a["id"] for a in listed} == {"garmin:60000001", "garmin:60000002", "garmin:60000003"}
    assert next(a for a in listed if a["id"] == "garmin:60000001")["extra"]["sets"] == 8
    boot = client.get("/api/bootstrap").json()
    ids = [v["id"] for v in boot["vues"]]
    assert ids.index("renfo") == ids.index("entrainement") + 1  # la vue Renfo arrive après Entraînement
    renfo_view = next(v for v in boot["vues"] if v["id"] == "renfo")
    assert [t["type"] for t in renfo_view["spec"]["tuiles"]][:2] == ["renfo", "renfo_exercices"]
    assert renfo_view["spec"]["tuiles"][0]["params"]["periode"] == "herite"  # suit la période de la vue
    seance = next(v for v in boot["vues"] if v["id"] == "seance")
    assert [t["type"] for t in seance["spec"]["tuiles"]][:2] == ["seance_resume", "seance_renfo"]
    # supprimée, la vue ne revient pas à la synchro suivante
    assert client.delete("/api/views/renfo", headers={"X-Foulee": "1"}).json()["supprimee"]
    sync.run()
    with db.session() as conn:
        assert not conn.execute("SELECT 1 FROM views WHERE id = 'renfo'").fetchone()


def test_no_renfo_view_without_exercises(monkeypatch):
    with FakeGarmin(days=10, activities=2) as fake:
        monkeypatch.setenv("GARMIN_PERSONAL_API_BASE_URL", fake.url)
        vault.set_key("cle-de-test")
        sync.run(since=fake.today - dt.timedelta(days=8))
    with db.session() as conn:
        assert not conn.execute("SELECT 1 FROM views WHERE id = 'renfo'").fetchone()
        assert renfo.period(conn, fake.today - dt.timedelta(days=29), fake.today)["nb_seances"] == 0


def test_seance_tile_added_once_to_an_existing_seance_view():
    with db.session() as conn:
        spec = json.loads(conn.execute("SELECT spec FROM views WHERE id = 'seance'").fetchone()[0])
        spec["tuiles"] = [t for t in spec["tuiles"] if t["type"] != "seance_renfo"]
        conn.execute("UPDATE views SET spec = ? WHERE id = 'seance'", (json.dumps(spec),))
        db.delete_meta(conn, "vue_seance_renfo")  # une base d'avant la 0.6
    with db.session() as conn:
        tiles = [t["type"] for t in json.loads(conn.execute("SELECT spec FROM views WHERE id = 'seance'").fetchone()[0])["tuiles"]]
        assert tiles[:2] == ["seance_resume", "seance_renfo"]
        spec = json.loads(conn.execute("SELECT spec FROM views WHERE id = 'seance'").fetchone()[0])
        spec["tuiles"] = [t for t in spec["tuiles"] if t["type"] != "seance_renfo"]  # retirée à la main
        conn.execute("UPDATE views SET spec = ? WHERE id = 'seance'", (json.dumps(spec),))
    with db.session() as conn:
        tiles = [t["type"] for t in json.loads(conn.execute("SELECT spec FROM views WHERE id = 'seance'").fetchone()[0])["tuiles"]]
        assert "seance_renfo" not in tiles  # elle ne revient pas


def test_upgrade_reads_exercises_back_from_saved_garmin_answers(garmin):
    """Base d'avant la 0.6 : la mise à niveau retrouve les exercices dans les réponses brutes, sans Garmin,
    et la vue Renfo arrive aussitôt."""
    with db.session() as conn:
        conn.execute("DELETE FROM exercises")
        conn.execute("UPDATE activities SET extra = NULL WHERE id = 'garmin:60000001'")
        conn.execute("DELETE FROM views WHERE id = 'renfo'")
        db.delete_meta(conn, "renfo_vue")
        conn.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
    with db.session() as conn:
        assert db.get_meta(conn, "schema_version") == str(db.SCHEMA_VERSION)
        assert conn.execute("SELECT COUNT(*) FROM exercises").fetchone()[0] == 6
        extra = json.loads(conn.execute("SELECT extra FROM activities WHERE id = 'garmin:60000001'").fetchone()[0])
        assert extra["sets"] == 8
        assert conn.execute("SELECT 1 FROM views WHERE id = 'renfo'").fetchone()


# ------------------------------------------------------------------ Claude Desktop
def test_claude_sees_renfo(garmin):
    from foulee import mcp_server

    period = mcp_server.renfo_period()
    assert period["totaux"]["seances"] == 3 and period["totaux"]["series"] == 16
    squat = next(e for e in period["exercices"] if e["nom"] == "Squat goblet")
    assert [h["charge_kg"] for h in squat["evolution"]] == [14.0, 16.0]
    assert "Pectoraux" in period["muscles_non_travailles"]
    assert set(list(period["muscles_series"])[:2]) == {"Fessiers", "Quadriceps"}  # 12 séries chacun
    detail = mcp_server.detail_seance("garmin:60000001")
    assert detail["renfo"]["exercices"][0]["series"] == "3 × 10 répétitions, 16 kg"
    assert detail["renfo"]["exercices"][2]["series"] == "2 × 40 s"
    assert "Abducteurs (secondaire)" in detail["renfo"]["exercices"][2]["muscles"]
    assert "renfo" not in mcp_server.detail_seance("garmin:50000000")


# ------------------------------------------------------------------ démo
def test_demo_has_renfo():
    from foulee import demo

    demo.build(days=120, second_profile=False)
    try:
        with db.session(readonly=True) as conn:
            assert renfo.has_any(conn)
            assert conn.execute("SELECT 1 FROM views WHERE id = 'renfo'").fetchone()
            end = dt.date.today()
            data = renfo.period(conn, end - dt.timedelta(days=89), end)
            assert data["nb_seances"] >= 4 and len(data["exercices"]) >= 6
            assert all("(" not in e["nom"] for e in data["exercices"])  # tous traduits
    finally:
        config.set_demo(False)


def test_tile_types():
    types = {t["type"]: t for t in views.TILE_TYPES}
    assert {"renfo", "renfo_exercices", "seance_renfo"} <= set(types)
    assert types["renfo"]["params"][0]["default"] == "herite"
    assert types["renfo_exercices"]["params"][0]["default"] == "herite"
