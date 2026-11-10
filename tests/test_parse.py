"""Traduction des réponses Garmin (structures conformes à l'API, valeurs inventées)."""

from datetime import datetime, timezone

from foulee.garmin import parse


def ms(moment: datetime) -> int:
    return int(moment.replace(tzinfo=timezone.utc).timestamp() * 1000)


def test_daily_summary():
    item = {
        "calendarDate": "2026-10-20",
        "movement": {"steps": {"value": 12345}, "floorsAscended": {"value": 9}},
        "calories": {"burnedTotal": 2400, "burnedActive": 700},
        "heartRate": {"restingValue": 47, "minValue": 43, "maxValue": 171},
        "intensityMinutes": {"moderate": 20, "vigorous": 15},
        "stress": {"avgLevel": 28, "maxLevel": -1, "highStressDurationInMillis": 3_600_000},
        "bodyBattery": {"minValue": 15, "maxValue": 88, "chargedValue": 70, "drainedValue": 65},
    }
    date, values = parse.parse_daily_summary(item)
    assert date == "2026-10-20"
    assert values["steps"] == 12345
    assert values["resting_hr"] == 47
    assert values["int_minutes"] == 50  # 20 + 2 × 15
    assert values["stress_high_s"] == 3600
    assert values["stress_max"] is None  # -1 = pas de donnée
    assert values["bb_max"] == 88


def test_sleep_local_millis_and_bedtime_after_midnight():
    item = {
        "calendarDate": "2026-10-21",
        "sleepTimeSeconds": 22000,
        "sleepStartTimestampLocal": ms(datetime(2026, 10, 21, 0, 30)),
        "sleepEndTimestampLocal": ms(datetime(2026, 10, 21, 7, 15)),
        "deepSleepSeconds": 4000, "remSleepSeconds": 5000, "lightSleepSeconds": 12000, "awakeSleepSeconds": 1000,
        "sleepScores": {"overall": {"value": 77}},
        "avgHeartRate": 51.2,
    }
    _, values = parse.parse_sleep(item)
    assert values["sleep_s"] == 22000
    assert values["sleep_start_h"] == 24.5  # 00 h 30 → 24,5 pour rester continu
    assert values["sleep_end_h"] == 7.25
    assert values["sleep_score"] == 77


def test_sleep_without_night_only_keeps_nap():
    _, values = parse.parse_sleep({"calendarDate": "2026-10-22", "sleepTimeSeconds": 0, "napTimeSeconds": 1200})
    assert values == {"nap_s": 1200}


def test_hrv_and_status_code():
    items = parse.hrv_items({"hrvSummaries": [{"calendarDate": "2026-10-20", "lastNightAvg": 58, "weeklyAvg": 55,
                                               "status": "UNBALANCED", "baseline": {"balancedLow": 50, "balancedUpper": 63}}]})
    date, values = parse.parse_hrv(items[0])
    assert date == "2026-10-20"
    assert values["hrv_night"] == 58 and values["hrv_status"] == 2 and values["hrv_bl_high"] == 63


def test_wake_body_battery_uses_gmt_sleep_end():
    end_gmt = datetime(2026, 10, 21, 5, 0)
    bb = {"bodyBatteryValuesArray": [[ms(datetime(2026, 10, 21, 4, 40)), 70], [ms(datetime(2026, 10, 21, 5, 3)), 74],
                                     [ms(datetime(2026, 10, 21, 7, 0)), 60]],
          "bodyBatteryValueDescriptorDTOList": [
              {"bodyBatteryValueDescriptorIndex": 0, "bodyBatteryValueDescriptorKey": "timestamp"},
              {"bodyBatteryValueDescriptorIndex": 1, "bodyBatteryValueDescriptorKey": "bodyBatteryLevel"}]}
    assert parse.wake_body_battery(bb, {"sleepEndTimestampGMT": ms(end_gmt)}) == 74


def test_weight_in_grams():
    _, values = parse.parse_weight({"summaryDate": "2026-10-20", "latestWeight": {"weight": 71234.0, "bodyFat": 14.1,
                                                                                  "muscleMass": 33500}})
    assert values["weight_kg"] == 71.23 and values["muscle_kg"] == 33.5


def test_activity_summary_and_sports():
    row = parse.parse_activity({
        "activityId": 123, "activityName": "Sortie longue", "description": "Jambes lourdes au 15e km",
        "startTimeLocal": "2026-10-19 09:12:00", "startTimeGMT": "2026-10-19 07:12:00",
        "activityType": {"typeKey": "trail_running"}, "distance": 18000.0, "duration": 6000.0,
        "averageSpeed": 3.0, "averageHR": 140.0, "activityTrainingLoad": 150.0, "vO2MaxValue": 54.0,
        "hrTimeInZone_1": 100.0, "hrTimeInZone_2": 3000.0,
    })
    assert row["id"] == "garmin:123" and row["date"] == "2026-10-19" and row["sport"] == "trail"
    assert row["description"] == "Jambes lourdes au 15e km"
    assert row["garmin_load"] == 150.0
    assert parse.normalize_sport("treadmill_running") == "course"
    assert parse.normalize_sport("road_biking") == "velo"
    assert parse.normalize_sport("strength_training") == "renfo"
    assert parse.normalize_sport("quelque_chose") == "autre"


def test_heart_rate_zones():
    zones = parse.heart_rate_zones([{"sport": "DEFAULT", "maxHeartRateUsed": 188, "restingHeartRateUsed": 47,
                                     "zone1Floor": 94, "zone2Floor": 113, "zone3Floor": 132, "zone4Floor": 150,
                                     "zone5Floor": 169}])
    assert zones["max"] == 188 and zones["floors"][4] == 169
