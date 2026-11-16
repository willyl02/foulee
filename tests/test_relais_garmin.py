"""Séances sur la montre : la Training API de Garmin par le relais, contre un faux Garmin.

Le parcours complet : « Envoyer sur ma montre » → adresse d'autorisation de Garmin (PKCE) → retour sur le relais
→ jetons chiffrés → la séance part toute seule ; ensuite, directement. Et aussi : jeton renouvelé, séance
modifiée ou supprimée par le coach, envoi par le coach, délier, quitter le groupe.
"""

import base64
import hashlib
import json
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from foulee import coach, db, garmin_training, vault, workout_fit
from foulee.relais import garmin, store
from foulee.relais.app import create_relay_app

PASSWORD = "un-mot-de-passe-solide"
ADDRESS = "https://relais.test"
SECRET = "secret-de-test-du-club"


class FakeGarmin:
    """Ce que fait Garmin : jetons, identifiant, autorisations, séances et planifications."""

    def __init__(self):
        self.codes = {}          # code → code_challenge
        self.calls = []
        self.workouts = {}
        self.schedules = {}
        self.next_id = 1000
        self.permissions = ["WORKOUT_IMPORT"]
        self.refused_access = set()
        self.reject_zones = False
        self.registered = True
        self.tokens = 0

    def authorize(self, url):
        """L'élève accepte chez Garmin : renvoie (state, code) comme le ferait la redirection."""
        query = parse_qs(urlsplit(url).query)
        assert query["code_challenge_method"] == ["S256"] and query["client_id"] == ["id-club"]
        assert query["redirect_uri"] == [ADDRESS + "/garmin/retour"]
        code = f"code-{len(self.codes)}"
        self.codes[code] = query["code_challenge"][0]
        return query["state"][0], code

    def _new_tokens(self):
        self.tokens += 1
        return {"access_token": f"acces-{self.tokens}", "refresh_token": f"renouv-{self.tokens}",
                "expires_in": 86400, "refresh_token_expires_in": 7775998, "token_type": "bearer"}

    def __call__(self, method, url, *, headers, form=None, body=None):
        self.calls.append((method, url, form, body))
        if url.endswith("/oauth/token"):
            assert form["client_secret"] == SECRET
            if form["grant_type"] == "authorization_code":
                challenge = self.codes.pop(form["code"], None)
                verifier = form["code_verifier"]
                expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
                if challenge != expected:
                    return 400, {"error": "invalid_grant"}
                return 200, self._new_tokens()
            if form["refresh_token"] != f"renouv-{self.tokens}":
                return 400, {"error": "invalid_grant"}
            return 200, self._new_tokens()
        token = headers.get("Authorization", "")[7:]
        if token != f"acces-{self.tokens}" or token in self.refused_access:
            return 401, None
        path = urlsplit(url).path
        if path == "/wellness-api/rest/user/id":
            return 200, {"userId": "garmin-user-1"}
        if path == "/wellness-api/rest/user/permissions":
            return 200, self.permissions
        if path == "/wellness-api/rest/user/registration" and method == "DELETE":
            self.registered = False
            return 204, None
        if path == "/workoutportal/workout/v2" and method == "POST":
            if self.reject_zones and garmin_training.has_zones(body):
                return 400, {"message": "invalid target"}
            self.next_id += 1
            self.workouts[self.next_id] = body
            return 200, {"workoutId": self.next_id, **body}
        if path == "/training-api/schedule/" and method == "POST":
            assert body["workoutId"] in self.workouts
            self.next_id += 1
            self.schedules[self.next_id] = body
            return 200, self.next_id
        if path.startswith("/training-api/schedule/") and method == "DELETE":
            return (204, None) if self.schedules.pop(int(path.rsplit("/", 1)[1]), None) else (404, None)
        if path.startswith("/training-api/workout/v2/") and method == "DELETE":
            return (204, None) if self.workouts.pop(int(path.rsplit("/", 1)[1]), None) else (404, None)
        return 404, None


@pytest.fixture
def fake(monkeypatch):
    fake = FakeGarmin()
    monkeypatch.setattr(garmin, "transport", fake)
    return fake


@pytest.fixture
def relay(monkeypatch, fake):
    client = TestClient(create_relay_app())

    def send(method, url, *, headers, payload):
        path = url.split("://", 1)[1].split("/", 1)[1]
        response = client.request(method, "/" + path, headers=headers, json=payload)
        return response.status_code, response.json() if response.content else {}

    monkeypatch.setattr(coach, "transport", send)
    with store.session() as conn:
        store.create_account(conn, ident="sophie", name="Sophie R.", password=PASSWORD, role="coach", admin=True)
    garmin.save_app("id-club", SECRET, "relais.test")
    return client


def token(client, ident):
    return {"Authorization": "Bearer " + client.post("/api/v1/connexion", json={
        "identifiant": ident, "mot_de_passe": PASSWORD}).json()["jeton"]}


def join(client, coach_headers, ident, name):
    code = client.post("/api/v1/invitations", headers=coach_headers).json()["invitation"]["code"]
    res = client.post("/api/v1/inscription", json={"code": code, "identifiant": ident, "nom": name,
                                                   "mot_de_passe": PASSWORD})
    return {"Authorization": "Bearer " + res.json()["jeton"]}, res.json()["compte"]["id"]


BLOCKS = [{"nom": "Échauffement", "duree_min": 20, "pct_vma": 65, "genre": "echauffement"},
          {"nom": "Seuil", "repetitions": 3, "duree_min": 10, "pct_vma": 88, "recup_min": 2},
          {"nom": "Côtes", "repetitions": 6, "distance_m": 200, "zone_fc": 5, "recup_texte": "retour en trottinant"},
          {"nom": "Retour au calme", "duree_min": 10, "genre": "calme"}]


def propose(client, headers, student_id, day=None, title="Seuil 3 × 10"):
    day = day or (date.today() + timedelta(days=2))
    res = client.post("/api/v1/propositions", headers=headers, json={
        "eleves": [student_id], "date": day.isoformat(), "titre": title, "sport": "course", "blocs": BLOCKS,
        "consigne": "Régulier sur les 3 blocs"})
    assert res.status_code == 200, res.text
    return res.json()["propositions"][0]["id"]


def accept(client, fake, url):
    state, code = fake.authorize(url)
    return client.get("/garmin/retour", params={"state": state, "code": code})


# ----------------------------------------------------------------- la séance
def test_workout_matches_the_fit_file():
    item = {"titre": "Seuil 3 × 10", "sport": "course", "blocs": BLOCKS, "consigne": "Régulier"}
    workout = garmin_training.build(item, 16.0)
    steps = workout["segments"][0]["steps"]
    assert workout["sport"] == "RUNNING" and workout["workoutProvider"] == "Foulée"
    assert [s["type"] for s in steps] == ["WorkoutStep", "WorkoutRepeatStep", "WorkoutRepeatStep", "WorkoutStep"]
    warm, seuil, cotes, calm = steps
    assert warm["intensity"] == "WARMUP" and warm["durationType"] == "TIME" and warm["durationValue"] == 1200
    speed = 16 * 0.65 / 3.6
    assert warm["targetType"] == "PACE" and warm["targetValueLow"] < speed < warm["targetValueHigh"]
    assert seuil["repeatValue"] == 3 and [s["intensity"] for s in seuil["steps"]] == ["INTERVAL", "RECOVERY"]
    assert seuil["steps"][1]["durationValue"] == 120
    assert cotes["steps"][0]["durationType"] == "DISTANCE" and cotes["steps"][0]["durationValueType"] == "METER"
    assert cotes["steps"][0]["targetType"] == "HEART_RATE" and cotes["steps"][0]["targetValue"] == 5
    assert cotes["steps"][1]["durationType"] == "OPEN" and "trottinant" in cotes["steps"][1]["description"]
    assert calm["intensity"] == "COOLDOWN" and calm["targetType"] == "OPEN"
    orders = [warm["stepOrder"], seuil["stepOrder"], *[s["stepOrder"] for s in seuil["steps"]], cotes["stepOrder"]]
    assert orders == [1, 2, 3, 4, 5]
    # même découpage que le fichier .fit : autant d'étapes (boucles comprises)
    fit_steps = workout_fit.steps_for(item, 16.0)
    assert len(fit_steps) == 1 + 3 + 3 + 1
    # sans VMA : pas d'allure, le % de VMA reste écrit
    plain = garmin_training.build(item, None)["segments"][0]["steps"][0]
    assert plain["targetType"] == "OPEN" and "65 % VMA" in plain["description"]
    no_zones = garmin_training.build(item, 16.0, zones=False)
    assert not garmin_training.has_zones(no_zones) and garmin_training.has_zones(workout)


def test_too_many_steps_and_empty():
    with pytest.raises(workout_fit.WorkoutError):
        garmin_training.build({"blocs": []}, None)
    many = [{"nom": f"B{i}", "repetitions": 2, "duree_min": 1, "recup_min": 1} for i in range(40)]
    with pytest.raises(workout_fit.WorkoutError, match="100"):
        garmin_training.build({"blocs": many}, None)


# --------------------------------------------------------------- le parcours
def test_first_send_links_then_sends_directly(relay, fake):
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    first = propose(relay, sophie, lucas_id)
    assert relay.get("/api/v1/garmin", headers=lucas).json() == {
        "disponible": True, "relie": False, "relie_le": None, "coach_peut_envoyer": True}

    res = relay.post("/api/v1/garmin/envoyer", headers=lucas, json={"proposition": first, "vma_kmh": 16})
    assert res.status_code == 200 and res.json()["a_relier"] is True
    url = res.json()["adresse"]
    assert url.startswith("https://connect.garmin.com/oauth2Confirm?") and not fake.workouts

    page = accept(relay, fake, url)
    assert page.status_code == 200 and "Seuil 3 × 10" in page.text and "calendrier" in page.text
    assert page.headers["content-security-policy"].startswith("default-src 'none'")
    (workout,) = fake.workouts.values()
    assert workout["workoutName"] == "Seuil 3 × 10" and workout["description"] == "Régulier sur les 3 blocs"
    (schedule,) = fake.schedules.values()
    assert schedule["date"] == (date.today() + timedelta(days=2)).isoformat()
    pace = workout["segments"][0]["steps"][0]
    assert pace["targetType"] == "PACE" and abs(pace["targetValueLow"] - 16 * 0.65 / 3.6 * 0.97) < 0.001

    # les jetons sont chiffrés en base ; le Client Secret n'y est pas
    with store.session() as conn:
        raw = conn.execute("SELECT jetons FROM garmin_liens").fetchone()[0]
        assert "acces-1" not in raw and "renouv" not in raw
    dump = (store.db_path().read_bytes() + store.db_path().with_suffix(".db-wal").read_bytes()
            if store.db_path().with_suffix(".db-wal").exists() else store.db_path().read_bytes())
    assert b"acces-1" not in dump and SECRET.encode() not in dump

    # une 2e séance part directement
    second = propose(relay, sophie, lucas_id, date.today() - timedelta(days=1), "Footing")
    res = relay.post("/api/v1/garmin/envoyer", headers=lucas, json={"proposition": second, "vma_kmh": 16})
    assert res.json()["envoi"]["date"] == date.today().isoformat()  # passée : planifiée aujourd'hui
    assert len(fake.workouts) == 2
    mine = relay.get("/api/v1/moi/coach", headers=lucas).json()
    assert mine["montre"]["relie"] is True
    sent = {p["id"]: p["montre"] for p in mine["propositions"]}
    assert sent[first]["a_jour"] is True and sent[first]["par"] == "eleve"

    # renvoyer remplace la précédente (pas de doublon dans le calendrier)
    relay.post("/api/v1/garmin/envoyer", headers=lucas, json={"proposition": second, "vma_kmh": 16})
    assert len(fake.workouts) == 2 and len(fake.schedules) == 2

    # le lien d'autorisation ne sert qu'une fois
    assert relay.get("/garmin/retour", params={"state": "inconnu", "code": "x"}).status_code == 400


def test_refusal_and_missing_permission(relay, fake):
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    first = propose(relay, sophie, lucas_id)
    url = relay.post("/api/v1/garmin/envoyer", headers=lucas, json={"proposition": first}).json()["adresse"]
    state, _ = fake.authorize(url)
    page = relay.get("/garmin/retour", params={"state": state, "error": "access_denied"})
    assert page.status_code == 400 and "refusé" in page.text
    assert relay.get("/api/v1/garmin", headers=lucas).json()["relie"] is False

    fake.permissions = ["ACTIVITY_EXPORT"]
    url = relay.post("/api/v1/garmin/envoyer", headers=lucas, json={"proposition": first}).json()["adresse"]
    page = accept(relay, fake, url)
    assert "Workout import" in page.text and not fake.workouts and fake.registered is False
    assert relay.get("/api/v1/garmin", headers=lucas).json()["relie"] is False


def test_token_refresh_and_revoked_access(relay, fake):
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    first = propose(relay, sophie, lucas_id)
    accept(relay, fake, relay.post("/api/v1/garmin/relier", headers=lucas).json()["adresse"])
    # jeton expiré : renouvelé sans rien demander à l'élève
    with store.session() as conn:
        tokens = garmin._open(conn.execute("SELECT jetons FROM garmin_liens").fetchone()[0])
        tokens["expire"] = 0
        conn.execute("UPDATE garmin_liens SET jetons = ?", (garmin._seal(tokens),))
    res = relay.post("/api/v1/garmin/envoyer", headers=lucas, json={"proposition": first})
    assert "envoi" in res.json() and fake.tokens == 2
    # autorisation retirée chez Garmin : il faut relier à nouveau, et la séance attend
    fake.refused_access.add(f"acces-{fake.tokens}")
    fake.tokens += 1  # le renouvellement échoue aussi
    res = relay.post("/api/v1/garmin/envoyer", headers=lucas, json={"proposition": first}).json()
    assert res["a_relier"] is True and "relie" in res["raison"]
    assert relay.get("/api/v1/garmin", headers=lucas).json()["relie"] is False


def test_heart_rate_zones_refused_are_dropped(relay, fake):
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    first = propose(relay, sophie, lucas_id)
    accept(relay, fake, relay.post("/api/v1/garmin/relier", headers=lucas).json()["adresse"])
    fake.reject_zones = True
    assert "envoi" in relay.post("/api/v1/garmin/envoyer", headers=lucas, json={"proposition": first}).json()
    (workout,) = fake.workouts.values()
    assert not garmin_training.has_zones(workout)
    assert "zone FC 5" in json.dumps(workout, ensure_ascii=False)


def test_coach_sends_edits_and_deletes(relay, fake):
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    emma, emma_id = join(relay, sophie, "emma", "Emma T.")
    accept(relay, fake, relay.post("/api/v1/garmin/relier", headers=lucas).json()["adresse"])
    group = {e["id"]: e["montre"] for e in relay.get("/api/v1/groupe", headers=sophie).json()["eleves"]}
    assert group[lucas_id] == {"relie": True, "coach_peut_envoyer": True} and group[emma_id]["relie"] is False
    p_lucas, p_emma = propose(relay, sophie, lucas_id), propose(relay, sophie, emma_id)
    res = relay.post("/api/v1/garmin/coach", headers=sophie, json={"propositions": [p_lucas, p_emma]}).json()
    assert res["envoyees"] == ["Lucas B."] and res["non_reliees"] == ["Emma T."]
    fiche = relay.get(f"/api/v1/eleves/{lucas_id}/fiche", headers=sophie).json()
    assert fiche["montre"]["relie"] and fiche["propositions"][0]["montre"]["par"] == "coach"
    # le coach modifie la séance : elle est renvoyée telle quelle
    (old,) = fake.workouts
    relay.put(f"/api/v1/propositions/{p_lucas}", headers=sophie, json={
        "date": (date.today() + timedelta(days=3)).isoformat(), "titre": "Seuil 2 × 15", "sport": "course",
        "blocs": BLOCKS})
    (new,) = fake.workouts
    assert new != old and fake.workouts[new]["workoutName"] == "Seuil 2 × 15"
    assert list(fake.schedules.values())[0]["date"] == (date.today() + timedelta(days=3)).isoformat()
    # supprimée : elle quitte le calendrier Garmin
    relay.delete(f"/api/v1/propositions/{p_lucas}", headers=sophie)
    assert not fake.workouts and not fake.schedules
    # l'élève refuse que son coach envoie
    relay.put("/api/v1/garmin", headers=lucas, json={"coach_peut_envoyer": False})
    p2 = propose(relay, sophie, lucas_id)
    res = relay.post("/api/v1/garmin/coach", headers=sophie, json={"propositions": [p2]}).json()
    assert res["refusees"] == ["Lucas B."] and not fake.workouts
    # mais un élève ne peut pas envoyer pour un autre, ni le coach à la place de l'élève par cette route
    assert relay.post("/api/v1/garmin/envoyer", headers=emma, json={"proposition": p2}).status_code == 404
    assert relay.post("/api/v1/garmin/coach", headers=lucas, json={"propositions": [p2]}).status_code == 403


def test_unlink_and_leaving_revoke_at_garmin(relay, fake):
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    accept(relay, fake, relay.post("/api/v1/garmin/relier", headers=lucas).json()["adresse"])
    assert relay.delete("/api/v1/garmin", headers=lucas).json()["relie"] is False and fake.registered is False
    fake.registered = True
    accept(relay, fake, relay.post("/api/v1/garmin/relier", headers=lucas).json()["adresse"])
    relay.post("/api/v1/moi/quitter", headers=lucas, json={"mot_de_passe": PASSWORD})
    assert fake.registered is False
    with store.session() as conn:
        assert conn.execute("SELECT COUNT(*) FROM garmin_liens").fetchone()[0] == 0


def test_relay_without_garmin_app(relay, fake):
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    first = propose(relay, sophie, lucas_id)
    vault.delete_secret("relais-garmin-appli")
    res = relay.post("/api/v1/garmin/envoyer", headers=lucas, json={"proposition": first})
    assert res.status_code == 503 and "foulee relais garmin" in res.json()["detail"]
    assert relay.get("/api/v1/garmin", headers=lucas).json()["disponible"] is False


def test_foulee_button_end_to_end(relay, fake):
    """Depuis Foulée (l'élève) : le bouton, la liaison, puis l'envoi direct avec la VMA de Foulée."""
    sophie = token(relay, "sophie")
    code = relay.post("/api/v1/invitations", headers=sophie).json()["invitation"]["code"]
    with db.session() as conn:
        coach.join(conn, ADDRESS, code=code, ident="lucas", name="Lucas B.", password=PASSWORD)
        db.set_setting(conn, "vma_kmh", 17.5)
        student_id = coach.status(conn)["compte"]["id"]
    proposal = propose(relay, sophie, student_id)
    with db.session() as conn:
        res = coach.garmin_send(conn, proposal)
        assert res["a_relier"] is True
    accept(relay, fake, res["adresse"])
    with db.session() as conn:
        assert coach.garmin_status(conn)["relie"] is True
        assert "envoi" in coach.garmin_send(conn, proposal)
        sent = list(fake.workouts.values())[-1]
        assert abs(sent["segments"][0]["steps"][0]["targetValueLow"] - 17.5 * 0.65 / 3.6 * 0.97) < 0.001
        coach.garmin_settings(conn, False)
        assert coach.garmin_status(conn)["coach_peut_envoyer"] is False
        assert coach.garmin_unlink(conn)["relie"] is False


def test_cli_registers_the_garmin_app(monkeypatch, capsys):
    from foulee import cli

    answers = iter(["id-du-club", "relais.mon-club.com"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "le-secret")
    assert cli.main(["relais", "garmin"]) == 0
    out = capsys.readouterr().out
    assert "https://relais.mon-club.com/garmin/retour" in out and "le-secret" not in out
    assert garmin.app_settings() == {"client_id": "id-du-club", "client_secret": "le-secret",
                                     "adresse": "https://relais.mon-club.com"}
    assert cli.main(["relais", "garmin", "retirer"]) == 0 and garmin.app_settings() is None


def test_cli_tests_the_garmin_app(monkeypatch, capsys):
    from foulee import cli

    garmin.save_app("id-du-club", "le-secret", "relais.mon-club.com")
    replies = {"le-secret": (400, {"error": "invalid_grant"}), "mauvais": (401, {"error": "invalid_client"})}
    def answer(method, url, **kw):
        secret = kw["form"].get("client_secret")
        if secret is None:  # identifiants en en-tête « Basic »
            import base64
            secret = base64.b64decode(kw["headers"]["Authorization"].split()[1]).decode().split(":", 1)[1]
        return replies[secret]

    monkeypatch.setattr(garmin, "transport", answer)
    assert cli.main(["relais", "garmin", "tester"]) == 0
    out = capsys.readouterr().out
    assert "Garmin reconnaît l'appli" in out and "le-secret" not in out and "9 caractères" in out
    garmin.save_app("id-du-club", "mauvais", "relais.mon-club.com")
    assert cli.main(["relais", "garmin", "tester"]) == 1
    assert "invalid_client" in capsys.readouterr().out
    with pytest.raises(garmin.GarminError) as refused:
        garmin._token_request({"grant_type": "authorization_code", "code": "x"})
    assert "invalid_client" in str(refused.value) and "garmin tester" in str(refused.value)
    garmin.vault.delete_secret("relais-garmin-appli")


def test_token_service_falls_back_to_the_other_address(monkeypatch):
    garmin.save_app("id-du-club", "le-secret", "relais.mon-club.com")
    monkeypatch.delenv("FOULEE_GARMIN_TOKEN_URL", raising=False)
    calls = []

    def answer(method, url, **kw):
        calls.append(url)
        if url == garmin.TOKEN_URL:
            return 401, "<!doctype html><html><head><title>HTTP Status 401 – Unauthorized</title></head></html>"
        return 400, {"error": "invalid_grant"}

    monkeypatch.setattr(garmin, "transport", answer)
    result = garmin.check_app()
    assert result["ok"] and calls == [garmin.TOKEN_URL, garmin.TOKEN_URL, garmin.TOKEN_URL_ALT]
    assert garmin._reason("<html><title>HTTP Status 401 – Unauthorized</title></html>") == "HTTP Status 401 – Unauthorized"
    garmin.vault.delete_secret("relais-garmin-appli")
