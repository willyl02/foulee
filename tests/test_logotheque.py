"""Logothèque (logos ACCT livrés, logos importés et nommés, choisis pour le club et l'application partenaire) et
couleurs des zones."""

import io
import shutil

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from foulee import club, config, db, logotheque, partenaire, reglages, zones

HEADERS = {"X-Foulee": "1"}


def png(size=(200, 120), color=(200, 30, 40, 255)):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    for x in range(10, size[0] - 10):
        for y in range(10, size[1] - 10):
            image.putpixel((x, y), color)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def client():
    from foulee.web import create_app

    return TestClient(create_app())


def test_builtin_acct_logos_are_listed_and_can_be_chosen():
    web = client()
    lib = web.get("/api/logos").json()
    builtin = [x for x in lib["logos"] if x["integre"]]
    assert [x["id"] for x in builtin] == ["acct", "acct-1904"] and all(x["v"] for x in builtin)
    assert lib["club"] is None and lib["partenaire"] is None and lib["accueil"] is True
    assert web.get("/api/logos/acct/image").status_code == 200
    assert web.get("/api/logos/u99/image").status_code == 404
    assert web.get("/api/logos/..%2Fsecret/image").status_code == 404

    lib = web.put("/api/logos/choix", json={"club": "acct", "partenaire": "acct-1904"}, headers=HEADERS).json()
    assert lib["club"] == "acct" and lib["partenaire"] == "acct-1904"
    boot = web.get("/api/bootstrap").json()
    assert boot["club_logo"] and boot["partenaire"]["logo"] and boot["logotheque"]["club"] == "acct"
    own = (logotheque.BUILTIN_DIR / "acct.png").read_bytes()
    assert web.get(f"/api/club/logo?v={boot['club_logo']}").content == own
    assert web.get("/api/sites/partenaire/logo").content == (logotheque.BUILTIN_DIR / "acct-1904.png").read_bytes()
    # sans logo : le globe pour l'application partenaire, rien pour le club ; les logos restent dans la liste
    web.put("/api/logos/choix", json={"club": None, "partenaire": None}, headers=HEADERS)
    boot = web.get("/api/bootstrap").json()
    assert boot["club_logo"] is None and boot["partenaire"]["logo"] is None
    assert web.get("/api/club/logo").status_code == 404
    assert web.put("/api/logos/choix", json={"club": "u42"}, headers=HEADERS).status_code == 400
    assert web.delete("/api/logos/acct", headers=HEADERS).status_code == 400  # livré avec Foulée : il reste


def test_named_import_joins_both_lists_once_and_can_be_removed():
    web = client()
    res = web.put("/api/logos/import?nom=%20Mon%20%20club%20&pour=club", content=png(), headers={**HEADERS, "Content-Type": "image/png"})
    assert res.status_code == 200
    lib = res.json()
    added = lib["ajoute"]
    entry = next(x for x in lib["logos"] if x["id"] == added)
    assert entry == {"id": added, "nom": "Mon club", "integre": False, "v": entry["v"]} and lib["club"] == added
    assert res.json()["transparent"] is True
    # le même fichier n'entre qu'une fois, même sous un autre nom ; il sert aussi à l'application partenaire
    again = web.put("/api/logos/import?nom=Doublon&pour=partenaire", content=png(), headers={**HEADERS, "Content-Type": "image/png"}).json()
    assert again["ajoute"] == added and again["partenaire"] == added
    assert len([x for x in again["logos"] if not x["integre"]]) == 1
    # un nom est demandé ; une image illisible est refusée
    assert "nom" in web.put("/api/logos/import?nom=", content=png((90, 90)), headers=HEADERS).json()["detail"]
    assert web.put("/api/logos/import?nom=X", content=b"rien", headers=HEADERS).status_code == 400
    assert web.put("/api/logos/import?nom=X&pour=ailleurs", content=png((90, 90)), headers=HEADERS).status_code == 400
    # retiré de la liste : plus de logo là où il servait
    lib = web.delete(f"/api/logos/{added}", headers=HEADERS).json()
    assert lib["club"] is None and lib["partenaire"] is None and all(x["integre"] for x in lib["logos"])
    assert web.get(f"/api/logos/{added}/image").status_code == 404


def test_home_banner_switch():
    web = client()
    assert web.put("/api/logos/choix", json={"accueil": False}, headers=HEADERS).json()["accueil"] is False
    assert web.get("/api/bootstrap").json()["logotheque"]["accueil"] is False
    assert logotheque.home() is False
    logotheque.set_home(True)
    assert logotheque.home() is True


def test_logos_from_before_the_library_move_in():
    folder = config.data_dir()
    old_club = png((300, 300))
    (folder / "club-logo.png").write_bytes(old_club)
    (folder / "sites-logos").mkdir(parents=True, exist_ok=True)
    (folder / "sites-logos" / "partenaire.png").write_bytes(png((96, 96), (20, 90, 200, 255)))
    lib = logotheque.listing()
    names = {x["nom"]: x["id"] for x in lib["logos"] if not x["integre"]}
    assert set(names) == {"Logo de mon club", "Logo de l'application partenaire"}
    assert lib["club"] == names["Logo de mon club"] and lib["partenaire"] == names["Logo de l'application partenaire"]
    assert not (folder / "club-logo.png").exists() and not (folder / "sites-logos" / "partenaire.png").exists()
    assert club.logo_path().read_bytes() == old_club and club.logo_version()
    assert partenaire.logo_version("partenaire")
    config.set_demo(True)  # le mode démo a sa propre logothèque
    try:
        assert logotheque.listing()["club"] is None
    finally:
        config.set_demo(False)
    assert logotheque.listing()["club"] == names["Logo de mon club"]


def test_settings_export_carries_imported_logos_and_choices():
    logotheque.add("Club des amis", png(), use="partenaire")
    logotheque.choose("club", "acct")
    logotheque.set_home(False)
    with db.session() as conn:
        data = reglages.export(conn)
    assert data["logotheque"]["club"] == "acct" and data["logotheque"]["partenaire"] == "importe:0"
    assert data["logotheque"]["importes"][0]["nom"] == "Club des amis" and data["logo_club"]
    shutil.rmtree(config.data_dir() / "logos")
    assert logotheque.listing()["club"] is None
    with db.session() as conn:
        report = reglages.import_(conn, data, parts={"logo"})
    lib = logotheque.listing()
    imported = [x for x in lib["logos"] if not x["integre"]]
    assert report["logo"] is True and lib["club"] == "acct" and lib["accueil"] is False
    assert [x["nom"] for x in imported] == ["Club des amis"] and lib["partenaire"] == imported[0]["id"]


def test_old_export_with_a_single_club_logo_still_imports():
    with db.session() as conn:
        report = reglages.import_(conn, {"foulee_reglages": 1, "logo_club": __import__("base64").b64encode(png()).decode()},
                                  parts={"logo"})
    lib = logotheque.listing()
    assert report["logo"] is True and lib["club"] and next(x for x in lib["logos"] if x["id"] == lib["club"])["nom"] == "Logo de mon club"


def test_zone_colors_setting():
    assert zones.clean_colors(None) is None
    assert zones.clean_colors("bleus") == {"style": "bleus"}
    perso = ["#9EA8A3", "#2a78d6", "#13a06e", "#f08a1c", "#d3263a"]
    assert zones.clean_colors({"style": "perso", "perso": perso})["perso"][0] == "#9ea8a3"
    assert zones.clean_colors({"style": "garmin", "perso": perso})["style"] == "garmin"  # les siennes, gardées pour plus tard
    for bad in ({"style": "rose"}, {"style": "perso"}, {"style": "perso", "perso": perso[:4]},
                {"style": "perso", "perso": [*perso[:4], "rouge"]}, 12):
        with pytest.raises(ValueError, match="Couleurs des zones"):
            zones.clean_colors(bad)
    with db.session() as conn:
        assert db.get_settings(conn)["couleurs_zones"] is None
        saved, recompute = reglages.apply(conn, {"couleurs_zones": {"style": "bleus"}})
        assert saved["couleurs_zones"] == {"style": "bleus"} and recompute is False
        with pytest.raises(reglages.SettingsError, match="Couleurs des zones"):
            reglages.apply(conn, {"couleurs_zones": {"style": "perso", "perso": ["#fff"] * 5}})
