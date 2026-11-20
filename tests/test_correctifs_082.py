"""0.8.2 : correctifs relevés par William et Jason (objectif par défaut, profils lus sans mise à niveau…)."""

import json

from foulee import __version__, analysis, db, views
from test_relais_club import relay  # noqa: F401  (le relais du club, en mémoire)


def test_a_new_install_has_no_objective():
    with db.session() as conn:
        settings = db.get_settings(conn)
    assert not settings["objectif"]["nom"] and not settings["objectif"]["date"]
    assert "jours_restants" not in analysis.objective(settings)


def test_a_saved_objective_stays_and_the_old_default_is_gone():
    with db.session() as conn:  # une base d'avant la 0.8.2 : rien de saisi, on y voyait le semi de Paris
        assert not db.get_settings(conn)["objectif"]["nom"]
        db.set_setting(conn, "objectif", {"nom": "Semi-marathon de Paris", "date": "2027-03-07",
                                          "distance_km": 21.0975, "temps_cible": "1:25:00"})
    with db.session() as conn:  # celui qu'on a enregistré (le centre des objectifs l'écrit) reste
        assert db.get_settings(conn)["objectif"]["temps_cible"] == "1:25:00"


def test_a_profile_only_read_is_upgraded_first():
    """Un profil qu'on regarde sans le synchroniser (lecture seule) passe quand même par la mise à niveau :
    sinon il garde « Cap semi de Paris » (cas des deux autres profils de William, créés avant la 0.8.1)."""
    with db.session() as conn:
        conn.execute("DELETE FROM views WHERE id = 'objectifs'")
        old = {"tuiles": [views._tile("objectif", 4, 2), views._tile("fractions", 8, 2, periode="120")]}
        conn.execute("INSERT INTO views(id, name, icon, position, spec, builtin) VALUES ('cap-semi', "
                     "'Cap semi de Paris', 'flag', 5, ?, 1)", (json.dumps(old),))
        db.delete_meta(conn, "vue_objectifs")
        db.set_meta(conn, "init_version", "0.8.0")  # mise à niveau faite par une version plus ancienne
    with db.session(readonly=True) as conn:
        names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM views")}
        assert names.get("objectifs") == "Objectifs" and "cap-semi" not in names
        assert db.get_meta(conn, "init_version") == __version__


def test_a_strength_session_planned_in_garmin_is_strength():
    from foulee import calendrier

    title = "5x10 Squat arrière avec poids(65kg) + 5x10 Hip thrust(47kg)"
    assert calendrier.classify({"title": title, "garmin": True, "all_day": True}) == ("seance", "renfo")
    assert calendrier.classify({"title": "VMA courte", "garmin": True, "all_day": True}) == ("seance", "course")
    with db.session() as conn:  # rangée en course à pied par une version d'avant : relue à la synchro suivante
        conn.execute(calendrier.INSERT, ("2026-11-18", None, None, 1, title, None, None, "seance", "course",
                                         "garmin-1", db.now_iso()))
        calendrier.store(conn, [], today=__import__("datetime").date(2026, 11, 20))
        assert conn.execute("SELECT sport FROM calendar_events WHERE title = ?", (title,)).fetchone()[0] == "renfo"


def test_lap_by_lap_analysis_like_intervals_icu():
    floors = [100, 130, 145, 155, 165]  # bas des zones 1 à 5
    laps = [{"start_s": 0, "duration_s": 600, "elapsed_s": 600, "avg_hr": 128, "avg_speed": 3.0, "intensity": "warmup"},
            {"start_s": 600, "duration_s": 300, "elapsed_s": 300, "avg_hr": 166, "avg_speed": 5.0, "intensity": "active"},
            {"start_s": 900, "duration_s": 120, "elapsed_s": 120, "avg_hr": 140, "avg_speed": 2.0, "intensity": "rest"}]
    t = list(range(0, 1021))
    hr = [125] * 600 + [150] * 60 + [168] * 240 + [140] * 121  # le premier quart de l'effort sous la zone 5
    segs = analysis.lap_analysis(laps, {"t": t, "hr": hr}, floors)
    assert [s["zone"] for s in segs] == [1, 5, 2]
    assert segs[1]["zone_pct"] == 80 and segs[0]["zone_pct"] == 100
    assert segs[1]["debut_s"] == 600 and segs[1]["fin_s"] == 900
    assert analysis.lap_analysis(laps, None, floors)[1]["zone_pct"] is None  # sans courbe : la zone seule


def test_the_coach_gets_zones_and_a_light_curve(monkeypatch):
    from foulee import coach
    from foulee.relais import club

    streams = {"t": list(range(0, 2000)), "spd": [3.5] * 2000, "hr": [150] * 2000}
    curve = coach.light_curve(streams)
    assert len(curve["t"]) <= coach.CURVE_POINTS and curve["fc"][0] == 150 and curve["v"][0] == 3.5
    raw = {"date": "2026-11-13", "cle": "garmin:1", "sport": "course",
           "tours": [{"duree_s": 600, "debut_s": 0, "fin_s": 600, "zone": 2, "zone_pct": 73, "fc_moy": 140},
                     {"duree_s": 300, "debut_s": 600, "fin_s": 900, "zone": 5, "zone_pct": 100, "fc_moy": 166}],
           "courbe": curve}
    clean = club._clean_session(raw, "2026-10-01")
    assert clean["tours"][1]["zone"] == 5 and clean["tours"][0]["zone_pct"] == 73
    assert clean["courbe"]["t"][:3] == curve["t"][:3] and len(clean["courbe"]["fc"]) == len(clean["courbe"]["t"])


def test_free_reps_end_at_the_lap_key():
    """Demande de Jason : des répétitions « libres », sans temps ni distance (sur piste, de ligne à ligne)."""
    from foulee import coach, garmin_training, workout_fit
    from foulee.relais import club

    blocks = club.clean_blocks([{"genre": "corps", "nom": "Lignes droites", "repetitions": 6, "libre": True,
                                 "pct_vma": 100, "recup_libre": True, "recup_texte": "marche"}])
    assert blocks[0]["libre"] and blocks[0]["recup_libre"] and "duree_min" not in blocks[0]
    item = {"titre": "Piste", "sport": "course", "blocs": blocks}
    steps = workout_fit.steps_for(item, 16.0)
    assert [s["duration_type"] for s in steps] == ["open", "open", "repeat_until_steps_cmplt"]
    workout_fit.decode(workout_fit.build(item, 16.0))  # un vrai fichier, que la montre lit
    repeat = garmin_training.build(item, 16.0)["segments"][0]["steps"][0]
    assert [s["durationType"] for s in repeat["steps"]] == ["OPEN", "OPEN"] and repeat["repeatValue"] == 6
    assert "touche Lap" in coach.block_text(blocks[0], 16.0) and "récup libre (Lap)" in coach.block_text(blocks[0], 16.0)


def test_coach_and_student_get_a_nine_week_calendar_with_sketches(relay):
    from datetime import date, timedelta

    from foulee import coach, demo
    from test_relais_club import PASSWORD, token

    sophie = token(relay, "sophie")
    code = relay.post("/api/v1/invitations", headers=sophie).json()["invitation"]["code"]
    demo.build(days=45, second_profile=False)
    with db.session() as conn:
        coach.join(conn, "https://relais.test", code=code, ident="demo.eleve", name="Élève démo", password=PASSWORD)
        coach.set_accord(conn, {"seances": True, "objectif": True})
    sid = relay.get("/api/v1/groupe", headers=sophie).json()["eleves"][0]["id"]
    day = (date.today() + timedelta(days=3)).isoformat()
    relay.post("/api/v1/propositions", headers=sophie, json={"eleves": [sid], "date": day, "titre": "Piste", "sport": "course",
                                                            "blocs": [{"genre": "corps", "repetitions": 6, "libre": True,
                                                                       "pct_vma": 100, "recup_libre": True}]})
    page = relay.get(f"/api/v1/eleves/{sid}/fiche", headers=sophie).json()
    days = page["mois"]["jours"]
    assert len(days) == 63 and date.fromisoformat(days[0]["date"]).weekday() == 0
    mine = next(p for d in days if d["date"] == day for p in d["prevu"] if p["source"] == "coach")
    assert mine["blocs"][0]["libre"] is True
    assert any(p.get("blocs") for d in days for p in d["prevu"] if p["source"] == "plan")  # le plan, esquissé
    with db.session() as conn:  # côté élève (« Mon coach ») : le même calendrier, et ses objectifs
        mine = coach.my_page(conn)
    assert len(mine["mois"]["jours"]) == 63 and mine["objectifs"][0]["nom"] == "Semi-marathon (exemple)"
