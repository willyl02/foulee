"""Application partenaire (0.8.2) : le site du club dans Foulée, réglable et rangé dans la colonne de gauche."""

import pytest
from fastapi.testclient import TestClient

from foulee import partenaire
from foulee.web import create_app


def test_defaults_and_cleaning():
    assert partenaire.resolve(None) == {"actif": False, "nom": "Club en ligne", "adresse": "https://app.clubenligne.fr/",
                                        "logo": None}
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
    assert boot == {"actif": True, "nom": "ACCT", "adresse": "https://app.clubenligne.fr/competitions", "logo": None}
    bad = client.put("/api/settings", headers=headers, json={"partenaire": {"actif": True, "adresse": "javascript:x"}})
    assert bad.status_code == 400 and "https://" in bad.json()["detail"]


# ------------------------------------------------------------------ sites externes (0.8.3)
def _png(width: int, height: int, color=(211, 38, 58, 255)) -> bytes:
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGBA", (width, height), color).save(out, "PNG")
    return out.getvalue()


def test_external_sites_are_cleaned_and_numbered():
    assert partenaire.resolve_sites(None) == []
    sites = partenaire.clean_sites([{"nom": "  FFA ", "adresse": "www.athle.fr"},
                                    {"id": "s1", "nom": "Ligue", "adresse": "https://ligue.exemple.fr/", "actif": False},
                                    {"id": "s1", "nom": "Doublon", "adresse": "https://doublon.exemple.fr/"}])
    assert [(s["id"], s["nom"], s["actif"]) for s in sites] == [("s2", "FFA", True), ("s1", "Ligue", False), ("s3", "Doublon", True)]
    assert sites[0]["adresse"] == "https://www.athle.fr"
    for bad in ([{"nom": "", "adresse": "https://a.fr"}], [{"nom": "X", "adresse": "javascript:alert(1)"}],
                [{"nom": f"S{i}", "adresse": "https://a.fr"} for i in range(9)], {"nom": "X"}):
        with pytest.raises(partenaire.PartnerError):
            partenaire.clean_sites(bad)


def test_external_sites_reach_the_menu_with_their_logo():
    client = TestClient(create_app())
    headers = {"X-Foulee": "1"}
    assert client.get("/api/bootstrap").json()["sites_externes"] == []
    saved = client.put("/api/settings", headers=headers, json={"sites_externes": [
        {"nom": "FFA", "adresse": "https://www.athle.fr/"}, {"nom": "Ligue", "adresse": "https://ligue.exemple.fr/"}]})
    assert saved.status_code == 200
    ids = [s["id"] for s in saved.json()["reglages"]["sites_externes"]]
    assert ids == ["s1", "s2"]
    # le logo : un PNG carré, entre 64 et 512 pixels, 200 Ko au plus ; gardé à 96 pixels
    assert client.put("/api/sites/s1/logo", headers=headers, content=_png(256, 256)).status_code == 200
    boot = client.get("/api/bootstrap").json()["sites_externes"]
    assert boot[0]["logo"] and boot[1]["logo"] is None and boot[0]["actif"] is True
    logo = client.get("/api/sites/s1/logo")
    assert logo.status_code == 200 and logo.headers["content-type"] == "image/png"
    from PIL import Image
    import io

    assert Image.open(io.BytesIO(logo.content)).size == (96, 96)
    for data, word in [(_png(40, 40), "entre 64"), (_png(600, 600), "entre 64"), (_png(300, 120), "carré"),
                       (b"pas une image", "PNG")]:
        refused = client.put("/api/sites/s2/logo", headers=headers, content=data)
        assert refused.status_code == 400 and word in refused.json()["detail"]
    assert client.put("/api/sites/x9/logo", headers=headers, content=_png(64, 64)).status_code == 400
    assert client.put("/api/sites/../logo", headers=headers, content=_png(64, 64)).status_code in (400, 404, 405)
    assert client.delete("/api/sites/s1/logo", headers=headers).json() == {"id": "s1", "logo": None}
    assert client.get("/api/sites/s1/logo").status_code == 404


def test_partner_app_can_have_its_own_logo():
    client = TestClient(create_app())
    headers = {"X-Foulee": "1"}
    assert client.get("/api/bootstrap").json()["partenaire"]["logo"] is None
    assert client.put("/api/sites/partenaire/logo", headers=headers, content=_png(128, 128)).status_code == 200
    app = client.get("/api/bootstrap").json()["partenaire"]
    assert app["logo"] and app["nom"] == "Club en ligne"
    assert client.get("/api/sites/partenaire/logo").status_code == 200
    client.delete("/api/sites/partenaire/logo", headers=headers)
    assert client.get("/api/bootstrap").json()["partenaire"]["logo"] is None
