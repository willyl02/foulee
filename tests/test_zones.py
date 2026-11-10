"""Zones FC (Garmin, % FC max, % FC de réserve, % du seuil, bornes à la main) et zones d'allure."""

import json

import pytest
from fastapi.testclient import TestClient

from foulee import analysis, db, web, zones

WRITE = {"X-Foulee": "1"}
GARMIN = {"floors": [94.0, 113.0, 132.0, 150.0, 169.0], "max": 188.0, "rest": 48.0, "method": "HR_MAX", "lthr": 172.0}


@pytest.mark.parametrize("config, expected_method, expected", [
    (None, "garmin", [94, 113, 132, 150, 169]),
    ({"methode": "pct_max"}, "pct_max", [93, 112, 130, 149, 167]),                       # 186 × 50 … 90 %
    ({"methode": "pct_max", "pct": [55, 65, 75, 82, 89]}, "pct_max", [102, 121, 140, 153, 166]),
    ({"methode": "pct_reserve"}, "pct_reserve", [116, 130, 144, 158, 172]),               # 46 + % × 140
    ({"methode": "pct_seuil"}, "pct_seuil", [120, 146, 155, 163, 172]),                   # % × 172 (Garmin)
    ({"methode": "pct_seuil", "seuil": 168}, "pct_seuil", [118, 143, 151, 160, 168]),
    ({"methode": "bornes", "bornes": [143, 151, 159, 168]}, "bornes", [0, 143, 151, 159, 168]),  # comme Strava
])
def test_hr_methods(config, expected_method, expected):
    result = zones.hr_floors(config, 186, 46, GARMIN)
    assert result["methode"] == expected_method
    assert result["floors"] == [float(v) for v in expected]


def test_hr_fallbacks():
    # Pas de zones Garmin, ou FC max imposée : % de la FC max, comme avant la 0.5
    assert zones.hr_floors(None, 190, 50, None)["methode"] == "pct_max"
    assert zones.hr_floors(None, 190, 50, GARMIN, max_from_settings=True)["methode"] == "pct_max"
    # % du seuil sans seuil connu : % de la FC max
    assert zones.hr_floors({"methode": "pct_seuil"}, 190, 50, {"floors": GARMIN["floors"]})["methode"] == "pct_max"
    assert zones.hr_bounds_text([0, 143, 151, 159, 168])[0] == "< 143 bpm"


@pytest.mark.parametrize("data, message", [
    ({"methode": "pct_max", "pct": [50, 60, 70, 80]}, "5 valeurs"),
    ({"methode": "pct_max", "pct": [50, 70, 60, 80, 90]}, "dépasser la précédente"),
    ({"methode": "bornes", "bornes": [143, 151, 159, 300]}, "valeurs possibles"),
    ({"methode": "magie"}, "inconnue"),
])
def test_hr_settings_are_checked(data, message):
    with pytest.raises(zones.ZoneError, match=message):
        zones.clean_hr(data)


def test_pace_methods():
    vma = zones.pace_bounds(None, 16.0, [70, 80, 88, 95])
    assert vma["methode"] == "pct_vma" and vma["vitesses"][0] == pytest.approx(16 * 0.7 / 3.6)
    threshold = zones.pace_bounds({"methode": "pct_seuil", "seuil": 245}, 16.0)
    assert threshold["vitesses"][-1] == pytest.approx(1000 / 245 * 1.02)
    garmin = zones.pace_bounds({"methode": "pct_seuil"}, 16.0, garmin_threshold_speed=3.846)
    assert garmin["seuil_vitesse"] == pytest.approx(3.846)
    manual = zones.clean_pace({"methode": "bornes", "bornes": ["6:00", "5:15", "4:30", "4:00"]})
    assert manual["bornes"] == [360, 315, 270, 240]
    assert zones.pace_bounds(manual, 16.0)["vitesses"] == pytest.approx([1000 / 360, 1000 / 315, 1000 / 270, 1000 / 240])
    with pytest.raises(zones.ZoneError, match="plus lente"):
        zones.clean_pace({"methode": "bornes", "bornes": ["4:00", "4:30", "5:15", "6:00"]})


def _activity(conn, garmin_zones):
    streams = {"t": list(range(0, 600)), "hr": [120] * 200 + [145] * 200 + [175] * 200, "spd": [3.0] * 600}
    from foulee import fitfile

    conn.execute("INSERT INTO activities(id, source, source_id, start_local, date, sport, duration_s, avg_hr, "
                 "hr_zones_garmin, has_streams) VALUES ('garmin:1', 'garmin', '1', '2026-11-10 08:00:00', "
                 "'2026-11-10', 'course', 600, 147, ?, 1)", (json.dumps(garmin_zones),))
    conn.execute("INSERT INTO streams(activity_id, payload) VALUES ('garmin:1', ?)", (fitfile.pack_streams(streams),))
    conn.commit()


def test_activity_zones_follow_the_chosen_method():
    with db.session() as conn:
        db.set_meta(conn, "garmin_hr_zones", json.dumps(GARMIN))
        _activity(conn, [10, 20, 30, 40, 50])
        settings = db.get_settings(conn)
        analysis.refresh_all_activities(conn, settings)
        row = conn.execute("SELECT hr_zones FROM activities").fetchone()
        assert json.loads(row["hr_zones"]) == [10, 20, 30, 40, 50]  # zones Garmin : le décompte de la montre

        db.set_setting(conn, "zones_fc", {"methode": "bornes", "bornes": [140, 150, 160, 170]})
        settings = db.get_settings(conn)
        analysis.refresh_all_activities(conn, settings)
        recomputed = json.loads(conn.execute("SELECT hr_zones FROM activities").fetchone()["hr_zones"])
        assert recomputed == [199, 200, 0, 0, 200]  # recompté sur la courbe : 120 bpm en Z1, 145 en Z2, 175 en Z5
        profile = analysis.hr_profile(conn, settings)
        assert profile["methode"] == "bornes" and profile["bornes"][0] == "< 140 bpm"
        zones_tile = analysis.zones(conn, "fc", analysis.to_date("2026-11-01"), analysis.to_date("2026-11-30"),
                                    "total", None, settings)
        assert zones_tile["methode"] == "bornes" and zones_tile["series"][0]["secondes"] == recomputed


def test_settings_api_checks_zones():
    client = TestClient(web.create_app())
    bad = client.put("/api/settings", json={"zones_fc": {"methode": "pct_max", "pct": [50, 60]}}, headers=WRITE)
    assert bad.status_code == 400 and "5 valeurs" in bad.json()["detail"]
    ok = client.put("/api/settings", json={"zones_fc": {"methode": "pct_reserve"},
                                           "zones_allure": {"methode": "bornes", "bornes": ["6:00", "5:10", "4:30", "4:00"]}},
                    headers=WRITE).json()
    assert ok["recalcul"] and ok["profil_fc"]["methode"] == "pct_reserve"
    assert ok["profil_fc"]["allure"]["methode"] == "bornes"
    assert ok["profil_fc"]["allure"]["bornes"][0] == "plus lent que 6:00 /km"
