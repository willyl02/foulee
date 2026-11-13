"""Renfo : équilibre avant / arrière (chaîne antérieure contre chaîne postérieure), de l'exercice à l'interface."""

import datetime as dt
import json

import pytest
from fake_garmin import FakeGarmin
from fastapi.testclient import TestClient
from test_renfo import LEGS, strength

from foulee import db, renfo, sync, vault, views


def rows(*items: tuple) -> list[dict]:
    return [{"category": c, "name": n, "sets": s} for c, n, s in items]


# Exercices réels (montre Garmin, profil FIT) et écrits à la main (description Strava)
@pytest.mark.parametrize("category, name, family", [
    ("plyo", "lateral_leap_and_hop", "lateral"),
    ("hip_raise", "kettlebell_swing", "hanche"),
    ("calf_raise", "single_leg_standing_calf_raise", "mollets"),
    ("lunge", "dumbbell_lunge", "genou"),
    ("squat", "weighted_wall_squat", "genou"),
    ("plank", "side_plank", "lateral"),
    ("plank", "swiss_ball_plank", "abdos"),
    ("leg_curl", "swiss_ball_hip_raise_and_leg_curl", "hanche"),
    ("triceps_extension", "bench_dip", "triceps"),
    ("lateral_raise", None, "poussee"),
    ("lateral_raise", "bent_over_lateral_raise", "tirage"),
    ("flye", "dumbbell_flye", "poussee"),
    ("flye", "kneeling_rear_flye", "tirage"),
    ("shoulder_stability", "45_degree_cable_external_rotation", "tirage"),
    ("hip_stability", "prone_hip_internal_rotation", "lateral"),  # la hanche, pas l'épaule
    ("bench_press", "barbell_bench_press", "poussee"),
    ("row", "dumbbell_row", "tirage"),
    ("deadlift", "romanian_deadlift", "hanche"),
    ("hyperextension", "superman_from_floor", "lombaires"),
    ("core", "russian_twist", "lateral"),
    ("hip_stability", "dead_bug", "abdos"),
    ("hip_stability", "lateral_walks_with_band_at_ankles", "lateral"),
    ("crunch", "leg_extensions", "abdos"),  # au sol, les abdos : pas la machine à quadriceps
    ("hip_raise", "incline_rear_leg_extension", "hanche"),
    ("push_up", "feet_elevated_side_to_side_push_up", "poussee"),
    ("push_up", "push_up_and_row", "mixte"),
    ("total_body", "burpee", "mixte"),
    ("olympic_lift", "clean_and_jerk", "mixte"),
    ("olympic_lift", "power_clean", "hanche"),
    ("curl", "dumbbell_biceps_curl", "biceps"),
    ("leg_curl", "nordic_hamstring_curl", "hanche"),
    ("warm_up", "ankle_dorsiflexion_with_band", None),
    ("unknown", None, None),
    ("cardio", "jump_rope", None),
    ("indoor_row", None, None),
    ("texte", "Soulevé de terre roumain", "hanche"),
    ("texte", "Pompes", "poussee"),
    ("texte", "Tractions", "tirage"),
    ("texte", "Bench Press (Barbell)", "poussee"),
    ("texte", "Élévations latérales", "poussee"),
    ("texte", "Planche latérale", "lateral"),
    ("texte", "Squat bulgare", "genou"),
    ("texte", "Élévation des orteils", "releveurs"),
    ("texte", "Rameur", None),
    ("texte", "Corde à sauter", None),
])
def test_chain_family(category, name, family):
    assert renfo.chain_family(category, name) == family


def test_every_garmin_exercise_is_ranged_without_error():
    """Les 1 846 exercices du profil FIT : une famille connue (ou rien), et les catégories de musculation
    ont toutes une famille par défaut."""
    from garmin_fit_sdk import Profile

    types = Profile["types"]
    for key in types:
        if key.endswith("_exercise_name"):
            category = key[:-len("_exercise_name")]
            for name in types[key].values():
                family = renfo.chain_family(category, name)
                assert family is None or family in renfo.CHAIN_FAMILIES
                if category not in renfo.CHAIN_SKIP and category not in ("banded_exercises", "suspension"):
                    assert family is not None, (category, name)


def test_the_examples_of_the_1_to_1_rule():
    # « 4 séries de développé couché ↔ 4 séries de rowing », « 4 séries de squat ↔ 4 séries de soulevé de terre roumain »
    b = renfo.balance(rows(("bench_press", "barbell_bench_press", 4), ("row", "barbell_row", 4),
                           ("squat", "barbell_back_squat", 4), ("deadlift", "romanian_deadlift", 4)))
    assert (b["avant"], b["arriere"], b["ratio"], b["ratio_texte"], b["zone"]) == (8, 8, 1.0, "1 : 1", "cible")
    assert {p["cle"]: (p["avant"]["series"], p["arriere"]["series"], p["penche"]) for p in b["paires"]} == {
        "haut": (4, 4, "equilibre"), "bas": (4, 4, "equilibre")}
    assert b["conseil"] == "Rien à corriger : continue comme ça."


def test_zones_and_how_the_ratio_is_written():
    assert renfo.balance_zone(10, 7) == ("avant", 0.7)
    assert renfo.balance_zone(10, 7.96) == ("proche", 0.8)  # « 1 : 0,8 » à l'écran : pas « trop d'avant »
    assert renfo.balance_zone(10, 9) == ("proche", 0.9)
    assert renfo.balance_zone(10, 10) == ("cible", 1.0)
    assert renfo.balance_zone(10, 20) == ("cible", 2.0)  # 1:2, le haut de la cible du coureur
    assert renfo.balance_zone(10, 21) == ("arriere", 2.1)
    assert renfo.balance_zone(10, 41) == ("arriere_fort", 4.1)
    assert renfo.balance_zone(0, 5) == ("arriere_fort", None)
    assert renfo.balance_zone(0, 0) == ("vide", None)
    assert [renfo.ratio_text(r) for r in (0.0, 0.75, 0.8, 1.0, 1.07, 1.5, 2.0, None)] == [
        "1 : 0", "1 : 0,75", "1 : 0,8", "1 : 1", "1 : 1,1", "1 : 1,5", "1 : 2", "tout à l'arrière"]


def test_william_like_period():
    """Beaucoup de jambes et de mollets, des bonds latéraux : la cible, mais le bas du corps et le tronc penchent."""
    b = renfo.balance(rows(
        ("plyo", "lateral_leap_and_hop", 22), ("hip_raise", "kettlebell_swing", 16),
        ("calf_raise", "single_leg_standing_calf_raise", 11), ("lunge", "dumbbell_lunge", 11), ("squat", "weighted_squat", 10),
        ("calf_raise", "weighted_standing_calf_raise", 9), ("plank", "side_plank", 9), ("plank", "swiss_ball_plank", 9),
        ("leg_curl", "swiss_ball_hip_raise_and_leg_curl", 8), ("unknown", None, 5), ("squat", "weighted_back_squats", 4),
        ("squat", "weighted_wall_squat", 4), ("warm_up", "ankle_dorsiflexion_with_band", 4), ("lunge", "offset_dumbbell_lunge", 3),
        ("calf_raise", "standing_barbell_calf_raise", 2), ("cardio", None, 2), ("cardio", "jump_rope", 1), ("core", None, 1),
        ("lateral_raise", None, 1), ("push_up", None, 1), ("triceps_extension", "bench_dip", 1)))
    assert (b["avant"], b["arriere"], b["ratio_texte"], b["zone"], b["verdict"]) == (44, 47, "1 : 1,1", "cible", "Dans la cible")
    assert (b["neutre"], b["non_comptees"], b["mixte"]) == (31, 12, 0)
    pairs = {p["cle"]: p for p in b["paires"]}
    assert (pairs["bas"]["avant"]["series"], pairs["bas"]["arriere"]["series"], pairs["bas"]["ratio_texte"]) == (32, 24, "1 : 0,75")
    assert pairs["bas"]["penche"] == "avant" and pairs["tronc"]["penche"] == "avant"
    assert pairs["haut"]["penche"] is None  # 2 séries : trop peu pour juger
    assert pairs["jambe"]["penche"] == "arriere" and pairs["bas"]["avant"]["court"] == "genou"
    assert b["conseil"].startswith("Bon équilibre d'ensemble, mais le bas du corps penche vers l'avant "
                                   "(32 séries côté genou pour 24 côté hanche), le tronc aussi "
                                   "(10 séries d'abdos, aucune de lombaires).")
    assert "soulevé de terre roumain" in b["conseil"] and "superman" in b["conseil"]
    assert b["conseil_court"].startswith("Bon équilibre d'ensemble, mais le bas du corps et le tronc penchent vers l'avant : ajoute")


def test_whole_body_counts_half_on_each_side_and_lateral_apart():
    b = renfo.balance(rows(("total_body", "burpee", 4), ("bench_press", None, 2), ("plank", "side_plank", 3)))
    assert (b["avant"], b["arriere"], b["mixte"], b["neutre"], b["zone"]) == (4, 2, 4, 3, "avant")
    assert b["conseil"] == "Ajoute des séries côté arrière, par exemple du rowing, des tractions ou de l'oiseau."
    behind = renfo.balance(rows(("deadlift", "romanian_deadlift", 6), ("calf_raise", None, 6), ("squat", None, 2)))
    assert behind["zone"] == "arriere_fort" and behind["ratio_texte"] == "1 : 6"
    assert behind["conseil"] == "Garde aussi un peu d'avant : des squats, des fentes ou des step-up."
    empty = renfo.balance(rows(("warm_up", None, 3), ("plank", "side_plank", 2)))
    assert empty["zone"] == "vide" and empty["conseil"] is None and empty["ratio_texte"] is None


@pytest.fixture
def garmin(monkeypatch):
    with FakeGarmin(days=40, activities=2) as fake:
        fake.activities.append(strength(1, fake.today - dt.timedelta(days=2), LEGS))
        monkeypatch.setenv("GARMIN_PERSONAL_API_BASE_URL", fake.url)
        vault.set_key("cle-de-test")
        sync.run(since=fake.today - dt.timedelta(days=35))
        yield fake


def test_session_period_api_and_claude(garmin):
    from foulee import mcp_server
    from foulee.web import create_app

    client = TestClient(create_app())
    detail = client.get("/api/activities/garmin:60000001", params={"fetch": 0}).json()
    b = detail["renfo"]["equilibre"]
    assert (b["avant"], b["arriere"], b["neutre"], b["ratio_texte"], b["zone"]) == (6, 0, 2, "1 : 0", "avant")
    assert b["conseil"] == ("Le bas du corps penche vers l'avant (6 séries côté genou, aucune côté hanche). "
                            "Ajoute du soulevé de terre roumain, du hip thrust ou du leg curl.")
    chains = [e["chaine"] for e in detail["renfo"]["exercices"]]
    assert [c["famille"] for c in chains] == ["genou", "genou", "lateral"]
    assert chains[0] == {"famille": "genou", "nom": "Dominante genou", "chaine": "avant", "chaine_nom": "Avant"}

    period = client.get("/api/renfo").json()
    assert period["equilibre"]["zone"] == "avant" and len(period["semaines"]) == 12
    weeks = [w["equilibre"] for w in period["semaines"]]
    assert weeks[-1] is None or weeks[-1]["zone"] == "avant"  # la séance est de cette semaine ou de la précédente
    assert sum(w is not None for w in weeks) == 1 and next(w for w in weeks if w)["ratio_texte"] == "1 : 0"

    seen = mcp_server.detail_seance("garmin:60000001")["renfo"]["equilibre_avant_arriere"]
    assert seen["rapport"] == "1 : 0" and seen["verdict"] == "Trop d'avant" and seen["lateral_et_rotation_series"] == 2
    assert seen["familles_des_exercices"]["Squat goblet"] == "Avant · Dominante genou"
    assert seen["familles_des_exercices"]["Planche latérale"] == "Latéral et rotation (à part, ni devant ni derrière)"
    whole = mcp_server.renfo_period()
    assert whole["equilibre_avant_arriere"]["paires"][0]["paire"] == "Bas du corps"
    assert any(w["equilibre"] == "1 : 0" for w in whole["semaines"])


def test_tiles_added_once_to_the_views_already_in_place(garmin):
    def tiles(conn, view_id):
        return [t["type"] for t in json.loads(conn.execute("SELECT spec FROM views WHERE id = ?", (view_id,)).fetchone()[0])["tuiles"]]

    with db.session() as conn:  # une installation neuve : les deux tuiles sont déjà là
        assert tiles(conn, "seance")[:3] == ["seance_resume", "seance_renfo", "seance_effet"]
        assert tiles(conn, "renfo")[:3] == ["renfo", "renfo_equilibre", "renfo_exercices"]
        for view_id, kind in (("seance", "seance_effet"), ("renfo", "renfo_equilibre")):
            spec = json.loads(conn.execute("SELECT spec FROM views WHERE id = ?", (view_id,)).fetchone()[0])
            spec["tuiles"] = [t for t in spec["tuiles"] if t["type"] != kind]
            conn.execute("UPDATE views SET spec = ? WHERE id = ?", (json.dumps(spec), view_id))
        db.delete_meta(conn, "vue_effet_entrainement")  # une base d'avant la 0.7.0b3
        db.delete_meta(conn, "vue_renfo_equilibre")
    with db.session() as conn:
        assert tiles(conn, "seance")[:3] == ["seance_resume", "seance_renfo", "seance_effet"]
        assert tiles(conn, "renfo")[:3] == ["renfo", "renfo_equilibre", "renfo_exercices"]
        for view_id, kind in (("seance", "seance_effet"), ("renfo", "renfo_equilibre")):  # retirées à la main
            spec = json.loads(conn.execute("SELECT spec FROM views WHERE id = ?", (view_id,)).fetchone()[0])
            spec["tuiles"] = [t for t in spec["tuiles"] if t["type"] != kind]
            conn.execute("UPDATE views SET spec = ? WHERE id = ?", (json.dumps(spec), view_id))
    with db.session() as conn:
        assert "seance_effet" not in tiles(conn, "seance") and "renfo_equilibre" not in tiles(conn, "renfo")


def test_tile_types():
    types = {t["type"]: t for t in views.TILE_TYPES}
    assert types["renfo_equilibre"]["params"][0]["default"] == "herite"
    assert types["renfo_equilibre"]["icone"] == "balance" and types["seance_effet"]["icone"] == "gauge"
    assert types["seance_effet"]["categorie"] == "Séances" and types["seance_effet"]["params"] == []
