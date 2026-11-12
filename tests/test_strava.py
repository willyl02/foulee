"""Strava, en lecture seule : connexion, synchro dans un cache de 48 heures, doublons avec Garmin, renfo noté
dans la description, sources des tuiles, et jamais rien pour Claude Desktop (règles de l'API de Strava)."""

import datetime as dt
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fake_strava import CLIENT_ID, CLIENT_SECRET, FakeStrava, run
from fastapi.testclient import TestClient

from foulee import db, sync, utilisateurs, vault, web
from foulee.strava import cache, client, parse

WRITE = {"X-Foulee": "1"}
TODAY = dt.date.today()
HEVY = """Pecs et dos
Bench Press (Barbell)
Set 1: 60 kg x 10
Set 2: 60 kg x 8

Pull Up
Set 1: 8 reps
Set 2: 6 reps
Logged with Hevy"""


def at(days_ago: int, hour: int = 9, minute: int = 0) -> dt.datetime:
    day = TODAY - dt.timedelta(days=days_ago)
    return dt.datetime(day.year, day.month, day.day, hour, minute)


@pytest.fixture
def strava(monkeypatch):
    with FakeStrava() as fake:
        monkeypatch.setenv("FOULEE_STRAVA_API", f"{fake.url}/api/v3")
        monkeypatch.setenv("FOULEE_STRAVA_OAUTH", f"{fake.url}/oauth")
        yield fake


def connect(http: TestClient, fake: FakeStrava, *, scope: str | None = None):
    """Le parcours de l'interface : appli enregistrée, « Connecter », « Autoriser » chez Strava, retour."""
    saved = http.put("/api/strava/appli", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}, headers=WRITE)
    assert saved.status_code == 200, saved.text
    started = http.post("/api/strava/connexion", json={"origine": "http://testserver"}, headers=WRITE)
    assert started.status_code == 200, started.text
    query = {k: v[0] for k, v in parse_qs(urlparse(started.json()["url"]).query).items()}
    assert query["scope"] == "read,activity:read_all"  # lecture seule
    assert query["redirect_uri"] == "http://testserver/strava/retour" and query["client_id"] == CLIENT_ID
    if scope:
        fake.scope = scope
    back = http.get("/strava/retour", params={"code": fake.issue_code(), "state": query["state"],
                                              "scope": scope or fake.scope}, follow_redirects=False)
    assert back.status_code == 303 and back.headers["location"].startswith("/#/reglages?section=strava")
    return back


def wait(http: TestClient) -> dict:
    """Attend la fin de la synchro ; garde le message de connexion (affiché une seule fois)."""
    note = None
    for _ in range(300):
        info = http.get("/api/strava").json()
        note = note or info.get("note")
        if not info["synchro"]["en_cours"]:
            return {**info, **({"note": note} if note else {})}
        time.sleep(0.05)
    raise AssertionError("synchro Strava trop longue")


def add_garmin(activity_id: str, start: dt.datetime, minutes: float, sport: str = "course", name: str = "Footing"):
    with db.session() as conn:
        conn.execute("INSERT INTO activities(id, source, source_id, start_local, date, sport, name, duration_s, "
                     "elapsed_s, distance_m) VALUES (?, 'garmin', ?, ?, ?, ?, ?, ?, ?, 8000)",
                     (f"garmin:{activity_id}", activity_id, start.isoformat(sep=" "), start.date().isoformat(), sport,
                      name, minutes * 60, minutes * 60))


def sources_of(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        out[row["source"]] = out.get(row["source"], 0) + 1
    return out


# --------------------------------------------------------------- connexion
def test_connect_imports_read_only(strava):
    strava.activities += [run(101, at(3), 45, km=8.2), run(102, at(1), 60, km=10.1, name="Sortie longue")]
    http = TestClient(web.create_app())
    connect(http, strava)
    info = wait(http)
    assert info["connecte"] and info["note"]["statut"] == "connecte" and info["cache"]["seances"] == 2
    assert info["client_id"] == CLIENT_ID and CLIENT_SECRET not in json.dumps(info)
    rows = http.get("/api/activities").json()
    assert sources_of(rows) == {"strava": 2}
    assert rows[0]["name"] == "Sortie longue" and rows[0]["appareil"] == "COROS PACE 3"
    # Les données ne se lisent qu'en GET ; les seuls POST servent à l'autorisation
    assert {m for m, path, _ in strava.requests if path.startswith("/api/")} == {"GET"}
    assert {path for m, path, _ in strava.requests if m == "POST"} == {"/oauth/token"}
    # Jamais de jeton ni de Secret vers l'interface
    boot = http.get("/api/bootstrap").json()
    assert boot["strava"]["connecte"] and strava.access not in json.dumps(boot) and strava.refresh not in json.dumps(info)
    assert [c["cle"] for c in boot["connexions"]] == ["strava"]  # sans clé Garmin, pas de pastille Garmin rouge


def test_app_is_set_by_the_principal_from_the_machine(strava):
    http = TestClient(web.create_app())
    bad = http.put("/api/strava/appli", json={"client_id": "abc", "client_secret": CLIENT_SECRET}, headers=WRITE)
    assert bad.status_code == 400 and "nombre" in bad.json()["detail"]
    bad = http.put("/api/strava/appli", json={"client_id": CLIENT_ID, "client_secret": "trop-court"}, headers=WRITE)
    assert bad.status_code == 400 and "40" in bad.json()["detail"]
    lan = TestClient(web.create_app(), client=("192.168.0.50", 50000))
    assert lan.put("/api/strava/appli", json={}, headers={**WRITE, "Host": "192.168.0.19"}).status_code in (401, 403)
    ruben = utilisateurs.create("Ruben")
    other = TestClient(web.create_app())
    other.post("/api/utilisateurs/choisir", json={"id": ruben["id"]}, headers=WRITE)
    refused = other.put("/api/strava/appli", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
                        headers=WRITE)
    assert refused.status_code == 403 and "principal" in refused.json()["detail"]


def test_unchecked_activities_scope_is_refused(strava):
    http = TestClient(web.create_app())
    connect(http, strava, scope="read")
    info = http.get("/api/strava").json()
    assert not info["connecte"] and "doit rester cochée" in info["note"]["message"]
    assert strava.revoked and not client.load()  # accès retiré chez Strava, jetons oubliés


def test_private_sessions_hidden_is_said(strava):
    http = TestClient(web.create_app())
    connect(http, strava, scope="read,activity:read")
    info = wait(http)
    assert info["connecte"] and not info["seances_privees"] and "Moi uniquement" in info["note"]["message"]


# --------------------------------------------------------------- doublons
def test_garmin_copies_count_once_and_lend_their_strava_title(strava):
    add_garmin("555", at(2, 18), 50, name="Seuil 3 × 2 km")
    add_garmin("556", at(1, 7), 40)
    strava.activities += [
        run(201, at(2, 18), 50, km=10, device="Garmin Forerunner 965", external_id="garmin_push_555",
            name="Seuil du mardi", description="Bonnes jambes, dernière fraction la plus rapide."),
        run(202, at(1, 7, 1), 39, km=7, device="Garmin Forerunner 965"),  # même séance, sans numéro Garmin
        run(203, at(1, 18), 30, km=12, sport="Ride", name="Vélotaf", device="Wahoo ELEMNT BOLT"),
    ]
    http = TestClient(web.create_app())
    connect(http, strava)
    info = wait(http)
    assert info["cache"]["seules"] == 1 and info["cache"]["copies"] == 2
    rows = http.get("/api/activities").json()
    assert sources_of(rows) == {"garmin": 2, "strava": 1} and rows[0]["name"] == "Vélotaf"
    detail = http.get("/api/activities/garmin:555").json()
    assert detail["strava"]["nom"] == "Seuil du mardi" and detail["strava"]["seance_strava"] is False
    assert "Bonnes jambes" in detail["strava"]["description"]  # détail lu pour les séances récentes
    assert detail["strava"]["url"] == "https://www.strava.com/activities/201"
    # Une séance Garmin arrivée après la copie Strava : la copie s'efface d'elle-même des listes
    add_garmin("557", at(1, 18), 30, sport="velo", name="Vélotaf")
    assert sources_of(http.get("/api/activities").json()) == {"garmin": 3}


def test_strava_session_detail_and_curves_on_demand(strava):
    strava.activities.append(run(301, at(40), 30, km=6, name="Footing ancien"))
    http = TestClient(web.create_app())
    connect(http, strava)
    wait(http)
    before = len(strava.api_calls())
    detail = http.get("/api/activities/strava:301").json()
    assert detail["source"] == "strava" and detail["strava"]["url"].endswith("/301")
    assert detail["calories"] == 420 and len(detail["tours"]) == 2 and "hr" in detail["courbes_disponibles"]
    assert detail["sources"] == [{"cle": "strava", "nom": "Strava", "appareils": ["COROS PACE 3"]}]
    assert len(strava.api_calls()) == before + 2  # détail et courbes
    http.get("/api/activities/strava:301")
    assert len(strava.api_calls()) == before + 2  # gardés : rien de redemandé
    curves = http.get("/api/activities/strava:301/streams").json()
    assert curves["hr"][0] == 140 and curves["cad"][0] == 176  # cadence de Strava par jambe → pas par minute


# ------------------------------------------------------------- 48 heures
def test_cache_keeps_strava_data_48_hours_at_most(strava):
    strava.activities += [run(401, at(5), 30, km=5), run(402, at(4), 30, km=5)]
    http = TestClient(web.create_app())
    connect(http, strava)
    wait(http)
    assert len(http.get("/api/activities").json()) == 2
    old = (dt.datetime.now() - dt.timedelta(hours=49)).replace(microsecond=0).isoformat(sep=" ")
    with cache.session() as cconn:
        cconn.execute("UPDATE activities SET confirmed_at = ? WHERE id = 'strava:401'", (old,))
    assert [r["id"] for r in http.get("/api/activities").json()] == ["strava:402"]  # plus montrée tout de suite
    # Séance effacée chez Strava : la liste complète suivante l'efface aussi
    strava.activities = [a for a in strava.activities if a["id"] != 402]
    with cache.session() as cconn:
        cache.set_meta(cconn, "liste_complete_le", old)
    sync.run(sources=["strava"])
    with cache.session() as cconn:
        assert [r[0] for r in cconn.execute("SELECT id FROM activities")] == ["strava:401"]  # relue, reconfirmée


def test_access_withdrawn_forgets_strava_data(strava):
    strava.activities.append(run(501, at(2), 30, km=5))
    http = TestClient(web.create_app())
    connect(http, strava)
    wait(http)
    strava.revoked = True  # Foulée retiré de « Mes applis » sur Strava
    with cache.session() as cconn:
        cache.set_meta(cconn, "liste_complete_le", None)
    tokens = client.load()
    client._write(client.TOKENS, {**tokens, "expires_at": 0})
    result = sync.run(sources=["strava"])
    assert "reconnecte" in result["sources"]["strava"]["erreur"]
    assert not cache.path().exists()  # données Strava oubliées, comme Strava le demande
    with db.session(readonly=True) as conn:
        pill = {c["cle"]: c for c in sync.connections(conn)}["strava"]
    assert pill["etat"] == "ko" and pill["bloque"] and "Strava n'accepte plus" in pill["texte"]


def test_disconnect_revokes_and_forgets(strava):
    strava.activities.append(run(601, at(2), 30, km=5))
    http = TestClient(web.create_app())
    connect(http, strava)
    wait(http)
    res = http.delete("/api/strava", headers=WRITE).json()
    assert res["revoque"] and strava.revoked and not res["connecte"]
    assert not cache.path().exists() and not client.load() and client.has_app()
    assert http.get("/api/activities").json() == []


def test_quota_is_respected(strava):
    strava.activities += [run(700 + i, at(i + 1), 30, km=5) for i in range(5)]
    http = TestClient(web.create_app())
    connect(http, strava)
    wait(http)
    strava.used15 = strava.limit15  # quota du quart d'heure épuisé
    with cache.session() as cconn:
        cache.set_meta(cconn, "liste_complete_le", None)
    result = sync.run(sources=["strava"])
    assert result["statut"] == "partiel" and "Quota de Strava" in result["sources"]["strava"]["erreurs"][0]
    assert client.quota()["used15"] == strava.limit15
    assert not client.can_spend(1)
    with db.session(readonly=True) as conn:
        assert {c["cle"]: c for c in sync.connections(conn)}["strava"]["etat"] == "ok"  # la connexion va bien


# ------------------------------------------------------------------ renfo
def test_gym_session_noted_on_strava_shows_its_exercises(strava):
    strava.activities.append(run(801, at(3, 19), 55, sport="WeightTraining", name="Muscu", description=HEVY,
                                 device=None))
    http = TestClient(web.create_app())
    connect(http, strava)
    wait(http)
    data = http.get("/api/renfo", params={"start": (TODAY - dt.timedelta(days=30)).isoformat()}).json()
    names = [e["nom"] for e in data["exercices"]]
    assert names == ["Bench Press (Barbell)", "Pull Up"]  # noms gardés tels qu'écrits, en anglais
    bench = data["exercices"][0]
    assert bench["series"] == 2 and bench["charge_max_kg"] == 60 and bench["muscles"][0]["cle"] == "pectoraux"
    assert {s["cle"] for s in data["sources"]} == {"strava"}
    with db.session(readonly=True) as conn:
        assert db.get_meta(conn, "renfo_vue") == "1"  # la vue « Renfo » arrive avec ces exercices


# ------------------------------------------------------------- sources
def test_tiles_say_where_their_numbers_come_from(strava):
    add_garmin("901", at(3, 7), 40)
    strava.activities.append(run(902, at(2, 18), 60, km=25, sport="Ride", device="Wahoo ELEMNT BOLT"))
    strava.activities.append(run(903, at(2, 7), 40, km=7, device="Garmin Forerunner 255"))
    http = TestClient(web.create_app())
    connect(http, strava)
    wait(http)
    series = http.get("/api/series", params={"metric": "act.distance_km", "agg": "semaine"}).json()
    assert series["sources"] == [{"cle": "garmin", "nom": "Garmin", "appareils": []},
                                 {"cle": "strava", "nom": "Strava",
                                  "appareils": ["Garmin Forerunner 255", "Wahoo ELEMNT BOLT"]}]
    # La charge compte les séances Strava (la séance Garmin du test, sans charge, ne la nourrit pas)
    assert [x["cle"] for x in http.get("/api/load").json()["sources"]] == ["strava"]
    # Une métrique ne cite que les séances qui lui donnent une valeur : pas de vélo dans l'allure de course
    pace = http.get("/api/series", params={"metric": "act.distance_km", "sport": "pied"}).json()
    assert pace["sources"][1]["appareils"] == ["Garmin Forerunner 255"]


# ------------------------------------------------------- jamais pour Claude
def test_claude_never_sees_strava(strava):
    from foulee import mcp_server

    vault.set_key("cle-de-test")
    strava.activities.append(run(1001, at(2), 30, km=5, name="Séance Strava secrète"))
    http = TestClient(web.create_app())
    connect(http, strava)
    wait(http)
    assert http.get("/api/activities").json()[0]["name"] == "Séance Strava secrète"
    assert mcp_server.lister_seances()["seances"] == []
    assert "Séance Strava secrète" not in json.dumps(mcp_server.statut())
    assert "interdit" in mcp_server.statut()["strava"]["note"]
    # Le journal des synchros, que Claude lit, ne garde rien des séances Strava (ni nombre, ni nom)
    journal = mcp_server.statut()["synchro"]["derniere"]["resume"]
    assert set(journal) == {"strava"} and set(journal["strava"]) <= {"appels", "erreurs"}
    assert mcp_server.requete_sql("SELECT COUNT(*) FROM activities")["lignes"] == [[0]]
    attempt = mcp_server.requete_sql(f"SELECT * FROM pragma_database_list WHERE file = '{cache.path()}'")
    assert attempt.get("lignes", []) == []
    calls = len(strava.requests)
    sync.SOURCES_BACKUP = dict(sync.SOURCES)
    try:
        sync.SOURCES["garmin"] = lambda conn, **kw: {"erreurs": []}
        result = mcp_server.synchroniser()
    finally:
        sync.SOURCES.update(sync.SOURCES_BACKUP)
    assert "strava" not in json.dumps(result.get("resultat", {}).get("sources", {}))
    assert len(strava.requests) == calls  # Claude ne déclenche jamais d'appel à Strava


# ----------------------------------------------------------------- lecture
def test_summary_parsing():
    row = parse.summary_row(run(1, at(1, 6, 30), 42, km=8, device="COROS PACE 3", external_id="garmin_ping_42"))
    assert row["id"] == "strava:1" and row["sport"] == "course" and row["avg_cadence"] == 176
    assert row["start_local"] == at(1, 6, 30).isoformat(sep=" ") and row["garmin_id"] == "42"
    assert json.loads(row["extra"])["appareil"] == "COROS PACE 3"
    assert parse.sport_family("GravelRide") == "velo" and parse.sport_family("WeightTraining") == "renfo"
    assert parse.sport_family("Kitesurf") == "autre"
    assert parse.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == [(38.5, -120.2), (40.7, -120.95),
                                                                     (43.252, -126.453)]


@pytest.mark.parametrize("text, expected", [
    ("Squat arrière 4x10 @ 65 kg\nPompes : 3 x 15\nGainage 3 x 45 s",
     [("Squat arrière", 4, 40, 0, 65.0), ("Pompes", 3, 45, 0, 0.0), ("Gainage", 3, 0, 135, 0.0)]),
    ("Deadlift (Barbell)\n1: 225 lb × 5\n2: 225 lb × 5", [("Deadlift (Barbell)", 2, 10, 0, 102.06)]),
    ("Footing tranquille 45 min, 4x30s accélérations", []),
    ("", []),
])
def test_exercises_from_description(text, expected):
    got = [(e["name"], e["sets"], e["reps"], e["duration_s"], e["max_kg"]) for e in parse.exercises_from_text(text)]
    assert got == expected


def test_credentials_are_checked():
    assert client.clean_client_id(" 123456 ") == "123456"
    assert client.clean_client_secret(CLIENT_SECRET.upper()) == CLIENT_SECRET
    with pytest.raises(ValueError):
        client.clean_client_id("12ab")
    with pytest.raises(ValueError):
        client.clean_client_secret("x" * 40)
    assert client.granted("read,activity:read_all") == (True, True)
    assert client.granted("read activity:read") == (True, False)
    assert client.granted("read") == (False, False)


def test_strava_only_profile_syncs_on_its_own(strava):
    strava.activities.append(run(1101, at(1), 30, km=5))
    http = TestClient(web.create_app())
    connect(http, strava)
    wait(http)
    assert not vault.has_key() and sync.can_sync()
    with db.session(readonly=True) as conn:
        assert sync.due_sources(conn, time.time() + 4 * 3600) == ["strava"]
    assert http.post("/api/sync", headers=WRITE).json()["lance"]
