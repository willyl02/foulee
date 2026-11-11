"""Mon club : numéro de club, saisons FFA, fiche collée depuis athle.fr, licence et vue « Mon club »."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from foulee import club, db, mcp_server, reglages, views, web

WRITE = {"X-Foulee": "1"}
SHEET_LINES = """AC Exemple
Retour
Classement
Coordonnées et contacts
Président
DUPONT Jean
Adresse du siège
Mr Jean Dupont
1 Rue Des Lilas
75001 Paris
Téléphone
06 12 34 56 78
Site internet
http://ac-exemple.fr
Nos pratiques détaillées
Jeunes
Piste
"""
SHEET_INLINE = """Accueil > Trouver un club > AC Exemple
Club n° 012345
Coordonnées et contacts
Président : DUPONT Jean
Adresse : Mr Jean Dupont 1 Rue Des Lilas 75001 Paris
Téléphone : +33 6 12 34 56 78
E-mail : contact@ac-exemple.fr
Site internet : www.ac-exemple.fr
https://www.athle.fr/clubs/10000
"""


def new_client() -> TestClient:
    return TestClient(web.create_app())


# ------------------------------------------------------------------ saisie
@pytest.mark.parametrize("value, expected", [("2024", "002024"), (" 012 345 ", "012345"), (12345, "012345")])
def test_club_number_is_padded_like_on_the_licence(value, expected):
    assert club.clean_number(value) == expected


@pytest.mark.parametrize("value, message", [("", "Indique le numéro"), ("12a45", "6 chiffres"), ("1234567", "6 chiffres")])
def test_bad_club_numbers_are_explained(value, message):
    with pytest.raises(club.ClubError, match=message):
        club.clean_number(value)


def test_ffa_seasons_start_on_september_first():
    assert club.season(dt.date(2026, 8, 31)) == 2026
    assert club.season(dt.date(2026, 9, 1)) == 2027
    assert club.season(dt.date(2027, 1, 15)) == 2027
    assert club.season_label(2027) == "2026-2027"


def test_ranking_link_is_the_one_of_the_ffa_site():
    assert club.classement_url("002024", 2027) == (
        "https://www.athle.fr/bases/liste.aspx?frmbase=cclubs&frmmode=2&frmespace=&frmtypeclub=M"
        "&frmsaison=2027&frmnclub=002024&frmruptures=")


def test_settings_are_cleaned():
    cleaned = club.clean({
        "actif": True, "numero": "12345", "nom": "  AC   Exemple ", "site": "ac-exemple.fr",
        "page": "www.athle.fr/clubs/10000", "email": "contact@ac-exemple.fr",
        "licence": {"numero": "12 345 67", "type": "Course sur route", "expire": "2027-08-31"},
        "inconnu": "ignoré",
    })
    assert cleaned["numero"] == "012345" and cleaned["nom"] == "AC Exemple"
    assert cleaned["site"] == "https://ac-exemple.fr" and cleaned["page"] == "https://www.athle.fr/clubs/10000"
    assert cleaned["licence"] == {"numero": "1234567", "type": "Autre", "expire": "2027-08-31"}
    assert "inconnu" not in cleaned
    # Case décochée : le numéro peut manquer, rien n'est perdu de ce qui a été saisi
    assert club.clean({"actif": False, "nom": "AC Exemple"})["numero"] == ""
    assert club.clean(None) is None and club.clean({}) is None


@pytest.mark.parametrize("value, message", [
    ({"actif": True}, "Indique le numéro"),
    ({"actif": True, "numero": "1", "page": "https://example.com/club"}, "athle.fr"),
    ({"actif": True, "numero": "1", "email": "pas une adresse"}, "e-mail illisible"),
    ({"actif": True, "numero": "1", "site": "deux mots"}, "Adresse web illisible"),
    ({"actif": True, "numero": "1", "licence": {"expire": "31/08/2027"}}, "Date de fin"),
    ({"actif": True, "numero": "1", "nom": "x" * 81}, "trop long"),
    ("002024", "illisible"),
])
def test_bad_settings_are_refused(value, message):
    with pytest.raises(club.ClubError, match=message):
        club.clean(value)


# -------------------------------------------------------------- fiche collée
def test_sheet_with_labels_on_their_own_lines():
    assert club.parse_sheet(SHEET_LINES) == {
        "nom": "AC Exemple", "president": "DUPONT Jean", "adresse": "1 Rue Des Lilas", "code_postal": "75001",
        "ville": "Paris", "telephone": "06 12 34 56 78", "site": "http://ac-exemple.fr",
    }


def test_sheet_on_one_line_per_field_with_page_and_number():
    found = club.parse_sheet(SHEET_INLINE)
    assert found["nom"] == "AC Exemple"  # dernier élément du fil d'Ariane
    assert found["numero"] == "012345"
    assert found["adresse"] == "1 Rue Des Lilas"  # sans le destinataire, ni le code postal et la ville
    assert (found["code_postal"], found["ville"]) == ("75001", "Paris")
    assert found["telephone"] == "06 12 34 56 78"  # +33 6… remis au format français
    assert found["email"] == "contact@ac-exemple.fr"
    assert found["site"] == "https://www.ac-exemple.fr"
    assert found["page"] == "https://www.athle.fr/clubs/10000"


def test_sheet_copied_from_a_table():
    found = club.parse_sheet("Running Club 77\nPrésident\tMARTIN Paul\nCode postal\t77000\nVille\tMelun\n"
                             "Tél.\t01.23.45.67.89\nSite internet\tNon renseigné\n")
    assert found == {"nom": "Running Club 77", "president": "MARTIN Paul", "code_postal": "77000", "ville": "Melun",
                     "telephone": "01 23 45 67 89"}


def test_sheet_without_colons_and_from_the_licence():
    assert club.parse_sheet("Président DURAND Marie\nTéléphone 0612345678\ncontact : jean@exemple.fr") == {
        "president": "DURAND Marie", "telephone": "06 12 34 56 78", "email": "jean@exemple.fr"}
    # Le texte de la licence : le numéro de club, pas un nom de club
    assert club.parse_sheet("LICENCE 2026-2027\nNom : X\nN° Club : 2024") == {"numero": "002024"}


@pytest.mark.parametrize("text", ["", "bonjour", "   \n\n "])
def test_unrelated_text_gives_nothing(text):
    assert club.parse_sheet(text) == {}


def test_parsed_sheet_can_be_saved_as_is():
    for sheet in (SHEET_LINES, SHEET_INLINE):
        found = club.parse_sheet(sheet)
        saved = club.clean({**found, "actif": True, "numero": found.get("numero", "1")})
        assert all(saved[key] for key in found if key != "numero")


# ------------------------------------------------------------------ résumé
def test_summary_links_and_licence_reminder():
    settings = club.clean({"actif": True, "numero": "2024", "nom": "AC Exemple", "adresse": "1 rue des Lilas",
                           "code_postal": "75001", "ville": "Paris", "telephone": "06 12 34 56 78",
                           "email": "contact@ac-exemple.fr",
                           "licence": {"type": "Athlé Running", "expire": "2027-08-31"}})
    early = club.summary(settings, today=dt.date(2026, 11, 11))
    assert early["saison"] == 2027 and early["saison_label"] == "2026-2027"
    assert early["liens"]["classement"] == club.classement_url("002024", 2027)
    assert early["liens"]["classement_precedent"] == club.classement_url("002024", 2026)
    assert early["liens"]["saison_precedente"] == "2025-2026"
    assert early["liens"]["telephone"] == "tel:+33612345678"
    assert early["liens"]["email"] == "mailto:contact@ac-exemple.fr"
    assert early["liens"]["carte"].startswith("https://www.openstreetmap.org/search?query=1%20rue%20des%20Lilas")
    assert early["liens"]["page"] is None and early["liens"]["trouver"] == club.FIND_URL
    assert early["adresse_complete"] == "1 rue des Lilas, 75001 Paris"
    assert early["licence"]["renseignee"] and not early["licence"]["a_renouveler"]

    soon = club.summary(settings, today=dt.date(2027, 8, 10))["licence"]
    assert soon["a_renouveler"] and not soon["expiree"] and soon["jours_restants"] == 21
    late = club.summary(settings, today=dt.date(2027, 9, 2))["licence"]
    assert late["expiree"] and late["jours_restants"] == -2


def test_summary_without_licence_or_when_off():
    plain = club.clean({"actif": True, "numero": "2024"})
    licence = club.summary(plain, today=dt.date(2027, 8, 20))["licence"]
    # Pas de licence saisie : la fin de saison sert de date, sans rappel
    assert licence["expire"] == "2027-08-31" and not licence["renseignee"] and not licence["a_renouveler"]
    assert club.summary({**plain, "actif": False}) is None
    assert club.summary(None) is None


# ------------------------------------------------------- réglages et vue
def view_ids(client: TestClient) -> list[str]:
    return [view["id"] for view in client.get("/api/views").json()]


def test_ticking_the_box_adds_the_view_right_after_home():
    client = new_client()
    assert "club" not in view_ids(client) and client.get("/api/bootstrap").json()["club"] is None
    saved = client.put("/api/settings", json={"club": {"actif": True, "numero": "2024", "nom": "AC Exemple"}},
                       headers=WRITE)
    assert saved.status_code == 200, saved.text
    assert saved.json()["reglages"]["club"]["numero"] == "002024"
    ids = view_ids(client)
    assert ids[ids.index("accueil") + 1] == "club" and ids.count("club") == 1
    boot = client.get("/api/bootstrap").json()
    assert boot["club"]["nom"] == "AC Exemple" and boot["club"]["liens"]["classement"].endswith("frmnclub=002024&frmruptures=")
    assert "Athlé Running" in boot["club_licences"]
    view = next(v for v in boot["vues"] if v["id"] == "club")
    assert view["name"] == "Mon club" and view["icon"] == "club" and view["spec"]["tuiles"][0]["type"] == "club"

    # Décocher retire la vue mais garde ce qui a été saisi ; recocher la remet une seule fois
    client.put("/api/settings", json={"club": {"actif": False, "numero": "2024", "nom": "AC Exemple"}}, headers=WRITE)
    assert "club" not in view_ids(client)
    assert client.get("/api/settings").json()["club"]["nom"] == "AC Exemple"
    assert client.get("/api/bootstrap").json()["club"] is None
    for _ in range(2):
        client.put("/api/settings", json={"club": {"actif": True, "numero": "2024"}}, headers=WRITE)
    assert view_ids(client).count("club") == 1


def test_bad_club_settings_are_refused_with_a_message():
    client = new_client()
    refused = client.put("/api/settings", json={"club": {"actif": True, "numero": "1234567"}}, headers=WRITE)
    assert refused.status_code == 400 and "6 chiffres" in refused.json()["detail"]
    assert "club" not in view_ids(client)


def test_deleted_view_comes_back_when_saving_the_club():
    client = new_client()
    client.put("/api/settings", json={"club": {"actif": True, "numero": "2024"}}, headers=WRITE)
    client.delete("/api/views/club", headers=WRITE)
    assert "club" not in view_ids(client)
    client.put("/api/settings", json={"club": {"actif": True, "numero": "2024"}}, headers=WRITE)
    assert "club" in view_ids(client)


def test_restoring_default_views_keeps_the_club_view():
    client = new_client()
    client.put("/api/settings", json={"club": {"actif": True, "numero": "2024"}}, headers=WRITE)
    client.post("/api/views/reset", headers=WRITE)
    assert "club" in view_ids(client)


def test_club_travels_with_the_settings_export():
    with db.session() as conn:
        reglages.apply(conn, {"club": {"actif": True, "numero": "2024", "nom": "AC Exemple"}})
        exported = reglages.export(conn, with_views=False, with_photo=False)
        assert exported["reglages"]["club"]["numero"] == "002024"
        reglages.apply(conn, {"club": None})
        assert "club" not in [v["id"] for v in views.list_views(conn)]
        reglages.import_(conn, exported, parts={"reglages"})
        assert db.get_settings(conn)["club"]["nom"] == "AC Exemple"
        assert "club" in [v["id"] for v in views.list_views(conn)]


def test_sheet_endpoint():
    client = new_client()
    found = client.post("/api/club/fiche", json={"texte": SHEET_INLINE}, headers=WRITE).json()
    assert found["champs"]["president"] == "DUPONT Jean" and found["trouves"] == len(found["champs"])
    too_long = client.post("/api/club/fiche", json={"texte": "x" * 20001}, headers=WRITE)
    assert too_long.status_code == 400 and "trop long" in too_long.json()["detail"]


def test_club_tile_is_available_in_the_editor():
    tile = next(t for t in views.TILE_TYPES if t["type"] == "club")
    assert tile["label"] == "Mon club" and tile["icone"] in views.ICONS


def test_claude_sees_the_club_and_can_set_it():
    assert "club_resume" not in mcp_server.lire_reglages()
    done = mcp_server.modifier_reglages({"club": {"actif": True, "numero": "2024", "nom": "AC Exemple"}})
    assert done["reglages"]["club"]["numero"] == "002024"
    summary = mcp_server.lire_reglages()["club_resume"]
    assert summary["liens"]["classement"].endswith("frmnclub=002024&frmruptures=")
    with db.session(readonly=True) as conn:
        assert "club" in [v["id"] for v in views.list_views(conn)]
    refused = mcp_server.modifier_reglages({"club": {"actif": True, "numero": "abc"}})
    assert "6 chiffres" in refused["erreur"]
