"""0.8.3 : les séances prévues du calendrier Garmin lues chez Garmin, pour les dessiner telles qu'elles sont
(demande de William : « Endurance de Force : Avis de tempête », 7 × 30 s rapides et 3 min de récup)."""

import datetime as dt
import json

from foulee import calendrier, db
from foulee.garmin import seances
from foulee.garmin.client import GarminError

TODAY = dt.date.today()


def day(offset: int) -> dt.date:
    return TODAY + dt.timedelta(days=offset)


def step(order, kind, cond, value, target="no.target", low=None, high=None, zone=None):
    return {"type": "ExecutableStepDTO", "stepOrder": order, "stepType": {"stepTypeKey": kind},
            "endCondition": {"conditionTypeKey": cond}, "endConditionValue": value,
            "targetType": {"workoutTargetTypeKey": target}, "targetValueOne": low, "targetValueTwo": high,
            "zoneNumber": zone}


def kmh(v):  # km/h → m/s
    return v / 3.6


TEMPETE = {  # comme la renvoie Garmin Connect (allégée)
    "workoutId": 1763763857, "workoutName": "21KM-S3-6-Endurance de Force : « Avis de tempête »",
    "sportType": {"sportTypeKey": "running"},
    "workoutSegments": [{"segmentOrder": 1, "workoutSteps": [
        step(1, "warmup", "time", 1200, "pace.zone", kmh(10.5), kmh(11.7)),
        {"type": "RepeatGroupDTO", "stepOrder": 2, "stepType": {"stepTypeKey": "repeat"}, "numberOfIterations": 7,
         "endCondition": {"conditionTypeKey": "iterations"}, "endConditionValue": 7, "workoutSteps": [
             step(3, "interval", "time", 30, "pace.zone", kmh(17.5), kmh(18.5)),
             step(4, "recovery", "time", 180)]},
        step(5, "cooldown", "time", 600, "heart.rate.zone", zone=1),
    ]}]}
SQUATS = {"workoutId": 1762623899, "sportType": {"sportTypeKey": "strength_training"},
          "workoutSegments": [{"segmentOrder": 1, "workoutSteps": [step(1, "interval", "reps", 10)]}]}


def test_a_garmin_workout_becomes_the_blocks_of_the_sketch():
    blocks = seances.blocks_of(TEMPETE, vma=16)
    assert blocks == [
        {"genre": "echauffement", "duree_min": 20.0, "pct_vma": 69},
        {"genre": "corps", "duree_min": 0.5, "pct_vma": 112, "repetitions": 7, "recup_min": 3.0},
        {"genre": "calme", "duree_min": 10.0, "zone_fc": 1},
    ]
    assert seances.sport_of(TEMPETE) == "course" and seances.sport_of(SQUATS) == "renfo"
    assert seances.workout_id("20261120T223509Z-1763763857@172.23.128.1") == "1763763857"
    assert seances.workout_id("coach:3") is None and seances.workout_id(None) is None
    # sans VMA : la durée reste, l'intensité vient du genre ; une distance, un « jusqu'au bouton Lap »
    track = {"workoutSegments": [{"workoutSteps": [step(1, "interval", "distance", 400), step(2, "interval", "lap.button", None)]}]}
    assert seances.blocks_of(track, None) == [{"genre": "corps", "distance_m": 400}, {"genre": "corps", "libre": True}]
    assert seances.blocks_of(None, 16) == [] and seances.blocks_of({"workoutSegments": "x"}, 16) == []


class FakeSession:
    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def call(self, method, path):
        assert method == "get"
        self.asked.append(path)
        answer = self.answers.get(path.rsplit("/", 1)[1])
        if isinstance(answer, Exception):
            raise answer
        return answer


def _feed():
    events = [(-1, "20261120T223509Z-1763763857@172.23.128.1", "21KM-S3-6-Endurance de Force : « Avis de tempête »"),
              (2, "20261121T122111Z-1762623899@172.23.128.1", "Séance S2 du mardi")]
    return "\r\n".join(["BEGIN:VCALENDAR", "PRODID:-//Garmin Connect//ICalProvider 1.0//EN",
                        *[line for d, uid, title in events for line in
                          ("BEGIN:VEVENT", f"UID:{uid}", f"DTSTART;VALUE=DATE:{day(d):%Y%m%d}", f"SUMMARY:{title}", "END:VEVENT")],
                        "END:VCALENDAR"])


def test_the_sync_reads_them_once_and_the_calendar_draws_them():
    with db.session() as conn:
        db.set_setting(conn, "vma_kmh", 16)
        calendrier.store(conn, calendrier.parse(_feed(), day(-1)), today=day(-1))
        before = {p["titre"][:10]: p for p in calendrier.plan(conn, day(-3), day(3))}
        assert before["21KM-S3-6-"]["esquisse_approchee"] is True  # deviné du nom
        assert before["Séance S2 "]["sport"] != "renfo"             # rien dans le nom pour le dire
        session = FakeSession({"1763763857": TEMPETE, "1762623899": SQUATS})
        assert seances.sync(conn, session) == {"lues": 2}
        assert seances.sync(conn, session) == {"lues": 0} and len(session.asked) == 2  # pas relues tout de suite
        after = {p["titre"][:10]: p for p in calendrier.plan(conn, day(-3), day(3))}
    tempete = after["21KM-S3-6-"]
    assert tempete["esquisse_approchee"] is False and tempete["blocs"][1]["repetitions"] == 7
    assert after["Séance S2 "]["sport"] == "renfo" and "blocs" not in after["Séance S2 "]


def test_a_key_without_access_to_workouts_is_left_alone_for_a_week(caplog):
    caplog.set_level("INFO", logger="foulee.garmin")
    with db.session() as conn:
        calendrier.store(conn, calendrier.parse(_feed(), day(-1)), today=day(-1))
        refused = FakeSession({"1763763857": GarminError("refus", 403, detail="Forbidden"),
                               "1762623899": GarminError("refus", 403, detail="Forbidden")})
        result = seances.sync(conn, refused)
        assert result["refus"] is True and result["statut"] == 403 and len(refused.asked) == 1
        assert seances.sync(conn, refused) == {"lues": 0, "refus": True} and len(refused.asked) == 1
        assert "lecture refusée (HTTP 403" in caplog.text
        # trois « introuvable » d'affilée sans aucune séance lue : l'API ne les donne pas
        db.set_meta(conn, seances.REFUSAL_KEY, "")
        feed = "\r\n".join(["BEGIN:VCALENDAR", "PRODID:-//Garmin Connect//ICalProvider 1.0//EN", *[
            line for n in range(4) for line in ("BEGIN:VEVENT", f"UID:2026Z-17000000{n}@x", f"DTSTART;VALUE=DATE:{day(n + 3):%Y%m%d}",
                                                f"SUMMARY:Footing {n}", "END:VEVENT")], "END:VCALENDAR"])
        calendrier.store(conn, calendrier.parse(feed, TODAY), today=TODAY)
        empty = FakeSession({})
        assert seances.sync(conn, empty)["statut"] == 404 and len(empty.asked) == 3
        assert json.loads(db.get_meta(conn, seances.REFUSAL_KEY))["statut"] == 404
