"""Calendrier d'entraînement (lien iCal) : lecture du calendrier publié par Garmin Connect (ou d'un autre agenda),
séances prévues face aux séances faites, vue « Calendrier », « Ta semaine », pastille, et un lien qui ne sort jamais
(il donne le calendrier à quiconque le connaît)."""

import datetime as dt
import json
import logging

import pytest
from fake_calendar import TOKEN, FakeCalendar, garmin_feed
from fastapi.testclient import TestClient

from foulee import calendrier, db, sync, utilisateurs, vault, views, web

WRITE = {"X-Foulee": "1"}
TODAY = dt.date.today()


def day(offset: int) -> dt.date:
    return TODAY + dt.timedelta(days=offset)


def add_activity(conn, ident: str, when: dt.date, sport: str = "course", name: str | None = None) -> None:
    conn.execute("INSERT INTO activities(id, source, source_id, start_local, date, sport, name, distance_m, duration_s) "
                 "VALUES (?, 'garmin', ?, ?, ?, ?, ?, 8000, 2700)",
                 (ident, ident, f"{when.isoformat()} 08:00:00", when.isoformat(), sport, name or f"Séance {ident}"))


@pytest.fixture
def calendar():
    with FakeCalendar(garmin_feed(TODAY)) as fake:
        yield fake


def link(http: TestClient, fake: FakeCalendar):
    res = http.put("/api/calendrier", json={"lien": f"  {fake.link}  "}, headers=WRITE)
    assert res.status_code == 200, res.text
    return res.json()


def secret_free(*texts) -> bool:
    return all(TOKEN not in (t if isinstance(t, str) else json.dumps(t, ensure_ascii=False)) for t in texts)


# ------------------------------------------------------------------ lecture
GOOGLE = "\n".join([
    "BEGIN:VCALENDAR", "PRODID:-//Google Inc//Google Calendar 70.9054//EN", "X-WR-CALNAME:Club",
    "X-WR-TIMEZONE:Europe/Paris",
    "BEGIN:VTIMEZONE", "TZID:Europe/Paris", "BEGIN:STANDARD", "DTSTART:19701025T030000", "TZOFFSETFROM:+0200",
    "TZOFFSETTO:+0100", "END:STANDARD", "END:VTIMEZONE",
    "BEGIN:VEVENT", "DTSTART:20261110T170000Z", "DTEND:20261110T180000Z", "RRULE:FREQ=WEEKLY;BYDAY=TU,TH;COUNT=6",
    "EXDATE;TZID=Europe/Paris:20261112T180000", "UID:serie", "SUMMARY:Renfo du club",
    "BEGIN:VALARM", "TRIGGER:-PT30M", "ACTION:DISPLAY", "DESCRIPTION:Rappel", "END:VALARM", "END:VEVENT",
    "BEGIN:VEVENT", "DTSTART:20261119T180000Z", "DURATION:PT1H30M", "RECURRENCE-ID:20261119T170000Z", "UID:serie",
    "SUMMARY:Renfo du club (décalé)", "END:VEVENT",
    "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20261220", "DTEND;VALUE=DATE:20261223", "UID:v", "SUMMARY:Vacances",
    "END:VEVENT",
    "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20261231", "UID:c", "SUMMARY:Corrida de la Saint-Sylvestre",
    "DESCRIPTION:<b>Départ</b> 18 h<br>Dossards sur place &amp; vestiaires", "END:VEVENT",
    "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20261201", "UID:x", "SUMMARY:Annulé", "STATUS:CANCELLED", "END:VEVENT",
    "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20261204", "UID:m", "RRULE:FREQ=MONTHLY;BYDAY=-1FR;COUNT=3",
    "SUMMARY:Sortie longue du club", "END:VEVENT",
    "END:VCALENDAR"])


def test_garmin_feed_is_read_as_published():
    events, info = calendrier.parse_feed(garmin_feed(TODAY), TODAY)
    assert info == {"nom": None, "garmin": True}
    titles = [e["title"] for e in events]
    assert titles[2] == "Renforcement musculaire : gainage et PPG pour les coureurs qui veulent tenir la distance"
    workout = events[1]
    assert workout["start"] == day(1) and workout["all_day"]
    assert workout["description"] == "Échauffement 20 min, puis 10 × 400 m à 100 % VMA\nRécupération 1 min 30"
    race = events[3]
    assert race["start"] == dt.datetime.combine(day(12), dt.time(9, 30))  # l'heure affichée par Garmin, telle quelle
    assert race["location"] == "Saint-Rémy, France" and not race["all_day"]
    assert [calendrier.classify(e) for e in events] == [("seance", "course"), ("seance", "course"),
                                                        ("seance", "renfo"), ("course", "course")]
    # Une course sans heure ni lieu se reconnaît à son nom ; les séances d'un plan Garmin Coach, jamais
    garmin = {"all_day": True, "garmin": True}
    assert calendrier.classify({**garmin, "title": "Semi-marathon de Boulogne"}) == ("course", "course")
    assert calendrier.classify({**garmin, "title": "Course de base"}) == ("seance", "course")
    assert calendrier.classify({**garmin, "title": "Allure marathon 3 × 5 km"}) == ("seance", "course")
    assert calendrier.classify({**garmin, "title": "Strength Workout"}) == ("seance", "renfo")
    assert calendrier.classify({**garmin, "title": "Indoor Cycling"}) == ("seance", "velo")


def test_other_agendas_recurrences_and_time_zones():
    events = calendrier.parse(GOOGLE, dt.date(2026, 11, 12))
    by_title = {}
    for e in events:
        by_title.setdefault(e["title"], []).append(e)
    # 18 h à Paris (17 h UTC), mardis et jeudis, sauf le 12 (EXDATE) et le 19 déplacé (RECURRENCE-ID)
    assert [e["start"] for e in by_title["Renfo du club"]] == [
        dt.datetime(2026, 11, 10, 18), dt.datetime(2026, 11, 17, 18), dt.datetime(2026, 11, 24, 18),
        dt.datetime(2026, 11, 26, 18)]
    moved = by_title["Renfo du club (décalé)"][0]
    assert moved["start"] == dt.datetime(2026, 11, 19, 19) and moved["end"] == dt.datetime(2026, 11, 19, 20, 30)
    assert "Annulé" not in by_title and "Rappel" not in json.dumps([e["description"] for e in events])
    assert [e["start"] for e in by_title["Sortie longue du club"]] == [
        dt.date(2026, 12, 25), dt.date(2027, 1, 29), dt.date(2027, 2, 26)]  # dernier vendredi du mois
    holidays = by_title["Vacances"][0]
    assert calendrier.classify(holidays) == ("autre", None) and calendrier._end(holidays) == "2026-12-22"
    race = by_title["Corrida de la Saint-Sylvestre"][0]
    assert calendrier.classify(race) == ("course", "course")
    assert race["description"] == "Départ 18 h\nDossards sur place & vestiaires"  # HTML de Google : texte simple
    assert calendrier.classify({"title": "Footing 10 km", "all_day": True}) == ("seance", "course")
    assert calendrier.classify({"title": "Sortie vélo 2 h", "all_day": True}) == ("seance", "velo")
    assert calendrier.classify({"title": "Triathlon de Nice", "all_day": True}) == ("course", None)
    assert calendrier.classify({"title": "Dentiste", "all_day": False}) == ("autre", None)
    assert calendrier.classify({"title": "Développé couché", "all_day": True}) == ("autre", None)


def test_links_are_cleaned_and_only_ever_shown_masked():
    assert calendrier.clean_url(f" webcal://connect.garmin.com/modern/calendar/export/{TOKEN} ") == \
        f"https://connect.garmin.com/modern/calendar/export/{TOKEN}"
    for wrong in ("", "connect.garmin.com/calendar", "ftp://exemple.fr/a.ics", "https://a b.fr/x.ics"):
        with pytest.raises(ValueError):
            calendrier.clean_url(wrong)
    shown = calendrier.masked(f"https://connect.garmin.com/modern/calendar/export/{TOKEN}")
    assert shown == f"connect.garmin.com/…{TOKEN[-4:]}" and TOKEN not in shown


def test_errors_never_repeat_the_link(calendar):
    calendar.status = 404
    with pytest.raises(calendrier.CalendarError) as gone:
        calendrier.fetch(calendar.link)
    assert gone.value.access_refused and "annulée" in str(gone.value) and TOKEN not in str(gone.value)
    calendar.status, calendar.body = 200, "<html>pas un agenda</html>"
    with pytest.raises(calendrier.CalendarError) as wrong:
        calendrier.fetch(calendar.link)
    assert "iCal" in str(wrong.value) and not wrong.value.access_refused
    with pytest.raises(calendrier.CalendarError) as down:
        calendrier.fetch(f"http://127.0.0.1:9/modern/calendar/export/{TOKEN}")
    assert "injoignable" in str(down.value) and TOKEN not in str(down.value)
    assert down.value.__suppress_context__  # le message d'origine (avec l'adresse) n'est jamais montré


# ------------------------------------------------------------- prévu et fait
def test_history_is_kept_and_the_future_replaced():
    with db.session() as conn:
        calendrier.store(conn, calendrier.parse(garmin_feed(day(-3)), day(-3)), today=day(-3))
        # Trois jours plus tard : Garmin ne publie plus le passé, Foulée le garde
        feed = calendrier.parse(garmin_feed(TODAY), TODAY)
        summary = calendrier.store(conn, feed, today=TODAY)
        rows = conn.execute("SELECT date, title FROM calendar_events ORDER BY date, title").fetchall()
    dates = [r["date"] for r in rows]
    assert day(-3).isoformat() in dates and day(-2).isoformat() in dates  # le passé lu il y a trois jours
    assert summary == {"evenements": 4, "a_venir": 4, "courses": 1}
    # Tout ce qui vient a été remplacé : la course lue il y a trois jours (à J+9) a laissé place à la nouvelle
    assert day(9).isoformat() not in dates
    assert [r["date"] for r in rows if r["title"] == "10 km de la Vallée"] == [day(12).isoformat()]


def test_a_session_of_today_that_leaves_the_feed_stays():
    with db.session() as conn:
        calendrier.store(conn, calendrier.parse(garmin_feed(TODAY), TODAY), today=TODAY)
        # Ce soir, le calendrier publié n'a plus la séance du jour : elle reste, pour dire « fait » ou « manqué »
        lines = garmin_feed(TODAY).split("\r\n")
        start = lines.index("UID:w1-garmin") - 1
        del lines[start:lines.index("END:VEVENT", start) + 1]
        assert "Footing 45 min" not in "\r\n".join(lines)
        calendrier.store(conn, calendrier.parse("\r\n".join(lines), TODAY), today=TODAY)
        assert conn.execute("SELECT COUNT(*) FROM calendar_events WHERE date = ? AND title = 'Footing 45 min'",
                            (TODAY.isoformat(),)).fetchone()[0] == 1
        calendrier.store(conn, calendrier.parse(garmin_feed(TODAY), TODAY), today=TODAY)  # et pas en double
        assert conn.execute("SELECT COUNT(*) FROM calendar_events WHERE date = ?",
                            (TODAY.isoformat(),)).fetchone()[0] == 1


def test_planned_sessions_against_done_sessions():
    feed = "\r\n".join([
        "BEGIN:VCALENDAR", "PRODID:-//Garmin Connect//ICalProvider 1.0//EN",
        *[line for d, title in ((-3, "Fractionné 6 × 800 m"), (-2, "Footing 50 min"), (-1, "Renforcement"),
                                (0, "Seuil 3 × 3 km"), (2, "Sortie longue"))
          for line in ("BEGIN:VEVENT", f"DTSTART;VALUE=DATE:{day(d):%Y%m%d}", f"SUMMARY:{title}", "END:VEVENT")],
        "BEGIN:VEVENT", f"DTSTART;TZID=Europe/Paris:{day(-1):%Y%m%d}T100000", "SUMMARY:Trail des Crêtes",
        "LOCATION:Vercors", "END:VEVENT", "END:VCALENDAR"])
    with db.session() as conn:
        calendrier.store(conn, calendrier.parse(feed, day(-3)), today=day(-3))
        add_activity(conn, "garmin:1", day(-3))
        add_activity(conn, "garmin:2", day(-1), sport="trail", name="Trail des Crêtes")
        add_activity(conn, "garmin:3", day(-1), sport="velo")  # pas du renfo : la séance de renfo est manquée
        plan = calendrier.plan(conn, day(-7), day(7))
    state = {p["titre"]: (p["statut"], p["seance_id"]) for p in plan}
    assert state == {
        "Fractionné 6 × 800 m": ("fait", "garmin:1"), "Footing 50 min": ("manque", None),
        "Renforcement": ("manque", None), "Trail des Crêtes": ("fait", "garmin:2"),  # la course passe d'abord
        "Seuil 3 × 3 km": ("aujourdhui", None), "Sortie longue": ("a_venir", None)}
    assert calendrier.tally(plan) == {"prevues": 6, "faites": 2, "manquees": 2, "a_venir": 2, "courses": 1}


# --------------------------------------------------------------- l'interface
def test_linking_the_calendar_adds_the_view_the_week_and_a_green_pill(calendar, caplog):
    caplog.set_level(logging.DEBUG)
    http = TestClient(web.create_app())
    assert http.get("/api/bootstrap").json()["calendrier"]["lie"] is False
    bad = http.put("/api/calendrier", json={"lien": calendar.link.replace(TOKEN, "0" * 32)}, headers=WRITE)
    assert bad.status_code == 400 and "annulée" in bad.json()["detail"] and vault.get_secret("calendrier") is None

    info = link(http, calendar)
    assert info["lie"] and info["masque"].endswith(TOKEN[-4:]) and info["lu"]["a_venir"] == 4
    assert info["vue"] == "calendrier" and vault.get_secret("calendrier") == calendar.link
    names = [v["id"] for v in http.get("/api/views").json()]
    assert names.index("calendrier") == names.index("accueil") + 1  # juste après l'Accueil, dans la colonne
    boot = http.get("/api/bootstrap").json()
    assert boot["calendrier"]["prochaine_course"]["titre"] == "10 km de la Vallée"
    pill = next(c for c in boot["connexions"] if c["cle"] == "calendrier")
    assert pill["etat"] == "ok" and pill["reglages"] == "calendrier"

    week = http.get("/api/semaine").json()
    planned = [p for d in week["jours"] for p in d["prevu"]]
    assert planned and {p["statut"] for p in planned} <= {"aujourdhui", "a_venir"}
    assert any(s["cle"] == "calendrier" for s in week["sources"])
    month = http.get("/api/calendrier", params={"start": TODAY.isoformat(),
                                                "end": day(20).isoformat()}).json()
    assert [e["titre"] for e in month["evenements"]][-1] == "10 km de la Vallée"
    assert month["bilan"]["courses"] == 1 and month["evenements"][-1]["heure"] == "09:30"

    # Le lien ne sort jamais : ni l'interface, ni les réglages exportés, ni le journal
    every = [http.get(path).text for path in ("/api/bootstrap", "/api/calendrier/statut", "/api/sync",
                                               "/api/reglages/export", "/api/views", "/api/semaine")]
    with db.session(readonly=True) as conn:
        every += [json.dumps([dict(r) for r in conn.execute("SELECT * FROM meta")]),
                  json.dumps([dict(r) for r in conn.execute("SELECT * FROM sync_log")])]
    assert secret_free(*every, caplog.text)

    gone = http.delete("/api/calendrier", headers=WRITE).json()
    assert gone["lie"] is False and vault.get_secret("calendrier") is None
    assert "calendrier" not in [v["id"] for v in http.get("/api/views").json()]
    assert not any(c["cle"] == "calendrier" for c in http.get("/api/bootstrap").json()["connexions"])
    assert http.get("/api/semaine").json()["plan"] is None


def test_a_cancelled_publication_turns_the_pill_red_and_pauses_it(calendar):
    http = TestClient(web.create_app())
    link(http, calendar)
    calendar.status = 404
    failed = http.post("/api/calendrier/actualiser", headers=WRITE)
    assert failed.status_code == 502 and "annulée" in failed.json()["detail"] and TOKEN not in failed.text
    pill = next(c for c in http.get("/api/sync").json()["connexions"] if c["cle"] == "calendrier")
    assert pill["etat"] == "ko" and pill["bloque"] and "colle le nouveau lien" in pill["texte"]
    with db.session(readonly=True) as conn:
        assert "calendrier" not in sync.due_sources(conn)  # en pause : réessayer ne sert à rien
        assert calendrier.plan(conn, TODAY, day(20))  # les séances déjà lues restent
    calendar.status = 200
    assert http.post("/api/calendrier/actualiser", headers=WRITE).status_code == 200
    pill = next(c for c in http.get("/api/sync").json()["connexions"] if c["cle"] == "calendrier")
    assert pill["etat"] == "ok" and not pill["bloque"]


def test_the_link_only_travels_through_the_machine_itself(calendar, monkeypatch):
    from foulee import access

    monkeypatch.setattr(access, "ITERATIONS", 1000)
    access.set_password("mot-de-passe-maison")
    lan = TestClient(web.create_app(), client=("192.168.0.50", 50000))
    host = {**WRITE, "Host": "192.168.0.19"}
    assert lan.post("/api/connexion", json={"mot_de_passe": "mot-de-passe-maison"}, headers=host).status_code == 200
    assert lan.put("/api/calendrier", json={"lien": calendar.link}, headers=host).status_code == 403
    assert vault.get_secret("calendrier") is None and calendar.hits == 0
    assert lan.get("/api/calendrier/statut", headers=host).json()["local"] is False


# ------------------------------------------------------------------ la synchro
def test_the_calendar_follows_the_sync_but_is_not_a_first_import(calendar):
    calendrier.save_url(calendar.link)
    assert sync.active_sources() == ["garmin", "calendrier"] and sync.can_sync()
    with db.session() as conn:
        assert sync.due_sources(conn) == ["calendrier"]  # avant le premier import : le calendrier seul
    result = sync.run(sources=["calendrier"])
    assert result["statut"] == "ok" and result["sources"]["calendrier"]["a_venir"] == 4
    with db.session(readonly=True) as conn:
        assert db.get_meta(conn, "last_sync") is None  # pas une synchro des données
        assert sync.due_sources(conn) == []  # lu à l'instant
        log = conn.execute("SELECT summary FROM sync_log").fetchone()["summary"]
    assert TOKEN not in log


def test_claude_sees_the_plan_but_never_the_link(calendar):
    from foulee import mcp_server

    http = TestClient(web.create_app())
    link(http, calendar)
    with db.session() as conn:
        add_activity(conn, "garmin:9", TODAY)
    state = mcp_server.statut()["calendrier"]
    assert state["lie"] and "masque" not in state
    plan = mcp_server.calendrier_entrainement()
    assert plan["evenements"][0]["statut"] == "fait" and plan["bilan"]["courses"] == 1
    week = mcp_server.semaine()
    assert any(p["titre"] == "Footing 45 min" for d in week["jours"] for p in d["prevu"])
    rows = mcp_server.requete_sql("SELECT * FROM meta")
    assert secret_free(state, plan, week, rows, mcp_server.schema_base())


def test_a_view_of_the_same_name_is_never_touched():
    with db.session() as conn:
        views.save_view(conn, "calendrier", "Calendrier", {"tuiles": []}, "calendar")
        mine = views.sync_calendar_view(conn, True)
        assert mine == "calendrier-2"
        views.sync_calendar_view(conn, False)
        assert [r["id"] for r in conn.execute("SELECT id FROM views WHERE id LIKE 'calendrier%'")] == ["calendrier"]


def test_deleting_a_profile_forgets_its_calendar(calendar):
    entry = utilisateurs.create("Léa")
    from foulee import config

    with config.using_profile(entry):
        calendrier.save_url(calendar.link)
        assert calendrier.linked()
    assert not calendrier.linked()  # chaque profil a le sien
    utilisateurs.delete(entry["id"])
    with config.using_profile(entry):
        assert not calendrier.linked()


def test_demo_has_a_calendar():
    from foulee import demo

    demo.build(days=40, second_profile=False)
    http = TestClient(web.create_app())
    boot = http.get("/api/bootstrap").json()
    assert boot["calendrier"]["lie"] and boot["calendrier"]["prochaine_course"]
    assert any(v["id"] == "calendrier" for v in boot["vues"])
    month = http.get("/api/calendrier", params={"start": day(-14).isoformat(), "end": day(30).isoformat()}).json()
    states = {e["statut"] for e in month["evenements"]}
    assert {"fait", "manque", "a_venir"} <= states
    assert http.put("/api/calendrier", json={"lien": "https://exemple.fr/a.ics"}, headers=WRITE).status_code == 400
