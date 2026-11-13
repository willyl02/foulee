"""Toutes les données de Garmin : nouvelles valeurs, données brutes comme métriques, journée en détail, migration."""

import datetime as dt
import json
import sqlite3

import pytest
from fake_garmin import FakeGarmin
from fastapi.testclient import TestClient

from foulee import analysis, config, db, metrics, sync, vault, views, web
from foulee.garmin import intraday, parse

WRITE = {"X-Foulee": "1"}


@pytest.fixture
def filled(monkeypatch):
    with FakeGarmin(days=20, activities=4) as fake:
        monkeypatch.setenv("GARMIN_PERSONAL_API_BASE_URL", fake.url)
        vault.set_key("cle-de-test")
        assert sync.run(since=fake.today - dt.timedelta(days=15))["statut"] == "ok"
        yield fake


def test_new_daily_values_are_read():
    item = {"calendarDate": "2026-11-10", "pulseOx": {"avgValue": 98, "minValue": 86},
            "respiration": {"avgValue": 18, "minValue": 6, "maxValue": 48},
            "movement": {"steps": {"value": 15145, "goal": 10000, "distanceInMeters": 14865.0},
                         "floorsDescended": {"value": 13}},
            "bodyBattery": {"latestValue": 41, "activityEvents": [
                {"eventType": "SLEEP", "bodyBatteryImpact": 59}, {"eventType": "ACTIVITY", "bodyBatteryImpact": -15},
                {"eventType": "ACTIVITY", "bodyBatteryImpact": -7}]},
            "stress": {"activityDurationInMillis": 8520000}, "hydration": {"goalInMl": 3651}}
    _, values = parse.parse_daily_summary(item)
    assert values["spo2_avg"] == 98 and values["spo2_min"] == 86 and values["resp_max"] == 48
    assert values["steps_goal"] == 10000 and values["steps_km"] == 14.87 and values["floors_down"] == 13
    assert values["bb_sleep_gain"] == 59 and values["bb_activity_cost"] == 22 and values["bb_last"] == 41
    assert values["stress_activity_s"] == 8520 and values["hydration_goal_ml"] == 3651
    _, sleep = parse.parse_sleep({"calendarDate": "2026-11-09", "sleepTimeSeconds": 24900, "averageSpO2Value": 99.0,
                                  "lowestSpO2Value": 87, "awakeCount": 1, "sleepScores": {"deepPercentage": {"value": 12}},
                                  "sleepAlignment": {"lastSleepMidpointMins": 237}, "sleepNeed": {"baseline": 420}})
    assert sleep["sleep_spo2_min"] == 87 and sleep["sleep_awake_count"] == 1 and sleep["sleep_deep_pct"] == 12
    assert sleep["sleep_mid_h"] == pytest.approx(3.95) and sleep["sleep_need_base_min"] == 420
    for key in list(values) + list(sleep):
        assert key in metrics.CATALOG or key in ("cal_resting",), key


def test_activity_extras_and_measures(filled):
    with db.session(readonly=True) as conn:
        row = conn.execute("SELECT * FROM activities ORDER BY date DESC LIMIT 1").fetchone()
        extra = json.loads(row["extra"])
        assert extra["gct"] == 241.1 and extra["vr"] == 6.86 and extra["best_1000"] == 270.0
        assert extra["te_label"] == "LACTATE_THRESHOLD" and extra["lieu"] == "Nogentel"
        detail = analysis.activity_detail(conn, row["id"], db.get_settings(conn))
        shown = {m["cle"]: m["affiche"] for m in detail["mesures"]}
        assert shown["gct"] == "241 ms" and shown["stride"] == "1,08 m" and shown["te_label"] == "Seuil (aérobie élevée)"
        assert shown["gcb"] == "50,4 % / 49,6 %" and shown["best_1000"] == "4:30"
        week = analysis.series(conn, "act.gct", filled.today - dt.timedelta(days=15), filled.today, "semaine")
        assert any(v for _, v in week["points"])
        records = analysis.records(conn, None, None)["records"]
        assert [r["nom"] for r in records] == ["1 km", "1 mile"] and records[0]["record"]["temps"] == "4:27"
        assert json.loads(row["hr_zones_garmin"]) == [60.0, 300.0, 600.0, 200.0, 40.0]


def test_profile_threshold_from_garmin(filled):
    with db.session(readonly=True) as conn:
        garmin = analysis.garmin_profile(conn)
        assert garmin["zones_fc"]["lthr"] == 172
        assert garmin["profil"]["seuil_fc"] == 171 and garmin["profil"]["seuil_vitesse"] == pytest.approx(3.846)
        settings = {**db.get_settings(conn), "zones_allure": {"methode": "pct_seuil"}}
        assert analysis.pace_profile(settings, garmin["profil"])["seuil_vitesse"] == pytest.approx(3.846)


def test_raw_values_work_as_metrics(filled):
    client = TestClient(web.create_app())
    fields = client.get("/api/garmin/champs").json()["champs"]
    keys = {f["key"] for f in fields}
    assert "garmin:activity:avgVerticalRatio" in keys and "garmin:activity:fastestSplit_1000" in keys
    assert not any(k.endswith("activityId") or "Timestamp" in k for k in keys)
    series = client.get("/api/series", params={"metric": "garmin:activity:avgGroundContactTime", "agg": "semaine",
                                               "start": (filled.today - dt.timedelta(days=15)).isoformat()}).json()
    assert series["fmt"] == "num" and any(v for _, v in series["points"])
    assert client.get("/api/series", params={"metric": "garmin:nimporte:quoi"}).status_code == 400
    # Une tuile peut s'en servir : la clé passe la validation des vues, et l'interface reçoit son libellé
    view = client.post("/api/views", json={"name": "Brut", "spec": {"tuiles": [
        {"type": "serie", "params": {"metriques": ["garmin:activity:avgGroundContactTime", "pas:une:cle"]}}]}},
        headers=WRITE).json()
    assert view["spec"]["tuiles"][0]["params"]["metriques"] == ["garmin:activity:avgGroundContactTime"]
    boot = client.get("/api/bootstrap").json()
    assert any(m["key"] == "garmin:activity:avgGroundContactTime" and m["kind"] == "raw" for m in boot["metriques"])


def test_day_detail_is_fetched_once_then_kept(filled, monkeypatch):
    yesterday = filled.today - dt.timedelta(days=1)
    with db.session() as conn:
        sleep = intraday.day_detail(conn, "sommeil", yesterday)
        assert not sleep["vide"] and sleep["debut"].endswith("T23:00:00")
        spent = {}
        for phase in sleep["phases"]:
            start = dt.datetime.fromisoformat(phase["debut"])
            end = dt.datetime.fromisoformat(phase["fin"])
            spent[phase["phase"]] = spent.get(phase["phase"], 0) + (end - start).total_seconds()
        assert spent == {"léger": 18000, "profond": 3600, "paradoxal": 6600, "éveil": 600}
        hr = intraday.day_detail(conn, "fc", yesterday)
        assert len(hr["points"]) == 720 and hr["points"][0][0].endswith("T00:00:00") and hr["repos"] == 47
        hrv = intraday.day_detail(conn, "vfc", yesterday)
        assert len(hrv["points"]) == 84 and hrv["resume"]["hrv_night"] == 61
        battery = intraday.day_detail(conn, "body_battery", yesterday)
        assert battery["points"] and not battery["vide"]
        calls = list(filled.intraday_calls)
        intraday.day_detail(conn, "sommeil", yesterday)  # un jour passé ne change plus : pas de nouvel appel
        assert filled.intraday_calls == calls
        # Aujourd'hui : redemandé au bout de 15 minutes
        intraday.day_detail(conn, "fc", filled.today)
        conn.execute("UPDATE raw SET fetched_at = '2000-01-01 00:00:00' WHERE kind = 'hr_day'")
        intraday.day_detail(conn, "fc", filled.today)
        assert filled.intraday_calls.count(("fc", filled.today.isoformat())) == 2
        # Garmin injoignable : on garde ce qu'on a
        filled.fail_status = 503
        from foulee.garmin import client as garmin_client

        monkeypatch.setattr(garmin_client.time, "sleep", lambda s: None)
        conn.execute("UPDATE raw SET fetched_at = '2000-01-01 00:00:00' WHERE kind = 'hr_day'")
        kept = intraday.day_detail(conn, "fc", filled.today)
        assert not kept["vide"] and "dernière synchro" in kept["message"]
    client = TestClient(web.create_app())
    assert client.get("/api/journee", params={"donnee": "inconnue"}).status_code == 400


def test_day_detail_without_key():
    with db.session() as conn:
        empty = intraday.day_detail(conn, "fc", dt.date.today())
    assert empty["vide"] and "clé API" in empty["message"]


def test_database_from_0_4_is_upgraded():
    path = config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    old_schema = db.SCHEMA.replace(
        "    hr_zones_garmin TEXT,               -- JSON : secondes en zones FC 1..5 comptées par Garmin\n", "").replace(
        "    extra        TEXT,                  -- JSON : autres valeurs Garmin (dynamique de course, puissance…)\n", "")
    assert "extra" not in old_schema.split("CREATE TABLE IF NOT EXISTS activities")[1].split(");")[0]
    conn.executescript(old_schema)
    conn.execute("INSERT INTO meta VALUES ('schema_version', '1')")
    payload = {"activityId": 7, "startTimeLocal": "2026-11-10 08:52:49", "activityType": {"typeKey": "running"},
               "avgGroundContactTime": 241.1, "fastestSplit_5000": 1290.0, "hrTimeInZone_2": 100.0}
    conn.execute("INSERT INTO raw VALUES ('garmin', 'activity', '7', '2026-11-10 09:00:00', ?)", (json.dumps(payload),))
    conn.execute("INSERT INTO activities(id, source, source_id, start_local, date, sport, hr_zones) VALUES "
                 "('garmin:7', 'garmin', '7', '2026-11-10 08:52:49', '2026-11-10', 'course', '[0, 100, 0, 0, 0]')")
    conn.execute("INSERT INTO raw VALUES ('garmin', 'daily', '2026-11-10', '2026-11-10 09:00:00', ?)",
                 (json.dumps({"calendarDate": "2026-11-10", "pulseOx": {"avgValue": 97}}),))
    conn.execute("INSERT INTO views(id, name, icon, position, spec, builtin) VALUES ('perso', 'Perso', 'star', 0, "
                 "'{\"tuiles\": []}', 0)")
    conn.commit()
    conn.close()
    with db.session() as conn:
        assert db.get_meta(conn, "schema_version") == str(db.SCHEMA_VERSION)
        row = conn.execute("SELECT extra, hr_zones_garmin FROM activities").fetchone()
        assert json.loads(row["extra"]) == {"gct": 241.1, "best_5000": 1290.0}
        assert json.loads(row["hr_zones_garmin"])[1] == 100.0
        assert conn.execute("SELECT value FROM daily WHERE metric = 'spo2_avg'").fetchone()["value"] == 97
        assert [v["id"] for v in views.list_views(conn)] == ["accueil", "perso"]
