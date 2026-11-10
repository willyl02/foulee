"""Horaires de travail : modèles (bureau, 2x8, 3x8, 5x8), congés, comparaisons, même règle côté interface."""

import json
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foulee import analysis, db, schedule, web

WRITE = {"X-Foulee": "1"}
FORMAT_JS = Path(__file__).resolve().parents[1] / "foulee" / "static" / "js" / "format.js"


def test_old_alternating_setting_still_reads_the_same():
    """Les réglages « postes » de la 0.4 deviennent un 2x8 ancré sur la parité des semaines ISO."""
    legacy = {"actif": True, "impaires": "soir", "paires": "matin", "jours_ouvres": True,
              "semaines_exclues": ["2026-W32", "pas-une-semaine"]}
    h = schedule.from_legacy(legacy)
    plan = schedule.Schedule(h)
    assert h["modele"] == "2x8" and h["cycle"]["ancrage"] == "parite"
    monday_odd = date.fromisocalendar(2026, 45, 1)
    assert plan.shift_of(monday_odd) == "soir" and plan.shift_of(monday_odd + timedelta(days=7)) == "matin"
    assert plan.shift_of(monday_odd + timedelta(days=5)) is None              # samedi : repos, pas compté
    assert plan.shift_of(monday_odd + timedelta(days=5), include_rest=True) == "soir"  # ou rattaché à sa semaine
    assert h["conges"] == [{"du": "2026-08-03", "au": "2026-08-09", "nom": "Semaine 32"}]
    assert plan.shift_of(date(2026, 8, 5)) is None and plan.day(date(2026, 8, 5))["conges"] == "Semaine 32"
    # Sans réglage « horaires », c'est ce que voient tous les calculs
    settings = {"postes": legacy, "horaires": None}
    assert analysis.shift_of(monday_odd, settings) == "soir"


def test_three_shifts_rotate_week_by_week():
    h = schedule.preset("3x8", today=date(2026, 11, 10))
    plan = schedule.Schedule(schedule.clean(h))
    monday = date(2026, 11, 9)  # semaine n° 1 du cycle
    assert [plan.shift_of(monday + timedelta(days=7 * k)) for k in range(4)] == ["matin", "apres-midi", "nuit", "matin"]
    assert [plan.shift_of(monday - timedelta(days=7 * k)) for k in range(1, 3)] == ["nuit", "apres-midi"]
    assert plan.day(monday + timedelta(days=14)) == {
        "date": "2026-11-23", "poste": "nuit", "nom": "Nuit", "debut": "21:00", "fin": "05:00", "repos": False,
        "conges": None, "actif": True, "semaine_cycle": 3}


def test_five_shifts_follow_a_day_cycle():
    h = schedule.preset("5x8", today=date(2026, 11, 10))
    plan = schedule.Schedule(schedule.clean(h))
    days = [plan.day(date(2026, 11, 10) + timedelta(days=i)) for i in range(12)]
    assert [d["poste"] for d in days] == ["matin", "matin", "apres-midi", "apres-midi", "nuit", "nuit",
                                          None, None, None, None, "matin", "matin"]
    assert days[6]["repos"] and plan.shift_of(date(2026, 11, 16)) is None
    # Jours de repos comptés à part dans un cycle en jours
    assert plan.shift_of(date(2026, 11, 16), include_rest=True) == schedule.REPOS
    assert [g["id"] for g in plan.groups(include_rest=True)] == ["matin", "apres-midi", "nuit", "repos"]
    assert plan.shift_of(date(2026, 11, 9)) is None  # la veille du 1er jour : 10e jour du cycle précédent (repos)


@pytest.mark.parametrize("change, message", [
    (lambda h: h["cycle"]["semaines"][0].__setitem__(0, "inconnu"), "poste inconnu"),
    (lambda h: h["cycle"]["semaines"].append(h["cycle"]["semaines"][0]), "parité"),
    (lambda h: h["postes"][0].__setitem__("debut", "25:00"), "heure illisible"),
    (lambda h: h["cycle"]["semaines"][0].pop(), "7 jours"),
    (lambda h: h.__setitem__("postes", []), "au moins un poste"),
])
def test_bad_schedules_are_explained(change, message):
    h = schedule.preset("2x8")
    change(h)
    with pytest.raises(schedule.ScheduleError, match=message):
        schedule.clean(h)


def test_compare_three_shifts_and_leaves():
    with db.session() as conn:
        h = schedule.preset("3x8", today=date(2026, 9, 7))
        h["conges"] = [{"du": "2026-10-05", "au": "2026-10-11", "nom": "Vacances"}]
        db.set_setting(conn, "horaires", h)
        plan = schedule.Schedule(schedule.clean(h))
        for i in range(70):
            day = date(2026, 9, 7) + timedelta(days=i)
            sleep = {"matin": 5.5, "apres-midi": 7.5, "nuit": 6.0}.get(plan.code(day), 8.5)
            db.put_daily(conn, day.isoformat(), {"sleep_s": sleep * 3600 + (i % 3) * 60})
        conn.commit()
        settings = db.get_settings(conn)
        result = analysis.shift_compare(conn, ["sleep_s"], date(2026, 9, 7), date(2026, 11, 15), settings)
    assert [g["id"] for g in result["groupes"]] == ["matin", "apres-midi", "nuit"]
    row = result["metriques"][0]
    assert row["groupes"]["matin"]["moyenne"] == pytest.approx(5.5 * 3600 + 60, abs=60)
    assert row["entre"] == ["apres-midi", "matin"] and row["effet"]["lecture"] == "net"
    # La semaine de congés (du 5 au 11 octobre) n'est comptée nulle part
    assert sum(result["jours"].values()) == 10 * 5 - 5


def test_settings_api_validates_and_returns_the_plan():
    client = TestClient(web.create_app())
    bad = schedule.preset("2x8")
    bad["cycle"]["semaines"][0][0] = "inconnu"
    refused = client.put("/api/settings", json={"horaires": bad}, headers=WRITE)
    assert refused.status_code == 400 and "poste inconnu" in refused.json()["detail"]
    good = schedule.preset("bureau")
    saved = client.put("/api/settings", json={"horaires": good}, headers=WRITE).json()
    assert saved["reglages"]["horaires"]["modele"] == "bureau"
    assert saved["planning"]["modele"] == "Horaires de bureau"
    week = client.get("/api/horaires", params={"start": "2026-11-09", "end": "2026-11-15"}).json()["jours"]
    assert [d["poste"] for d in week] == ["journee"] * 5 + [None, None]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js absent")
@pytest.mark.parametrize("model", ["2x8", "3x8", "5x8", "bureau"])
def test_interface_uses_the_same_rule(model, tmp_path):
    """format.js (interface) et schedule.py (serveur) donnent le même poste, jour après jour."""
    h = schedule.clean(schedule.preset(model, today=date(2026, 11, 10)))
    h["conges"] = [{"du": "2026-12-21", "au": "2027-01-03", "nom": "Noël"}]
    plan = schedule.Schedule(h)
    days = [date(2026, 10, 1) + timedelta(days=i) for i in range(120)]
    expected = [[plan.shift_of(d), plan.shift_of(d, include_rest=True)] for d in days]
    script = tmp_path / "check.mjs"
    script.write_text(
        f"import * as F from {json.dumps(FORMAT_JS.as_uri())};\n"
        f"const settings = {{ horaires: {json.dumps(h)} }};\n"
        f"const days = {json.dumps([d.isoformat() for d in days])};\n"
        "console.log(JSON.stringify(days.map((d) => [F.shiftOf(F.parseDate(d), settings), F.shiftOf(F.parseDate(d), settings, true)])));\n",
        encoding="utf-8")
    out = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == expected
