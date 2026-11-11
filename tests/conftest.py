import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Chaque test travaille dans ses propres dossiers, sans clé ni base réelles."""
    monkeypatch.setenv("FOULEE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("FOULEE_SECRETS", str(tmp_path / "secrets"))
    monkeypatch.setenv("FOULEE_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("FOULEE_COFFRE", "fichier")  # jamais le vrai Gestionnaire d'identification Windows
    monkeypatch.setenv("FOULEE_TEST", "1")  # jamais le vrai registre Windows (démarrage avec la session)
    # Jamais la vraie configuration de Claude Desktop, ni les vrais dossiers de l'utilisateur
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    for name in ("FOULEE_ECOUTE", "FOULEE_MAJ", "FOULEE_HOTES", "FOULEE_DEPOT", "GITHUB_TOKEN", "FOULEE_GITHUB_TOKEN",
                 "FOULEE_PORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FOULEE_DEMO", "0")
    monkeypatch.delenv("GARMIN_PERSONAL_API_KEY", raising=False)
    no_proxy = ",".join(filter(None, [os.environ.get("NO_PROXY", ""), "127.0.0.1", "localhost"]))
    monkeypatch.setenv("NO_PROXY", no_proxy)
    monkeypatch.setenv("no_proxy", no_proxy)
    # Profils : rien ne passe d'un test à l'autre (profil de Claude Desktop, contrôle d'accès)
    from foulee import config

    monkeypatch.setattr(config, "_process_profile", None)
    monkeypatch.setattr(config, "_access_check", None)
    # Alerte « nouvelle version » : aucun résultat ne passe d'un test à l'autre
    from foulee import updates

    updates.WATCH.forget()
    yield tmp_path
    updates.WATCH.forget()
