"""Profil (prénom, logo, photo) et sauvegarde des réglages entre deux installations."""

import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from foulee import db, profile, reglages, web

WRITE = {"X-Foulee": "1"}


def image_bytes(size=(600, 400), fmt="PNG", exif=False) -> bytes:
    out = io.BytesIO()
    image = Image.new("RGB", size, (200, 30, 40))
    kwargs = {}
    if exif:
        data = Image.Exif()
        data[0x010F] = "Téléphone"     # fabricant
        data[0x8825] = {2: (48.0, 24.0, 0.0)}  # position GPS : ne doit pas survivre
        kwargs["exif"] = data
    image.save(out, fmt, **kwargs)
    return out.getvalue()


def test_photo_is_cropped_resized_and_cleaned():
    client = TestClient(web.create_app())
    assert client.get("/api/profil/photo").status_code == 404
    saved = client.put("/api/profil/photo", content=image_bytes(exif=True, fmt="JPEG"),
                       headers={**WRITE, "Content-Type": "image/jpeg"})
    assert saved.status_code == 200 and saved.json()["photo"]
    stored = client.get("/api/profil/photo")
    assert stored.headers["content-type"] == "image/jpeg" and stored.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(stored.content)) as image:
        assert image.size == (256, 256) and image.format == "JPEG"
        assert not image.getexif()  # ni lieu, ni appareil


@pytest.mark.parametrize("payload, message", [
    (b"pas une image", "pas une image lisible"),
    (image_bytes((20, 20)), "entre 32 et"),
    (image_bytes(fmt="BMP"), "non accepté"),
    (b"", "vide"),
])
def test_bad_photos_are_refused(payload, message):
    client = TestClient(web.create_app())
    refused = client.put("/api/profil/photo", content=payload, headers={**WRITE, "Content-Type": "image/png"})
    assert refused.status_code == 400 and message in refused.json()["detail"]
    assert not profile.photo_path().exists()


def test_logo_and_first_name():
    client = TestClient(web.create_app())
    state = client.put("/api/profil", json={"prenom": " William ", "logo": "chrono"}, headers=WRITE).json()
    assert state["prenom"] == "William" and state["prenom_affiche"] == "William" and state["logo"] == "chrono"
    assert client.put("/api/profil", json={"logo": "inconnu"}, headers=WRITE).json()["logo"] == "foulee"
    client.put("/api/profil/photo", content=image_bytes(), headers={**WRITE, "Content-Type": "image/png"})
    client.put("/api/profil", json={"logo": "photo"}, headers=WRITE)
    after = client.delete("/api/profil/photo", headers=WRITE).json()
    assert not after["photo"] and after["logo"] == "foulee"  # plus de photo : retour au logo de Foulée
    assert client.get("/api/bootstrap").json()["profil"]["logo"] == "foulee"


def test_first_name_from_garmin():
    with db.session() as conn:
        db.put_raw(conn, "garmin", "activity", "1", {"activityId": 1, "ownerFullName": "Alex Coureur",
                                                     "ownerProfileImageUrlLarge": "https://exemple.s3.amazonaws.com/p.jpg"})
        conn.commit()
        assert profile.first_name(conn, db.get_settings(conn)) == "Alex"
        assert profile.garmin_identity(conn)["photo_url"].startswith("https://")
        db.put_raw(conn, "garmin", "activity", "2", {"activityId": 2, "ownerProfileImageUrlLarge": "http://ailleurs.example/p.jpg"})
        conn.execute("UPDATE raw SET fetched_at = '2999-01-01 00:00:00' WHERE key = '2'")
        assert profile.garmin_identity(conn)["photo_url"] is None  # adresse non HTTPS ou d'un autre site : ignorée


def test_export_then_import_elsewhere(tmp_path, monkeypatch):
    client = TestClient(web.create_app())
    client.put("/api/settings", json={"vma_kmh": 15.2, "canal_maj": "beta", "zones_fc": {"methode": "pct_reserve"}},
               headers=WRITE)
    client.put("/api/profil", json={"prenom": "William", "logo": "montagne"}, headers=WRITE)
    client.put("/api/profil/photo", content=image_bytes(), headers={**WRITE, "Content-Type": "image/png"})
    client.post("/api/views", json={"name": "Ma vue", "spec": {"tuiles": [{"type": "kpi", "params": {"metrique": "hrv_night"}}]}},
                headers=WRITE)
    exported = client.get("/api/reglages/export")
    assert "attachment" in exported.headers["content-disposition"]
    data = exported.json()
    assert data["foulee_reglages"] == 1 and "canal_maj" not in data["reglages"] and data["photo"]
    assert "historique_depuis" not in data["reglages"]
    text = json.dumps(data)
    assert "GCDC_" not in text and "mot_de_passe" not in text

    # Une autre installation, toute neuve
    monkeypatch.setenv("FOULEE_DATA", str(tmp_path / "serveur"))
    other = TestClient(web.create_app())
    assert not profile.photo_path().exists()
    report = other.post("/api/reglages/import", json={"donnees": data}, headers=WRITE).json()
    assert report["photo"] and report["vues"] >= 7 and report["recalcul"]
    boot = other.get("/api/bootstrap").json()
    assert boot["reglages"]["vma_kmh"] == 15.2 and boot["reglages"]["zones_fc"]["methode"] == "pct_reserve"
    assert boot["reglages"]["canal_maj"] == "stable"  # le canal reste propre à chaque installation
    assert boot["profil"]["prenom"] == "William" and boot["profil"]["photo"]
    assert "ma-vue" in [v["id"] for v in boot["vues"]]

    # Seulement les réglages, et un fichier qui n'en est pas un
    again = other.post("/api/reglages/import", json={"donnees": data, "parties": ["reglages"]}, headers=WRITE).json()
    assert again["vues"] == 0 and not again["photo"]
    bad = other.post("/api/reglages/import", json={"donnees": {"name": "vue"}}, headers=WRITE)
    assert bad.status_code == 400


def test_import_skips_bad_values():
    with db.session() as conn:
        report = reglages.import_(conn, {"foulee_reglages": 1, "reglages": {
            "vma_kmh": 99, "fc_repos": 52, "inconnu": 1, "zones_fc": {"methode": "magie"}}})
        assert report["reglages"] == 1 and db.get_settings(conn)["fc_repos"] == 52
        assert any(item.startswith("vma_kmh") for item in report["ignores"])
        assert "inconnu" in report["ignores"]


def test_demo_keeps_its_own_photo(monkeypatch):
    client = TestClient(web.create_app())
    client.put("/api/profil/photo", content=image_bytes(), headers={**WRITE, "Content-Type": "image/png"})
    monkeypatch.setenv("FOULEE_DEMO", "1")
    assert not profile.photo_path().exists() and profile.photo_path().name == "profil-demo.jpg"
    too_big = client.put("/api/profil/photo", content=b"0" * 16, headers={**WRITE, "Content-Type": "image/png",
                                                                        "Content-Length": str(20 * 1024 * 1024)})
    assert too_big.status_code in (400, 413)
