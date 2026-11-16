"""0.8.1b5 : la VO2max lue dans les fichiers FIT, la veille des nouvelles séances, la période de chaque vue,
et le logo partout."""

import datetime as dt
import json
import time
from pathlib import Path

import pytest
from fake_garmin import FakeGarmin

from conftest import REAL_NEW_ACTIVITIES
from fake_garmin import make_fit

from foulee import db, fitfile, sync, vault, views
from foulee.garmin import sync as garmin_sync


@pytest.fixture
def garmin(monkeypatch):
    with FakeGarmin(days=30, activities=4) as fake:
        for item in fake.activities:  # comme la vraie API personnelle : pas de VO2max dans les séances
            item.pop("vO2MaxValue", None)
        monkeypatch.setenv("GARMIN_PERSONAL_API_BASE_URL", fake.url)
        vault.set_key("cle-de-test")
        yield fake


# ------------------------------------------------------------------------ VO2max
def test_vo2max_comes_from_the_fit_files(garmin):
    garmin.vo2max = 55.3  # l'API ne la donne pas, la montre l'écrit dans chaque séance
    assert sync.run(since=garmin.today - dt.timedelta(days=25))["statut"] == "ok"
    with db.session() as conn:
        values = [r["vo2max"] for r in conn.execute("SELECT vo2max FROM activities")]
        assert values and all(v == 55.3 for v in values)
        daily = conn.execute("SELECT COUNT(*) AS n FROM daily WHERE metric = 'vo2max' AND value = 55.3").fetchone()
        assert daily["n"] == len(values)  # la tuile « VO2max estimée par Garmin » a ses points
    assert sync.run()["statut"] == "ok"  # le résumé de l'API (sans VO2max) ne l'efface pas
    with db.session() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM activities WHERE vo2max IS NULL").fetchone()["n"] == 0


def test_old_fit_files_are_read_again(garmin):
    assert sync.run(since=garmin.today - dt.timedelta(days=25))["statut"] == "ok"  # FIT sans VO2max

    with db.session() as conn:
        rows = conn.execute("SELECT id, fit_path FROM activities WHERE vo2max IS NULL").fetchall()
        assert rows and all(Path(r["fit_path"]).exists() for r in rows)
        for r in rows:  # des séances d'avant la 0.8.1b5, dont la montre avait écrit la VO2max
            Path(r["fit_path"]).write_bytes(make_fit(dt.datetime(2026, 11, 1, 7, tzinfo=dt.timezone.utc), minutes=2,
                                                     vo2max=54.0))
        db.delete_meta(conn, "vo2_relus")  # des fichiers jamais relus, comme avant la 0.8.1b5
        assert garmin_sync.backfill_vo2max(conn, limit=2) == 2  # par petits paquets
        assert garmin_sync.backfill_vo2max(conn) == len(rows) - 2
        assert garmin_sync.backfill_vo2max(conn) == 0  # chaque fichier n'est relu qu'une fois


def test_vo2max_of_prefers_the_session_sport():
    when = dt.datetime(2026, 11, 1, 7)
    messages = {"max_met_data_mesgs": [{"vo2_max": 48.0, "sport": "cycling", "update_time": when},
                                       {"vo2_max": 55.1, "sport": "running", "update_time": when},
                                       {"vo2_max": 0, "sport": "running", "update_time": when}]}
    assert fitfile.vo2max_of(messages, "running") == 55.1
    assert fitfile.vo2max_of(messages, "cycling") == 48.0
    assert fitfile.vo2max_of({}, "running") is None


# ------------------------------------------------------------------ veille
def test_watch_starts_a_sync_when_a_new_session_arrives(garmin, monkeypatch):
    monkeypatch.setattr(sync, "new_garmin_activities", REAL_NEW_ACTIVITIES)  # la vraie, contre le faux Garmin
    assert sync.run(since=garmin.today - dt.timedelta(days=25))["statut"] == "ok"
    now = time.time()
    assert sync.watch_check(now) == []  # rien de neuf
    start = dt.datetime.combine(garmin.today, dt.time(12, 0))
    garmin.activities.insert(0, {**garmin.activities[0], "activityId": 59_999_999, "activityName": "Sortie du midi",
                                 "startTimeLocal": start.strftime("%Y-%m-%d %H:%M:%S"),
                                 "startTimeGMT": (start - dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")})
    assert sync.watch_check(now + 60) == []  # au plus une veille toutes les 20 minutes
    calls = len(garmin.requests)
    assert sync.watch_check(now + sync.WATCH_EVERY) == ["garmin"]
    assert len(garmin.requests) - calls <= 2  # un seul appel (plus l'échange du jeton s'il le faut)
    assert sync.watch_check(now + 2 * sync.WATCH_EVERY) == []  # déjà signalée : pas de synchro en boucle
    assert sync.run(sources=["garmin"])["statut"] == "ok"
    with db.session() as conn:
        assert conn.execute("SELECT name FROM activities WHERE id = 'garmin:59999999'").fetchone()["name"] == "Sortie du midi"


def test_no_watch_without_garmin_or_before_the_first_import(garmin):
    assert sync.watch_check() == []  # pas encore de premier import
    vault.delete_key()
    with db.session() as conn:
        db.set_meta(conn, "last_sync", "2026-11-15 10:00:00")
    assert sync.watch_check() == []


# ------------------------------------------------------------------ périodes
def test_each_view_has_its_period_and_its_tiles_follow_it():
    tiles_of = {v["id"]: v for v in views.default_views()}
    assert tiles_of["entrainement"]["spec"]["periode"] == 180 and tiles_of["objectifs"]["spec"]["periode"] == 180
    for view_id in ("entrainement", "recup-postes", "objectifs"):
        fixed = [t for t in tiles_of[view_id]["spec"]["tuiles"] if t["params"].get("periode") not in (None, "herite")]
        assert fixed == [], view_id
    assert views.clean_spec({"periode": 365, "tuiles": []})["periode"] == 365
    assert "periode" not in views.clean_spec({"periode": 45, "tuiles": []})


def test_old_views_follow_the_selector_once():
    with db.session() as conn:  # une base d'avant la 0.8.1b5 : périodes fixes, dont une changée à la main
        spec = {"tuiles": [views._tile("serie", 8, 2, titre="Km", metriques=["act.distance_km"], periode="180"),
                           views._tile("zones", 6, 2, zones="fc", periode="90"),
                           views._tile("charge", 12, 3, periode="30")]}
        conn.execute("UPDATE views SET spec = ? WHERE id = 'entrainement'", (json.dumps(spec),))
        db.delete_meta(conn, "vue_periodes")
    with db.session() as conn:
        spec = json.loads(conn.execute("SELECT spec FROM views WHERE id = 'entrainement'").fetchone()["spec"])
        assert spec["periode"] == 180
        assert [t["params"]["periode"] for t in spec["tuiles"]] == ["herite", "herite", "30"]


# ------------------------------------------------------------------ logo
def test_the_old_balise_is_gone():
    static = Path(views.__file__).parent / "static"
    for name in ("sw.js", "connexion.html", "reseau-desactive.html", "index.html", "js/welcome.js", "js/logos.js"):
        text = (static / name).read_text(encoding="utf-8")
        assert "blaze" not in text and "#4b3e34" not in text, name
    assert "fill=\"#182020\"" in (static / "sw.js").read_text(encoding="utf-8")  # la page « injoignable » du téléphone
