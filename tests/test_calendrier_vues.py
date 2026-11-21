"""0.8.3 : le calendrier des pages coach et élève à la semaine, au mois ou à l'année (demande de William)."""

from datetime import date, timedelta

import pytest

from foulee import coach, db, demo
from test_relais_club import PASSWORD, relay, token  # noqa: F401  (le relais du club, en mémoire)


def _group(relay):
    sophie = token(relay, "sophie")
    code = relay.post("/api/v1/invitations", headers=sophie).json()["invitation"]["code"]
    demo.build(days=45, second_profile=False)
    with db.session() as conn:
        coach.join(conn, "https://relais.test", code=code, ident="demo.eleve", name="Élève démo", password=PASSWORD)
        coach.set_accord(conn, {"seances": True, "objectif": True})
    sid = relay.get("/api/v1/groupe", headers=sophie).json()["eleves"][0]["id"]
    return sophie, sid


def test_any_period_from_a_week_to_a_year(relay):
    sophie, sid = _group(relay)
    later = date.today() + timedelta(days=120)  # au-delà des neuf semaines du départ
    relay.post("/api/v1/propositions", headers=sophie, json={"eleves": [sid], "date": later.isoformat(), "titre": "Piste",
                                                            "sport": "course", "blocs": [{"genre": "corps", "duree_min": 20, "pct_vma": 80}]})
    first = later.replace(day=1)
    month = relay.get(f"/api/v1/eleves/{sid}/calendrier", headers=sophie,
                      params={"debut": first.isoformat(), "fin": (first + timedelta(days=40)).isoformat()}).json()
    days = month["jours"]
    assert date.fromisoformat(days[0]["date"]).weekday() == 0 and date.fromisoformat(days[-1]["date"]).weekday() == 6
    assert days[0]["date"] <= first.isoformat() and len(days) % 7 == 0
    piste = next(p for d in days if d["date"] == later.isoformat() for p in d["prevu"] if p["source"] == "coach")
    assert piste["blocs"]  # au mois : les esquisses
    year = relay.get(f"/api/v1/eleves/{sid}/calendrier", headers=sophie,
                     params={"debut": f"{later.year}-01-01", "fin": f"{later.year}-12-31"}).json()
    assert len(year["jours"]) <= 378
    piste = next(p for d in year["jours"] if d["date"] == later.isoformat() for p in d["prevu"] if p["source"] == "coach")
    assert "blocs" not in piste  # à l'année : des pastilles, pas d'esquisses
    # refus : plus d'un an, dates illisibles, élève d'un autre groupe ; l'élève ne lit que le sien
    too_long = relay.get(f"/api/v1/eleves/{sid}/calendrier", headers=sophie, params={"debut": "2026-01-01", "fin": "2027-06-01"})
    assert too_long.status_code == 400
    assert relay.get(f"/api/v1/eleves/{sid}/calendrier", headers=sophie, params={"debut": "hier", "fin": "demain"}).status_code == 400
    assert relay.get(f"/api/v1/eleves/{sid + 99}/calendrier", headers=sophie,
                     params={"debut": "2026-11-01", "fin": "2026-11-30"}).status_code == 403
    with db.session() as conn:  # côté élève, par la passerelle de Foulée
        mine = coach.proxy(conn, "GET", "moi/calendrier", None, {"debut": first.isoformat(), "fin": (first + timedelta(days=6)).isoformat()})
        assert len(mine["jours"]) in (7, 14)
        with pytest.raises(coach.CoachError):
            coach.proxy(conn, "GET", "moi/calendrier", None, {"debut": "x"})
