"""Notifications du relais (0.8.2) : ntfy pour la séance reçue, modifiée, annulée et les messages ; e-mail préparé."""

from datetime import datetime, timedelta

import pytest

from foulee.relais import club, notifs, store
from test_relais_club import join, relay, token  # noqa: F401


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(notifs, "SYNC", True)
    monkeypatch.setattr(notifs, "TRANSPORT", lambda url, payload: calls.append((url, payload)) or (200, "{}"))
    return calls


def _on(relay, headers, **extra):
    return relay.put("/api/v1/notifications", headers=headers, json={"ntfy": {"actif": True}, **extra}).json()


def test_new_changed_and_cancelled_sessions_reach_the_student(relay, sent, monkeypatch):
    monkeypatch.setattr(store, "local_now", lambda: datetime(2026, 11, 20, 14, 0))
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    emma, emma_id = join(relay, sophie, "emma", "Emma L.")
    page = relay.get("/api/v1/notifications", headers=lucas).json()
    assert page["reglages"]["ntfy"]["actif"] is False and page["reglages"]["ntfy"]["sujet"].startswith("foulee-")
    assert [e["cle"] for e in page["evenements"]] == ["seance", "seance_modifiee", "seance_annulee", "message"]
    assert [e["cle"] for e in relay.get("/api/v1/notifications", headers=sophie).json()["evenements"]] == ["message"]
    topic = _on(relay, lucas)["reglages"]["ntfy"]["sujet"]
    day = (club._today() + timedelta(days=1)).isoformat()
    blocks = [{"genre": "corps", "nom": "Seuil", "repetitions": 3, "duree_min": 10, "pct_vma": 88}]
    made = relay.post("/api/v1/propositions", headers=sophie, json={
        "eleves": [lucas_id, emma_id], "date": day, "titre": "Seuil 3 × 10 min", "blocs": blocks}).json()["propositions"]
    assert len(sent) == 1  # Emma n'a pas activé ntfy
    url, payload = sent[0]
    assert url == "https://ntfy.sh/" and payload["topic"] == topic
    assert payload["title"].startswith("Nouvelle séance de ") and payload["message"].startswith("Seuil 3 × 10 min, ")
    assert "delay" not in payload
    mine = next(p for p in made if p["eleve_id"] == lucas_id)
    relay.put(f"/api/v1/propositions/{mine['id']}", headers=sophie, json={"date": day, "titre": "Seuil 4 × 8 min",
                                                                          "blocs": blocks})
    assert "a modifié une séance" in sent[-1][1]["title"] and sent[-1][1]["message"].startswith("Seuil 4 × 8 min")
    relay.delete(f"/api/v1/propositions/{mine['id']}", headers=sophie)
    assert "a annulé une séance" in sent[-1][1]["title"] and len(sent) == 3
    # sans le détail ; et un événement décoché ne prévient plus
    relay.put("/api/v1/notifications", headers=lucas, json={"detail": False, "evenements": {"seance_annulee": False}})
    again = relay.post("/api/v1/propositions", headers=sophie, json={
        "eleves": [lucas_id], "date": day, "titre": "VMA courte", "blocs": blocks}).json()["propositions"][0]
    assert sent[-1][1]["title"] == "Foulée" and sent[-1][1]["message"] == "Nouvelle séance de Ton coach"
    relay.delete(f"/api/v1/propositions/{again['id']}", headers=sophie)
    assert len(sent) == 4
    # une vieille séance qu'on range : personne n'est dérangé
    old = relay.post("/api/v1/propositions", headers=sophie, json={
        "eleves": [lucas_id], "date": (club._today() - timedelta(days=3)).isoformat(), "titre": "Footing",
        "blocs": blocks}).json()["propositions"][0]
    count = len(sent)
    relay.delete(f"/api/v1/propositions/{old['id']}", headers=sophie)
    assert len(sent) == count


def test_messages_quiet_hours_test_and_failures(relay, sent, monkeypatch):
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    emma, _ = join(relay, sophie, "emma", "Emma L.")
    coach_topic = _on(relay, sophie)["reglages"]["ntfy"]["sujet"]
    lucas_topic = _on(relay, lucas)["reglages"]["ntfy"]["sujet"]
    monkeypatch.setattr(store, "local_now", lambda: datetime(2026, 11, 20, 18, 0))
    relay.post(f"/api/v1/fils/eleve-{lucas_id}", headers=lucas, json={"texte": "Je décale ma séance à jeudi ?"})
    (url, payload), = sent
    assert payload["topic"] == coach_topic and payload["title"].startswith("Message de Lucas")
    assert payload["message"] == "Je décale ma séance à jeudi ?"
    # le coach écrit au groupe, à 23 h 30 : Lucas (abonné) la reçoit à 7 h, pas tout de suite ; Emma n'a rien activé
    monkeypatch.setattr(store, "local_now", lambda: datetime(2026, 11, 20, 23, 30))
    relay.post("/api/v1/fils/groupe", headers=sophie, json={"texte": "Rendez-vous samedi 9 h au stade"})
    payload = sent[-1][1]
    assert payload["topic"] == lucas_topic and "fil du groupe" in payload["title"]
    assert payload["delay"] == str(int(datetime(2026, 11, 21, 7, 0).timestamp()))
    assert len(sent) == 2 and emma
    # l'essai part tout de suite, même pendant les heures calmes
    assert relay.post("/api/v1/notifications/essai", headers=lucas).json()["ok"] is True
    assert "delay" not in sent[-1][1] and sent[-1][1]["title"] == "Foulée : ça marche !"
    assert relay.get("/api/v1/notifications", headers=lucas).json()["dernier"]["statut"] == "ok"
    # ntfy injoignable ou qui refuse : noté, visible dans les réglages
    monkeypatch.setattr(notifs, "TRANSPORT", lambda url, payload: (500, "boom"))
    relay.post("/api/v1/notifications/essai", headers=lucas)
    last = relay.get("/api/v1/notifications", headers=lucas).json()["dernier"]
    assert last["statut"] == "echec" and "HTTP 500" in last["detail"]


def test_settings_validation_and_new_topic(relay, sent):
    sophie = token(relay, "sophie")
    first = _on(relay, sophie)
    again = relay.put("/api/v1/notifications", headers=sophie, json={"nouveau_sujet": True}).json()
    assert again["reglages"]["ntfy"]["sujet"] != first["reglages"]["ntfy"]["sujet"]
    assert again["abonnement"] == f"https://ntfy.sh/{again['reglages']['ntfy']['sujet']}"
    bad = relay.put("/api/v1/notifications", headers=sophie, json={"ntfy": {"serveur": "javascript:alert(1)"}})
    assert bad.status_code == 400
    own = relay.put("/api/v1/notifications", headers=sophie, json={"ntfy": {"serveur": "https://ntfy.relais.exemple.fr/"},
                                                                   "calme": {"actif": True, "debut": "21:30", "fin": "25:00"}})
    assert own.json()["reglages"]["ntfy"]["serveur"] == "https://ntfy.relais.exemple.fr"
    assert own.json()["reglages"]["calme"] == {"actif": True, "debut": "21:30", "fin": "07:00"}
    assert notifs._quiet_until({"actif": True, "debut": "13:00", "fin": "14:00"}, datetime(2026, 1, 1, 13, 30)) \
        == datetime(2026, 1, 1, 14, 0)
    assert notifs._quiet_until({"actif": False, "debut": "22:00", "fin": "07:00"}, datetime(2026, 1, 1, 23, 0)) is None
