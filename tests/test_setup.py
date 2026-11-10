"""Saisie de la clé, messages d'erreur sans fuite, configuration de Claude Desktop, verrou de synchro."""

import json
import os

import pytest
from fake_garmin import FakeGarmin

from foulee import cli, keyinput, sync, vault
from foulee.garmin.client import garmin_detail

KEY = "GCDC_0f1e2d3c-test.4b5a6978-cle.SecretDeTest"


# --------------------------------------------------------------- nettoyage
@pytest.mark.parametrize("raw, notes", [
    (f"  {KEY} \r\n", []),
    (f"{KEY[:20]}\n{KEY[20:]}", ["2 morceaux recollés"]),
    (f"​{KEY}﻿", []),
    (f"« {KEY} »", ["guillemets retirés"]),
    (KEY + KEY, ["clé présente deux fois, un seul exemplaire gardé"]),
    (f"{KEY}\r\n{KEY}\r\n", ["2 morceaux recollés", "clé présente deux fois, un seul exemplaire gardé"]),
])
def test_normalize_key(raw, notes):
    assert keyinput.normalize_key(raw) == (KEY, notes)


def test_key_checks_never_reveal_the_key():
    assert keyinput.key_problem("") == "aucun texte"
    assert keyinput.key_problem("\x16").startswith("1 caractère impossible")  # Ctrl+V reçu comme caractère
    assert keyinput.key_problem("GCDC_abcGCDC_def").startswith("2 clés")
    assert keyinput.key_problem("GCDC_clé") is not None
    assert keyinput.key_problem(KEY) is None
    description = keyinput.describe_key(KEY)
    assert description == f"{len(KEY)} caractères, commence bien par GCDC_"
    assert "Secret" not in description
    assert "ne commence pas" in keyinput.describe_key("abc")


def test_garmin_detail_masks_secrets_and_html():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
    text = f"<html><head><style>p{{}}</style></head><body><p>Refusé {KEY} et {jwt}</p></body></html>"
    detail = garmin_detail(text, KEY)
    assert KEY not in detail and jwt not in detail and "<" not in detail
    assert detail.startswith("Refusé")
    assert garmin_detail("Bad key GCDC_autre-cle-123", None) == "Bad key [masqué]"
    assert len(garmin_detail("x" * 1000)) == 200


# ------------------------------------------------------------ foulee setup
@pytest.fixture
def garmin(monkeypatch):
    with FakeGarmin(days=10, activities=2) as fake:
        monkeypatch.setenv("GARMIN_PERSONAL_API_BASE_URL", fake.url)
        yield fake


@pytest.fixture
def console(monkeypatch):
    """Simule la console Windows : réponses aux invites masquées et presse-papiers."""
    state = {"answers": [], "clipboard": None, "cleared": False}

    def fake_getpass(prompt=""):
        return state["answers"].pop(0) if state["answers"] else "q"

    def fake_clear():
        state["cleared"] = True
        return True

    monkeypatch.setattr("getpass.getpass", fake_getpass)
    monkeypatch.setattr(keyinput, "clipboard_available", lambda: state["clipboard"] is not None)
    monkeypatch.setattr(keyinput, "read_clipboard", lambda: state["clipboard"])
    monkeypatch.setattr(keyinput, "clear_clipboard", fake_clear)
    return state


def test_setup_reads_clipboard_and_clears_it(garmin, console, capsys):
    console["clipboard"] = f"{KEY[:30]}\r\n{KEY[30:]}\r\n"  # clé copiée sur deux lignes
    console["answers"] = [""]  # Entrée
    assert cli.main(["setup", "--sans-import"]) == 0
    assert vault.get_key() == KEY
    assert console["cleared"]
    out = capsys.readouterr().out
    assert "lue dans le presse-papiers" in out and "commence bien par GCDC_" in out
    assert "Garmin accepte la clé" in out
    assert KEY not in out


def test_setup_accepts_a_key_pasted_twice(garmin, console, capsys):
    console["answers"] = [KEY + KEY]  # collée deux fois dans l'invite masquée (pas de presse-papiers lisible)
    assert cli.main(["setup", "--sans-import"]) == 0
    assert vault.get_key() == KEY
    assert not console["cleared"]  # la clé a été collée : on ne touche pas au presse-papiers
    assert "un seul exemplaire gardé" in capsys.readouterr().out


def test_setup_explains_a_refusal_without_showing_the_key(garmin, console, capsys):
    refused = "GCDC_refuse-0000.1111.secret"
    console["clipboard"] = refused
    console["answers"] = ["", "q"]  # Entrée, puis abandon après le refus
    assert cli.main(["setup", "--sans-import"]) == 1
    assert vault.get_key() is None
    assert not console["cleared"]  # on garde la clé copiée pour réessayer
    out = capsys.readouterr().out
    assert "Garmin a refusé cette clé (HTTP 401)" in out
    assert "Réponse de Garmin" in out and "[clé masquée]" in out
    assert refused not in out


def test_setup_rejects_control_characters_without_calling_garmin(garmin, console, capsys):
    console["answers"] = ["\x16", "q"]  # Ctrl+V arrivé comme caractère
    assert cli.main(["setup", "--sans-import"]) == 1
    assert "ne peut pas être une clé Garmin" in capsys.readouterr().out
    assert garmin.requests == []  # rien n'est parti chez Garmin


# --------------------------------------------------- configuration de Claude
def test_claude_config_finds_the_packaged_app_and_keeps_its_settings(tmp_path, monkeypatch, capsys):
    local, roaming = tmp_path / "Local", tmp_path / "Roaming"
    packaged = local / "Claude-Data" / "claude_pzs8sxrjxfjjc"
    packaged.mkdir(parents=True)
    packaged_config = packaged / "claude_desktop_config.json"
    packaged_config.write_text(json.dumps({"preferences": {"theme": "dark"}, "mcpServers": {"autre": {"command": "x"}}}),
                               encoding="utf-8")
    old_config = roaming / "Claude" / "claude_desktop_config.json"
    old_config.parent.mkdir(parents=True)
    old_config.write_text("﻿{}", encoding="utf-8")  # BOM laissé par un éditeur
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(cli, "claude_desktop_running", lambda: False)

    assert cli.claude_config_paths()[0] == packaged_config
    assert cli.main(["claude-config", "--ecrire"]) == 0
    for path in (packaged_config, old_config):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        data = json.loads(raw)
        assert data["mcpServers"]["foulee"]["args"] == ["-m", "foulee", "mcp"]
    data = json.loads(packaged_config.read_text(encoding="utf-8"))
    assert data["preferences"] == {"theme": "dark"} and "autre" in data["mcpServers"]
    assert list(packaged.glob("claude_desktop_config.json.sauvegarde-*"))

    assert cli.main(["claude-config"]) == 0
    assert "Foulée présent" in capsys.readouterr().out

    assert cli.main(["claude-config", "--retirer"]) == 0
    data = json.loads(packaged_config.read_text(encoding="utf-8"))
    assert "foulee" not in data["mcpServers"] and "autre" in data["mcpServers"]


def test_claude_config_creates_the_file_of_a_fresh_packaged_install(tmp_path, monkeypatch):
    local = tmp_path / "Local"
    packaged = local / "Claude-Data" / "claude_pzs8sxrjxfjjc"
    packaged.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(cli, "claude_desktop_running", lambda: False)
    assert cli.main(["claude-config", "--ecrire"]) == 0
    assert "foulee" in json.loads((packaged / "claude_desktop_config.json").read_text(encoding="utf-8"))["mcpServers"]
    assert not (tmp_path / "Roaming" / "Claude").exists()


# ---------------------------------------------------------- verrou de synchro
def test_sync_lock_left_by_a_killed_process_is_released(tmp_path):
    lock = sync._lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("999999999", encoding="ascii")  # processus disparu
    assert not sync.is_running()
    with sync._Lock():
        assert lock.read_text(encoding="ascii") == str(os.getpid())
        assert sync.is_running()
        with pytest.raises(sync.SyncBusy):
            with sync._Lock():
                pass
    assert not lock.exists()
