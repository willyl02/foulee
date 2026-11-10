"""Désinstallation : Claude Desktop, et « effacer mes données » sans jamais toucher aux fichiers de l'utilisateur."""

import json
import subprocess
import sys

from foulee import claude_desktop, config, db, uninstall, vault


def test_claude_entry_is_removed_only_if_it_runs_this_installation(tmp_path, monkeypatch):
    mine = tmp_path / "mine.json"
    other = tmp_path / "other.json"
    mine.write_text(json.dumps({"mcpServers": {"foulee": claude_desktop.mcp_entry(), "autre": {"command": "x"}}}))
    other.write_text(json.dumps({"mcpServers": {"foulee": {"command": "C:\\\\ailleurs\\\\python.exe", "args": []}}}))
    monkeypatch.setattr(claude_desktop, "config_targets", lambda: [mine, other, tmp_path / "absent.json"])
    report = claude_desktop.write(remove=True, only_mine=True)
    assert report["modifies"] == [str(mine)] and not report["erreurs"]
    assert json.loads(mine.read_text())["mcpServers"] == {"autre": {"command": "x"}}
    assert "foulee" in json.loads(other.read_text())["mcpServers"]
    assert not (tmp_path / "absent.json").exists()  # on ne crée rien en retirant


def test_erase_everything_keeps_the_user_files(tmp_path, monkeypatch):
    chosen = tmp_path / "Sport"  # dossier choisi par l'utilisateur, qui contient aussi ses affaires
    chosen.mkdir()
    (chosen / "mes-notes.txt").write_text("à garder")
    (chosen / "logs").mkdir()
    (chosen / "logs" / "journal-perso.md").write_text("à garder aussi")
    monkeypatch.setenv("FOULEE_DATA", str(chosen))
    with db.session():
        pass
    (config.fit_dir() / "123.fit").write_bytes(b"FIT")
    (config.log_dir() / "web.log").write_text("log")
    (chosen / "diagnostic-20261110-120000.txt").write_text("rapport")
    vault.set_key("GCDC_cle-de-test")
    config.save_user_config({"dossier_donnees": str(chosen)})

    removed = uninstall.erase_everything()
    assert any(r.endswith("foulee.db") for r in removed) and "secret « garmin »" in removed
    assert sorted(p.name for p in chosen.rglob("*")) == ["journal-perso.md", "logs", "mes-notes.txt"]
    assert vault.get_key() is None
    assert not (config.user_config_dir() / "config.json").exists()


def test_before_uninstall_command(tmp_path):
    with db.session():
        pass
    result = subprocess.run([sys.executable, "-m", "foulee", "avant-desinstallation", "--effacer-donnees"],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (config.data_dir() / "foulee.db").exists()
    assert not (config.data_dir() / "logs").exists()  # aucun journal écrit pendant le ménage
