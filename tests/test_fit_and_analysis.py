"""Décodage FIT (SDK officiel Garmin) et calculs dérivés."""

import datetime as dt
import io
import zipfile

from fake_garmin import make_fit

from foulee import analysis, fitfile


def test_decode_fit_from_zip():
    raw = make_fit(dt.datetime(2026, 10, 1, 6, 0, tzinfo=dt.timezone.utc), minutes=10)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("1_ACTIVITY.fit", raw)
    decoded = fitfile.decode(fitfile.extract_fit(buffer.getvalue()))
    streams = decoded["streams"]
    assert decoded["sport"] == "running"
    assert len(streams["t"]) == 600
    assert streams["cad"][0] == 171.0  # (85 + 0,5) × 2 : cadence en pas/min
    assert round(streams["lat"][0], 1) == 48.4
    assert len(decoded["laps"]) == 2 and decoded["laps"][0]["avg_cadence"] == 170.0


def test_trimp_zones_splits_and_decoupling():
    raw = make_fit(dt.datetime(2026, 10, 1, 6, 0, tzinfo=dt.timezone.utc), minutes=30, speed=3.0)
    streams = fitfile.decode(raw)["streams"]
    trimp = analysis.trimp_from_streams(streams, 50, 190, 1.92)
    assert 30 < trimp < 120
    zones = analysis.pace_zone_seconds(streams, analysis.pace_bounds({"vma_kmh": 16, "zones_allure_pct_vma": [70, 80, 88, 95]}))
    assert sum(zones) > 1700
    splits = analysis.km_splits(streams)
    assert splits[0]["km"] == 1.0 and splits[0]["allure"] == "5:33 /km"
    assert analysis.decoupling(streams)["derive_pct"] is not None
    packed = fitfile.pack_streams(streams)
    assert fitfile.unpack_streams(packed)["t"][-1] == streams["t"][-1]


def test_shift_rule():
    settings = {"postes": {"actif": True, "impaires": "matin", "paires": "soir", "jours_ouvres": True,
                           "semaines_exclues": ["2026-W46"]}}
    assert analysis.shift_of(dt.date(2026, 11, 3), settings) == "matin"   # S45, mardi
    assert analysis.shift_of(dt.date(2026, 11, 8), settings) is None      # dimanche
    assert analysis.shift_of(dt.date(2026, 11, 10), settings) is None     # S46 exclue
    assert analysis.shift_of(dt.date(2026, 11, 17), settings) == "matin"  # S47
    assert analysis.shift_of(dt.date(2026, 11, 24), settings) == "soir"   # S48


def test_objective():
    goal = analysis.objective({"vma_kmh": 16, "objectif": {"nom": "Semi", "date": "2027-03-07", "distance_km": 21.0975,
                                                           "temps_cible": "1:25:00"}})
    assert goal["allure_cible"] == "4:02 /km"
    assert round(goal["pct_vma"]) == 93
