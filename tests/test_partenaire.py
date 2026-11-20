"""Application partenaire (0.8.2) : le site du club dans Foulée, réglable et rangé dans la colonne de gauche."""

import pytest
from fastapi.testclient import TestClient

from foulee import partenaire
from foulee.web import create_app


def test_defaults_and_cleaning():
    assert partenaire.resolve(None) == {"actif": False, "nom": "Club en ligne", "adresse": "https://app.clubenligne.fr/"}
    custom = partenaire.clean({"actif": 1, "nom": "  ACCT   club ", "adresse": "app.clubenligne.fr/entrainements"})
    assert custom == {"actif": True, "nom": "ACCT club", "adresse": "https://app.clubenligne.fr/entrainements"}
    assert partenaire.clean({"actif": True, "nom": "", "adresse": ""})["adresse"] == "https://app.clubenligne.fr/"
    for bad in ("javascript:alert(1)", "ftp://exemple.fr", "https://", "https://exemple .fr"):
        with pytest.raises(partenaire.PartnerError):
            partenaire.clean({"actif": True, "adresse": bad})
    assert partenaire.resolve({"adresse": "javascript:alert(1)"})["adresse"] == "https://app.clubenligne.fr/"


def test_setting_reaches_the_menu():
    client = TestClient(create_app())
    headers = {"X-Foulee": "1"}
    assert client.get("/api/bootstrap").json()["partenaire"]["actif"] is False
    saved = client.put("/api/settings", headers=headers, json={"partenaire": {
        "actif": True, "nom": "ACCT", "adresse": "https://app.clubenligne.fr/competitions"}})
    assert saved.status_code == 200 and saved.json()["reglages"]["partenaire"]["nom"] == "ACCT"
    boot = client.get("/api/bootstrap").json()["partenaire"]
    assert boot == {"actif": True, "nom": "ACCT", "adresse": "https://app.clubenligne.fr/competitions"}
    bad = client.put("/api/settings", headers=headers, json={"partenaire": {"actif": True, "adresse": "javascript:x"}})
    assert bad.status_code == 400 and "https://" in bad.json()["detail"]
