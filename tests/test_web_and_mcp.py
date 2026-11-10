"""Serveur web (API + protections) et serveur MCP, sur une base remplie par le faux Garmin."""

import asyncio
import datetime as dt
import json
import os
import sys
import time

import pytest
from fake_garmin import FakeGarmin
from fastapi.testclient import TestClient

from foulee import sync, vault


@pytest.fixture
def filled(monkeypatch):
    with FakeGarmin(days=40, activities=8) as fake:
        monkeypatch.setenv("GARMIN_PERSONAL_API_BASE_URL", fake.url)
        vault.set_key("cle-de-test")
        sync.run(since=fake.today - dt.timedelta(days=35))
        yield fake


def test_web_api(filled):
    from foulee.web import create_app

    client = TestClient(create_app())
    boot = client.get("/api/bootstrap").json()
    assert boot["volumes"]["activities"] == 8 and len(boot["vues"]) == 6 and boot["cle"]
    assert boot["vues"][0]["id"] == "accueil"  # la page d'accueil ouvre l'interface
    assert client.get("/").status_code == 200
    assert client.get("/static/js/app.js").status_code == 200
    # protections
    assert client.post("/api/sync").status_code == 403
    assert client.get("/api/bootstrap", headers={"Host": "attaquant.example"}).status_code == 403
    # séries, chiffres clés, séances
    series = client.get("/api/series", params={"metric": "act.distance_km", "agg": "semaine"}).json()
    assert any(v for _, v in series["points"])
    assert client.get("/api/kpi", params={"metric": "sleep_s"}).json()["value"] == 25800
    activity = client.get("/api/activities", params={"limit": 1}).json()[0]
    detail = client.get(f"/api/activities/{activity['id']}").json()
    assert len(detail["tours"]) == 2
    streams = client.get(f"/api/activities/{activity['id']}/streams", params={"max_points": 300}).json()
    assert len(streams["t"]) <= 300
    # réglages : la VMA relance le calcul des zones
    res = client.put("/api/settings", json={"vma_kmh": 15.5}, headers={"X-Foulee": "1"}).json()
    assert res["reglages"]["vma_kmh"] == 15.5 and res["recalcul"]
    # synchro lancée depuis l'interface
    started = client.post("/api/sync", headers={"X-Foulee": "1"}).json()
    assert started["lance"]
    for _ in range(100):
        state = client.get("/api/sync").json()
        if not state["job"]["en_cours"]:
            break
        time.sleep(0.2)
    assert state["job"]["resultat"]["statut"] == "ok"
    # vues : création, nettoyage d'une tuile invalide, suppression
    view = client.post("/api/views", json={"name": "Essai", "spec": {"tuiles": [
        {"type": "kpi", "params": {"metrique": "hrv_night"}}, {"type": "inexistant"}]}}, headers={"X-Foulee": "1"}).json()
    assert len(view["spec"]["tuiles"]) == 1
    assert client.delete(f"/api/views/{view['id']}", headers={"X-Foulee": "1"}).json()["supprimee"]


def test_mcp_server(filled, tmp_path):
    from mcp import ClientSession, StdioServerParameters, stdio_client

    async def scenario():
        params = StdioServerParameters(command=sys.executable, args=["-m", "foulee", "mcp"],
                                       env={**os.environ, "PYTHONUTF8": "1"})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                assert {"statut", "lister_seances", "detail_seance", "comparer_postes", "requete_sql"} <= names
                status = json.loads((await session.call_tool("statut", {})).content[0].text)
                assert status["seances"]["nombre"] == 8 and status["cle_api_garmin"] == "présente"
                rows = json.loads((await session.call_tool("lister_seances", {"limite": 3})).content[0].text)["seances"]
                assert rows[0]["description"] == "Bonnes jambes" and rows[0]["allure"] == "5:13 /km"
                refused = json.loads((await session.call_tool("requete_sql", {"sql": "DROP TABLE activities"})).content[0].text)
                assert "erreur" in refused

    asyncio.run(scenario())
