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
    monkeypatch.setenv("FOULEE_DEMO", "0")
    monkeypatch.delenv("GARMIN_PERSONAL_API_KEY", raising=False)
    no_proxy = ",".join(filter(None, [os.environ.get("NO_PROXY", ""), "127.0.0.1", "localhost"]))
    monkeypatch.setenv("NO_PROXY", no_proxy)
    monkeypatch.setenv("no_proxy", no_proxy)
    yield tmp_path
