"""Effet d'entraînement de Garmin (Training Effect) : niveaux, avantage principal, comparaison aux séances
précédentes, API et Claude."""

import datetime as dt

import pytest
from fake_garmin import FakeGarmin
from fastapi.testclient import TestClient

from foulee import analysis, db, sync, vault


@pytest.mark.parametrize("value, level", [
    (0.0, "aucun"), (0.94, "aucun"), (0.96, "faible"), (1.9, "faible"), (2.0, "maintien"), (2.95, "impact"),
    (3.9, "impact"), (3.97, "fort"), (4.9, "fort"), (5.0, "surcharge"),
])
def test_levels_follow_garmin_connect(value, level):
    """Le niveau de la valeur affichée (au dixième) : 0,96 s'affiche 1,0, « faible avantage »."""
    assert analysis.te_level(value)[0] == level


def test_levels_have_the_labels_of_garmin_connect():
    assert [analysis.te_level(v)[1] for v in (0.5, 1.5, 2.5, 3.5, 4.5, 5.0)] == [
        "Aucune amélioration", "Faible avantage", "Maintien", "Impact", "Fort impact", "Effort trop soutenu"]


def test_primary_benefit():
    base = analysis.te_benefit("AEROBIC_BASE")
    assert (base["libelle"], base["famille"], base["famille_libelle"]) == ("Base", "aerobie_faible", "Aérobie faible")
    assert analysis.te_benefit("BASE")["cle"] == "AEROBIC_BASE"  # ancien nom
    assert analysis.te_benefit_text("LACTATE_THRESHOLD") == "Seuil (aérobie élevée)"
    assert analysis.te_benefit_text("SPEED") == "Sprint (anaérobique)"
    assert analysis.te_benefit_text("ANAEROBIC_CAPACITY") == "Capacité anaérobie (anaérobique)"
    assert analysis.te_benefit("UNKNOWN") is None and analysis.te_benefit(None) is None


def add(conn, n: int, day: dt.date, sport: str, aero, anaero, hour: int = 8) -> dict:
    conn.execute(
        "INSERT INTO activities(id, source, source_id, start_local, date, sport, name, te_aerobic, te_anaerobic, "
        "garmin_load) VALUES (?, 'garmin', ?, ?, ?, ?, ?, ?, ?, ?)",
        (f"garmin:{n}", str(n), f"{day.isoformat()} {hour:02d}:00:00", day.isoformat(), sport, f"Séance {n}", aero,
         anaero, 80.4))
    return dict(conn.execute("SELECT * FROM activities WHERE id = ?", (f"garmin:{n}",)).fetchone())


def test_compared_with_the_same_sport_over_the_4_previous_weeks():
    today = dt.date(2026, 11, 13)
    with db.session() as conn:
        add(conn, 1, today - dt.timedelta(days=40), "course", 4.8, 3.0)  # trop ancienne
        add(conn, 2, today - dt.timedelta(days=20), "course", 2.1, 0.0)
        add(conn, 3, today - dt.timedelta(days=12), "trail", 3.6, 0.4)  # course et trail ensemble
        add(conn, 4, today - dt.timedelta(days=5), "course", 2.9, 0.0)
        add(conn, 5, today - dt.timedelta(days=3), "velo", 1.2, 0.0)  # un autre sport
        add(conn, 6, today, "course", 3.4, 0.0, hour=18)  # plus tard le même jour : après
        row = add(conn, 7, today, "course", 2.94, 0.04, hour=7)
        effect = analysis.training_effect(conn, row, {"te_label": "TEMPO"})
        assert effect["aerobie"] == {"valeur": 2.9, "niveau": "maintien", "libelle": "Maintien",
                                     "texte": analysis.TE_TEXTS["aerobie"]["maintien"]}
        assert effect["anaerobie"]["valeur"] == 0.0 and effect["anaerobie"]["niveau"] == "aucun"
        assert effect["avantage"]["libelle"] == "Tempo" and effect["charge_garmin"] == 80
        ctx = effect["contexte"]
        assert ctx["sport"] == "de course et trail" and ctx["jours"] == 28
        assert [s["id"] for s in ctx["seances"]] == ["garmin:2", "garmin:3", "garmin:4"]
        assert ctx["aerobie"] == {"nombre": 3, "min": 2.1, "max": 3.6, "moyenne": 2.9, "en_dessous": 1, "au_dessus": 1}
        assert ctx["anaerobie"]["en_dessous"] == 0 and ctx["anaerobie"]["au_dessus"] == 1  # 0,0 comme 2 d'entre elles
        alone = analysis.training_effect(conn, add(conn, 8, today, "natation", 1.5, None), {})
        assert alone["contexte"] is None and alone["anaerobie"] is None and alone["avantage"] is None
        assert analysis.training_effect(conn, add(conn, 9, today, "course", None, None), {}) is None


@pytest.fixture
def garmin(monkeypatch):
    with FakeGarmin(days=30, activities=4) as fake:
        monkeypatch.setenv("GARMIN_PERSONAL_API_BASE_URL", fake.url)
        vault.set_key("cle-de-test")
        sync.run(since=fake.today - dt.timedelta(days=28))
        yield fake


def test_api_and_claude(garmin):
    from foulee import mcp_server
    from foulee.web import create_app

    client = TestClient(create_app())
    detail = client.get("/api/activities/garmin:50000000", params={"fetch": 0}).json()
    effect = detail["effet"]
    assert (effect["aerobie"]["valeur"], effect["aerobie"]["libelle"]) == (3.1, "Impact")
    assert (effect["anaerobie"]["valeur"], effect["anaerobie"]["libelle"]) == (0.8, "Aucune amélioration")
    assert effect["avantage"]["libelle"] == "Seuil" and effect["avantage"]["famille"] == "aerobie_elevee"
    assert effect["contexte"]["aerobie"]["nombre"] >= 2  # les footings des 4 semaines d'avant (tous à 3,1)
    assert effect["contexte"]["aerobie"]["en_dessous"] == 0 and effect["contexte"]["aerobie"]["au_dessus"] == 0
    seen = mcp_server.detail_seance("garmin:50000000")
    assert seen["effet_anaerobie"] == 0.8
    assert seen["effet_entrainement"]["aerobie"]["niveau"] == "Impact"
    assert seen["effet_entrainement"]["avantage_principal"].startswith("Seuil (aérobie élevée) : ")
    assert seen["effet_entrainement"]["comparaison"]["sport"] == "de course et trail"
    listed = mcp_server.lister_seances()["seances"][0]
    assert listed["effet_aerobie"] == 3.1 and listed["effet_anaerobie"] == 0.8
    with db.session() as conn:  # une séance sans effet d'entraînement (Strava, montre sans cardio…)
        conn.execute("UPDATE activities SET te_aerobic = NULL, te_anaerobic = NULL WHERE id = 'garmin:50000001'")
    assert client.get("/api/activities/garmin:50000001", params={"fetch": 0}).json()["effet"] is None
    assert mcp_server.detail_seance("garmin:50000001")["effet_entrainement"] is None
