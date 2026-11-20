"""Mes séances de renfo (0.8.2) : composées dans Foulée, gardées, en .fit et sur la montre par le relais."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from foulee import coach, db, renfo, renfo_seances, workout_fit
from foulee.web import create_app
from test_relais_garmin import ADDRESS, PASSWORD, accept, fake, relay, token  # noqa: F401

SESSION = {"titre": "Renfo arrière", "consigne": "Lentement",
           "exercices": [{"nom": "Pont fessier", "series": 3, "reps": "15", "recup_s": 45},
                         {"nom": "Planche", "series": 3, "reps": "30 à 45 s", "recup_s": 30},
                         {"nom": "Rowing inversé", "series": 3, "reps": "8 à 12", "recup_s": 60}]}


def test_session_becomes_watch_blocks():
    assert renfo_seances.parse_dosage("3 × 10 par jambe") == (3, "10 par jambe")
    item = renfo_seances.to_item(SESSION, "2026-12-01")
    assert item["sport"] == "renfo" and item["date"] == "2026-12-01"
    warm, bridge, plank, row, stretch = item["blocs"]
    assert warm["genre"] == "echauffement" and stretch["genre"] == "calme"
    assert bridge == {"genre": "corps", "nom": "Pont fessier", "repetitions": 3, "libre": True,
                      "note": "15 répétitions", "recup_min": 0.75}
    assert plank["duree_min"] == 0.5 and "libre" not in plank   # une série en secondes est chronométrée
    assert row["note"] == "8 à 12 répétitions"
    # sans échauffement ni étirements, et le fichier .fit se fabrique
    bare = renfo_seances.to_item({**SESSION, "echauffement": False, "etirements": False})
    assert [b["nom"] for b in bare["blocs"]] == ["Pont fessier", "Planche", "Rowing inversé"]
    assert workout_fit.build(item, None)[:14]
    with pytest.raises(renfo_seances.SessionError):
        renfo_seances.clean({"titre": "Vide", "exercices": []})


def test_library_names_count_on_the_right_side():
    lib = renfo_seances.library()
    assert {f["famille"] for f in lib} == set(renfo.EXERCISE_LIBRARY)
    bridge = next(e for f in lib for e in f["exercices"] if e["nom"] == "Pont fessier")
    assert (bridge["series"], bridge["reps"]) == (3, "15")


def test_app_keeps_sessions_and_makes_the_fit_file():
    client = TestClient(create_app())
    headers = {"X-Foulee": "1"}
    start = client.get("/api/renfo/seances").json()
    assert start["seances"] == [] and start["montre"] is False and start["bibliotheque"]
    saved = client.put("/api/renfo/seances", headers=headers, json={"seances": [SESSION]}).json()["seances"]
    assert saved[0]["titre"] == "Renfo arrière" and len(saved[0]["id"]) >= 6
    assert client.get("/api/renfo/seances").json()["seances"] == saved
    fit = client.post("/api/renfo/seance.fit", headers=headers, json={"seance": SESSION})
    assert fit.status_code == 200 and fit.headers["content-disposition"].endswith('.fit"') and fit.content[8:12] == b".FIT"
    bad = client.put("/api/renfo/seances", headers=headers, json={"seances": [{"titre": "", "exercices": []}]})
    assert bad.status_code == 400
    # sans relais : pas d'envoi sur la montre, le fichier .fit reste
    watch = client.post("/api/renfo/seance/montre", headers=headers, json={"seance": SESSION})
    assert watch.status_code == 409 and ".fit" in watch.json()["detail"]


def test_my_session_goes_to_my_watch_through_the_relay(relay, fake):
    sophie = token(relay, "sophie")
    code = relay.post("/api/v1/invitations", headers=sophie).json()["invitation"]["code"]
    with db.session() as conn:
        coach.join(conn, ADDRESS, code=code, ident="lucas", name="Lucas B.", password=PASSWORD)
    day = (date.today() + timedelta(days=1)).isoformat()
    item = renfo_seances.to_item(SESSION, day)
    with db.session() as conn:
        first = coach.garmin_personal(conn, item)
    assert first["a_relier"] is True and not fake.workouts
    accept(relay, fake, first["adresse"])
    assert not fake.workouts  # relier ne l'envoie pas toute seule : on la renvoie
    with db.session() as conn:
        sent = coach.garmin_personal(conn, item)
    assert sent["envoi"]["date"] == day
    (workout,) = fake.workouts.values()
    assert workout["sport"] == "STRENGTH_TRAINING" and workout["workoutName"] == "Renfo arrière"
    loop = workout["segments"][0]["steps"][1]
    assert loop["repeatValue"] == 3 and loop["steps"][0]["durationType"] == "OPEN"
    assert loop["steps"][0]["description"] == "Pont fessier · 15 répétitions"
    assert loop["steps"][1]["intensity"] == "RECOVERY" and loop["steps"][1]["durationValue"] == 45
    (schedule,) = fake.schedules.values()
    assert schedule["date"] == day
    # le relais garde seulement l'envoi chez Garmin, pas la séance ; un coach ne s'en sert pas
    assert relay.post("/api/v1/garmin/perso", headers=sophie, json=item).status_code == 403
