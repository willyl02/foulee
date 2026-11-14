"""0.8.0b4 : la séance du coach en fichier FIT, le calendrier qui suit le relais, la forme du jour en petites
courbes (et l'Accueil qui lui laisse la place), le logo du club."""

import io
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from foulee import analysis, club, coach, config, db, reglages, views, workout_fit
from foulee.relais import store
from foulee.relais.app import create_relay_app

PASSWORD = "un-mot-de-passe-solide"
HEADERS = {"X-Foulee": "1"}

SEUIL = {"id": 7, "date": "2026-11-16", "titre": "Seuil 3 × 10 min", "sport": "course",
         "consigne": "Régulier, sans finir à bloc.",
         "blocs": [{"genre": "echauffement", "duree_min": 20, "pct_vma": 65},
                   {"genre": "corps", "nom": "Seuil", "repetitions": 3, "duree_min": 10, "pct_vma": 88,
                    "recup_min": 2, "recup_texte": "trot"},
                   {"genre": "corps", "nom": "Côtes", "repetitions": 6, "distance_m": 200, "zone_fc": 5},
                   {"genre": "calme", "duree_min": 10}]}


# ------------------------------------------------------------------ fichier FIT
def steps_of(data):
    return workout_fit.decode(data)["workout_step_mesgs"]


def test_fit_workout_steps_repeats_and_targets():
    data = workout_fit.build(SEUIL, 16.0)
    messages = workout_fit.decode(data)
    assert messages["file_id_mesgs"][0]["type"] == "workout"
    workout = messages["workout_mesgs"][0]
    assert workout["wkt_name"] == "Seuil 3 × 10 min" and workout["sport"] == "running"
    steps = messages["workout_step_mesgs"]
    assert workout["num_valid_steps"] == len(steps) == 7
    warm, seuil, rest, loop, hills, loop2, cool = steps
    assert warm["intensity"] == "warmup" and warm["duration_type"] == "time" and warm["duration_time"] == 1200
    # 88 % de 16 km/h = 3,91 m/s : une fourchette de ± 3 % autour, en allure
    assert seuil["target_type"] == "speed"
    assert seuil["custom_target_speed_low"] == pytest.approx(3.79, abs=0.01)
    assert seuil["custom_target_speed_high"] == pytest.approx(4.03, abs=0.01)
    assert "88 % VMA · 4:16 /km" in seuil["notes"]
    assert rest["intensity"] == "recovery" and rest["duration_time"] == 120 and rest["notes"] == "trot"
    assert loop["duration_type"] == "repeat_until_steps_cmplt"
    assert loop["duration_step"] == 1 and loop["repeat_steps"] == 3  # revenir à l'étape 1, trois fois
    assert hills["duration_type"] == "distance" and hills["duration_distance"] == 200
    assert hills["target_type"] == "heart_rate" and hills["target_hr_zone"] == 5
    assert loop2["duration_step"] == 4 and loop2["repeat_steps"] == 6
    assert cool["intensity"] == "cooldown" and cool["target_type"] == "open"


def test_fit_without_vma_or_on_a_bike_keeps_open_targets():
    seuil = steps_of(workout_fit.build(SEUIL, None))[1]
    assert seuil["target_type"] == "open" and seuil["notes"].startswith("88 % VMA")
    bike = {**SEUIL, "sport": "velo"}
    messages = workout_fit.decode(workout_fit.build(bike, 16.0))
    assert messages["workout_mesgs"][0]["sport"] == "cycling"
    assert messages["workout_step_mesgs"][1]["target_type"] == "open"  # une allure n'a pas de sens à vélo
    with pytest.raises(workout_fit.WorkoutError):
        workout_fit.build({**SEUIL, "blocs": []}, 16.0)


def test_fit_file_name_is_plain_ascii():
    assert workout_fit.file_name(SEUIL) == "2026-11-16-seuil-3-10-min.fit"
    assert workout_fit.file_name({"titre": "Échauffement + côtes"}) == "echauffement-cotes.fit"


# ------------------------------------------------------- relais : élève et coach
@pytest.fixture
def relay(monkeypatch):
    client = TestClient(create_relay_app())

    def send(method, url, *, headers, payload):
        path = url.split("://", 1)[1].split("/", 1)[1]
        response = client.request(method, "/" + path, headers=headers, json=payload)
        return response.status_code, response.json() if response.content else {}

    monkeypatch.setattr(coach, "transport", send)
    with store.session() as conn:
        store.create_account(conn, ident="sophie", name="Sophie R.", password=PASSWORD, role="coach", admin=True)
    return client


def bearer(client, ident):
    return {"Authorization": "Bearer " + client.post("/api/v1/connexion", json={
        "identifiant": ident, "mot_de_passe": PASSWORD}).json()["jeton"]}


def invite(client):
    return client.post("/api/v1/invitations", headers=bearer(client, "sophie")).json()["invitation"]["code"]


def test_student_and_coach_download_the_fit(relay):
    """L'élève (profil démo) télécharge la séance avec sa VMA ; le coach (vrai profil), avec celle de l'élève."""
    from foulee import demo
    from foulee.web import create_app

    code = invite(relay)
    demo.build(days=10, second_profile=False)
    with db.session() as conn:
        coach.join(conn, "https://relais.test", code=code, ident="demo.eleve", name="Élève démo", password=PASSWORD)
        coach.set_accord(conn, {"seances": True, "objectif": True, "gps": False, "masquer": False})
        vma = db.get_settings(conn)["vma_kmh"]
    sophie = bearer(relay, "sophie")
    student_id = relay.get("/api/v1/groupe", headers=sophie).json()["eleves"][0]["id"]
    day = (date.today() + timedelta(days=2)).isoformat()
    relay.post("/api/v1/propositions", headers=sophie, json={"eleves": [student_id], "date": day, **{
        k: SEUIL[k] for k in ("titre", "sport", "consigne", "blocs")}})
    with db.session() as conn:
        proposal = coach.my_page(conn)["propositions"][0]
        name, data = coach.workout_file(conn, proposal["id"])
    assert name == f"{day}-seuil-3-10-min.fit"
    seuil = steps_of(data)[1]
    assert seuil["custom_target_speed_low"] == pytest.approx(vma * 0.88 / 3.6 * 0.97, abs=0.002)

    web = TestClient(create_app())
    res = web.get(f"/api/coach/seances/{proposal['id']}.fit")
    assert res.status_code == 200 and res.headers["content-type"] == "application/vnd.ant.fit"
    assert f'filename="{name}"' in res.headers["content-disposition"]
    assert steps_of(res.content) == steps_of(data)
    missing = web.get("/api/coach/seances/999999.fit")
    assert missing.status_code == 404 and "Mon coach" in missing.json()["detail"]

    config.set_demo(False)
    with db.session() as conn:
        coach.login(conn, "https://relais.test", "sophie", PASSWORD)
    res = TestClient(create_app()).get(f"/api/coach/eleves/{student_id}/seances/{proposal['id']}.fit")
    assert res.status_code == 200
    assert steps_of(res.content)[1]["custom_target_speed_high"] == pytest.approx(vma * 0.88 / 3.6 * 1.03, abs=0.002)


# ------------------------------------------------------ calendrier et relais
def calendar_views(conn):
    return [r["id"] for r in conn.execute("SELECT id FROM views WHERE id LIKE 'calendrier%'")]


def test_calendar_view_comes_with_the_relay(relay):
    from foulee import calendrier

    code = invite(relay)
    with db.session() as conn:
        views.ensure_default_views(conn)
        assert calendar_views(conn) == []
        coach.join(conn, "https://relais.test", code=code, ident="marie", name="Marie", password=PASSWORD)
        assert calendar_views(conn) == ["calendrier"]
        assert calendrier.status(conn)["lie"] is True and calendrier.status(conn)["relais"] is True
        coach.logout(conn)
        assert calendar_views(conn) == []  # ni relais ni calendrier Garmin : la vue repart
        # Avec un calendrier Garmin relié, la vue reste après la déconnexion du relais
        coach.login(conn, "https://relais.test", "marie", PASSWORD)
        calendrier.save_url("https://connect.garmin.com/modern/calendar/export/abc")
        coach.logout(conn)
        assert calendar_views(conn) == ["calendrier"]


def test_calendar_unlink_keeps_the_view_while_relay_linked(relay):
    from foulee import calendrier
    from foulee.web import create_app

    code = invite(relay)
    with db.session() as conn:
        views.ensure_default_views(conn)
        coach.join(conn, "https://relais.test", code=code, ident="marie", name="Marie", password=PASSWORD)
        calendrier.save_url("https://connect.garmin.com/modern/calendar/export/abc")
    res = TestClient(create_app()).delete("/api/calendrier", headers=HEADERS)
    assert res.status_code == 200, res.text
    with db.session() as conn:
        assert calendar_views(conn) == ["calendrier"]  # les séances du coach y restent


# ------------------------------------------------------- l'Accueil : forme large
def home_sizes(conn):
    spec = json.loads(conn.execute("SELECT spec FROM views WHERE id = 'accueil'").fetchone()["spec"])
    return {t["type"]: (t["w"], t["h"]) for t in spec["tuiles"] if t["type"] in ("forme", "objectif")}


def set_home(conn, form, goal):
    spec = json.loads(conn.execute("SELECT spec FROM views WHERE id = 'accueil'").fetchone()["spec"])
    for tile in spec["tuiles"]:
        if tile["type"] in ("forme", "objectif"):
            tile["w"], tile["h"] = form if tile["type"] == "forme" else goal
    conn.execute("UPDATE views SET spec = ? WHERE id = 'accueil'", (json.dumps(spec),))
    db.delete_meta(conn, "vue_forme_large")


def test_home_form_tile_widens_once():
    with db.session() as conn:
        views.ensure_default_views(conn)
        assert home_sizes(conn) == {"forme": (9, 3), "objectif": (3, 3)}  # installation neuve
        set_home(conn, (8, 2), (4, 2))  # l'Accueil d'avant 0.8.0b4
        views.ensure_default_views(conn)
        assert home_sizes(conn) == {"forme": (9, 3), "objectif": (3, 3)}
        set_home(conn, (6, 2), (6, 2))  # arrangé autrement : pas touché
        views.ensure_default_views(conn)
        assert home_sizes(conn) == {"forme": (6, 2), "objectif": (6, 2)}
        set_home(conn, (8, 3), (4, 2))
        views.ensure_default_views(conn)
        assert home_sizes(conn) == {"forme": (8, 3), "objectif": (4, 2)}
        assert db.get_meta(conn, "vue_forme_large") == "1"


def test_day_form_signals_carry_their_little_chart():
    today = date.today()
    with db.session() as conn:
        for i in range(1, 31):
            db.put_daily(conn, (today - timedelta(days=i)).isoformat(),
                         {"resting_hr": 46, "hrv_night": 60, "hrv_bl_low": 55, "hrv_bl_high": 68, "sleep_s": 7 * 3600})
        db.put_daily(conn, today.isoformat(), {"resting_hr": 50, "hrv_night": 52, "hrv_bl_low": 55, "hrv_bl_high": 68,
                                               "sleep_s": 6 * 3600, "sleep_need_min": 480, "sleep_score": 71})
        conn.commit()
        form = analysis.day_form(conn, today, db.get_settings(conn))
    charts = {s["metric"]: s["graphe"] for s in form["signaux"]}
    rhr = charts["resting_hr"]
    assert rhr["type"] == "ligne" and len(rhr["valeurs"]) == 30 and rhr["valeurs"][-1] == 50
    assert rhr["moyenne"] == pytest.approx(46.1, abs=0.2) and rhr["fin"] == today.isoformat()
    hrv = charts["hrv_night"]
    assert hrv["bande"][-1] == [55, 68] and len(hrv["bande"]) == 30 and hrv["valeurs"][-1] == 52
    sleep = charts["sleep_s"]
    assert sleep["type"] == "barres" and len(sleep["valeurs"]) == 14 and sleep["seuil"] == 480 * 60
    assert sleep["affiches"][-1]  # la valeur lisible, pour l'info-bulle de chaque barre
    score = charts["sleep_score"]
    assert (score["seuil"], score["min"], score["max"]) == (80, 0, 100)
    assert all(c["legende"] for c in charts.values())


# ------------------------------------------------------------- logo du club
def png(size=(800, 600), *, transparent=True, margin=100):
    image = Image.new("RGBA", size, (0, 0, 0, 0) if transparent else (255, 255, 255, 255))
    for x in range(margin, size[0] - margin):
        for y in range(margin, size[1] - margin, 7):
            image.putpixel((x, y), (200, 30, 40, 255))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def test_club_logo_keeps_transparency_trims_and_shrinks():
    info = club.save_logo(png())
    assert info["logo"] and info["transparent"] is True and info["logo_maj"]
    with Image.open(club.logo_path()) as kept:
        assert kept.format == "PNG" and kept.mode == "RGBA"
        assert kept.width == 500 and kept.height in (333, 334)  # sans les marges transparentes (600 × 400), 500 px au plus
        low, high = kept.getchannel("A").getextrema()
        assert low == 0 and high > 0  # la transparence est gardée
    small = club.save_logo(png((120, 120), transparent=False, margin=0))
    assert small["transparent"] is False
    with Image.open(club.logo_path()) as kept:
        assert kept.size == (120, 120)  # jamais agrandi
    assert club.delete_logo()["logo"] is False and not club.logo_path().exists()


def test_club_logo_refusals():
    for data, words in ((b"", "vide"), (b"pas une image", "lisible"), (png((20, 20), margin=2), "entre 32"),
                        (png((64, 64), margin=40), "transparente")):
        with pytest.raises(club.LogoError, match=words):
            club.save_logo(data)
    gif = io.BytesIO()
    Image.new("RGB", (64, 64), "red").save(gif, "GIF")
    with pytest.raises(club.LogoError, match="GIF"):
        club.save_logo(gif.getvalue())


def test_club_logo_web_bootstrap_and_demo_apart():
    from foulee.web import create_app

    web = TestClient(create_app())
    assert web.get("/api/bootstrap").json()["club_logo"] is None
    assert web.get("/api/club/logo").status_code == 404
    res = web.put("/api/club/logo", content=png(), headers={**HEADERS, "Content-Type": "image/png"})
    assert res.status_code == 200 and res.json()["transparent"] is True
    version = web.get("/api/bootstrap").json()["club_logo"]
    assert version == res.json()["logo_maj"]
    logo = web.get(f"/api/club/logo?v={version}")
    assert logo.status_code == 200 and logo.headers["content-type"] == "image/png"
    bad = web.put("/api/club/logo", content=b"rien", headers={**HEADERS, "Content-Type": "image/png"})
    assert bad.status_code == 400 and "lisible" in bad.json()["detail"]
    config.set_demo(True)  # le mode démo a son propre logo
    assert club.logo_version() is None
    config.set_demo(False)
    assert club.logo_version() == version
    assert web.delete("/api/club/logo", headers=HEADERS).json()["logo"] is False


def test_settings_export_carries_the_club_logo():
    club.save_logo(png())
    with db.session() as conn:
        data = reglages.export(conn)
        assert data["logo_club"]
        assert "logo_club" not in reglages.export(conn, with_logo=False)
    club.delete_logo()
    with db.session() as conn:
        report = reglages.import_(conn, data, parts={"logo"})
    assert report["logo"] is True and club.logo_path().exists()


# ------------------------------------------------- « Ton coach fait-il partie de ton club ? »
def test_same_club_answer_is_the_students_and_goes_with_the_link(relay):
    from foulee.web import create_app

    code = invite(relay)
    with db.session() as conn:
        coach.join(conn, "https://relais.test", code=code, ident="marie", name="Marie", password=PASSWORD)
        assert coach.status(conn)["meme_club"] is False
    web = TestClient(create_app())
    res = web.put("/api/coach/meme-club", headers=HEADERS, json={"oui": True})
    assert res.status_code == 200 and res.json()["meme_club"] is True
    assert web.get("/api/bootstrap").json()["coach"]["meme_club"] is True
    assert web.put("/api/coach/meme-club", headers=HEADERS, json={"oui": False}).json()["meme_club"] is False
    web.put("/api/coach/meme-club", headers=HEADERS, json={"oui": True})
    with db.session() as conn:
        coach.logout(conn)  # se déconnecter efface la réponse (un autre coach, peut-être, la prochaine fois)
        assert db.get_meta(conn, coach.META_SAME_CLUB) is None
        coach.login(conn, "https://relais.test", "sophie", PASSWORD)
        with pytest.raises(coach.CoachError, match="élèves"):
            coach.set_same_club(conn, True)


def test_relay_names_unnamed_blocks_by_their_kind():
    from foulee.relais import club as relay_club

    blocks = relay_club.clean_blocks([{"genre": "echauffement", "duree_min": 20}, {"duree_min": 5},
                                      {"genre": "calme", "nom": "", "duree_min": 10}])
    assert [b["nom"] for b in blocks] == ["Échauffement", "Bloc", "Retour au calme"]
