"""Chaîne complète contre un faux serveur Garmin : client officiel → synchro → base → analyses → MCP."""

import datetime as dt

import pytest
from fake_garmin import FakeGarmin

from foulee import analysis, db, sync, vault
from foulee.garmin.client import GarminError, check_key


@pytest.fixture
def garmin(monkeypatch):
    with FakeGarmin(days=70, activities=12) as fake:
        monkeypatch.setenv("GARMIN_PERSONAL_API_BASE_URL", fake.url)
        yield fake


def test_bad_key_is_explained(garmin):
    with pytest.raises(GarminError) as error:
        check_key("mauvaise-cle")
    assert error.value.key_rejected and error.value.status == 401
    assert "refusé la clé" in str(error.value) and "HTTP 401" in str(error.value)
    assert error.value.detail == '{"error": "invalid key"}'


def test_full_then_incremental_sync(garmin):
    assert check_key("cle-de-test")["ok"]
    vault.set_key("cle-de-test")
    since = garmin.today - dt.timedelta(days=65)
    result = sync.run(since=since)
    assert result["statut"] == "ok", result
    g = result["sources"]["garmin"]
    assert g["seances_nouvelles"] == 12 and g["fit"] == 12

    # Aucune requête ne dépasse les limites de plage de Garmin
    for path, query in garmin.requests:
        if "startDate" in query and "endDate" in query and "search" not in path:
            span = (dt.date.fromisoformat(query["endDate"]) - dt.date.fromisoformat(query["startDate"])).days + 1
            assert span <= 31, (path, query)
        if "search" in path:
            assert int(query["limit"]) <= 45

    with db.session() as conn:
        day = (garmin.today - dt.timedelta(days=2)).isoformat()
        values = {r["metric"]: r["value"] for r in conn.execute("SELECT metric, value FROM daily WHERE date = ?", (day,))}
        assert values["sleep_s"] == 25800 and values["sleep_end_h"] == 6.75
        assert values["hrv_night"] > 0 and values["bb_wake"] == 74
        assert "steps" in values and "resting_hr" in values
        assert conn.execute("SELECT COUNT(*) AS n FROM activities WHERE has_streams = 1").fetchone()["n"] == 12
        assert conn.execute("SELECT COUNT(*) AS n FROM laps").fetchone()["n"] == 24
        assert conn.execute("SELECT COUNT(*) AS n FROM daily WHERE metric = 'ctl'").fetchone()["n"] > 30
        settings = db.get_settings(conn)
        first = analysis.activities_list(conn, limit=1)[0]
        detail = analysis.activity_detail(conn, first["id"], settings)
        assert detail["description"] == "Bonnes jambes" and len(detail["tours"]) == 2 and detail["splits_km"]
        assert analysis.hr_profile(conn, settings)["max"] == 188  # zones Garmin
        assert db.get_meta(conn, "last_sync")

    calls_first = len(garmin.requests)
    sync.run()
    calls_second = len(garmin.requests) - calls_first
    assert calls_second < calls_first / 3  # la seconde synchro ne reprend que les derniers jours


def test_reparse_rebuilds_from_raw(garmin):
    vault.set_key("cle-de-test")
    sync.run(since=garmin.today - dt.timedelta(days=20))
    from foulee.garmin.sync import reparse_all

    with db.session() as conn:
        before = conn.execute("SELECT COUNT(*) AS n FROM daily WHERE source = 'garmin'").fetchone()["n"]
        conn.execute("DELETE FROM daily WHERE source = 'garmin'")
        reparse_all(conn)
        after = conn.execute("SELECT COUNT(*) AS n FROM daily WHERE source = 'garmin'").fetchone()["n"]
    assert after == before


def test_diagnostic_report_has_no_values(garmin):
    vault.set_key("cle-de-test")
    from foulee.garmin.diagnostic import run

    text = run().read_text(encoding="utf-8")
    assert "Fichier FIT" in text and "métriques comprises" in text
    assert "Footing" not in text and "Bonnes jambes" not in text  # aucun contenu personnel
