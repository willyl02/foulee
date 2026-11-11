"""Application de bureau : une seule copie, arrêt propre, synchro automatique, réglages."""

import json
import os
import subprocess
import sys
import time
import urllib.request

import pytest
from fastapi.testclient import TestClient

from foulee import config, db, desktop, vault, web

WRITE = {"X-Foulee": "1"}
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _get(port, path):
    with OPENER.open(f"http://127.0.0.1:{port}{path}", timeout=10) as response:
        return json.loads(response.read())


def _start_app(*extra):
    return subprocess.Popen([sys.executable, "-m", "foulee", "app", "--sans-icone", "--sans-navigateur", *extra],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONUTF8": "1"})


def _wait_instance(process, timeout=60):
    # Le numéro de processus noté peut différer de process.pid : sous Windows, le python.exe d'un
    # environnement virtuel relance le vrai interpréteur dans un processus enfant
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = desktop.read_instance()
        if info:
            try:
                _get(info["port"], "/api/app")
                return info
            except OSError:
                pass
        if process.poll() is not None:
            raise AssertionError(process.stdout.read().decode(errors="replace"))
        time.sleep(0.2)
    raise AssertionError("l'application n'a pas démarré")


def test_single_instance_and_clean_quit():
    first = _start_app("--port", "0")
    try:
        info = _wait_instance(first)
        assert _get(info["port"], "/api/app")["application"] is True
        assert _get(info["port"], "/api/bootstrap")["application"] is True

        second = _start_app("--port", "0")  # déjà lancé : la seconde copie s'efface tout de suite
        assert second.wait(timeout=30) == 0
        assert desktop.read_instance()["pid"] == info["pid"]

        quit_command = subprocess.run([sys.executable, "-m", "foulee", "app", "--quitter"], capture_output=True,
                                      text=True, timeout=60, env={**os.environ, "PYTHONUTF8": "1"})
        assert quit_command.returncode == 0, quit_command.stdout + quit_command.stderr
        assert first.wait(timeout=30) == 0
        assert desktop.read_instance() is None
    finally:
        if first.poll() is None:
            first.kill()


def test_quit_when_nothing_runs():
    assert desktop.quit_running(timeout=1) is True


def test_port_already_taken_moves_to_the_next_one():
    taken = desktop.bind_socket(0)
    taken.listen(1)
    port = taken.getsockname()[1]
    try:
        other = desktop.bind_socket(port, tries=5)
        assert other.getsockname()[1] != port
        other.close()
        with pytest.raises(OSError, match="Aucun port libre"):
            desktop.bind_socket(port, tries=1)
    finally:
        taken.close()


class FakeJob:
    def __init__(self, outcome="ok"):
        self.outcome = outcome
        self.started = 0

    def start(self):
        self.started += 1
        if self.outcome == "ok":
            with db.session() as conn:
                db.set_meta(conn, "last_sync", db.now_iso())
        return True

    def wait(self):
        return {"en_cours": False, "resultat": {"statut": self.outcome}}


def test_autosync_runs_when_due_only():
    now = [time.time()]
    job = FakeJob()
    notes = []
    auto = desktop.AutoSync(job.start, job.wait, notes.append, clock=lambda: now[0])
    assert auto.tick() is None and job.started == 0  # pas de clé : rien

    vault.set_key("GCDC_cle-de-test")
    assert auto.tick() is None and job.started == 0  # jamais synchronisé : le premier import se choisit
    with db.session() as conn:
        db.set_meta(conn, "last_sync", "2026-01-01 08:00:00")  # premier import fait il y a longtemps
    assert auto.tick()["resultat"]["statut"] == "ok" and job.started == 1
    assert auto.tick() is None  # la dernière synchro est toute fraîche
    now[0] += desktop.SYNC_EVERY
    assert auto.tick() is not None and job.started == 2

    # Échec (réseau coupé…) : on réessaie, mais pas plus d'une fois par demi-heure
    failing = FakeJob("echec")
    auto = desktop.AutoSync(failing.start, failing.wait, notes.append, clock=lambda: now[0])
    now[0] += desktop.SYNC_EVERY
    auto.tick()
    auto.tick()
    assert failing.started == 1
    now[0] += desktop.RETRY_AFTER_FAILURE
    auto.tick()
    assert failing.started == 2 and notes == []

    # Clé refusée par Garmin : une notification, puis plus d'essai jusqu'à la nouvelle clé
    def refuse():
        with db.session() as conn:
            db.set_meta(conn, "cle_refusee", json.dumps({"depuis": db.now_iso(), "statut": 401}))
        return True

    auto = desktop.AutoSync(refuse, failing.wait, notes.append, clock=lambda: now[0])
    now[0] += desktop.SYNC_EVERY
    auto.tick()
    assert notes and "refuse ta clé" in notes[0]
    now[0] += desktop.SYNC_EVERY
    assert auto.tick() is None


def test_autosync_warns_once_when_withings_withdraws_access():
    now = [time.time()]
    notes = []
    vault.set_key("GCDC_cle-de-test")
    with db.session() as conn:
        db.set_meta(conn, "last_sync", "2026-01-01 08:00:00")

    def withdrawn():  # Garmin répond, Withings refuse le renouvellement de l'accès
        with db.session() as conn:
            db.set_meta(conn, "last_sync", db.now_iso())
            db.set_meta(conn, "withings_refus", json.dumps({"depuis": db.now_iso(), "statut": 401}))
        return True

    auto = desktop.AutoSync(withdrawn, lambda: {"en_cours": False, "resultat": {"statut": "partiel"}}, notes.append,
                            clock=lambda: now[0])
    auto.tick()
    assert len(notes) == 1 and "Withings n'accepte plus l'accès" in notes[0] and "Réglages → Withings" in notes[0]
    now[0] += desktop.SYNC_EVERY
    assert auto.tick() is not None and len(notes) == 1  # la synchro Garmin continue, sans nouvel avertissement


def test_sync_summary():
    assert desktop.sync_summary({"erreur": "réseau"}) == "Synchro impossible : réseau"
    done = {"resultat": {"sources": {"garmin": {"seances_nouvelles": 2}}}}
    assert desktop.sync_summary(done) == "Synchro terminée : 2 nouvelles séances."
    assert "à jour" in desktop.sync_summary({"resultat": {"sources": {"garmin": {}}}})
    assert desktop.sync_summary({"resultat": {"sources": {"garmin": {"erreur": "clé refusée"}}}}) == \
        "Synchro impossible : clé refusée"
    both = {"resultat": {"sources": {"garmin": {"seances_nouvelles": 1}, "withings": {"erreur": "accès refusé"}}}}
    assert desktop.sync_summary(both) == "Synchro partielle. Withings : accès refusé"
    withings = {"resultat": {"sources": {"garmin": {}, "withings": {"mesures": 3}}}}
    assert desktop.sync_summary(withings) == "Synchro terminée : tout est à jour."


def test_app_endpoints_outside_the_application():
    client = TestClient(web.create_app())
    assert client.get("/api/app").json() == {"application": False, "demarrage_windows": None,
                                            "synchro_auto_heures": None}
    assert client.post("/api/app/quitter", headers=WRITE).status_code == 404
    assert client.put("/api/app", json={"demarrage_windows": True}, headers=WRITE).status_code == 404


def test_quit_endpoint_calls_the_application():
    app = web.create_app()
    called = []
    app.state.quit = lambda: called.append(True)
    client = TestClient(app)
    assert client.post("/api/app/quitter", headers=WRITE).json() == {"ok": True}
    time.sleep(0.6)
    assert called == [True]
    lan = TestClient(app, client=("192.168.0.50", 50000))
    assert lan.post("/api/app/quitter", headers={**WRITE, "Host": "192.168.0.19"}).status_code in (401, 403)


def test_first_import_from_a_chosen_date(monkeypatch):
    from foulee import sync

    seen = []
    monkeypatch.setattr(sync, "run", lambda since=None, progress=None: seen.append(since) or {"statut": "ok"})
    client = TestClient(web.create_app())
    assert client.post("/api/sync", json={"depuis": "2024-01-01"}, headers=WRITE).json()["lance"] is False
    vault.set_key("GCDC_cle-de-test")
    assert client.post("/api/sync", json={"depuis": "hier"}, headers=WRITE).status_code == 400
    assert client.post("/api/sync", json={"depuis": "2999-01-01"}, headers=WRITE).status_code == 400
    assert client.post("/api/sync", json={"depuis": "2024-01-01"}, headers=WRITE).json()["lance"] is True
    for _ in range(50):
        if seen:
            break
        time.sleep(0.05)
    assert str(seen[0]) == "2024-01-01"


def test_demo_switch(monkeypatch):
    from foulee import demo

    def fake_build():
        config.set_demo(True)
        with db.session() as conn:
            conn.execute("INSERT INTO activities(id, source, source_id, start_local, date, sport) "
                         "VALUES ('demo:1', 'demo', '1', '2026-11-01 08:00:00', '2026-11-01', 'course')")
            conn.commit()
        return {}

    monkeypatch.setattr(demo, "build", fake_build)
    client = TestClient(web.create_app())
    assert client.post("/api/demo", json={"actif": True}, headers=WRITE).status_code == 200
    for _ in range(100):
        state = client.get("/api/demo").json()
        if not state["preparation"]:
            break
        time.sleep(0.05)
    assert state == {"actif": True, "preparation": False, "erreur": None}
    assert client.get("/api/bootstrap").json()["demo"] is True
    assert client.post("/api/demo", json={"actif": False}, headers=WRITE).json()["actif"] is False
    assert client.get("/api/bootstrap").json()["demo"] is False
