"""Groupes de niveau du coach (selon la VMA) et bibliothèque de séances (0.8.2)."""

from foulee import coach, db
from foulee.relais import club, store
from test_relais_club import PASSWORD, relay, token  # noqa: F401  (le relais du club, en mémoire)


def _student(relay, coach_token, ident, name, vma):
    code = relay.post("/api/v1/invitations", headers=coach_token).json()["invitation"]["code"]
    joined = relay.post("/api/v1/inscription", json={"code": code, "identifiant": ident, "nom": name,
                                                       "mot_de_passe": PASSWORD}).json()
    me = {"Authorization": f"Bearer {joined['jeton']}"}
    relay.put("/api/v1/partage/accord", headers=me, json={"seances": True})
    if vma:
        relay.put("/api/v1/partage", headers=me, json={"profil": {"vma_kmh": vma}, "seances": [], "jours": []})
    return joined["compte"]["id"], me


def test_levels_by_vma_with_club_test_and_manual_placement(relay):
    sophie = token(relay, "sophie")
    _student(relay, sophie, "lucas", "Lucas", 17.2)
    emma, _ = _student(relay, sophie, "emma", "Emma", 13.1)
    paul, _ = _student(relay, sophie, "paul", "Paul", None)  # ne partage pas sa VMA
    page = relay.put("/api/v1/niveaux", headers=sophie, json={"niveaux": [
        {"nom": "Groupe 1", "vma_min": 16, "couleur": "rouge"},
        {"nom": "Groupe 2", "vma_min": 14, "vma_max": 16},
        {"nom": "Groupe 3", "vma_max": 14}]}).json()
    where = {s["nom"]: (s["niveau"] or {}).get("nom") for s in page["eleves"]}
    assert where == {"Lucas": "Groupe 1", "Emma": "Groupe 3", "Paul": None}
    assert [s["nom"] for s in page["eleves"]] == ["Lucas", "Emma", "Paul"]  # VMA décroissante

    # Le test VMA du club prime sur celle qu'il partage ; Paul, sans VMA, est placé par son test
    page = relay.put(f"/api/v1/eleves/{paul}/niveau", headers=sophie, json={"vma_test": "15,5"}).json()
    paul_row = next(s for s in page["eleves"] if s["id"] == paul)
    assert paul_row["vma_kmh"] == 15.5 and paul_row["vma_source"] == "test" and paul_row["niveau"]["nom"] == "Groupe 2"
    # Placée à la main (elle revient de blessure) : Emma reste en groupe 2, quelle que soit sa VMA
    g2 = next(g for g in page["niveaux"] if g["nom"] == "Groupe 2")
    page = relay.put(f"/api/v1/eleves/{emma}/niveau", headers=sophie, json={"niveau": g2["id"]}).json()
    emma_row = next(s for s in page["eleves"] if s["id"] == emma)
    assert emma_row["niveau"]["nom"] == "Groupe 2" and emma_row["niveau_force"] is True
    group = relay.get("/api/v1/groupe", headers=sophie).json()["eleves"]
    assert {s["nom"]: s["niveau"]["nom"] for s in group if s["niveau"]} == {"Lucas": "Groupe 1", "Emma": "Groupe 2",
                                                                            "Paul": "Groupe 2"}
    # Groupe supprimé : Emma retrouve celui de sa VMA
    page = relay.put("/api/v1/niveaux", headers=sophie, json={"niveaux": [g for g in page["niveaux"]
                                                                          if g["nom"] != "Groupe 2"]}).json()
    assert {s["nom"]: (s["niveau"] or {}).get("nom") for s in page["eleves"]} == {
        "Lucas": "Groupe 1", "Emma": "Groupe 3", "Paul": None}
    # La montre : sans VMA partagée, le relais prend celle du test du club
    from foulee.relais import garmin

    with store.session() as conn:
        assert garmin._shared_vma(conn, paul) == 15.5
    bad = relay.put("/api/v1/niveaux", headers=sophie, json={"niveaux": [{"nom": "X", "vma_min": 17, "vma_max": 15}]})
    assert bad.status_code == 400
    student = token(relay, "lucas")
    assert relay.get("/api/v1/niveaux", headers=student).status_code == 403


def test_template_library_rename_and_edit(relay):
    sophie = token(relay, "sophie")
    blocks = [{"genre": "corps", "nom": "Seuil", "repetitions": 3, "duree_min": 10, "pct_vma": 85, "recup_min": 2}]
    saved = relay.post("/api/v1/modeles", headers=sophie, json={"titre": "Seuil 3 × 10", "blocs": blocks}).json()
    other = relay.post("/api/v1/modeles", headers=sophie, json={"titre": "VMA courte", "blocs": blocks}).json()
    tid = next(t["id"] for t in other["modeles"] if t["titre"] == "Seuil 3 × 10")
    renamed = relay.put(f"/api/v1/modeles/{tid}", headers=sophie, json={"titre": "Seuil 3 × 10 min"}).json()["modeles"]
    assert {t["titre"] for t in renamed} == {"Seuil 3 × 10 min", "VMA courte"}
    assert next(t for t in renamed if t["id"] == tid)["blocs"][0]["repetitions"] == 3  # le contenu ne bouge pas
    clash = relay.put(f"/api/v1/modeles/{tid}", headers=sophie, json={"titre": "VMA courte"})
    assert clash.status_code == 400 and "déjà" in clash.json()["detail"]
    edited = relay.put(f"/api/v1/modeles/{tid}", headers=sophie, json={
        "blocs": [{**blocks[0], "repetitions": 4}], "consigne": "Régulier"}).json()["modeles"]
    mine = next(t for t in edited if t["id"] == tid)
    assert mine["blocs"][0]["repetitions"] == 4 and mine["consigne"] == "Régulier" and len(saved["modeles"]) == 1


def test_the_app_lets_the_new_coach_pages_through():
    assert coach.PROXY_PATHS.match("niveaux") and coach.PROXY_PATHS.match("eleves/12/niveau")
    assert not coach.PROXY_PATHS.match("niveaux/../comptes")
    assert db and club.COLORS
