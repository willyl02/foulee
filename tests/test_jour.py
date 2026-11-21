"""« Ma séance du jour » (0.8.2) : verdict en une phrase, créneau selon le poste et la météo, ressenti pour le coach."""

import json
from datetime import date, datetime

from fastapi.testclient import TestClient

from foulee import db, jour, views
from foulee.web import create_app

MORNING = {"debut": "05:00", "fin": "13:00", "nom": "Matin"}


def _hours(rain_until=10, dark_from=18):
    return [{"heure": h, "temp": 9, "ressentie": 7, "pluie_pct": 70 if 7 <= h <= rain_until else 5, "pluie_mm": 0,
             "vent": 10, "code": 61 if 7 <= h <= rain_until else 1, "jour": 8 <= h < dark_from} for h in range(24)]


def test_advice_in_one_sentence():
    hard = [{"blocs": [{"genre": "corps", "pct_vma": 95}]}]
    assert jour.advice("bon", hard)["niveau"] == "feu"
    assert jour.advice("moyen", hard)["texte"].startswith("Fais la séance, mais garde de la marge")
    assert jour.advice("alerte", hard)["titre"] == "Récupération incomplète : allège la séance"
    assert jour.advice("alerte", [])["titre"] == "Journée facile"
    assert jour.advice(None, [])["niveau"] is None


def test_best_slot_follows_the_shift_the_rain_and_the_daylight():
    day = date(2026, 11, 21)
    before = datetime(2026, 11, 21, 6, 0)
    # poste du matin (5 h – 13 h) : après, à 14 h (une heure pour rentrer), au sec et de jour
    slot = jour.best_slot(MORNING, _hours(), 50, now=before, day=day)
    assert slot["debut"] == "14:00" and "après ton poste (05:00–13:00)" in slot["raison"]
    assert "sans pluie annoncée" in slot["raison"]
    # repos, mais pluie le matin : l'après-midi
    assert jour.best_slot({"debut": None, "fin": None}, _hours(rain_until=12), 60, now=before, day=day)["debut"] == "13:00"
    # 1 h 30 prévue : deux heures d'affilée
    long = jour.best_slot(MORNING, _hours(), 90, now=before, day=day)
    assert (long["debut"], long["fin"]) == ("14:00", "16:00")
    # le soir même, les heures passées ne comptent plus, et la nuit se dit
    late = jour.best_slot(MORNING, _hours(), 40, now=datetime(2026, 11, 21, 18, 40), day=day)
    assert late["debut"] == "19:00" and "à la frontale" in late["raison"]
    # sans météo : le premier moment libre après le poste
    assert jour.best_slot(MORNING, None, 40, now=before, day=day)["debut"] == "14:00"
    # poste de nuit (21 h – 5 h) : pas de créneau de 20 h à 6 h
    night = jour.best_slot({"debut": "21:00", "fin": "05:00"}, _hours(), 40, now=before, day=day)
    assert 6 <= int(night["debut"][:2]) < 20


def test_weather_is_rounded_cached_and_survives_offline(monkeypatch):
    calls = []

    def forecast(lat, lon):
        calls.append((lat, lon))
        times = [f"2026-11-21T{h:02d}:00" for h in range(24)]
        return {"hourly": {"time": times, "temperature_2m": [9] * 24, "apparent_temperature": [7] * 24,
                           "precipitation_probability": [10] * 24, "precipitation": [0] * 24,
                           "wind_speed_10m": [8] * 24, "weather_code": [1] * 24, "is_day": [1] * 24}}

    monkeypatch.setattr(jour, "_forecast", forecast)
    monkeypatch.setattr(jour, "_place", lambda conn: (49.0, 3.4))
    with db.session() as conn:
        first = jour.weather(conn, date(2026, 11, 21))
        again = jour.weather(conn, date(2026, 11, 21))
    assert len(first["heures"]) == 24 and first == again and calls == [(49.0, 3.4)]  # une heure de cache
    with db.session() as conn:
        db.set_meta(conn, jour.CACHE_KEY, json.dumps({**json.loads(db.get_meta(conn, jour.CACHE_KEY)), "le": "2020-01-01T00:00:00"}))

    def offline(lat, lon):
        raise jour.requests.ConnectionError("hors ligne")

    monkeypatch.setattr(jour, "_forecast", offline)
    with db.session() as conn:
        assert jour.weather(conn, date(2026, 11, 21))["heures"][0]["temp"] == 9  # la dernière lue
    monkeypatch.setattr(jour, "_place", lambda conn: None)
    with db.session() as conn:
        assert jour.weather(conn, date(2026, 11, 21)) is None


def test_day_page_feel_and_coach_text():
    client = TestClient(create_app())
    headers = {"X-Foulee": "1"}
    page = client.get("/api/jour").json()
    assert page["prevues"] == [] and page["faites"] == [] and page["conseil"]["titre"]
    with db.session() as conn:
        conn.execute("INSERT INTO activities(id, source, source_id, date, start_local, sport, name, duration_s, moving_s, "
                     "distance_m, avg_speed, avg_hr) VALUES ('garmin:1', 'garmin', '1', ?, ?, 'course', 'Seuil 3 × 10', "
                     "3420, 3400, 12400, 3.65, 158)", (date.today().isoformat(), f"{date.today().isoformat()} 18:00:00"))
    page = client.get("/api/jour").json()
    (done,) = page["faites"]
    assert done["allure"] == "4:34 /km" and done["fc_moy"] == 158 and done["heure"] == "18:00"
    bad = client.put("/api/jour/ressenti/garmin:1", headers=headers, json={"rpe": 12})
    assert bad.status_code == 400
    ok = client.put("/api/jour/ressenti/garmin:1", headers=headers, json={"rpe": 7, "note": "  jambes   lourdes "})
    assert ok.json()["ressenti"] == {"rpe": 7, "note": "jambes lourdes", "envoye_le": None}
    assert client.get("/api/jour").json()["faites"][0]["ressenti"]["rpe"] == 7
    with db.session() as conn:
        text = jour.coach_text(conn, "garmin:1")
    assert text.splitlines() == [f"Séance du {date.today():%d/%m} : Seuil 3 × 10 (12,4 km, 56 min)", "Ressenti : 7/10",
                                 "jambes lourdes"]
    # sans relais : le mot au coach attend qu'on se relie
    assert client.post("/api/jour/ressenti/garmin:1/coach", headers=headers).status_code == 409
    assert client.put("/api/jour/ressenti/inconnue", headers=headers, json={"rpe": 3}).status_code == 400


def test_old_today_view_becomes_the_day_page():
    with db.session() as conn:
        old = {"tuiles": [{"id": f"t{i}", "type": t, "w": 3, "h": 1, "params": {}} for i, t in enumerate(views.OLD_TODAY_TYPES)]}
        conn.execute("UPDATE views SET spec = ? WHERE id = 'aujourdhui'", (json.dumps(old),))
        conn.execute("DELETE FROM meta WHERE key = 'vue_seance_jour'")
        views.ensure_default_views(conn)
        spec = json.loads(conn.execute("SELECT spec FROM views WHERE id = 'aujourdhui'").fetchone()["spec"])
    assert [t["type"] for t in spec["tuiles"]] == ["jour"]
    with db.session() as conn:  # une vue arrangée à sa façon n'est pas touchée
        mine = {"tuiles": [{"id": "x", "type": "kpi", "w": 3, "h": 1, "params": {}}]}
        conn.execute("UPDATE views SET spec = ? WHERE id = 'aujourdhui'", (json.dumps(mine),))
        conn.execute("DELETE FROM meta WHERE key = 'vue_seance_jour'")
        views.ensure_default_views(conn)
        assert json.loads(conn.execute("SELECT spec FROM views WHERE id = 'aujourdhui'").fetchone()["spec"]) == mine
