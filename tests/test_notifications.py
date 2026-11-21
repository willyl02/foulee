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


# ------------------------------------------------------------------ e-mail (0.8.2b11)
import re  # noqa: E402
import smtplib  # noqa: E402

from foulee.relais import courriel  # noqa: E402

SMTP_KEY = "xsmtpsib-cle-de-test-0123456789abcdef"


@pytest.fixture
def mails(monkeypatch):
    """Le service d'envoi posé (dans le dossier des secrets de test), et les e-mails capturés au lieu de partir."""
    box = []
    monkeypatch.setattr(notifs, "SYNC", True)
    monkeypatch.setattr(courriel, "SENDER", lambda data, message: box.append(message))
    courriel.save("smtp-relay.brevo.com", 587, "9a1b2c@smtp-brevo.com", SMTP_KEY, "notifications@foulee-coach.com")
    return box


def _text(message) -> str:
    return message.get_body(("plain",)).get_content()


def _confirm(relay, headers, mails, address="lucas@exemple.fr"):
    page = relay.post("/api/v1/notifications/email/code", headers=headers, json={"adresse": address}).json()
    assert page["email_attente"] == address and "verification" not in page["reglages"]
    code = re.search(r"\b(\d{6})\b", mails[-1]["Subject"]).group(1)
    assert code in _text(mails[-1]) and mails[-1]["To"] == address
    return relay.post("/api/v1/notifications/email/verifier", headers=headers, json={"code": code}).json()


def test_email_waits_for_a_service_on_the_relay(relay):
    sophie = token(relay, "sophie")
    page = relay.get("/api/v1/notifications", headers=sophie).json()
    assert page["email_pret"] is False and page["email_attente"] is None
    refused = relay.post("/api/v1/notifications/email/code", headers=sophie, json={"adresse": "sophie@exemple.fr"})
    assert refused.status_code == 400 and "pas encore d'e-mails" in refused.json()["detail"]


def test_email_address_is_confirmed_by_a_code_then_receives_the_club(relay, mails, monkeypatch):
    monkeypatch.setattr(store, "local_now", lambda: datetime(2026, 11, 20, 14, 0))
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    assert relay.get("/api/v1/notifications", headers=lucas).json()["email_pret"] is True
    bad = relay.post("/api/v1/notifications/email/code", headers=lucas, json={"adresse": "pas une adresse"})
    assert bad.status_code == 400
    early = relay.put("/api/v1/notifications", headers=lucas, json={"email": {"actif": True}})
    assert early.status_code == 400 and "code" in early.json()["detail"]
    # le code part, un code faux compte un essai, le bon confirme et active
    relay.post("/api/v1/notifications/email/code", headers=lucas, json={"adresse": "lucas@exemple.fr"})
    sent_code = re.search(r"\b(\d{6})\b", mails[-1]["Subject"]).group(1)
    wrong = relay.post("/api/v1/notifications/email/verifier", headers=lucas,
                       json={"code": "000000" if sent_code != "000000" else "111111"}).json()
    assert wrong["erreur"].startswith("Code incorrect (4 essais") and wrong["reglages"]["email"]["verifiee_le"] is None
    page = _confirm(relay, lucas, mails)
    assert page["reglages"]["email"]["actif"] is True and page["reglages"]["email"]["adresse"] == "lucas@exemple.fr"
    assert page["email_attente"] is None and "erreur" not in page
    message = mails[-1]
    assert message["From"] == "Foulée Coach <notifications@foulee-coach.com>" and message["Auto-Submitted"]
    assert message.get_body(("html",)) is not None
    # une séance proposée : l'e-mail part (ntfy n'est pas activé), avec le titre et où la trouver
    count = len(mails)
    day = (club._today() + timedelta(days=1)).isoformat()
    blocks = [{"genre": "corps", "nom": "Seuil", "repetitions": 3, "duree_min": 10, "pct_vma": 88}]
    made = relay.post("/api/v1/propositions", headers=sophie, json={
        "eleves": [lucas_id], "date": day, "titre": "Seuil 3 × 10 min", "blocs": blocks}).json()["propositions"][0]
    assert len(mails) == count + 1
    assert mails[-1]["Subject"] == "Nouvelle séance de Sophie" and "Seuil 3 × 10 min" in _text(mails[-1])
    assert "Mon coach" in _text(mails[-1]) and SMTP_KEY not in mails[-1].as_string()
    # sans le détail : ni le titre ni le contenu
    relay.put("/api/v1/notifications", headers=lucas, json={"detail": False})
    relay.delete(f"/api/v1/propositions/{made['id']}", headers=sophie)
    assert mails[-1]["Subject"] == "Foulée : du nouveau" and "Seuil" not in mails[-1].as_string()
    # l'essai, puis décocher : plus rien
    assert relay.post("/api/v1/notifications/essai", headers=lucas, json={"canal": "email"}).json()["ok"]
    assert mails[-1]["Subject"] == "Foulée : du nouveau" and "Notification d'essai." in _text(mails[-1])
    relay.put("/api/v1/notifications", headers=lucas, json={"email": {"actif": False}})
    count = len(mails)
    relay.post("/api/v1/fils/groupe", headers=sophie, json={"texte": "Rendez-vous au stade samedi."})
    assert len(mails) == count
    last = relay.get("/api/v1/notifications", headers=lucas).json()["dernier"]
    assert last["canal"] == "email" and last["statut"] == "ok"
    # retirer l'adresse
    gone = relay.put("/api/v1/notifications", headers=lucas, json={"email": {"retirer": True}}).json()
    assert gone["reglages"]["email"] == {"actif": False, "adresse": None, "verifiee_le": None}


def test_quiet_hours_hold_the_email_until_their_end(relay, mails, monkeypatch):
    clock = {"now": datetime(2026, 11, 20, 23, 30)}
    monkeypatch.setattr(store, "local_now", lambda: clock["now"])
    sophie = token(relay, "sophie")
    lucas, lucas_id = join(relay, sophie, "lucas", "Lucas B.")
    _confirm(relay, lucas, mails)
    count = len(mails)
    relay.post("/api/v1/fils/eleve-" + str(lucas_id), headers=sophie, json={"texte": "Bien joué pour ce soir !"})
    assert len(mails) == count  # retenu jusqu'à 7 h
    with store.session() as conn:
        held = conn.execute("SELECT * FROM courriels_attente").fetchall()
    assert len(held) == 1 and held[0]["a_envoyer_le"] == "2026-11-21 07:00:00"
    assert notifs.flush_due() == 0
    clock["now"] = datetime(2026, 11, 21, 7, 1)
    assert notifs.flush_due() == 1
    assert mails[-1]["Subject"] == "Message de Sophie" and "Bien joué" in _text(mails[-1])
    assert "Messages" in _text(mails[-1])
    with store.session() as conn:
        assert conn.execute("SELECT COUNT(*) FROM courriels_attente").fetchone()[0] == 0


def test_email_codes_are_limited(relay, mails, monkeypatch):
    monkeypatch.setattr(store, "local_now", lambda: datetime(2026, 11, 20, 14, 0))
    sophie = token(relay, "sophie")
    for _ in range(notifs.CODES_PER_HOUR):
        assert relay.post("/api/v1/notifications/email/code", headers=sophie,
                          json={"adresse": "sophie@exemple.fr"}).status_code == 200
    sixth = relay.post("/api/v1/notifications/email/code", headers=sophie, json={"adresse": "sophie@exemple.fr"})
    assert sixth.status_code == 400 and "une heure" in sixth.json()["detail"]
    code = re.search(r"\b(\d{6})\b", mails[-1]["Subject"]).group(1)
    wrong = "111111" if code != "111111" else "222222"
    for _ in range(notifs.CODE_TRIES):
        assert "erreur" in relay.post("/api/v1/notifications/email/verifier", headers=sophie,
                                      json={"code": wrong}).json()
    blocked = relay.post("/api/v1/notifications/email/verifier", headers=sophie, json={"code": code})
    assert blocked.status_code == 400 and "Trop d'essais" in blocked.json()["detail"]
    # une heure plus tard, un nouveau code
    monkeypatch.setattr(store, "local_now", lambda: datetime(2026, 11, 20, 15, 1))
    assert _confirm(relay, sophie, mails, "sophie@exemple.fr")["reglages"]["email"]["actif"] is True


def test_smtp_refusals_are_explained_without_the_key(monkeypatch):
    courriel.save("smtp-relay.brevo.com", "587", "9a1b2c@smtp-brevo.com", SMTP_KEY, "notifications@foulee-coach.com")

    def refuse(data, message):
        raise smtplib.SMTPAuthenticationError(535, b"Authentication failed")

    monkeypatch.setattr(courriel, "SENDER", refuse)
    with pytest.raises(courriel.MailError) as err:
        courriel.send("lucas@exemple.fr", "Essai", "Bonjour")
    assert "clé SMTP" in str(err.value) and SMTP_KEY not in str(err.value)
    assert courriel.public()["cle"] == len(SMTP_KEY) and "mot_de_passe" not in courriel.public()
    with pytest.raises(courriel.MailError):
        courriel.save("smtp-relay.brevo.com", 587, "x@smtp-brevo.com", SMTP_KEY, "pas-une-adresse")


def test_cli_sets_and_tests_the_email_service(monkeypatch, capsys):
    from foulee import cli

    answers = iter(["", "", "9a1b2c@smtp-brevo.com", "notifications@foulee-coach.com", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    keys = iter(["xkeysib-une-cle-api", SMTP_KEY])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(keys))
    assert cli.main(["relais", "email"]) == 0
    out = capsys.readouterr().out
    assert "clé d'API" in out and f"({len(SMTP_KEY)} caractères)" in out and SMTP_KEY not in out
    saved = courriel.settings()
    assert saved["hote"] == "smtp-relay.brevo.com" and saved["port"] == 587 and saved["mot_de_passe"] == SMTP_KEY
    box = []
    monkeypatch.setattr(courriel, "SENDER", lambda data, message: box.append(message))
    assert cli.main(["relais", "email", "tester", "william@exemple.fr"]) == 0
    assert box[0]["To"] == "william@exemple.fr" and "✓" in capsys.readouterr().out
    assert cli.main(["relais", "email", "retirer"]) == 0 and courriel.settings() is None
