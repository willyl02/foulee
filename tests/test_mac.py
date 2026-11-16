"""L'application Mac, simulée sur n'importe quel système : dossiers, Trousseau, ouverture de session, mises à jour."""

import os
import plistlib
import sys
import types
from pathlib import Path

import pytest

from foulee import config, desktop, updates, vault


@pytest.fixture
def mac(monkeypatch, tmp_path):
    """Un Mac : sys.platform « darwin » et ce Python rangé dans un Foulee.app."""
    bundle = tmp_path / "Applications" / "Foulee.app"
    python = bundle / "Contents" / "Resources" / "python" / "bin" / "python3"
    python.parent.mkdir(parents=True)
    python.write_text("")
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "executable", str(python))
    return bundle


def test_folders_on_a_mac(mac, monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "william")
    assert config._local_base() == tmp_path / "william" / "Library" / "Application Support" / "Foulee"
    assert config.is_desktop()


def test_the_key_goes_to_the_keychain(mac, monkeypatch):
    stored = {}
    fake = types.SimpleNamespace(set_password=lambda s, u, v: stored.__setitem__((s, u), v),
                                 get_password=lambda s, u: stored.get((s, u)),
                                 delete_password=lambda s, u: stored.pop((s, u)))
    monkeypatch.setitem(sys.modules, "keyring", fake)
    monkeypatch.delenv("FOULEE_COFFRE")
    assert vault.set_key("GCDC_cle-de-test").startswith("Trousseau de macOS")
    assert vault.get_key() == "GCDC_cle-de-test" and not vault._plain_file().exists()
    assert vault.delete_key() and vault.get_key() is None


def test_without_keychain_a_protected_file(mac, monkeypatch):
    def refuse(*args):
        raise RuntimeError("Trousseau verrouillé")

    monkeypatch.setitem(sys.modules, "keyring", types.SimpleNamespace(set_password=refuse, get_password=refuse,
                                                                      delete_password=refuse))
    monkeypatch.delenv("FOULEE_COFFRE")
    assert vault.set_key("GCDC_cle-de-test").startswith("fichier protégé")
    if os.name == "posix":  # (les droits Unix n'ont pas de sens quand ce test tourne sous Windows)
        assert vault._plain_file().stat().st_mode & 0o777 == 0o600
    assert vault.get_key() == "GCDC_cle-de-test"
    assert vault.delete_key() and not vault._plain_file().exists()


def test_launch_at_login_with_a_launch_agent(mac, monkeypatch, tmp_path):
    monkeypatch.setenv("FOULEE_LAUNCH_AGENTS", str(tmp_path / "LaunchAgents"))
    assert desktop.mac_app_bundle() == mac.resolve()
    assert desktop.startup_supported() and not desktop.startup_enabled()
    desktop.set_startup(True)
    with open(desktop.launch_agent_file(), "rb") as handle:
        agent = plistlib.load(handle)
    assert agent["Label"] == "fr.foulee.app" and agent["RunAtLoad"] is True
    assert agent["ProgramArguments"] == [str(mac.resolve() / "Contents" / "MacOS" / "Foulee"), "--demarrage"]
    assert desktop.startup_enabled()
    desktop.set_startup(False)
    assert not desktop.startup_enabled() and not desktop.launch_agent_file().exists()


def test_no_launch_agent_outside_the_app(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert desktop.mac_app_bundle() is None
    assert not desktop.startup_supported()  # depuis le code source, pendant les tests : jamais


def test_mac_updates_pick_the_right_dmg(mac, monkeypatch):
    def release(tag, *names):
        return {"tag_name": tag, "prerelease": "b" in tag, "assets": [{"name": n, "url": n} for n in names]}

    files = ["Foulee-Setup-9.0.0.exe", "Foulee-9.0.0-mac-arm64.dmg", "Foulee-9.0.0-mac-intel.dmg", "SHA256SUMS.txt"]
    releases = [release("v9.0.0", *files), release("v9.1.0", "Foulee-Setup-9.1.0.exe", "SHA256SUMS.txt")]
    monkeypatch.setattr(config, "is_packaged", lambda: True)
    assert updates.mode() == "exe"
    monkeypatch.setattr(updates, "mac_arch", lambda: "arm64")
    best = updates.pick(releases, "stable")
    assert best["version"] == "9.0.0" and best["installateur"]["name"] == "Foulee-9.0.0-mac-arm64.dmg"  # 9.1.0 : pas de Mac
    monkeypatch.setattr(updates, "mac_arch", lambda: "intel")
    assert updates.pick(releases, "stable")["installateur"]["name"] == "Foulee-9.0.0-mac-intel.dmg"


def test_mac_update_replaces_the_app_after_foulee_quits(mac, monkeypatch, tmp_path):
    launched = []
    monkeypatch.setattr(updates.subprocess, "Popen", lambda args, **kw: launched.append((args, kw)))
    dmg = tmp_path / "maj" / "Foulee-9.0.0-mac-arm64.dmg"
    dmg.parent.mkdir()
    dmg.write_bytes(b"dmg")
    updates.launch_installer(dmg)
    (args, options), = launched
    script = Path(args[1])
    assert args[0] == "/bin/bash" and script.exists() and args[3] == str(dmg) and args[4] == str(mac.resolve())
    assert options["start_new_session"] is True
    text = script.read_text()
    assert "hdiutil attach" in text and 'ditto "$mnt/Foulee.app" "$app"' in text and "--apres-maj" in text


def test_menu_bar_and_window_on_a_mac(mac, monkeypatch, tmp_path):
    edge = tmp_path / "Edge"
    edge.write_text("")
    monkeypatch.setenv("FOULEE_NAVIGATEUR_APP", str(edge))
    assert desktop.app_browser() == str(edge)
    monkeypatch.setattr(desktop, "_mac_app_browser", lambda: None)
    monkeypatch.delenv("FOULEE_NAVIGATEUR_APP")
    assert desktop.app_browser() is None  # ni Chrome ni Edge : le navigateur habituel
