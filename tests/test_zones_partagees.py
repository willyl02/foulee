"""0.8.3 : l'élève peut partager les réglages de ses zones cardio Garmin ; le coach les voit sur sa fiche."""

from foulee import coach, db, demo
from foulee.garmin import parse
from foulee.relais import club
from test_relais_club import PASSWORD, relay, token  # noqa: F401

GARMIN = [{"trainingMethod": "LACTATE_THRESHOLD", "restingHeartRateUsed": 46, "lactateThresholdHeartRateUsed": 169,
           "zone1Floor": 110, "zone2Floor": 144, "zone3Floor": 152, "zone4Floor": 161, "zone5Floor": 169,
           "maxHeartRateUsed": 187, "restingHrAutoUpdateUsed": True, "sport": "DEFAULT"},
          {"trainingMethod": "LACTATE_THRESHOLD", "restingHeartRateUsed": 46, "lactateThresholdHeartRateUsed": 169,
           "zone1Floor": 110, "zone2Floor": 144, "zone3Floor": 152, "zone4Floor": 161, "zone5Floor": 169,
           "maxHeartRateUsed": 187, "restingHrAutoUpdateUsed": True, "sport": "RUNNING"}]


def test_garmin_zone_settings_are_read_profile_by_profile():
    zones = parse.heart_rate_zone_profiles(GARMIN)
    assert zones[1] == {"sport": "RUNNING", "methode": "LACTATE_THRESHOLD", "fc_max": 187, "fc_repos": 46,
                        "fc_seuil": 169, "repos_auto": True, "bornes": [110, 144, 152, 161, 169]}
    assert parse.heart_rate_zone_profiles([{"sport": "DEFAULT", "zone1Floor": 100}]) == []
    cleaned = club.clean_zones([*zones, {"sport": "x", "bornes": [150, 140, 1, 2, 3]}, "rien", {"bornes": [100] * 4}])
    assert [z["sport"] for z in cleaned] == ["DEFAULT", "RUNNING"] and cleaned[0]["methode"] == "LACTATE_THRESHOLD"


def test_zones_reach_the_coach_only_when_shared(relay):
    sophie = token(relay, "sophie")
    code = relay.post("/api/v1/invitations", headers=sophie).json()["invitation"]["code"]
    demo.build(days=20, second_profile=False)
    with db.session() as conn:
        db.put_raw(conn, "garmin", "hr_zones", "latest", GARMIN)
        coach.join(conn, "https://relais.test", code=code, ident="demo.eleve", name="Élève démo", password=PASSWORD)
        coach.set_accord(conn, {"seances": True, "objectif": True})  # zones : non cochées
    sid = relay.get("/api/v1/groupe", headers=sophie).json()["eleves"][0]["id"]
    fiche = relay.get(f"/api/v1/eleves/{sid}/fiche", headers=sophie).json()
    assert fiche["zones_fc"] == [] and fiche["accord"]["zones"] is False
    with db.session() as conn:
        coach.set_accord(conn, {"seances": True, "objectif": True, "zones": True})
    fiche = relay.get(f"/api/v1/eleves/{sid}/fiche", headers=sophie).json()
    assert fiche["accord"]["zones"] is True
    assert [z["sport"] for z in fiche["zones_fc"]] == ["DEFAULT", "RUNNING"]
    assert fiche["zones_fc"][1]["bornes"] == [110, 144, 152, 161, 169] and fiche["zones_fc"][1]["fc_seuil"] == 169
    with db.session() as conn:  # décoché : effacé tout de suite chez le coach
        coach.set_accord(conn, {"seances": True, "objectif": True, "zones": False})
    assert relay.get(f"/api/v1/eleves/{sid}/fiche", headers=sophie).json()["zones_fc"] == []


def test_the_watch_profile_chosen_drives_zones_max_and_rest():
    from fastapi.testclient import TestClient

    from foulee import analysis
    from foulee.web import create_app

    trail = {**GARMIN[1], "sport": "TRAIL_RUNNING", "trainingMethod": "HR_MAX_BASED", "maxHeartRateUsed": 192,
             "restingHeartRateUsed": 44, "zone1Floor": 96, "zone2Floor": 115, "zone3Floor": 134, "zone4Floor": 154,
             "zone5Floor": 173}
    with db.session() as conn:
        db.put_raw(conn, "garmin", "hr_zones", "latest", [*GARMIN, trail])
        db.set_setting(conn, "fc_max", 200)  # réglée dans Foulée : la montre l'emporte quand on suit la montre
        db.set_setting(conn, "zones_fc", {"methode": "garmin", "profil_garmin": "TRAIL_RUNNING"})
        hrp = analysis.hr_profile(conn, db.get_settings(conn))
        assert hrp["floors"] == [96, 115, 134, 154, 173] and hrp["max"] == 192 and hrp["rest"] == 44
        assert hrp["source_max"] == "montre"
        db.set_setting(conn, "zones_fc", {"methode": "pct_max"})  # réglées dans Foulée : sa FC max à elle
        assert analysis.hr_profile(conn, db.get_settings(conn))["max"] == 200
    http = TestClient(create_app())
    saved = http.put("/api/settings", headers={"X-Foulee": "1"},
                     json={"zones_fc": {"methode": "garmin", "profil_garmin": "running"}})
    assert saved.status_code == 200 and saved.json()["reglages"]["zones_fc"]["profil_garmin"] == "RUNNING"
    data = http.get("/api/zones/montre").json()
    assert [p["sport"] for p in data["profils"]] == ["DEFAULT", "RUNNING", "TRAIL_RUNNING"]
    assert data["foulee"]["methode"] == "garmin" and data["foulee"]["profil_garmin"] == "RUNNING"
    assert data["foulee"]["planchers"] == [110, 144, 152, 161, 169] and data["partage"]["zones"] is False
