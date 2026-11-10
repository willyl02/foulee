"""Dossier des données : le choisir, y déplacer ses données ou reprendre celles qu'il contient."""

import json

import pytest
from fastapi.testclient import TestClient

from foulee import claude_desktop, config, datadir, db, sync, web

WRITE = {"X-Foulee": "1"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Comme sur un PC : pas de FOULEE_DATA, un dossier par défaut et quelques données dedans."""
    monkeypatch.delenv("FOULEE_DATA", raising=False)
    default = tmp_path / "defaut"
    monkeypatch.setattr(config, "default_data_dir", lambda: default)
    with db.session() as conn:
        conn.execute("INSERT INTO daily(date, metric, value, source) VALUES ('2026-11-01', 'resting_hr', 44, 'garmin')")
        conn.execute("INSERT INTO daily(date, metric, value, source) VALUES ('2026-11-02', 'resting_hr', 43, 'garmin')")
        conn.commit()
    (default / "fit").mkdir(parents=True, exist_ok=True)
    (default / "fit" / "123.fit").write_bytes(b"FIT" * 100)
    return default


def test_default_folder_is_described(home):
    info = datadir.describe()
    assert info["chemin"] == str(home) and info["source"] == "defaut" and info["modifiable"]
    assert info["base"] and info["est_defaut"] and info["taille"] > 0


def test_move_then_come_back(home, tmp_path):
    target = tmp_path / "Sport" / "Foulee"
    report = datadir.change(str(target), "deplacer")
    assert sorted(p.name for p in target.iterdir()) == ["fit", "foulee.db"]  # copie propre, sans reste
    assert report["base"]["valeurs"] == 2 and report["fichiers_fit"] == 1
    assert config.data_dir() == target and config.data_dir_source() == "reglages"
    assert (target / "fit" / "123.fit").read_bytes() == b"FIT" * 100
    assert (home / "foulee.db").exists()  # l'ancien dossier n'est jamais effacé
    with db.session(readonly=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM daily").fetchone()[0] == 2

    # Retour au dossier par défaut, qui contient toujours ses données
    back = datadir.change(str(home), "utiliser")
    assert back["base"]["valeurs"] == 2
    assert config.data_dir() == home and "dossier_donnees" not in config.load_user_config()


@pytest.mark.parametrize("make_target, mode, message", [
    (lambda home, tmp: "relatif/dossier", "deplacer", "chemin complet"),
    (lambda home, tmp: str(home), "deplacer", "déjà le dossier"),
    (lambda home, tmp: str(home / "sous-dossier"), "deplacer", "à l'intérieur"),
    (lambda home, tmp: str(tmp / "vide"), "utiliser", "ne contient pas de données"),
    (lambda home, tmp: str(home), "n'importe", "Mode inconnu"),
])
def test_refusals_are_explained(home, tmp_path, make_target, mode, message):
    with pytest.raises(datadir.DataDirError, match=message):
        datadir.change(make_target(home, tmp_path), mode)
    assert config.data_dir() == home


def _fresh_install(folder, *, with_data=False):
    """Base telle que la crée le premier démarrage (vide), ou avec une journée de données."""
    folder.mkdir(parents=True, exist_ok=True)
    conn = db.connect(folder / "foulee.db")
    db.init(conn)
    if with_data:
        conn.execute("INSERT INTO daily(date, metric, value, source) VALUES ('2025-01-01', 'steps', 9000, 'garmin')")
    conn.commit()
    conn.close()


def test_move_refuses_a_folder_that_already_has_data(home, tmp_path):
    other = tmp_path / "autre"
    _fresh_install(other, with_data=True)
    with pytest.raises(datadir.DataDirError, match="contient déjà des données"):
        datadir.change(str(other), "deplacer")
    assert datadir.inspect(str(other))["modes"] == ["utiliser"]


def test_move_replaces_an_empty_database(home, tmp_path):
    """Une base vide (créée au premier démarrage d'une autre installation) n'est pas une donnée."""
    other = tmp_path / "autre"
    _fresh_install(other)
    assert datadir.summary(other) is None
    assert datadir.inspect(str(other))["modes"] == ["deplacer"]
    report = datadir.change(str(other), "deplacer")
    assert report["base"]["valeurs"] == 2 and config.data_dir() == other


def test_import_an_old_installation(tmp_path, monkeypatch):
    """Nouvelle installation (base vide) : on reprend les données de l'ancienne, sans changer de dossier."""
    monkeypatch.delenv("FOULEE_DATA", raising=False)
    new_home = tmp_path / "nouvelle"
    monkeypatch.setattr(config, "default_data_dir", lambda: new_home)
    old = tmp_path / "Foulee" / "data"
    _fresh_install(old, with_data=True)
    (old / "fit").mkdir()
    (old / "fit" / "9.fit").write_bytes(b"F" * 50)
    monkeypatch.setattr(datadir.Path, "home", classmethod(lambda cls: tmp_path))

    with db.session():
        pass  # le premier démarrage crée une base vide
    assert datadir.summary(new_home) is None
    found = datadir.previous_installs()
    assert [f["chemin"] for f in found] == [str(old)] and found[0]["contenu"]["valeurs"] == 1
    assert datadir.inspect(str(old))["modes"] == ["utiliser", "importer"]

    report = datadir.change(str(old), "importer")
    assert report["base"]["valeurs"] == 1 and report["fichiers_fit"] == 1
    assert config.data_dir() == new_home and config.data_dir_source() == "defaut"
    with db.session(readonly=True) as conn:
        assert conn.execute("SELECT value FROM daily").fetchone()[0] == 9000
    assert (old / "foulee.db").exists() and (new_home / "fit" / "9.fit").exists()
    # Une fois des données ici, un second import est refusé (il écraserait tout)
    with pytest.raises(datadir.DataDirError, match="déjà des données ici"):
        datadir.change(str(old), "importer")
    assert datadir.previous_installs()[0]["chemin"] == str(old)


def test_no_change_during_a_sync_or_when_imposed(home, tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "is_running", lambda: True)
    with pytest.raises(datadir.DataDirError, match="synchro est en cours"):
        datadir.change(str(tmp_path / "x"), "deplacer")
    monkeypatch.setenv("FOULEE_DATA", str(home))
    assert datadir.describe()["modifiable"] is False
    with pytest.raises(datadir.DataDirError, match="FOULEE_DATA"):
        datadir.change(str(tmp_path / "x"), "deplacer")


def test_claude_desktop_entry_pinned_to_the_old_folder_is_released(home, tmp_path, monkeypatch):
    claude_file = tmp_path / "claude" / "claude_desktop_config.json"
    claude_file.parent.mkdir()
    claude_file.write_text(json.dumps({"mcpServers": {"foulee": {
        "command": "python", "args": ["-m", "foulee", "mcp"], "env": {"PYTHONUTF8": "1", "FOULEE_DATA": str(home)}}}}))
    monkeypatch.setattr(claude_desktop, "config_paths", lambda: [claude_file])
    report = datadir.change(str(tmp_path / "nouveau"), "deplacer")
    assert report["claude"] == [str(claude_file)]
    env = json.loads(claude_file.read_text())["mcpServers"]["foulee"]["env"]
    assert "FOULEE_DATA" not in env and env["PYTHONUTF8"] == "1"


def test_web_api(home, tmp_path):
    client = TestClient(web.create_app())
    status = client.get("/api/dossier").json()
    assert status["chemin"] == str(home) and status["modifiable"]
    peek = client.post("/api/dossier/examiner", json={"chemin": str(tmp_path / "neuf")}, headers=WRITE).json()
    assert peek["probleme"] is None and not peek["existe"]
    bad = client.put("/api/dossier", json={"chemin": str(home), "mode": "deplacer"}, headers=WRITE)
    assert bad.status_code == 400 and "déjà le dossier" in bad.json()["detail"]
    moved = client.put("/api/dossier", json={"chemin": str(tmp_path / "neuf"), "mode": "deplacer"}, headers=WRITE)
    assert moved.status_code == 200 and moved.json()["dossier"]["chemin"] == str(tmp_path / "neuf")
    assert client.get("/api/bootstrap").json()["dossier_donnees"] == str(tmp_path / "neuf")
    # Depuis le réseau local, ce réglage reste fermé
    lan = TestClient(web.create_app(), client=("192.168.0.50", 50000))
    assert lan.put("/api/dossier", json={"chemin": str(home), "mode": "utiliser"},
                   headers={**WRITE, "Host": "192.168.0.19"}).status_code in (401, 403)
