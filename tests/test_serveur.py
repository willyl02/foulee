"""Mode serveur : noms d'hôte acceptés et appli installable sur le téléphone."""

from fastapi.testclient import TestClient

from foulee import web

TS_HOST = "foulee.tail1234.ts.net"


def make_client(monkeypatch, hotes: str = "") -> TestClient:
    monkeypatch.setenv("FOULEE_HOTES", hotes)
    return TestClient(web.create_app())


def test_tailscale_name_is_accepted_only_when_configured(monkeypatch):
    client = make_client(monkeypatch)
    assert client.get("/", headers={"Host": TS_HOST}).status_code == 403

    client = make_client(monkeypatch, "Foulee.Tail1234.ts.net., autre-nom")
    assert client.get("/", headers={"Host": TS_HOST}).status_code == 200
    assert client.get("/", headers={"Host": f"{TS_HOST}:443"}).status_code == 200
    assert client.get("/api/bootstrap", headers={"Host": "autre-nom"}).status_code == 200
    assert client.get("/", headers={"Host": "pirate.example"}).status_code == 403
    # Modifier quelque chose exige toujours l'en-tête X-Foulee, même par Tailscale
    blocked = client.put("/api/settings", json={"vma_kmh": 16.5}, headers={"Host": TS_HOST})
    assert blocked.status_code == 403


def test_phone_app_files_are_served(monkeypatch):
    client = make_client(monkeypatch)
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    data = manifest.json()
    assert data["display"] == "standalone" and data["start_url"] == "/" and data["scope"] == "/"
    assert {icon["purpose"] for icon in data["icons"]} == {"any", "maskable"}
    for icon in data["icons"]:
        image = client.get(icon["src"])
        assert image.status_code == 200 and image.content.startswith(b"\x89PNG")

    worker = client.get("/sw.js")
    assert worker.headers["content-type"].startswith("text/javascript")
    assert "Foulée est injoignable" in worker.text

    page = client.get("/").text
    assert 'rel="manifest"' in page and "apple-touch-icon" in page


def test_bootstrap_tells_where_foulee_runs(monkeypatch):
    client = make_client(monkeypatch)
    assert client.get("/api/bootstrap").json()["machine"] == "serveur"  # les tests tournent sous Linux
