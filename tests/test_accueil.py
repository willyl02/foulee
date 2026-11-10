"""Page d'accueil : tableau d'allures du club, test VAMEVAL, forme du jour, semaine, records, vue ajoutée."""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from foulee import analysis, db, views, web

WRITE = {"X-Foulee": "1"}


def test_paces_match_the_club_workbook():
    """Mêmes chiffres que le classeur « Allures d'entraînement selon la VMA » (secondes tronquées)."""
    table = analysis.paces_table({"vma_kmh": 15}, test="12:40")
    rows = {r["libelle"]: r for r in table["lignes"]}
    assert table["pct"] == [55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120]
    assert rows["Ma VMA"]["allures"] == ["07:16", "06:40", "06:09", "05:42", "05:20", "05:00", "04:42", "04:26",
                                         "04:12", "04:00", "03:48", "03:38", "03:28", "03:20"]
    assert rows["VMA du test (interpolée)"]["allures"] == ["08:10", "07:30", "06:55", "06:25", "06:00", "05:37", "05:17",
                                                           "05:00", "04:44", "04:30", "04:17", "04:05", "03:54", "03:45"]
    assert rows["Palier validé"]["allures"][:4] == ["08:23", "07:41", "07:06", "06:35"]
    assert rows["VMA du test (interpolée)"]["vitesses"][0] == 7.33
    track = {r["m"]: r["temps"] for r in table["piste"]["distances"]}
    assert track[200] == ["00:56", "00:53", "00:50", "00:48", "00:45", "00:43", "00:41", "00:40"]
    assert track[800] == ["03:45", "03:33", "03:22", "03:12", "03:02", "02:54", "02:46", "02:40"]
    # Une seconde VMA à comparer : une ligne de plus, et la piste se cale dessus
    other = analysis.paces_table({"vma_kmh": 15}, compare=13.0)
    assert other["lignes"][-1]["libelle"] == "Autre VMA" and other["piste"]["vma"] == 13.0


@pytest.mark.parametrize("time, palier, courue, validee, interpolee", [
    ("12:40", 11, 13.8, 13.0, 13.33),
    ("2:00", 1, 8.5, 8.0, 8.0),
    ("15:30", 14, 15.2, 14.5, 14.75),
])
def test_vameval_reading(time, palier, courue, validee, interpolee):
    test = analysis.vameval(time)
    assert (test["palier"], test["vitesse_courue"], test["vma_palier"], test["vma_interpolee"]) == \
        (palier, courue, validee, interpolee)


def test_vameval_refuses_nonsense():
    assert analysis.vameval("1:30") is None and analysis.vameval("abc") is None
    client = TestClient(web.create_app())
    assert client.get("/api/allures", params={"test": "n'importe"}).status_code == 400
    assert client.put("/api/settings", json={"vameval": "0:45"}, headers=WRITE).status_code == 400
    saved = client.put("/api/settings", json={"vameval": "12:40"}, headers=WRITE).json()["reglages"]
    assert saved["vameval"] == "12:40"
    assert len(client.get("/api/allures").json()["lignes"]) == 3  # le test gardé s'affiche sur l'accueil


def _day(conn, day, **values):
    db.put_daily(conn, day.isoformat(), values)


def test_day_form_reads_each_signal_against_habits():
    today = date.today()
    with db.session() as conn:
        for i in range(1, 31):
            _day(conn, today - timedelta(days=i), resting_hr=46, hrv_night=60)
        _day(conn, today, resting_hr=53, hrv_night=48, hrv_bl_low=55, hrv_bl_high=68, sleep_s=5 * 3600,
             sleep_need_min=480, sleep_score=58, bb_wake=35)
        conn.commit()
        form = analysis.day_form(conn, today, db.get_settings(conn))
    states = {s["metric"]: s["etat"] for s in form["signaux"]}
    assert states == {"resting_hr": "alerte", "hrv_night": "alerte", "sleep_s": "alerte", "sleep_score": "alerte",
                      "bb_wake": "alerte"}
    assert form["verdict"] == "alerte" and "journée facile" in form["resume"]
    assert "pas un avis médical" in form["note"]


def test_day_form_without_data():
    with db.session(readonly=True) as conn:
        form = analysis.day_form(conn, None, db.get_settings(conn))
    assert form["verdict"] is None and form["signaux"] == []


def _activity(conn, ident, day, km, extra=None, sport="course", load=50.0):
    conn.execute("INSERT INTO activities(id, source, source_id, start_local, date, sport, name, distance_m, duration_s, "
                 "load, extra) VALUES (?, 'garmin', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (ident, ident, f"{day} 08:00:00", day, sport, f"Sortie {ident}", km * 1000, km * 300, load,
                  json.dumps(extra or {})))


def test_records_and_week():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    with db.session() as conn:
        _activity(conn, "a", (today - timedelta(days=400)).isoformat(), 10, {"best_1000": 230.0, "best_5000": 1290.0})
        _activity(conn, "b", (today - timedelta(days=30)).isoformat(), 10, {"best_1000": 240.0, "best_5000": 1280.0})
        _activity(conn, "c", monday.isoformat(), 8, {"best_1000": 245.0})
        _activity(conn, "v", monday.isoformat(), 30, sport="velo", load=40)
        conn.commit()
        settings = db.get_settings(conn)
        rec = analysis.records(conn, today - timedelta(days=365), today)
        week = analysis.week_summary(conn, today, settings)
    by_name = {r["nom"]: r for r in rec["records"]}
    assert by_name["1 km"]["record"]["temps"] == "3:50" and by_name["1 km"]["periode"]["temps"] == "4:00"
    assert not by_name["1 km"]["egale_record"]
    assert by_name["5 km"]["egale_record"] and by_name["5 km"]["periode"]["allure"] == "4:16 /km"
    assert week["totaux"]["seances"] == 2 and week["totaux"]["km_course"] == 8.0 and week["totaux"]["km"] == 38.0
    assert week["jours"][0]["date"] == monday.isoformat() and len(week["jours"][0]["seances"]) == 2
    assert week["jours"][0]["planning"]["poste"] in ("matin", "soir", None)


def test_home_endpoints():
    client = TestClient(web.create_app())
    assert client.get("/api/forme").status_code == 200
    assert len(client.get("/api/semaine").json()["jours"]) == 7
    assert client.get("/api/records").json()["records"] == []
    assert client.get("/api/allures").json()["vma"] == 16.0
    boot = client.get("/api/bootstrap").json()
    assert boot["vues"][0]["id"] == "accueil" and boot["planning"]["aujourdhui"]["date"] == date.today().isoformat()
    assert {t["type"] for t in boot["tuiles"]} >= {"profil", "forme", "allures", "semaine", "records", "journee",
                                                   "seance_mesures"}


def test_home_view_arrives_once_for_existing_installs():
    """Une installation 0.4 garde ses vues ; l'accueil s'ajoute en tête, une seule fois."""
    with db.session() as conn:
        conn.execute("DELETE FROM views")
        conn.execute("DELETE FROM meta WHERE key = 'vue_accueil'")
        views.save_view(conn, "ma-vue", "Ma vue", {"tuiles": []}, "star", 0)
        views.save_view(conn, "autre", "Autre", {"tuiles": []}, "star", 1)
    with db.session() as conn:  # chaque ouverture passe par db.init → views.ensure_default_views
        ids = [v["id"] for v in views.list_views(conn)]
        assert ids == ["accueil", "ma-vue", "autre"]
        views.delete_view(conn, "accueil")
    with db.session() as conn:
        assert [v["id"] for v in views.list_views(conn)] == ["ma-vue", "autre"]  # supprimée : elle ne revient pas
