"""Synchro automatique : un rythme par source (Garmin, Withings), choisi dans les Réglages, de 30 min à 12 h."""

import json
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from foulee import cli, db, desktop, reglages, sync, vault, web
from foulee.withings import sync as wsync

WRITE = {"X-Foulee": "1"}
MIN = 60


@pytest.fixture
def calls(monkeypatch):
    """Garmin et Withings branchés sur le profil, sans réseau : chaque synchro de source est notée."""
    seen = []

    def source(name):
        def run(conn, **kwargs):
            seen.append(name)
            return {"erreurs": [], **({"mesures": 2, "nuits": 1} if name == "withings" else {"appels": 3})}
        return run

    monkeypatch.setattr(sync, "active_sources", lambda: ["garmin", "withings"])
    monkeypatch.setitem(sync.SOURCES, "garmin", source("garmin"))
    monkeypatch.setitem(sync.SOURCES, "withings", source("withings"))
    vault.set_key("cle-de-test")
    return seen


def journal(minutes_ago: float, results: dict) -> None:
    """Une synchro passée, comme sync.run la note (heure locale, résultat de chaque source)."""
    when = datetime.fromtimestamp(time.time() - minutes_ago * MIN).replace(microsecond=0).isoformat(sep=" ")
    with db.session() as conn:
        conn.execute("INSERT INTO sync_log(started_at, finished_at, source, status, summary) VALUES (?, ?, ?, ?, ?)",
                     (when, when, ",".join(results), "ok", json.dumps(results)))
        if any("erreur" not in r for r in results.values()):
            db.set_meta(conn, "last_sync", when)


def due(now: float | None = None) -> list[str]:
    with db.session(readonly=True) as conn:
        return sync.due_sources(conn, time.time() if now is None else now)


def rhythm(**minutes) -> None:
    with db.session() as conn:
        reglages.apply(conn, {"synchro_auto": minutes}, merge=True)


def test_intervals_are_bounded():
    assert sync.intervals({}) == {"garmin": 180, "withings": 180, "strava": 180, "calendrier": 180}  # 3 heures par défaut
    assert sync.intervals({"synchro_auto": {"garmin": 5, "withings": 5000}}) == \
        {"garmin": 30, "withings": 720, "strava": 180, "calendrier": 180}
    assert sync.intervals({"synchro_auto": {"garmin": "vite", "withings": None}})["garmin"] == 180
    assert sync.intervals({"synchro_auto": "toutes les heures"}) == {"garmin": 180, "withings": 180, "strava": 180, "calendrier": 180}


def test_setting_is_checked():
    assert reglages.clean("synchro_auto", {"garmin": "60", "withings": 720.0}) == {"garmin": 60, "withings": 720}
    for wrong, message in [({"garmin": 15}, "entre 30 et 720"), ({"withings": 1440}, "entre 30 et 720"),
                           ({"garmin": "vite"}, "n'est pas un nombre"), ({"polar": 60}, "source inconnue"),
                           (180, "un délai par source")]:
        with pytest.raises(reglages.SettingsError, match=message):
            reglages.clean("synchro_auto", wrong)


def test_setting_from_the_interface_and_from_claude():
    http = TestClient(web.create_app())
    assert http.get("/api/settings").json()["synchro_auto"] == {"garmin": 180, "withings": 180, "strava": 180, "calendrier": 180}
    saved = http.put("/api/settings", json={"synchro_auto": {"garmin": 60, "withings": 360}}, headers=WRITE)
    assert saved.status_code == 200
    assert saved.json()["reglages"]["synchro_auto"] == {"garmin": 60, "withings": 360, "strava": 180, "calendrier": 180}
    refused = http.put("/api/settings", json={"synchro_auto": {"garmin": 10}}, headers=WRITE)
    assert refused.status_code == 400 and "entre 30 et 720" in refused.text
    assert http.get("/api/settings").json()["synchro_auto"] == {"garmin": 60, "withings": 360, "strava": 180, "calendrier": 180}

    from foulee import mcp_server

    changed = mcp_server.modifier_reglages({"synchro_auto": {"withings": 120}})  # le reste est gardé
    assert changed["reglages"]["synchro_auto"] == {"garmin": 60, "withings": 120, "strava": 180, "calendrier": 180}
    assert "entre 30 et 720" in mcp_server.modifier_reglages({"synchro_auto": {"garmin": 1}})["erreur"]


def test_each_source_at_its_own_rhythm(calls):
    assert due() == []  # jamais synchronisé ici : le premier import se choisit sur l'Accueil
    journal(100, {"garmin": {}, "withings": {}})
    assert due() == []  # 3 heures par défaut
    assert due(time.time() + 80 * MIN) == ["garmin", "withings"]
    rhythm(garmin=60)
    assert due() == ["garmin"]
    rhythm(withings=90)
    assert due() == ["garmin", "withings"]

    journal(10, {"garmin": {"erreurs": ["Sommeil : HTTP 500"]}})  # Garmin seul, un flux en alerte : à jour
    assert due() == ["withings"]
    assert due(time.time() + 50 * MIN) == ["garmin", "withings"]  # une heure après (2 minutes de marge)


def test_after_a_failure_one_try_per_half_hour(calls):
    journal(200, {"garmin": {}, "withings": {}})
    journal(5, {"garmin": {"erreur": "Impossible de joindre Garmin"}, "withings": {}})
    assert due() == []  # Garmin a échoué il y a 5 minutes, Withings vient d'être synchronisé
    assert due(time.time() + 26 * MIN) == ["garmin"]


def test_refused_access_waits_for_the_settings(calls):
    journal(200, {"garmin": {}, "withings": {}})
    with db.session() as conn:
        db.set_meta(conn, sync.KEY_REFUSED, json.dumps({"depuis": db.now_iso(), "statut": 401}))
    assert due() == ["withings"]  # Garmin refuse la clé : rien tant qu'elle n'est pas remplacée
    with db.session() as conn:
        db.set_meta(conn, wsync.REFUSED, json.dumps({"depuis": db.now_iso(), "statut": 401}))
    assert due() == []


def test_journal_of_an_older_version(calls):
    """Avant la 0.6, le journal ne gardait pas le résultat de chaque source : la dernière synchro réussie compte."""
    with db.session() as conn:
        db.set_meta(conn, "last_sync", db.now_iso())
    assert due() == ["withings"]  # Withings jamais importé ici : il est dû
    assert due(time.time() + 3 * 3600) == ["garmin", "withings"]


def test_nothing_without_key_or_in_demo(calls, monkeypatch):
    journal(500, {"garmin": {}, "withings": {}})
    assert due() == ["garmin", "withings"]
    with monkeypatch.context() as demo:
        demo.setattr("foulee.config.is_demo", lambda: True)
        assert due() == []
    vault.delete_key()
    assert due() == []


def test_server_timer_syncs_only_what_is_due(calls, capsys):
    """La minuterie du serveur (foulee sync --auto, toutes les 15 minutes) : seulement les sources dues."""
    assert cli.main(["sync", "--auto", "--quiet"]) == 0 and calls == []  # pas encore de premier import
    journal(100, {"garmin": {}, "withings": {}})
    rhythm(garmin=60)
    assert cli.main(["sync", "--auto", "--quiet"]) == 0 and calls == ["garmin"]
    assert cli.main(["sync", "--auto", "--quiet"]) == 0 and calls == ["garmin"]  # Garmin vient d'être fait
    rhythm(withings=90)
    capsys.readouterr()
    assert cli.main(["sync", "--auto"]) == 0 and calls == ["garmin", "withings"]
    out = capsys.readouterr().out
    assert "Moi : Withings" in out and "2 mesure(s), 1 nuit(s)" in out and "appels à Garmin" not in out


def test_server_timer_waits_for_a_running_sync(calls, monkeypatch):
    journal(500, {"garmin": {}, "withings": {}})
    monkeypatch.setattr(sync, "is_running", lambda: True)  # « Synchroniser » ou premier import en cours
    assert cli.main(["sync", "--auto", "--quiet"]) == 0 and calls == []


def test_desktop_autosync_follows_each_rhythm(calls):
    """L'application du PC : chaque source à son rythme, d'après le journal des synchros."""
    now = [time.time()]
    requested = []

    def start(sources):
        requested.append(sources)
        sync.run(sources=sources)
        return True

    auto = desktop.AutoSync(start, lambda: {"en_cours": False, "resultat": {"statut": "ok"}}, lambda note: None,
                            clock=lambda: now[0])
    journal(500, {"garmin": {}, "withings": {}})
    rhythm(garmin=60, withings=240)
    assert auto.tick() is not None and requested == [["garmin", "withings"]]
    assert auto.tick() is None
    now[0] += 60 * MIN
    auto.tick()
    assert requested[-1] == ["garmin"]
    now[0] += 3 * 3600
    auto.tick()
    assert requested[-1] == ["garmin", "withings"] and calls.count("withings") == 2
