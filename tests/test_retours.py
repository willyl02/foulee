"""Aide et retours : où envoyer un bug ou une idée, ce que l'interface en sait, liens de l'aide."""

import re
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

from foulee import retours, web

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "foulee" / "static"


class Answer:
    def __init__(self, status: int, payload: dict | None = None):
        self.status_code = status
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def github(monkeypatch):
    """GitHub simulé : chaque appel prend la réponse suivante de la liste."""
    monkeypatch.setattr(retours, "_cache", {})
    calls: list[dict] = []
    answers: list = []

    def fake_get(url, headers=None, timeout=None):
        calls.append({"url": url, "headers": headers or {}})
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(retours.requests, "get", fake_get)
    return calls, answers


def test_bootstrap_gives_feedback_addresses(monkeypatch):
    client = TestClient(web.create_app())
    info = client.get("/api/bootstrap").json()["retours"]
    assert info == {"depot": "willyl02/foulee", "url": "https://github.com/willyl02/foulee",
                    "issues": "https://github.com/willyl02/foulee/issues",
                    "nouveau": "https://github.com/willyl02/foulee/issues/new", "email": retours.CONTACT_EMAIL}
    monkeypatch.setenv("FOULEE_DEPOT", "quelquun/fourche")  # une copie de Foulée publiée ailleurs
    assert client.get("/api/bootstrap").json()["retours"]["issues"] == "https://github.com/quelquun/fourche/issues"
    monkeypatch.setattr(retours, "CONTACT_EMAIL", " retours@exemple.org ")
    assert retours.info()["email"] == "retours@exemple.org"
    monkeypatch.setattr(retours, "CONTACT_EMAIL", "")
    assert retours.info()["email"] is None  # GitHub seulement : pas de bouton « Envoyer par e-mail »


def test_contact_address_lives_in_one_place():
    """L'adresse de contact, choisie par l'auteur, n'est écrite qu'une fois : l'interface la reçoit du serveur."""
    assert re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", retours.CONTACT_EMAIL)
    for path in [*STATIC.rglob("*.js"), *STATIC.rglob("*.html")]:
        assert not re.search(r"[\w.+-]+@[\w-]+\.(?:com|fr|org|net)\b", path.read_text(encoding="utf-8")), path


def test_visibility_is_asked_once_an_hour(github):
    calls, answers = github
    answers.append(Answer(404))
    assert retours.visibility() == "prive"
    assert retours.visibility() == "prive" and len(calls) == 1  # gardé en mémoire
    assert calls[0]["url"] == "https://api.github.com/repos/willyl02/foulee"
    assert "Authorization" not in calls[0]["headers"]  # ce que voit quelqu'un qui n'est pas invité
    answers.append(Answer(200, {"private": False}))
    assert retours.visibility(refresh=True) == "public"
    answers.append(Answer(200, {"private": True}))
    assert retours.visibility(refresh=True) == "prive"


def test_visibility_unknown_is_not_kept(github):
    calls, answers = github
    answers.extend([Answer(403), requests.ConnectionError("hors ligne"), Answer(404)])
    assert retours.visibility() == "inconnu"  # limite de requêtes atteinte
    assert retours.visibility() == "inconnu"  # GitHub injoignable
    assert retours.visibility() == "prive" and len(calls) == 3  # on a bien redemandé


def test_feedback_endpoint(github):
    _, answers = github
    answers.append(Answer(200, {"private": False}))
    data = TestClient(web.create_app()).get("/api/retours").json()
    assert data["visibilite"] == "public" and data["nouveau"] == "https://github.com/willyl02/foulee/issues/new"


def test_help_and_feedback_pages_are_served():
    client = TestClient(web.create_app())
    page = client.get("/").text
    assert 'id="help-link" href="#/aide"' in page and 'id="feedback-link" href="#/retours"' in page
    # Les liens d'aide et de retours sont au-dessus de la ligne « Dernière synchro »
    assert page.index('id="feedback-link"') < page.index('id="sync-line"')
    for name in ("faq.js", "feedback.js"):
        served = client.get(f"/static/js/{name}")
        assert served.status_code == 200 and "javascript" in served.headers["content-type"]


def test_help_links_lead_to_existing_settings():
    """Chaque lien « Réglages → … » de l'aide mène à une rubrique qui existe."""
    faq = (STATIC / "js" / "faq.js").read_text(encoding="utf-8")
    pages = (STATIC / "js" / "settings.js").read_text(encoding="utf-8") + (STATIC / "js" / "system.js").read_text(encoding="utf-8")
    wanted = set(re.findall(r'reglages\("([\w-]+)"', faq))
    assert len(wanted) >= 10
    existing = set(re.findall(r'data-section="([\w-]+)"', pages)) | set(re.findall(r'section\("([\w-]+)"', pages))
    assert wanted <= existing, wanted - existing
    # Les rubriques d'aide ont toutes un identifiant unique (liens #/aide?question=…)
    themes = re.findall(r'^\s+id: "([\w-]+)", titre:', faq, re.MULTILINE)
    assert len(themes) == len(set(themes)) >= 10


def test_github_labels_match_the_form():
    """Le formulaire préfixe les titres ; GitHub pose l'étiquette que l'interface explique.

    Pas de modèles de sujets dans .github/ISSUE_TEMPLATE : avec eux, GitHub montre d'abord une page de choix
    au lieu du formulaire déjà rempli par Foulée.
    """
    assert not (ROOT / ".github" / "ISSUE_TEMPLATE").exists()
    feedback = (STATIC / "js" / "feedback.js").read_text(encoding="utf-8")
    assert all(f'prefixe: "{p}"' in feedback for p in ("Bug", "Idée", "Question"))
    explained = re.findall(r'<span class="fb-label">(\w+)</span>', feedback)
    workflow = (ROOT / ".github" / "workflows" / "etiquettes.yml").read_text(encoding="utf-8")
    assert sorted(explained) == sorted(re.findall(r'label="(\w+)"', workflow)) == ["bug", "enhancement", "question"]
    assert "${{ github.event.issue.title }}" not in workflow.split("run: |")[1]  # titre passé par variable, jamais dans le script
