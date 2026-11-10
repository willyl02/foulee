"""Faux serveur Garmin pour les tests : mêmes chemins et mêmes formats que l'API personnelle.

Il permet de tester toute la chaîne (client officiel → synchro → base → analyses)
sans clé et sans réseau. Les valeurs sont inventées ; la structure suit les réponses
réelles de l'API.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from garmin_fit_sdk import Encoder, Profile

DAY = dt.timedelta(days=1)
MN = Profile["mesg_num"]


def make_jwt(lifetime: int = 86400) -> str:
    def enc(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{enc({'alg': 'none'})}.{enc({'exp': int(time.time()) + lifetime})}.signature"


def make_fit(start: dt.datetime, minutes: int = 20, speed: float = 3.2) -> bytes:
    """Petite séance de course : 1 point par seconde, deux tours."""
    enc = Encoder()
    enc.write_mesg({"mesg_num": MN["FILE_ID"], "manufacturer": "garmin", "product": 1, "time_created": start,
                    "type": "activity", "serial_number": 42})
    total = minutes * 60
    for i in range(total):
        fast = total // 2 <= i < total // 2 + 180
        v = speed * (1.3 if fast else 1.0)
        enc.write_mesg({
            "mesg_num": MN["RECORD"], "timestamp": start + dt.timedelta(seconds=i),
            "heart_rate": 140 + (20 if fast else 0), "enhanced_speed": v, "enhanced_altitude": 80 + (i % 300) / 10,
            "distance": i * speed, "cadence": 85, "fractional_cadence": 0.5,
            "position_lat": int(48.4 / (180 / 2**31)), "position_long": int((2.7 + i * 1e-5) / (180 / 2**31)),
        })
    half = total // 2
    for index, (a, b, intensity) in enumerate([(0, half, "active"), (half, total, "active")]):
        enc.write_mesg({
            "mesg_num": MN["LAP"], "timestamp": start + dt.timedelta(seconds=b - 1), "start_time": start + dt.timedelta(seconds=a),
            "total_elapsed_time": float(b - a), "total_timer_time": float(b - a), "total_distance": (b - a) * speed,
            "avg_heart_rate": 145, "max_heart_rate": 165, "enhanced_avg_speed": speed, "avg_cadence": 85,
            "intensity": intensity, "message_index": index,
        })
    enc.write_mesg({"mesg_num": MN["SESSION"], "timestamp": start + dt.timedelta(seconds=total - 1), "start_time": start,
                    "total_elapsed_time": float(total), "total_timer_time": float(total), "total_distance": total * speed,
                    "sport": "running", "sub_sport": "generic", "num_laps": 2, "first_lap_index": 0})
    enc.write_mesg({"mesg_num": MN["ACTIVITY"], "timestamp": start + dt.timedelta(seconds=total - 1), "num_sessions": 1,
                    "total_timer_time": float(total)})
    return enc.close()


class FakeGarmin:
    def __init__(self, days: int = 60, activities: int = 12):
        self.today = dt.date.today()
        self.first = self.today - dt.timedelta(days=days)
        self.requests: list[tuple[str, dict]] = []
        self.activities = []
        for i in range(activities):
            day = self.today - dt.timedelta(days=i * 4)
            start = dt.datetime(day.year, day.month, day.day, 7, 30)
            self.activities.append({
                "activityId": 50_000_000 + i, "activityName": f"Footing {i}", "description": "Bonnes jambes" if i == 0 else None,
                "startTimeLocal": start.strftime("%Y-%m-%d %H:%M:%S"),
                "startTimeGMT": (start - dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
                "activityType": {"typeId": 1, "typeKey": "trail_running" if i % 5 == 4 else "running"},
                "distance": 3840.0, "duration": 1200.0, "movingDuration": 1190.0, "elapsedDuration": 1210.0,
                "elevationGain": 35.0, "elevationLoss": 33.0, "averageSpeed": 3.2, "maxSpeed": 4.3,
                "averageHR": 147.0, "maxHR": 168.0, "averageRunningCadenceInStepsPerMinute": 171.0,
                "calories": 260.0, "aerobicTrainingEffect": 3.1, "anaerobicTrainingEffect": 0.8,
                "activityTrainingLoad": 64.0 + i, "vO2MaxValue": 53.0,
                "hrTimeInZone_1": 60.0, "hrTimeInZone_2": 300.0, "hrTimeInZone_3": 600.0, "hrTimeInZone_4": 200.0,
                "hrTimeInZone_5": 40.0, "startLatitude": 48.4, "startLongitude": 2.7, "lapCount": 2,
            })
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self) -> "FakeGarmin":
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()

    # ---------------------------------------------------------------- données
    def days(self, a: str, b: str) -> list[dt.date]:
        start, end = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        start = max(start, self.first)
        out = []
        while start <= min(end, self.today):
            out.append(start)
            start += DAY
        return out

    def daily_summary(self, day: dt.date) -> dict:
        n = day.toordinal() % 7
        return {
            "calendarDate": day.isoformat(),
            "movement": {"steps": {"goal": 9000, "value": 9000 + 300 * n, "distanceInMeters": 7000.0},
                         "floorsAscended": {"goal": 10, "value": 8 + n}},
            "calories": {"burnedResting": 1700, "burnedActive": 600, "burnedTotal": 2300},
            "heartRate": {"minValue": 44, "maxValue": 160, "restingValue": 48 + n % 3},
            "intensityMinutes": {"goal": 150, "moderate": 20, "vigorous": 10},
            "stress": {"avgLevel": 25 + n, "maxLevel": 90, "highStressDurationInMillis": 1_800_000,
                       "restDurationInMillis": 30_000_000},
            "bodyBattery": {"minValue": 20, "maxValue": 80 + n, "chargedValue": 60, "drainedValue": 55},
            "respiration": {"avgValue": 15},
        }

    def sleep(self, day: dt.date) -> dict:
        end_local = dt.datetime(day.year, day.month, day.day, 6, 45)
        start_local = end_local - dt.timedelta(hours=7, minutes=10)
        to_ms = lambda moment: int(moment.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)  # noqa: E731
        return {
            "calendarDate": day.isoformat(), "sleepTimeSeconds": 25800, "napTimeSeconds": 0,
            "sleepStartTimestampLocal": to_ms(start_local), "sleepEndTimestampLocal": to_ms(end_local),
            "sleepStartTimestampGMT": to_ms(start_local - dt.timedelta(hours=1)),
            "sleepEndTimestampGMT": to_ms(end_local - dt.timedelta(hours=1)),
            "deepSleepSeconds": 4800, "lightSleepSeconds": 14000, "remSleepSeconds": 6000, "awakeSleepSeconds": 1000,
            "avgHeartRate": 52.0, "avgSleepStress": 12.5, "averageRespirationValue": 14.2,
            "sleepScores": {"overall": {"value": 81, "qualifierKey": "GOOD"}},
            "sleepNeed": {"actual": 470},
        }

    def body_battery(self, day: dt.date) -> dict:
        wake_gmt = dt.datetime(day.year, day.month, day.day, 5, 45, tzinfo=dt.timezone.utc)
        values = [[int((wake_gmt + dt.timedelta(minutes=15 * k - 60)).timestamp() * 1000), 70 + k] for k in range(8)]
        return {"date": day.isoformat(), "charged": 60, "drained": 55, "bodyBatteryValuesArray": values,
                "bodyBatteryValueDescriptorDTOList": [
                    {"bodyBatteryValueDescriptorIndex": 0, "bodyBatteryValueDescriptorKey": "timestamp"},
                    {"bodyBatteryValueDescriptorIndex": 1, "bodyBatteryValueDescriptorKey": "bodyBatteryLevel"}]}

    # --------------------------------------------------------------- routage
    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def _json(self, payload, status=200):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                fake.requests.append((self.path, {}))
                if self.path.startswith("/personalapitoken-service/") and self.headers.get("Authorization", "").startswith("ApiKey "):
                    if self.headers["Authorization"] == "ApiKey mauvaise-cle":
                        return self._json({"error": "invalid key"}, 401)
                    if self.headers["Authorization"].startswith("ApiKey GCDC_refuse"):
                        # Réponse qui recopie la clé : Foulée ne doit jamais la réafficher
                        key = self.headers["Authorization"][len("ApiKey "):]
                        return self._json({"error": f"Unknown API key {key}"}, 401)
                    body = make_jwt().encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self._json({"error": "not found"}, 404)

            def do_GET(self):
                url = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                fake.requests.append((url.path, q))
                if not self.headers.get("Authorization", "").startswith("Bearer "):
                    return self._json({"error": "unauthorized"}, 401)
                p = url.path
                parts = p.strip("/").split("/")
                if p == "/usersummary-service/v2/dailysummaries":
                    return self._json({"data": [fake.daily_summary(d) for d in fake.days(q["startDate"], q["endDate"])]})
                if p == "/sleep-service/sleep/dailySleepSummariesByDate":
                    return self._json([fake.sleep(d) for d in fake.days(q["startDate"], q["endDate"])])
                if p.startswith("/hrv-service/hrv/daily/"):
                    return self._json({"hrvSummaries": [{"calendarDate": d.isoformat(), "lastNightAvg": 55 + d.day % 5,
                                                         "weeklyAvg": 56, "lastNight5MinHigh": 70, "status": "BALANCED",
                                                         "baseline": {"balancedLow": 48, "balancedUpper": 62}}
                                                        for d in fake.days(parts[-2], parts[-1])]})
                if p == "/wellness-service/wellness/bodyBattery/reports/daily":
                    return self._json([fake.body_battery(d) for d in fake.days(q["startDate"], q["endDate"])])
                if p.startswith("/weight-service/weight/range/"):
                    items = [{"summaryDate": d.isoformat(), "latestWeight": {"weight": 71500.0, "bodyFat": 14.2,
                                                                             "bmi": 22.1, "muscleMass": 33000}}
                             for d in fake.days(parts[-2], parts[-1]) if d.weekday() == 0]
                    return self._json({"dailyWeightSummaries": items})
                if p == "/biometric-service/heartRateZones/v2":
                    return self._json([{"trainingMethod": "HR_MAX", "restingHeartRateUsed": 48, "maxHeartRateUsed": 188,
                                        "zone1Floor": 94, "zone2Floor": 113, "zone3Floor": 132, "zone4Floor": 150,
                                        "zone5Floor": 169, "sport": "DEFAULT"}])
                if p.startswith("/fitnessage-service/"):
                    return self._json({"fitnessAge": 33.4, "chronologicalAge": 41})
                if p == "/userprofile-service/userprofile/settings":
                    return self._json({"measurementSystem": "metric"})
                if p == "/activitylist-service/activities/search/activities":
                    start, limit = int(q.get("start", 0)), int(q.get("limit", 20))
                    if limit > 45:
                        return self._json({"error": "page too large"}, 500)
                    lo = q.get("startDate", "1900-01-01")
                    hi = q.get("endDate", "2999-12-31")
                    items = [a for a in fake.activities if lo <= a["startTimeLocal"][:10] <= hi]
                    return self._json(items[start:start + limit])
                if p.startswith("/download-service/files/activity/"):
                    activity = next((a for a in fake.activities if str(a["activityId"]) == parts[-1]), None)
                    if not activity:
                        return self._json({"error": "not found"}, 404)
                    start = dt.datetime.strptime(activity["startTimeGMT"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
                    buffer = io.BytesIO()
                    with zipfile.ZipFile(buffer, "w") as archive:
                        archive.writestr(f"{parts[-1]}_ACTIVITY.fit", make_fit(start))
                    body = buffer.getvalue()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-zip-compressed")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return self._json({"error": f"unknown {p}"}, 404)

        return Handler
