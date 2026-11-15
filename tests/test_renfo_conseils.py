"""Renfo : les exercices pour rééquilibrer (côté élève), et l'équilibre avant / arrière vu par le coach."""

from datetime import timedelta

import pytest
from test_relais_club import (  # noqa: F401 (le fixture « relay »)
    join,
    relay,
    session,
    token,
)

from foulee import coach, db, renfo
from foulee.relais import club


def rows(*items: tuple) -> list[dict]:
    return [{"category": "texte", "name": n, "sets": s} for n, s in items]


FRONT_HEAVY = rows(("Squat", 12), ("Fente avant", 8), ("Pompes", 6), ("Planche", 6), ("Pont fessier", 4), ("Superman", 3))


@pytest.mark.parametrize("family, items", sorted(renfo.EXERCISE_LIBRARY.items()))
def test_every_suggested_exercise_counts_on_the_right_side(family, items):
    """Ce qu'on conseille, une fois noté dans une séance (Garmin ou Strava), compte bien du côté visé."""
    for name, gear, dose, tip in items:
        assert renfo.chain_family("texte", name) == family, name
        assert gear and dose and tip.endswith(".")
    assert renfo.FAMILY_WHY[family]


def test_too_much_front_asks_for_back_sets():
    bal = renfo.balance(FRONT_HEAVY)
    assert bal["zone"] == "avant" and bal["ratio_texte"] == "1 : 0,22"
    c = renfo.compensation(bal, 28, sessions=6)
    assert c["cote"] == "arriere" and c["cible"] == "1 : 1,5"
    assert c["manque_series"] == 41  # 1,5 × 32 devant − 7 derrière
    assert c["par_semaine"] == 10.2 and c["par_seance"] == 6.8
    assert c["titre"] == "Ajoute environ 10 séries par semaine côté arrière"
    assert c["resume"] == ("Sur 28 jours, tu es à 1 : 0,22 : pour viser 1 : 1,5, il manque environ 41 séries derrière, "
                           "soit 7 séries de plus par séance de renfo.")
    # le bas du corps d'abord, puis le haut, puis le tronc
    assert [f["famille"] for f in c["familles"]] == ["hanche", "tirage", "lombaires"]
    assert c["familles"][0]["constat"] == "20 séries côté genou pour 4 côté hanche"
    assert c["familles"][0]["exercices"][0]["nom"] == "Pont fessier"  # sans matériel d'abord


def test_balanced_but_one_pair_leans():
    bal = renfo.balance(rows(("Squat", 10), ("Soulevé de terre roumain", 14), ("Pompes", 8), ("Superman", 4),
                             ("Mollets", 6)))
    assert bal["zone"] == "cible"
    c = renfo.compensation(bal, 28, 4)
    assert c["cote"] == "arriere" and c["manque_series"] == 0
    assert c["titre"].startswith("Bon équilibre d'ensemble, mais le haut du corps penche vers l'avant")
    assert [f["famille"] for f in c["familles"]] == ["tirage"]


def test_too_much_back_keeps_some_front():
    bal = renfo.balance(rows(("Soulevé de terre roumain", 20), ("Superman", 10), ("Squat", 6)))
    c = renfo.compensation(bal, 28, 4)
    assert bal["zone"] == "arriere_fort" and c["cote"] == "avant" and c["manque_series"] == 14
    assert [f["famille"] for f in c["familles"]] == ["genou", "abdos"]
    assert renfo.coach_hint(bal)["cote"] == "avant"


def test_in_the_target_nothing_to_add():
    bal = renfo.balance(rows(("Squat", 10), ("Pont fessier", 15)))
    c = renfo.compensation(bal, 28, 4)
    assert c["cote"] is None and c["familles"] == [] and c["titre"] == "Dans la cible : garde le cap"
    assert renfo.compensation(renfo.balance(rows(("Corde à sauter", 5))), 28, 1) is None  # rien à comparer


def test_coach_hint_and_draft():
    hint = renfo.coach_hint(renfo.balance(FRONT_HEAVY))
    assert hint["texte"].startswith("Trop d'avant (1 : 0,22) : propose-lui du soulevé de terre roumain")
    assert hint["brouillon"].startswith("Ton renfo des 4 dernières semaines est à 1 : 0,22 (avant : arrière)")


# -------------------------------------------------------------------- partage au coach
def test_the_relay_keeps_only_known_families():
    sets = [{"exercice": "Soulevé de terre roumain", "series": 4, "chaine": "Arrière", "famille": "hanche"},
            {"exercice": "Squat", "series": 4, "chaine": "Avant", "famille": "pirate"}]
    cleaned = club.clean_share({"seances": [session("garmin:1", club._today(), sport="renfo", renfo=sets)]})
    kept = cleaned["seances"][0]["renfo"]
    assert kept[0]["famille"] == "hanche" and "famille" not in kept[1]  # une famille inconnue ne passe pas


def test_relay_balance_for_the_coach(relay):  # noqa: F811
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    today = club._today()
    old_style = [{"exercice": "Squat", "series": 6}, {"exercice": "Fente avant", "series": 4}]  # Foulée d'avant 0.8.1
    new_style = [{"exercice": "Soulevé de terre roumain", "series": 3, "chaine": "Arrière", "famille": "hanche"},
                 {"exercice": "Pompes", "series": 4, "chaine": "Avant", "famille": "poussee"},
                 {"exercice": "Échauffement", "series": 2}]
    payload = {"seances": [session("garmin:1", today, sport="renfo", renfo=new_style),
                           session("garmin:2", today - timedelta(days=9), sport="renfo", renfo=old_style),
                           session("garmin:3", today - timedelta(days=2))]}
    relay.put("/api/v1/partage/accord", headers=lucas, json={"seances": True})
    relay.put("/api/v1/partage", headers=lucas, json=payload)
    page = relay.get(f"/api/v1/eleves/{lucas_id}/fiche", headers=sophie).json()
    r = page["renfo"]
    assert r["seances"] == 2 and r["avant"] == 14 and r["arriere"] == 3 and r["ratio_texte"] == "1 : 0,21"
    assert r["zone"] == "avant" and r["non_comptees"] == 2
    assert r["conseil"]["cote"] == "arriere" and "propose-lui" in r["conseil"]["texte"]
    assert len(r["semaines"]) == 4 and r["semaines"][-1]["ratio_texte"] == "1 : 0,75"
    assert next(p for p in r["paires"] if p["cle"] == "bas")["penche"] == "avant"
    group = relay.get("/api/v1/groupe", headers=sophie).json()["eleves"][0]
    assert group["renfo"] == {"ratio_texte": "1 : 0,21", "zone": "avant", "verdict": "Trop d'avant", "seances": 2}
    assert group["prochain"] is None  # pas d'objectif partagé
    # sans le partage des séances, rien
    relay.put("/api/v1/partage/accord", headers=lucas, json={"seances": False, "objectif": True})
    assert relay.get(f"/api/v1/eleves/{lucas_id}/fiche", headers=sophie).json()["renfo"] is None
    assert relay.get("/api/v1/groupe", headers=sophie).json()["eleves"][0]["renfo"] is None


def test_snapshot_sends_chain_and_family():
    with db.session() as conn:
        day = club._today().isoformat()
        conn.execute("INSERT INTO activities(id, source, source_id, start_local, date, sport, name, duration_s) "
                     "VALUES ('garmin:9', 'garmin', '9', ?, ?, 'renfo', 'Renfo', 1800)", (f"{day}T18:00:00", day))
        conn.execute("INSERT INTO exercises(activity_id, idx, category, name, sets, reps, duration_s, max_kg, volume_kg) "
                     "VALUES ('garmin:9', 0, 'deadlift', 'romanian_deadlift', 4, 32, 300, 40, 1280)")
        snap = coach.snapshot(conn, {"seances": True})
    item = snap["seances"][0]["renfo"][0]
    assert item["famille"] == "hanche" and item["chaine"] == "Arrière"
