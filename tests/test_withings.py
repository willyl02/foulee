"""Withings : appli, autorisation par la page relais, jetons, synchro, vue et résumé, contre un faux Withings."""

import datetime as dt
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fake_withings import CLIENT_ID, CLIENT_SECRET, FakeWithings, stamp
from fastapi.testclient import TestClient

from foulee import config, db, sync, utilisateurs, vault, views, web
from foulee.withings import client, parse, vue
from foulee.withings import sync as wsync

WRITE = {"X-Foulee": "1"}
RELAY = "https://relais.test/foulee/withings/"


@pytest.fixture
def withings(monkeypatch):
    with FakeWithings(days=40, relay=RELAY) as fake:
        monkeypatch.setenv("FOULEE_WITHINGS_API", fake.url)
        monkeypatch.setenv("FOULEE_WITHINGS_COMPTE", fake.url)
        monkeypatch.setenv("FOULEE_WITHINGS_RELAIS", RELAY)
        yield fake


def authorize(http: TestClient, fake: FakeWithings, *, origin: str = "http://testserver") -> str:
    """Le parcours de l'interface : appli enregistrée, « Connecter », « Allow » chez Withings, page relais, retour."""
    assert http.put("/api/withings/appli", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
                    headers=WRITE).status_code == 200
    started = http.post("/api/withings/connexion", json={"origine": origin}, headers=WRITE)
    assert started.status_code == 200, started.text
    query = {k: v[0] for k, v in parse_qs(urlparse(started.json()["url"]).query).items()}
    # La page relais renvoie vers l'adresse portée par le « state » : ici, ce Foulée
    assert client.read_state(query["state"])["r"] == origin
    code = fake.issue_code()
    back = http.get("/withings/retour", params={"code": code, "state": query["state"]}, follow_redirects=False)
    assert back.status_code == 303
    return back.headers["location"]


def wait_for_sync(http: TestClient) -> dict:
    """Attend la fin du premier import ; garde le message de connexion (affiché une seule fois)."""
    note = None
    for _ in range(200):
        info = http.get("/api/withings").json()
        note = note or info.get("note")
        if not info["synchro"]["en_cours"]:
            return {**info, **({"note": note} if note else {})}
        time.sleep(0.05)
    raise AssertionError("synchro Withings trop longue")


# ------------------------------------------------------------------ lecture
def test_measures_become_daily_values():
    day = dt.date(2026, 11, 3)
    groups = [
        {"grpid": 1, "date": stamp(day, 8), "category": 1, "timezone": "Europe/Paris",  # 3 nov. 08:00 à Paris
         "measures": [{"value": 72350, "type": 1, "unit": -3}, {"value": 158, "type": 6, "unit": -1},
                      {"value": 41, "type": 77, "unit": 0}]},
        {"grpid": 2, "date": stamp(day, 21), "category": 1, "timezone": "Europe/Paris",  # le soir : la dernière pesée gagne
         "measures": [{"value": 72900, "type": 1, "unit": -3}, {"value": 128, "type": 10, "unit": 0},
                      {"value": 80, "type": 9, "unit": 0}]},
        {"grpid": 3, "date": stamp(day, 21, 5), "category": 1, "timezone": "Europe/Paris",
         "measures": [{"value": 120, "type": 10, "unit": 0}, {"value": 76, "type": 9, "unit": 0}]},
        {"grpid": 4, "date": stamp(day, 22), "category": 2,  # objectif : ignoré
         "measures": [{"value": 65000, "type": 1, "unit": -3}]},
    ]
    assert parse.group_day(groups[0]) == day.isoformat()
    values = parse.daily_from_groups(groups, height=1.78)
    assert values["wi_weight_kg"] == 72.9 and values["wi_fat_pct"] == 15.8
    assert values["wi_bp_sys"] == 124 and values["wi_bp_dia"] == 78  # moyenne des mesures du jour
    assert values["wi_water_pct"] == round(100 * 41 / 72.9, 3)  # eau rapportée au poids de la journée
    assert values["wi_bmi"] == round(72.9 / 1.78 ** 2, 3)


def test_sleep_counts_for_the_wake_up_day():
    night = dt.date(2026, 11, 3)
    item = {"startdate": stamp(night, 23, 30), "enddate": stamp(night + dt.timedelta(days=1), 7, 30),
            "timezone": "Europe/Paris",  # 3 nov. 23:30 → 4 nov. 07:30
            "data": {"total_sleep_time": 25200, "deepsleepduration": 5000, "sleep_efficiency": 0.92, "hr_average": 51}}
    day, values = parse.parse_sleep(item)
    assert day == "2026-11-04"
    assert values["wi_sleep_s"] == 25200 and values["wi_sleep_eff_pct"] == 92
    assert values["wi_bed_h"] == 23.5 and values["wi_rise_h"] == 7.5
    nap = {**item, "data": {"total_sleep_time": 1800}}
    assert parse.main_sleep([nap, item])["wi_sleep_s"] == 25200  # la nuit, pas la sieste


def test_activity_without_heart_rate():
    day, values = parse.parse_activity({"date": "2026-11-04", "steps": 9000, "distance": 6500.0, "hr_average": 0})
    assert day == "2026-11-04" and values == {"wi_steps": 9000, "wi_distance_km": 6.5}


def test_relay_rule_is_the_same_as_the_page():
    # Même liste que la vérification de la page relais (docs/withings/index.html)
    for host, expected in [("127.0.0.1", True), ("localhost", True), ("foulee.tail1234.ts.net", True),
                           ("192.168.1.20", True), ("100.101.102.103", True), ("10.0.0.5", True), ("serveur", True),
                           ("172.20.0.3", True), ("fd7a:115c:a1e0::1", True), ("exemple.fr", False),
                           ("8.8.8.8", False), ("100.200.1.1", False), ("172.32.0.1", False), ("2001:db8::1", False)]:
        assert client.relay_accepts(host) is expected, host
    assert client.origin_problem("http://127.0.0.1:8770", "127.0.0.1:8770") is None
    assert "ne correspond pas" in client.origin_problem("http://127.0.0.1:9999", "127.0.0.1:8770")
    assert "relais" in client.origin_problem("https://foulee.exemple.fr", "foulee.exemple.fr")


def test_credentials_are_cleaned():
    assert client.clean_credential(f"  {CLIENT_ID[:30]}\n{CLIENT_ID[30:]} ", "ClientID") == CLIENT_ID
    assert client.clean_credential(f"«{CLIENT_ID[:30]} {CLIENT_ID[30:]}»", "ClientID") == CLIENT_ID  # ligne → espace
    for bad in ("", "trop court", "avec des espaces partout dedans", "é" * 40):
        with pytest.raises(ValueError):
            client.clean_credential(bad, "ClientID")


# ------------------------------------------------------- connexion complète
def test_connect_sync_and_view(withings):
    http = TestClient(web.create_app())
    info = http.get("/api/withings").json()
    assert info["appli"] is False and info["connecte"] is False and info["relais"] == RELAY
    assert http.post("/api/withings/connexion", json={"origine": "http://testserver"}, headers=WRITE).status_code == 400

    bad = http.put("/api/withings/appli", json={"client_id": "abc", "client_secret": CLIENT_SECRET}, headers=WRITE)
    assert bad.status_code == 400 and "ClientID" in bad.json()["detail"]
    location = authorize(http, withings)
    assert location == "/#/reglages?section=withings&withings=connecte"

    # Jetons au coffre, jamais dans les réponses de l'interface
    stored = json.loads(vault.get_secret("withings"))
    assert stored["client_secret"] == CLIENT_SECRET and stored["refresh_token"] == withings.refresh
    info = wait_for_sync(http)
    text = json.dumps(info)
    assert CLIENT_SECRET not in text and withings.refresh not in text and withings.access not in text
    assert info["connecte"] and info["note"]["statut"] == "connecte" and "Premier import" in info["note"]["message"]
    assert "note" not in http.get("/api/withings").json()  # affichée une seule fois
    assert set(info["familles"]) == {"corps", "tension", "sommeil", "activite"}

    # Les mesures sont dans la base, par jour
    with db.session(readonly=True) as conn:
        rows = {(r["date"], r["metric"]): r["value"] for r in conn.execute("SELECT * FROM daily WHERE source = 'withings'")}
        first = withings.today - dt.timedelta(days=39)
        assert rows[(first.isoformat(), "wi_weight_kg")] == round(74.0 + 0.6, 3)  # deux pesées : la dernière
        assert (first.isoformat(), "wi_bp_sys") in rows and rows[(first.isoformat(), "wi_bp_sys")] == 122
        assert rows[(first.isoformat(), "wi_bmi")] == round((74.0 + 0.6) / 1.78 ** 2, 3)
        assert rows[(withings.today.isoformat(), "wi_sleep_s")] == 25200
        assert rows[(withings.today.isoformat(), "wi_steps")] == 8000 + 39 * 10
        assert not any(v == 70.0 for (d, m), v in rows.items() if m == "wi_weight_kg")  # objectif ignoré
        view = json.loads(conn.execute("SELECT spec FROM views WHERE id = 'withings'").fetchone()["spec"])
        assert view["tuiles"][0]["type"] == "withings"
        assert {"Poids", "Tension artérielle", "Sommeil (Withings)", "Pas par jour (Withings)"} <= {
            t.get("titre") for t in view["tuiles"]}
        order = [r["id"] for r in conn.execute("SELECT id FROM views ORDER BY position")]
        assert order[:2] == ["accueil", "withings"]

    # Pages lues jusqu'au bout (« more »), et la synchro suivante ne redemande que le récent
    pages = [q for p, q in withings.requests if p == "/measure" and "meastype" not in q]
    assert len(pages) > 3 and pages[1]["offset"] == "7"
    heights = [q for p, q in withings.requests if p == "/measure" and q.get("meastype") == "4"]
    assert len(heights) == 1 and "lastupdate" not in heights[0]  # la taille, demandée à part, sans limite de date
    withings.requests.clear()
    withings.add_weight(withings.today, 22, 73.1)
    result = sync.run(sources=["withings"])
    assert result["statut"] == "ok" and result["sources"]["withings"]["mesures"] >= 1
    since = int([q for p, q in withings.requests if p == "/measure"][0]["lastupdate"])
    assert time.time() - since < 2 * 86400
    with db.session(readonly=True) as conn:
        latest = conn.execute("SELECT value FROM daily WHERE source = 'withings' AND metric = 'wi_weight_kg' AND date = ?",
                              (withings.today.isoformat(),)).fetchone()["value"]
        assert latest == 73.1

    # Le résumé de la tuile
    summary = http.get("/api/withings/resume").json()
    assert summary["corps"]["date"] == withings.today.isoformat() and summary["corps"]["valeurs"]["wi_weight_kg"] == 73.1
    assert summary["corps"]["reference"]["date"] <= (withings.today - dt.timedelta(days=28)).isoformat()
    assert summary["tension"]["niveau"]["libelle"] == "Normale"
    assert summary["sommeil"]["valeurs"]["wi_sleep_s"] == 25200


def test_height_entered_long_ago_still_gives_bmi(withings):
    # Historique importé depuis 10 jours ; la taille date de la création du compte, 40 jours plus tôt
    with db.session() as conn:
        db.set_setting(conn, "historique_depuis", (withings.today - dt.timedelta(days=10)).isoformat())
        conn.commit()
    http = TestClient(web.create_app())
    authorize(http, withings)
    wait_for_sync(http)
    with db.session(readonly=True) as conn:
        bmi = conn.execute("SELECT value FROM daily WHERE source = 'withings' AND metric = 'wi_bmi' AND date = ?",
                           (withings.today.isoformat(),)).fetchone()
        assert bmi and bmi["value"] == round((74.0 - 0.02 * 39) / 1.78 ** 2, 3)
        assert conn.execute("SELECT MIN(date) AS d FROM daily WHERE source = 'withings'").fetchone()["d"] >= \
            (withings.today - dt.timedelta(days=11)).isoformat()
    withings.requests.clear()
    sync.run(sources=["withings"])
    assert not [q for p, q in withings.requests if q.get("meastype")]  # taille connue : plus redemandée


def test_access_token_renewed_and_refresh_token_rotated(withings):
    http = TestClient(web.create_app())
    authorize(http, withings)
    wait_for_sync(http)
    old_refresh = withings.refresh
    data = json.loads(vault.get_secret("withings"))
    data["expires_at"] = int(time.time()) - 10  # jeton d'accès périmé : renouvelé avant le premier appel
    vault.set_secret("withings", json.dumps(data))
    assert sync.run(sources=["withings"])["statut"] == "ok"
    assert json.loads(vault.get_secret("withings"))["refresh_token"] == withings.refresh != old_refresh
    withings.expire_access()  # refusé avant l'heure : renouvelé une fois, puis l'appel repart
    assert sync.run(sources=["withings"])["statut"] == "ok"


def test_withdrawn_access_is_reported_then_cleared(withings):
    http = TestClient(web.create_app())
    authorize(http, withings)
    wait_for_sync(http)
    withings.revoked = True
    withings.expire_access()
    result = sync.run(sources=["withings"])
    assert result["statut"] == "echec" and "reconnecte ton compte" in result["sources"]["withings"]["erreur"]
    boot = http.get("/api/bootstrap").json()
    assert boot["withings"]["refus"]["depuis"] and boot["withings"]["connecte"]
    assert http.get("/api/withings").json()["refus"]
    authorize(http, withings)  # reconnexion
    assert http.get("/api/bootstrap").json()["withings"]["refus"] is None


def test_one_source_failing_makes_a_partial_sync(withings, monkeypatch):
    http = TestClient(web.create_app())
    authorize(http, withings)
    wait_for_sync(http)
    monkeypatch.setitem(sync.SOURCES, "garmin", lambda conn, **kw: {"erreurs": []})  # Garmin sans souci
    withings.revoked = True
    withings.expire_access()
    result = sync.run()
    assert set(result["sources"]) == {"garmin", "withings"} and result["statut"] == "partiel"
    with db.session(readonly=True) as conn:
        assert vue.refused(conn) is not None and db.get_meta(conn, "last_sync")


def test_return_errors(withings):
    http = TestClient(web.create_app())
    assert http.put("/api/withings/appli", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
                    headers=WRITE).status_code == 200

    def start() -> str:
        url = http.post("/api/withings/connexion", json={"origine": "http://testserver"}, headers=WRITE).json()["url"]
        return parse_qs(urlparse(url).query)["state"][0]

    def back(**params) -> str:
        res = http.get("/withings/retour", params=params, follow_redirects=False)
        assert res.status_code == 303
        return res.headers["location"].rsplit("=", 1)[1]

    assert back(code="x", state="n'importe quoi") == "erreur"
    state = start()
    assert back(error="access_denied", state=state) == "refus"
    assert "Allow" in http.get("/api/withings").json()["note"]["message"]
    assert back(code=withings.issue_code(), state=state) == "erreur"  # déjà servi
    assert "expiré ou a déjà servi" in http.get("/api/withings").json()["note"]["message"]
    assert back(code="code-inconnu", state=start()) == "erreur"
    message = http.get("/api/withings").json()["note"]["message"]
    assert "refuse de terminer la connexion" in message and RELAY in message
    assert client.connected() is False
    # Une adresse que la page relais refuserait, ou qui n'est pas celle de la page
    res = http.post("/api/withings/connexion", json={"origine": "http://autre-site.fr"}, headers=WRITE)
    assert res.status_code == 400 and "ne correspond pas" in res.json()["detail"]


def test_return_from_the_relay_comes_without_the_profile_cookie(withings):
    """Plusieurs profils : le retour arrive de la page relais, un autre site, donc sans le cookie du profil
    (SameSite=Strict). La connexion va au profil qui l'a lancée, retrouvé par le « state »."""
    app = web.create_app()
    lea = utilisateurs.create("Léa")
    browser = TestClient(app)  # le navigateur, sur le profil de Léa
    browser.cookies.set(utilisateurs.cookie_name(), utilisateurs.make_cookie(lea))
    assert browser.put("/api/withings/appli", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
                       headers=WRITE).status_code == 200
    url = browser.post("/api/withings/connexion", json={"origine": "http://testserver"}, headers=WRITE).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    from_relay = TestClient(app)  # le même navigateur, venu de la page relais : aucun cookie
    res = from_relay.get("/withings/retour", params={"code": withings.issue_code(), "state": state},
                         follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"].endswith("withings=connecte")
    info = wait_for_sync(browser)
    assert info["connecte"] and info["note"]["statut"] == "connecte" and info["familles"]
    with config.using_profile(lea):
        assert client.connected()
        with db.session(readonly=True) as conn:
            assert conn.execute("SELECT 1 FROM views WHERE id = 'withings'").fetchone()
            assert conn.execute("SELECT COUNT(*) AS n FROM daily WHERE source = 'withings'").fetchone()["n"] > 0
    assert client.connected() is False  # le profil principal n'a rien reçu
    # Un retour qui ne mène à aucun profil (demande déjà servie) : le message s'affiche quand même
    assert from_relay.get("/withings/retour", params={"code": "x", "state": state},
                          follow_redirects=False).status_code == 303
    assert "expiré ou a déjà servi" in browser.get("/api/withings").json()["note"]["message"]


def test_secrets_only_from_this_machine(withings):
    app = web.create_app()
    lan = TestClient(app, client=("192.168.0.50", 50000))
    headers = {**WRITE, "Host": "192.168.0.19"}
    assert lan.put("/api/withings/appli", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
                   headers=headers).status_code in (401, 403)
    assert lan.post("/api/withings/connexion", json={"origine": "http://192.168.0.19"}, headers=headers).status_code in (401, 403)
    assert lan.delete("/api/withings", headers=headers).status_code in (401, 403)
    assert vault.get_secret("withings") is None


def test_disconnect_keeps_measures(withings):
    http = TestClient(web.create_app())
    authorize(http, withings)
    wait_for_sync(http)
    info = http.delete("/api/withings", headers=WRITE).json()
    assert info["connecte"] is False and info["appli"] is True and info["vue"] is False
    assert sync.active_sources() == ["garmin"]
    with db.session(readonly=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM daily WHERE source = 'withings'").fetchone()[0] > 100
    info = http.delete("/api/withings", params={"tout": 1}, headers=WRITE).json()
    assert info["appli"] is False and vault.get_secret("withings") is None


def test_view_follows_measures_until_edited():
    with db.session() as conn:
        views.sync_withings_view(conn, True, [])
        titles = lambda: [t.get("titre") for t in json.loads(  # noqa: E731
            conn.execute("SELECT spec FROM views WHERE id = 'withings'").fetchone()["spec"])["tuiles"]]
        assert titles() == [None, "Poids", "Composition corporelle"]
        views.sync_withings_view(conn, True, ["corps", "tension"])
        assert "Tension artérielle" in titles()
        view = next(v for v in views.list_views(conn) if v["id"] == "withings")
        views.save_view(conn, "withings", "Ma balance", {"tuiles": view["spec"]["tuiles"][:2]})
        views.sync_withings_view(conn, True, ["corps", "tension", "sommeil"])
        assert titles() == [None, "Poids"]  # modifiée à la main : on n'y touche plus
        views.sync_withings_view(conn, False)
        assert not conn.execute("SELECT 1 FROM views WHERE id = 'withings'").fetchone()


def test_each_profile_has_its_own_access(withings):
    http = TestClient(web.create_app())
    authorize(http, withings)
    wait_for_sync(http)
    other = utilisateurs.create("Léa")
    with config.using_profile(other):
        assert client.load() == {} and sync.active_sources() == ["garmin"]
        vault.set_secret("withings", json.dumps({"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}))
    utilisateurs.delete(other["id"])
    with config.using_profile(other):
        assert vault.get_secret("withings") is None
    assert client.connected()  # le profil principal garde le sien


def test_demo_has_a_withings_view():
    from foulee import demo

    demo.build(days=60, second_profile=False)
    with db.session(readonly=True) as conn:
        assert set(vue.families(conn)) == {"corps", "tension", "sommeil"}
        assert conn.execute("SELECT 1 FROM views WHERE id = 'withings'").fetchone()
        assert vue.summary(conn)["corps"]["valeurs"]["wi_weight_kg"] > 60
        assert vue.status(conn)["connecte"] is True
    config.set_demo(False)


def test_wsync_reparse(withings):
    http = TestClient(web.create_app())
    authorize(http, withings)
    wait_for_sync(http)
    with db.session() as conn:
        before = conn.execute("SELECT COUNT(*) FROM daily WHERE source = 'withings'").fetchone()[0]
        conn.execute("DELETE FROM daily WHERE source = 'withings'")
        counts = wsync.reparse_all(conn)
        after = conn.execute("SELECT COUNT(*) FROM daily WHERE source = 'withings'").fetchone()[0]
    assert counts["nuits"] == 40 and after == before
