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


# ------------------------------------------------- points 3 et 4 : quelle séance faite pour quelle séance prévue
def _calendar_day(conn, today):
    from foulee import calendrier

    day = "2026-11-17"
    rows = [("21KM-S3-2-Seuil 60", "seance", "course", "garmin-plan-1", None),
            ("VMA courte", "seance", "course", "garmin-ws-1", "Bien respecter les allures 100% VMA"),  # revenue de Garmin
            ("VMA courte (coach)", "seance", "course", "coach:5", "Échauffement : 20 min à 65 % VMA")]
    for title, kind, sport, uid, text in rows:
        conn.execute(calendrier.INSERT, (day, None, None, 1, title, text, None, kind, sport, uid, db.now_iso()))
    db.set_meta(conn, "relais_propositions", json.dumps([{"id": 5, "date": day, "titre": "VMA courte", "blocs": [
        {"genre": "echauffement", "duree_min": 20, "pct_vma": 65},
        {"genre": "corps", "repetitions": 10, "distance_m": 200, "pct_vma": 100, "recup_min": 0.67},
        {"genre": "calme", "duree_min": 10, "pct_vma": 55}]}]))
    return day


def test_the_session_done_goes_to_the_planned_session_it_resembles():
    """17 novembre : William fait « 21KM-S3-2-Seuil 60 » de son plan ; la « VMA courte » de son coach, prévue le
    même jour, ne doit pas passer « faite »."""
    from datetime import date

    from foulee import calendrier

    with db.session() as conn:
        day = _calendar_day(conn, date(2026, 11, 17))
        conn.execute("INSERT INTO activities(id, source, source_id, start_local, date, sport, name, duration_s, moving_s) "
                     "VALUES ('garmin:7', 'garmin', '7', ?, ?, 'course', 'Mézy-Moulins - 21KM-S3-2-Seuil 60', 3660, 3640)",
                     (f"{day} 05:30:00", day))
        items = calendrier.plan(conn, date(2026, 11, 17), date(2026, 11, 17), today=date(2026, 11, 18))
    by_title = {i["titre"]: i for i in items}
    assert "VMA courte" not in by_title  # point 4 : la copie revenue de Garmin n'est plus un doublon
    assert by_title["21KM-S3-2-Seuil 60"]["statut"] == "fait"
    assert by_title["VMA courte (coach)"]["statut"] == "manque"
    assert by_title["VMA courte (coach)"]["blocs"][1]["repetitions"] == 10


def test_the_coach_session_done_is_recognised_by_its_name_and_length():
    from datetime import date

    from foulee import calendrier

    with db.session() as conn:
        day = _calendar_day(conn, date(2026, 11, 17))
        conn.execute("INSERT INTO activities(id, source, source_id, start_local, date, sport, name, duration_s, moving_s) "
                     "VALUES ('garmin:8', 'garmin', '8', ?, ?, 'course', 'Chartèves - VMA courte', 2820, 2700)",
                     (f"{day} 18:00:00", day))
        items = {i["titre"]: i for i in calendrier.plan(conn, date(2026, 11, 17), date(2026, 11, 17),
                                                         today=date(2026, 11, 18))}
    assert items["VMA courte (coach)"]["statut"] == "fait" and items["21KM-S3-2-Seuil 60"]["statut"] == "manque"


def test_one_planned_one_done_still_go_together():
    from foulee import appariement, calendrier

    planned = [{"cle": 1, "date": "2026-11-20", "titre": "Footing", "sport": "course"}]
    done = [{"cle": "a", "date": "2026-11-20", "sport": "course", "nom": "Course à pied", "duree_s": 2400}]
    assert appariement.assign(planned, done, calendrier._fits)[1]["cle"] == "a"
    renfo = [{"cle": 2, "date": "2026-11-18", "titre": "5x10 Squat arrière + 5x10 Hip thrust", "sport": "renfo"}]
    assert not appariement.assign(renfo, [dict(done[0], date="2026-11-18")], calendrier._fits)  # pas une course


def test_the_relay_does_not_credit_the_coach_with_another_session():
    from foulee.relais import club

    day = club._today().isoformat()
    items = [{"id": 5, "date": day, "titre": "VMA courte", "sport": "course", "blocs": [
        {"genre": "corps", "repetitions": 10, "distance_m": 200, "pct_vma": 100, "recup_min": 0.67}]}]
    plan = [{"date": day, "titre": "21KM-S3-2-Seuil 60", "type": "seance", "sport": "course", "statut": "fait"},
            {"date": day, "titre": "VMA courte", "type": "seance", "sport": "course"}]  # la copie Garmin (0.8.1)
    seuil = [{"cle": "garmin:7", "date": day, "sport": "course", "nom": "Mézy-Moulins - 21KM-S3-2-Seuil 60",
              "duree_s": 3660}]
    club._with_status(items, seuil, plan, 16.0)
    assert items[0]["statut"] != "fait" and items[0]["seance"] is None
    vma = [{"cle": "garmin:8", "date": day, "sport": "course", "nom": "Chartèves - VMA courte", "duree_s": 2800}]
    club._with_status(items, seuil + vma, plan, 16.0)
    assert items[0]["statut"] == "fait" and items[0]["seance"]["cle"] == "garmin:8"
    # la semaine du coach : la séance du coach une seule fois, pas aussi sa copie revenue de Garmin
    days = club.week({"plan": plan, "seances": seuil + vma}, items, club._monday(club._today()))
    titles = [p["titre"] for d in days for p in d["prevu"]]
    assert titles.count("VMA courte") == 1
