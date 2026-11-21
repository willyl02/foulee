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
    """answers : {("planifiée"|"séance"|"activité", numéro): réponse ou exception}."""

    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def call(self, method, arg):
        if method == "get":
            kind = "planifiée" if "/schedule/" in arg else "séance"
            key = (kind, arg.rsplit("/", 1)[1])
        else:
            assert method == "get_activity_workouts"
            key = ("activité", str(arg))
        self.asked.append(key)
        answer = self.answers.get(key)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _feed(squats_title="Séance S2 du mardi"):
    events = [(-1, "20261120T223509Z-1763763857@172.23.128.1", "21KM-S3-6-Endurance de Force : « Avis de tempête »"),
              (2, "20261121T122111Z-1762623899@172.23.128.1", squats_title)]
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
        # le numéro de l'UID est celui de la séance planifiée : Garmin rend la planification et sa séance
        session = FakeSession({("planifiée", "1763763857"): {"workoutScheduleId": 1763763857, "workout": TEMPETE},
                               ("planifiée", "1762623899"): {"workout": SQUATS}})
        assert seances.sync(conn, session) == {"lues": 2}
        assert db.get_meta(conn, seances.ROUTE_KEY) == "planifiée"
        assert seances.sync(conn, session) == {"lues": 0} and len(session.asked) == 2  # pas relues tout de suite
        after = {p["titre"][:10]: p for p in calendrier.plan(conn, day(-3), day(3))}
    tempete = after["21KM-S3-6-"]
    assert tempete["esquisse_approchee"] is False and tempete["blocs"][1]["repetitions"] == 7
    assert after["Séance S2 "]["sport"] == "renfo" and "blocs" not in after["Séance S2 "]


def test_the_other_path_is_tried_and_remembered():
    with db.session() as conn:
        calendrier.store(conn, calendrier.parse(_feed(), day(-1)), today=day(-1))
        session = FakeSession({("séance", "1763763857"): TEMPETE, ("séance", "1762623899"): SQUATS})
        assert seances.sync(conn, session) == {"lues": 2}
        # la première fois les deux chemins, puis seulement celui qui a répondu
        assert session.asked[:2] == [("planifiée", "1762623899"), ("séance", "1762623899")]
        assert session.asked[2:] == [("séance", "1763763857")]
        assert db.get_meta(conn, seances.ROUTE_KEY) == "séance"


def test_done_sessions_are_found_through_their_activity():
    with db.session() as conn:
        db.set_setting(conn, "vma_kmh", 16)
        calendrier.store(conn, calendrier.parse(_feed(), day(-1)), today=day(-1))
        conn.execute("INSERT INTO activities(id, source, source_id, start_local, date, sport, name, distance_m, duration_s) "
                     "VALUES ('garmin:25150833128', 'garmin', '25150833128', ?, ?, 'course', 'Chartèves', 8500, 3300)",
                     (f"{day(-1).isoformat()} 10:00:00", day(-1).isoformat()))
        session = FakeSession({("activité", "25150833128"): [TEMPETE]})  # les chemins des séances : 404
        assert seances.sync(conn, session) == {"lues": 1}
        plan = {p["titre"][:10]: p for p in calendrier.plan(conn, day(-3), day(3))}
    assert plan["21KM-S3-6-"]["esquisse_approchee"] is False and plan["21KM-S3-6-"]["statut"] == "fait"


def test_a_key_without_access_to_workouts_is_left_alone_for_a_week(caplog):
    caplog.set_level("INFO", logger="foulee.garmin")
    with db.session() as conn:
        calendrier.store(conn, calendrier.parse(_feed(), day(-1)), today=day(-1))
        refused = FakeSession({(k, n): GarminError("refus", 403, detail="Forbidden")
                               for k in ("planifiée", "séance") for n in ("1763763857", "1762623899")})
        result = seances.sync(conn, refused)
        assert result["refus"] is True and result["statut"] == 403 and len(refused.asked) == 4
        assert seances.sync(conn, refused) == {"lues": 0, "refus": True} and len(refused.asked) == 4
        assert "rien de lisible (planifiée HTTP 403, séance HTTP 403)" in caplog.text
        assert "planifiée" in json.loads(db.get_meta(conn, seances.REFUSAL_KEY))["chemins"]
