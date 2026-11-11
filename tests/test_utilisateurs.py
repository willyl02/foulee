"""Profils : plusieurs personnes sur la même installation, chacune avec ses données, ses vues et sa clé."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from foulee import (
    cli,
    config,
    datadir,
    db,
    desktop,
    mcp_server,
    utilisateurs,
    vault,
    web,
)

WRITE = {"X-Foulee": "1"}


def new_client() -> TestClient:
    return TestClient(web.create_app())


def add_profile(client: TestClient, name: str, code: str | None = None) -> dict:
    res = client.post("/api/utilisateurs", json={"prenom": name, **({"code": code} if code else {})}, headers=WRITE)
    assert res.status_code == 200, res.text
    return res.json()["cree"]


def switch(client: TestClient, profile_id: str, code: str | None = None):
    return client.post("/api/utilisateurs/choisir", json={"id": profile_id, "code": code}, headers=WRITE)


def test_a_single_user_sees_no_change():
    client = new_client()
    boot = client.get("/api/bootstrap").json()
    assert not boot.get("profil_requis") and boot["utilisateur"] == {"id": "p0", "principal": True, "code": False,
                                                                    "claude": True}
    assert [u["id"] for u in boot["utilisateurs"]] == ["p0"]
    assert not utilisateurs.registry_path().exists()  # rien d'écrit tant qu'un seul profil suffit
    assert client.get("/api/views").status_code == 200


def test_profiles_have_their_own_data_views_and_settings():
    william = new_client()
    william.put("/api/settings", json={"vma_kmh": 16.4}, headers=WRITE)
    ruben = add_profile(william, "Ruben")
    assert ruben["prenom"] == "Ruben" and not ruben["principal"] and not ruben["claude"]
    assert utilisateurs.registry_path().exists()

    # Le navigateur du principal reste sur son profil ; un nouvel appareil doit choisir
    assert william.get("/api/bootstrap").json()["utilisateur"]["id"] == "p0"
    other = new_client()
    chooser = other.get("/api/bootstrap").json()
    assert chooser["profil_requis"] and {u["prenom"] for u in chooser["utilisateurs"]} == {"Moi", "Ruben"}
    assert "reglages" not in chooser and "vues" not in chooser  # rien des données de personne
    blocked = other.get("/api/views")
    assert blocked.status_code == 409 and blocked.json()["profil_requis"]

    assert switch(other, ruben["id"]).status_code == 200
    boot = other.get("/api/bootstrap").json()
    assert boot["utilisateur"]["id"] == ruben["id"] and boot["reglages"]["profil"]["prenom"] == "Ruben"
    assert boot["reglages"]["vma_kmh"] != 16.4 and boot["volumes"]["activities"] == 0
    other.put("/api/settings", json={"vma_kmh": 13.2}, headers=WRITE)
    other.post("/api/views", json={"name": "Vue de Ruben", "spec": {"tuiles": []}}, headers=WRITE)
    assert william.get("/api/settings").json()["vma_kmh"] == 16.4
    assert "vue-de-ruben" not in [v["id"] for v in william.get("/api/views").json()]
    assert "vue-de-ruben" in [v["id"] for v in other.get("/api/views").json()]
    assert (config.root_dir() / "profils" / ruben["id"] / "foulee.db").exists()


def test_installation_settings_are_for_the_principal_only():
    william = new_client()
    ruben = add_profile(william, "Ruben")
    kid = new_client()
    switch(kid, ruben["id"])
    for method, path, body in [("post", "/api/maj", {"action": "verifier"}), ("put", "/api/acces-reseau", {"mot_de_passe": "x" * 12}),
                               ("post", "/api/utilisateurs", {"prenom": "Intrus"}), ("delete", f"/api/utilisateurs/{ruben['id']}", None),
                               ("put", "/api/dossier", {"chemin": "/tmp/x", "mode": "deplacer"}), ("post", "/api/demo", {"actif": True}),
                               ("post", "/api/claude", {}), ("put", "/api/github-jeton", {"jeton": "x"})]:
        res = getattr(kid, method)(path, headers=WRITE, **({"json": body} if body is not None else {}))
        assert res.status_code == 403 and "principal" in res.json()["detail"], (path, res.text)
    # Le canal des mises à jour appartient à l'installation
    william.put("/api/settings", json={"canal_maj": "stable"}, headers=WRITE)
    kid.put("/api/settings", json={"canal_maj": "beta"}, headers=WRITE)
    assert william.get("/api/maj").json()["canal"] == "stable" and kid.get("/api/maj").json()["canal"] == "stable"
    assert kid.get("/api/utilisateurs").json()["gestion"] is False


def test_each_profile_has_its_own_garmin_key():
    vault.set_key("GCDC_cle-de-william")
    ruben = utilisateurs.create("Ruben")
    with config.using_profile(ruben):
        assert not vault.has_key()
        vault.set_key("GCDC_cle-de-ruben")
        assert vault.get_key() == "GCDC_cle-de-ruben"
        assert config.token_cache_file().name == f"garmin-jeton-{ruben['id']}.json"
    assert vault.get_key() == "GCDC_cle-de-william"
    assert (config.secrets_dir() / f"garmin-cle-{ruben['id']}.txt").exists()


def test_codes_protect_profiles(monkeypatch):
    william = new_client()
    ruben = add_profile(william, "Ruben", code="2468")
    kid = new_client()
    assert switch(kid, ruben["id"]).status_code == 401
    assert switch(kid, ruben["id"], "1111").status_code == 401
    assert switch(kid, ruben["id"], "2468").status_code == 200
    assert kid.get("/api/bootstrap").json()["utilisateur"]["id"] == ruben["id"]

    # Trop d'essais : une minute d'attente
    stranger = new_client()
    for _ in range(4):
        switch(stranger, ruben["id"], "0000")
    assert switch(stranger, ruben["id"], "0000").status_code == 401
    assert switch(stranger, ruben["id"], "2468").status_code == 429

    # Changer son code demande l'actuel ; les autres navigateurs devront le redonner
    assert kid.put("/api/utilisateurs/moi", json={"code": "1357", "ancien": "9999"}, headers=WRITE).status_code == 401
    assert kid.put("/api/utilisateurs/moi", json={"code": "12", "ancien": "2468"}, headers=WRITE).status_code == 400
    assert kid.put("/api/utilisateurs/moi", json={"code": "1357", "ancien": "2468"}, headers=WRITE).status_code == 200
    assert kid.get("/api/bootstrap").json()["utilisateur"]["id"] == ruben["id"]  # son cookie a été redonné
    stale = new_client()
    stale.cookies.set(utilisateurs.COOKIE, utilisateurs.make_cookie({**ruben, "code": None}))
    assert stale.get("/api/bootstrap").json().get("profil_requis")

    # Code oublié : le principal l'efface sans le connaître
    assert william.delete(f"/api/utilisateurs/{ruben['id']}/code", headers=WRITE).status_code == 200
    assert switch(new_client(), ruben["id"]).status_code == 200

    # Le principal aussi peut avoir un code : il faut alors le donner pour revenir sur son profil
    assert william.put("/api/utilisateurs/moi", json={"code": "8642"}, headers=WRITE).status_code == 200
    assert william.get("/api/bootstrap").json()["utilisateur"]["id"] == "p0"
    assert switch(kid, "p0").status_code == 401 and switch(kid, "p0", "8642").status_code == 200
    stored = json.loads(utilisateurs.registry_path().read_text(encoding="utf-8"))
    assert "8642" not in json.dumps(stored) and stored["profils"][0]["code"]["empreinte"]


def test_a_lone_principal_with_a_code_is_asked_for_it():
    william = new_client()
    william.put("/api/utilisateurs/moi", json={"code": "4321"}, headers=WRITE)
    assert new_client().get("/api/bootstrap").json().get("profil_requis")


def test_rename_and_delete():
    william = new_client()
    ruben = add_profile(william, "Ruben")
    assert william.post("/api/utilisateurs", json={"prenom": "ruben"}, headers=WRITE).status_code == 400  # doublon
    assert william.post("/api/utilisateurs", json={"prenom": "  "}, headers=WRITE).status_code == 400
    names = {u["prenom"] for u in william.put(f"/api/utilisateurs/{ruben['id']}", json={"prenom": "Aaron"},
                                               headers=WRITE).json()["utilisateurs"]}
    assert names == {"Moi", "Aaron"}
    with pytest.raises(RuntimeError, match="Profil incomplet"), config.using_profile(ruben):
        config.data_dir()  # une carte de l'interface, pas l'entrée du profil
    with config.using_profile(utilisateurs.get(ruben["id"])):
        vault.set_key("GCDC_cle-de-ruben")
        folder = config.data_dir()
        with db.session() as conn:
            assert db.get_settings(conn)["profil"]["prenom"] == "Aaron"
    detail = next(u for u in william.get("/api/utilisateurs").json()["utilisateurs"] if u["id"] == ruben["id"])
    assert detail["cle"] and detail["seances"] == 0  # le principal voit l'essentiel de chaque profil
    assert william.delete("/api/utilisateurs/p0", headers=WRITE).status_code == 400
    gone = william.delete(f"/api/utilisateurs/{ruben['id']}", headers=WRITE).json()
    assert gone["supprime"]["prenom"] == "Aaron" and [u["id"] for u in gone["utilisateurs"]] == ["p0"]
    assert not folder.exists() and not (config.secrets_dir() / f"garmin-cle-{ruben['id']}.txt").exists()
    assert config.root_dir().exists() and (config.root_dir() / "foulee.db").exists()


def test_sync_command_goes_through_every_profile(monkeypatch, capsys):
    vault.set_key("GCDC_cle-de-william")
    ruben = utilisateurs.create("Ruben")
    lea = utilisateurs.create("Léa")
    with config.using_profile(lea):
        vault.set_key("GCDC_cle-de-lea")
    seen = []

    def fake_run(**kwargs):
        seen.append((config.current_profile() or {}).get("id"))
        return {"statut": "ok", "sources": {"garmin": {"appels": 1}}}

    monkeypatch.setattr("foulee.sync.run", fake_run)
    assert cli.main(["sync"]) == 0
    assert seen == ["p0", lea["id"]]
    out = capsys.readouterr().out
    assert "Ruben : pas de clé API Garmin" in out
    seen.clear()
    assert cli.main(["sync", "--profil", "léa"]) == 0 and seen == [lea["id"]]
    with pytest.raises(SystemExit, match="Profil inconnu"):
        cli.main(["sync", "--profil", "Personne"])
    assert ruben["id"] not in seen


def test_auto_sync_checks_each_profile():
    vault.set_key("GCDC_cle-de-william")
    ruben = utilisateurs.create("Ruben")
    with config.using_profile(ruben):
        vault.set_key("GCDC_cle-de-ruben")
    for entry in utilisateurs.profiles():
        with config.using_profile(entry), db.session() as conn:
            db.set_meta(conn, "last_sync", "2026-01-01 08:00:00")
    started = []

    def start():
        started.append(config.current_profile()["id"])
        with db.session() as conn:
            db.set_meta(conn, "last_sync", db.now_iso())
        return True

    auto = desktop.AutoSync(start, lambda: {"resultat": {"statut": "ok"}}, lambda message: None, clock=time.time)
    assert auto.tick()["resultat"]["statut"] == "ok"
    assert started == ["p0", ruben["id"]]
    assert auto.tick() is None  # tout est frais


def test_claude_reads_only_the_profiles_that_allow_it():
    """Claude Desktop (un autre processus que l'interface) ne lit que les profils qui l'autorisent."""
    william = new_client()
    ruben = add_profile(william, "Ruben")
    kid = new_client()
    switch(kid, ruben["id"])

    def as_claude():  # le contrôle d'accès ne vaut que dans le processus de Claude Desktop
        config.set_access_check(utilisateurs.check_claude_access)

    def as_interface():
        config.set_access_check(None)

    assert mcp_server.start_profile()["id"] == "p0"
    as_claude()
    config.set_process_profile(mcp_server.start_profile())
    assert mcp_server.statut()["utilisateur"] == "Moi"
    listed = mcp_server.lister_utilisateurs()
    assert [p["prenom"] for p in listed["profils"]] == ["Moi"] and listed["non_accessibles"] == 1
    with pytest.raises(ValueError, match="Pas de profil accessible"):
        mcp_server.changer_utilisateur("Ruben")

    # Ruben autorise Claude depuis ses propres réglages
    as_interface()
    assert kid.put("/api/utilisateurs/moi", json={"claude": True}, headers=WRITE).json()["utilisateur"]["claude"]
    as_claude()
    assert mcp_server.changer_utilisateur("ruben")["utilisateur"] == "Ruben"
    assert mcp_server.statut()["seances"]["nombre"] == 0
    # … puis le retire : Claude ne peut plus rien lire de lui, même en cours de conversation
    as_interface()
    kid.put("/api/utilisateurs/moi", json={"claude": False}, headers=WRITE)
    as_claude()
    with pytest.raises(PermissionError, match="n'autorise pas Claude"):
        mcp_server.statut()
    with pytest.raises(PermissionError):
        mcp_server.requete_sql("SELECT COUNT(*) FROM activities")
    # Le principal peut aussi retirer l'accès à ses propres données
    as_interface()
    william.put("/api/utilisateurs/moi", json={"claude": False}, headers=WRITE)
    assert mcp_server.start_profile() is None


def test_moving_the_data_folder_brings_every_profile(tmp_path, monkeypatch):
    home = tmp_path / "donnees"
    monkeypatch.delenv("FOULEE_DATA", raising=False)  # dossier choisi dans les Réglages, pas imposé
    monkeypatch.setattr(config, "default_data_dir", lambda: home)
    william = new_client()
    ruben = add_profile(william, "Ruben")
    with config.using_profile(utilisateurs.get(ruben["id"])), db.session() as conn:
        db.put_daily(conn, "2026-11-10", {"resting_hr": 51})
    report = datadir.change(str(tmp_path / "ailleurs"), "deplacer")
    assert report["profils"] == 1
    moved = tmp_path / "ailleurs"
    assert (moved / "utilisateurs.json").exists() and (moved / "profils" / ruben["id"] / "foulee.db").exists()


def test_demo_has_a_second_profile():
    from foulee import demo

    counts = demo.build(days=12)
    assert counts["profils"] == 2
    names = [utilisateurs.card(p)["prenom"] for p in utilisateurs.profiles()]
    assert names == ["Camille", "Léo"]
    assert utilisateurs.registry_path().name == "utilisateurs-demo.json"
    assert not utilisateurs.protected()  # en démo, on arrive directement sur le profil principal
    leo = utilisateurs.profiles()[1]
    with config.using_profile(leo), db.session() as conn:
        assert db.table_counts(conn)["activities"] > 0
    config.set_demo(False)
    assert [p["id"] for p in utilisateurs.profiles()] == ["p0"]  # les vrais profils ne bougent pas


def test_a_stale_tab_reloads_instead_of_writing_elsewhere():
    """Un onglet resté sur un profil ne doit pas écrire dans celui choisi entre-temps dans un autre onglet."""
    william = new_client()
    ruben = add_profile(william, "Ruben")
    switch(william, ruben["id"])  # un autre onglet du même navigateur est passé sur Ruben
    stale = william.put("/api/settings", json={"vma_kmh": 19.9}, headers={**WRITE, "X-Foulee-Profil": "p0"})
    assert stale.status_code == 409 and stale.json()["profil_requis"]
    assert william.get("/api/settings").json()["vma_kmh"] != 19.9
    fine = william.put("/api/settings", json={"vma_kmh": 12.5}, headers={**WRITE, "X-Foulee-Profil": ruben["id"]})
    assert fine.status_code == 200 and fine.json()["reglages"]["vma_kmh"] == 12.5


def test_any_demo_profile_can_leave_the_demo():
    from foulee import demo

    demo.build(days=6)
    client = new_client()
    leo = next(p for p in utilisateurs.profiles() if not p["principal"])
    switch(client, leo["id"])
    assert client.post("/api/demo", json={"actif": True}, headers=WRITE).status_code == 403  # l'ouvrir : le principal
    assert client.post("/api/demo", json={"actif": False}, headers=WRITE).status_code == 200
    assert not config.is_demo()
