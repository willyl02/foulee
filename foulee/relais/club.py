"""Le relais au travail : ce que les élèves partagent, les messages, les séances proposées par le coach.

- **Partage** : chaque élève choisit ce qu'il partage (l'« accord ») ; son Foulée envoie alors un extrait de ses
  4 dernières semaines, qui remplace le précédent. Le relais refiltre toujours selon l'accord : une case décochée
  efface la donnée tout de suite, même avant le prochain envoi.
- **Messages** : le fil du groupe (« groupe »), la conversation entre le coach et un élève (« eleve-ID ») et le
  fil sous une séance (« seance-ID-CLÉ »). Chacun ne voit que les fils de son groupe, et un élève seulement les
  siens.
- **Séances proposées** : le coach décrit une séance en blocs (durée ou distance, % de VMA) pour un ou plusieurs
  élèves ; chaque Foulée d'élève la reçoit avec ses propres allures. Le coach garde aussi ses modèles.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import date, timedelta
from typing import Any

from .. import metrics, renfo
from .. import appariement
from . import garmin, notifs
from .store import RelayError, local_now, now

KEEP_DAYS = 28                 # le relais ne garde que 4 semaines de séances
MAX_TEXT = 4000                # longueur d'un message
ALERT_DAYS = 5                 # « N jours sans séance » à partir de 5 jours

ACCORD_DEFAULT = {"seances": True, "objectif": True, "gps": False, "masquer": True, "sante": False, "poids": False}
ACCORD_KEYS = tuple(ACCORD_DEFAULT)

FIL_RE = re.compile(r"^(groupe|eleve-\d{1,9}|seance-\d{1,9}-[A-Za-z0-9:_.-]{1,80})$")
COMPATIBLE = {"course": metrics.RUNNING_SPORTS, "trail": metrics.RUNNING_SPORTS, "renfo": ("renfo", "cardio"),
              "cardio": ("cardio", "renfo"), "marche": ("marche", "rando"), "rando": ("rando", "marche")}


def _fits(planned: str | None, done: str | None) -> bool:
    if not planned:
        return True
    return done in COMPATIBLE.get(planned, (planned,))


def _today() -> date:
    return local_now().date()


# ------------------------------------------------------------------- nettoyage
def _txt(value: Any, size: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()) if size <= 200 else str(value).strip()
    return text[:size] or None


def _num(value: Any, low: float, high: float, digits: int = 2) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not low <= number <= high:
        return None
    return round(number, digits)


def _day(value: Any) -> str | None:
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


SESSION_TEXT = {"cle": 80, "debut": 19, "sport": 20, "sport_label": 40, "nom": 120, "description": 1500,
                "allure": 16, "avantage": 60, "ressenti": 300, "prevue": 120}
SESSION_NUM = {"duree_s": (0, 200000, 0), "deplacement_s": (0, 200000, 0), "distance_m": (0, 1000000, 0),
               "denivele_m": (0, 20000, 0), "fc_moy": (20, 250, 0), "fc_max": (20, 250, 0), "vitesse_kmh": (0, 120, 1),
               "cadence": (0, 400, 0), "puissance": (0, 3000, 0), "calories": (0, 30000, 0),
               "effet_aerobie": (0, 5, 1), "effet_anaerobie": (0, 5, 1), "charge": (0, 3000, 0), "effort": (0, 10, 0)}
LAP_NUM = {"duree_s": (0, 100000, 0), "distance_m": (0, 500000, 0), "fc_moy": (20, 250, 0),
           "vitesse_kmh": (0, 120, 1), "denivele_m": (0, 10000, 0), "debut_s": (0, 200000, 1),
           "fin_s": (0, 200000, 1), "zone": (1, 5, 0), "zone_pct": (0, 100, 0)}
CURVE_MAX = 400  # points de la courbe allégée (allure, FC) d'une séance
DAY_NUM = {"sommeil_h": (0, 24, 1), "sommeil_score": (0, 100, 0), "vfc": (0, 300, 0), "fc_repos": (20, 150, 0),
           "poids_kg": (20, 400, 1)}


def _clean_session(raw: dict, oldest: str) -> dict | None:
    if not isinstance(raw, dict):
        return None
    day = _day(raw.get("date"))
    key = _txt(raw.get("cle"), 80)
    if not day or day < oldest or not key or not re.fullmatch(r"[A-Za-z0-9:_.-]+", key):
        return None
    out: dict[str, Any] = {"date": day}
    for name, size in SESSION_TEXT.items():
        value = _txt(raw.get(name), size)
        if value is not None:
            out[name] = value
    for name, (low, high, digits) in SESSION_NUM.items():
        value = _num(raw.get(name), low, high, digits)
        if value is not None:
            out[name] = value
    laps = []
    for lap in (raw.get("tours") or [])[:120]:
        if isinstance(lap, dict):
            item = {k: v for k, (lo, hi, dg) in LAP_NUM.items() if (v := _num(lap.get(k), lo, hi, dg)) is not None}
            if lap.get("allure"):
                item["allure"] = _txt(lap.get("allure"), 16)
            if lap.get("intensite"):
                item["intensite"] = _txt(lap.get("intensite"), 20)
            laps.append(item)
    if laps:
        out["tours"] = laps
    sets = []
    for row in (raw.get("renfo") or [])[:80]:
        if isinstance(row, dict) and row.get("exercice"):
            item = {"exercice": _txt(row.get("exercice"), 80), "series": _num(row.get("series"), 0, 200, 0),
                    "reps": _num(row.get("reps"), 0, 5000, 0), "kg": _num(row.get("kg"), 0, 1000, 1),
                    "chaine": _txt(row.get("chaine"), 20)}
            if row.get("famille") in renfo.CHAIN_FAMILIES:
                item["famille"] = row["famille"]
            sets.append(item)
    if sets:
        out["renfo"] = sets
    curve = raw.get("courbe")
    if laps and isinstance(curve, dict) and isinstance(curve.get("t"), list):
        times = [_num(x, 0, 200000, 0) for x in curve["t"][:CURVE_MAX]]
        speeds = [_num(x, 0, 40, 2) for x in (curve.get("v") or [])[:len(times)]]
        hrs = [_num(x, 20, 250, 0) for x in (curve.get("fc") or [])[:len(times)]]
        if len(times) >= 2 and all(x is not None for x in times):
            out["courbe"] = {"t": times, "v": speeds + [None] * (len(times) - len(speeds)),
                             "fc": hrs + [None] * (len(times) - len(hrs))}
    trace = raw.get("trace")
    if isinstance(trace, list) and trace:
        points = []
        for point in trace[:800]:
            if isinstance(point, (list, tuple)) and len(point) == 2:
                lat, lon = _num(point[0], -90, 90, 5), _num(point[1], -180, 180, 5)
                if lat is not None and lon is not None:
                    points.append([lat, lon])
        if len(points) >= 2:
            out["trace"] = points
    return out


def _clean_goal(goal: dict) -> dict:
    return {"nom": _txt(goal.get("nom"), 80), "date": _day(goal.get("date")),
            "distance_km": _num(goal.get("distance_km"), 0, 1000, 3), "temps_cible": _txt(goal.get("temps_cible"), 12),
            "d_plus_m": _num(goal.get("d_plus_m"), 0, 30000, 0)}


def renfo_balance(sessions: list[dict], today: date | None = None) -> dict | None:
    """L'équilibre avant / arrière du renfo partagé (4 semaines), comme l'élève le voit chez lui, avec ce que le
    coach peut lui dire, et semaine par semaine. Chaque exercice est rangé par sa famille quand Foulée l'envoie,
    sinon par son nom (versions de Foulée d'avant 0.8.1). None sans renfo."""
    today = today or _today()
    monday = _monday(today)
    weeks = [monday - timedelta(weeks=k) for k in range(3, -1, -1)]
    total: dict[str, float] = {}
    per_week: dict[date, dict[str, float]] = {w: {} for w in weeks}
    skipped = 0.0
    renfo_sessions = 0
    for session in sessions:
        sets = session.get("renfo") or []
        if not sets:
            continue
        renfo_sessions += 1
        week = _monday(date.fromisoformat(session["date"]))
        for row in sets:
            count = float(row.get("series") or 0)
            if not count:
                continue
            family = row.get("famille") or renfo.chain_family("texte", row.get("exercice") or "")
            if family is None:
                skipped += count
                continue
            total[family] = total.get(family, 0.0) + count
            if week in per_week:
                per_week[week][family] = per_week[week].get(family, 0.0) + count
    if not renfo_sessions:
        return None
    bal = renfo.balance_from_families(total, skipped)
    out = {k: bal[k] for k in ("avant", "arriere", "ratio", "ratio_texte", "part_arriere", "zone", "verdict",
                               "explication", "neutre", "mixte", "non_comptees")}
    out["paires"] = [{k: p[k] for k in ("cle", "nom", "avant", "arriere", "ratio_texte", "penche")} for p in bal["paires"]]
    out["seances"] = renfo_sessions
    out["conseil"] = renfo.coach_hint(bal)
    out["semaines"] = []
    for week in weeks:
        families = per_week[week]
        week_bal = renfo.balance_from_families(families) if families else None
        out["semaines"].append({"lundi": week.isoformat(), "ratio_texte": week_bal["ratio_texte"] if week_bal else None,
                                "zone": week_bal["zone"] if week_bal else None,
                                "part_arriere": week_bal["part_arriere"] if week_bal else None,
                                "series": round(sum(families.values()), 1)})
    return out


def clean_share(payload: Any) -> dict:
    """L'extrait envoyé par un élève, réduit à ce qui est prévu (champs connus, tailles bornées, 4 semaines)."""
    if not isinstance(payload, dict):
        raise RelayError("Partage illisible.")
    oldest = (_today() - timedelta(days=KEEP_DAYS + 1)).isoformat()
    sessions = [s for raw in (payload.get("seances") or [])[:300] if (s := _clean_session(raw, oldest))]
    seen: set[str] = set()
    sessions = [s for s in sorted(sessions, key=lambda s: (s["date"], s.get("debut") or ""), reverse=True)
                if not (s["cle"] in seen or seen.add(s["cle"]))]
    days = []
    for raw in (payload.get("jours") or [])[:60]:
        if isinstance(raw, dict) and (day := _day(raw.get("date"))) and day >= oldest:
            item = {k: v for k, (lo, hi, dg) in DAY_NUM.items() if (v := _num(raw.get(k), lo, hi, dg)) is not None}
            if item:
                days.append({"date": day, **item})
    profile_raw = payload.get("profil") if isinstance(payload.get("profil"), dict) else {}
    profile: dict[str, Any] = {}
    if (vma := _num(profile_raw.get("vma_kmh"), 5, 30, 1)) is not None:
        profile["vma_kmh"] = vma
    if (fcmax := _num(profile_raw.get("fc_max"), 100, 240, 0)) is not None:
        profile["fc_max"] = fcmax
    goal = profile_raw.get("objectif") if isinstance(profile_raw.get("objectif"), dict) else None
    if goal and goal.get("nom"):
        profile["objectif"] = _clean_goal(goal)
    others = [_clean_goal(g) for g in (profile_raw.get("objectifs") or [])[:10] if isinstance(g, dict) and g.get("nom")]
    if others:
        profile["objectifs"] = [g for g in others if g.get("date")]
    plan = []
    for raw in (payload.get("plan") or [])[:120]:
        if isinstance(raw, dict) and (day := _day(raw.get("date"))) and raw.get("titre"):
            item = {"date": day, "heure": _txt(raw.get("heure"), 5), "titre": _txt(raw.get("titre"), 120),
                    "type": raw.get("type") if raw.get("type") in ("seance", "course", "autre") else "seance",
                    "sport": _txt(raw.get("sport"), 20),
                    "statut": raw.get("statut") if raw.get("statut") in
                    ("fait", "manque", "aujourdhui", "a_venir", "passe") else None}
            try:  # l'esquisse de la séance (blocs lus dans son texte), pour le calendrier du coach
                blocks = clean_blocks(raw.get("blocs")) if raw.get("blocs") else []
            except RelayError:
                blocks = []
            if blocks:
                item["blocs"] = blocks
                item["esquisse_approchee"] = bool(raw.get("esquisse_approchee"))
            plan.append(item)
    return {"seances": sessions, "jours": sorted(days, key=lambda d: d["date"]), "profil": profile, "plan": plan}


def filter_share(content: dict, accord: dict) -> dict:
    """Ce que le coach a le droit de voir, selon l'accord en vigueur (même si l'extrait est plus ancien)."""
    out = {"seances": [], "jours": [], "profil": {}, "plan": []}
    if accord.get("seances"):
        out["plan"] = content.get("plan", [])
        sessions = []
        for session in content.get("seances", []):
            item = dict(session)
            if not accord.get("gps"):
                item.pop("trace", None)
            sessions.append(item)
        out["seances"] = sessions
    if accord.get("objectif"):
        out["profil"] = content.get("profil", {})
    for day in content.get("jours", []):
        item = {"date": day["date"]}
        if accord.get("sante"):
            item.update({k: day[k] for k in ("sommeil_h", "sommeil_score", "vfc", "fc_repos") if k in day})
        if accord.get("poids") and "poids_kg" in day:
            item["poids_kg"] = day["poids_kg"]
        if len(item) > 1:
            out["jours"].append(item)
    return out


# --------------------------------------------------------------------- accord
def clean_accord(payload: Any) -> dict:
    data = payload if isinstance(payload, dict) else {}
    return {key: bool(data.get(key, ACCORD_DEFAULT[key])) for key in ACCORD_KEYS}


def get_accord(conn: sqlite3.Connection, student_id: int) -> dict | None:
    row = conn.execute("SELECT choix FROM accords WHERE eleve_id = ?", (student_id,)).fetchone()
    return clean_accord(json.loads(row["choix"])) if row else None


def set_accord(conn: sqlite3.Connection, student_id: int, payload: Any) -> dict:
    accord = clean_accord(payload)
    conn.execute("INSERT INTO accords(eleve_id, choix, modifie_le) VALUES (?,?,?) ON CONFLICT(eleve_id) DO UPDATE "
                 "SET choix = excluded.choix, modifie_le = excluded.modifie_le",
                 (student_id, json.dumps(accord), now()))
    stored = load_share(conn, student_id)
    if stored is not None:  # une case décochée efface tout de suite ce qu'elle couvrait
        save_share(conn, student_id, filter_share(stored, accord), keep_date=True)
    return accord


# ---------------------------------------------------------------------- partage
def load_share(conn: sqlite3.Connection, student_id: int) -> dict | None:
    row = conn.execute("SELECT contenu FROM partages WHERE eleve_id = ?", (student_id,)).fetchone()
    return json.loads(row["contenu"]) if row else None


def save_share(conn: sqlite3.Connection, student_id: int, content: dict, *, keep_date: bool = False) -> None:
    stamp = now()
    if keep_date:
        row = conn.execute("SELECT recu_le FROM partages WHERE eleve_id = ?", (student_id,)).fetchone()
        stamp = row["recu_le"] if row else stamp
    conn.execute("INSERT INTO partages(eleve_id, contenu, recu_le) VALUES (?,?,?) ON CONFLICT(eleve_id) DO UPDATE "
                 "SET contenu = excluded.contenu, recu_le = excluded.recu_le",
                 (student_id, json.dumps(content, ensure_ascii=False, separators=(",", ":")), stamp))


def receive_share(conn: sqlite3.Connection, student_id: int, payload: Any) -> dict:
    accord = get_accord(conn, student_id)
    if accord is None:
        raise RelayError("Choisis d'abord ce que tu partages avec ton coach.")
    content = filter_share(clean_share(payload), accord)
    save_share(conn, student_id, content)
    return {"seances": len(content["seances"]), "jours": len(content["jours"]), "recu_le": now()}


def shared(conn: sqlite3.Connection, student_id: int) -> tuple[dict, str | None]:
    """(extrait filtré selon l'accord, date de réception) ; les séances de plus de 4 semaines sont écartées."""
    row = conn.execute("SELECT contenu, recu_le FROM partages WHERE eleve_id = ?", (student_id,)).fetchone()
    accord = get_accord(conn, student_id) or {k: False for k in ACCORD_KEYS}
    if not row:
        return filter_share({}, accord), None
    content = filter_share(json.loads(row["contenu"]), accord)
    oldest = (_today() - timedelta(days=KEEP_DAYS)).isoformat()
    content["seances"] = [s for s in content["seances"] if s["date"] >= oldest]
    return content, row["recu_le"]


# --------------------------------------------------------------- propositions
GENRE_NAMES = {"echauffement": "Échauffement", "corps": "Bloc", "calme": "Retour au calme", "libre": "Libre"}


def clean_blocks(raw: Any) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise RelayError("Ajoute au moins un bloc à la séance.")
    blocks = []
    for item in raw[:30]:
        if not isinstance(item, dict):
            continue
        genre = item.get("genre") if item.get("genre") in GENRE_NAMES else "corps"
        block = {"nom": _txt(item.get("nom"), 60) or GENRE_NAMES[genre],
                 "repetitions": int(_num(item.get("repetitions"), 1, 50, 0) or 1),
                 "duree_min": _num(item.get("duree_min"), 0.1, 600, 2),
                 "distance_m": _num(item.get("distance_m"), 1, 200000, 0),
                 "pct_vma": _num(item.get("pct_vma"), 30, 140, 0),
                 "zone_fc": _num(item.get("zone_fc"), 1, 5, 0),
                 "recup_min": _num(item.get("recup_min"), 0.1, 60, 2),
                 "recup_texte": _txt(item.get("recup_texte"), 40),
                 "note": _txt(item.get("note"), 200),
                 "genre": genre}
        if item.get("libre") and block["duree_min"] is None and block["distance_m"] is None:
            block["libre"] = True  # jusqu'à la touche Lap (sur piste, de ligne à ligne)
        if item.get("recup_libre") and block["recup_min"] is None:
            block["recup_libre"] = True
        if block["duree_min"] is None and block["distance_m"] is None and not block["note"] and not block.get("libre"):
            raise RelayError(f"Bloc « {block['nom']} » : indique une durée ou une distance (ou « libre », à la "
                             "touche Lap).")
        blocks.append({k: v for k, v in block.items() if v is not None})
    if not blocks:
        raise RelayError("Ajoute au moins un bloc à la séance.")
    return blocks


def _clean_proposal(payload: dict) -> tuple[str, str, str, dict]:
    day = _day(payload.get("date"))
    if not day:
        raise RelayError("Choisis la date de la séance.")
    title = _txt(payload.get("titre"), 80)
    if not title:
        raise RelayError("Donne un titre à la séance (par exemple « Seuil 3 × 10 min »).")
    sport = payload.get("sport") if payload.get("sport") in metrics.SPORTS else "course"
    content = {"blocs": clean_blocks(payload.get("blocs")), "consigne": _txt(payload.get("consigne"), 1500)}
    return day, title, sport, content


def _proposal_dict(row: sqlite3.Row) -> dict:
    content = json.loads(row["contenu"])
    return {"id": row["id"], "eleve_id": row["eleve_id"], "coach_id": row["coach_id"], "date": row["date"], "titre": row["titre"],
            "sport": row["sport"], "sport_label": metrics.SPORTS.get(row["sport"]), "blocs": content.get("blocs", []),
            "consigne": content.get("consigne"), "cree_le": row["cree_le"], "modifie_le": row["modifie_le"]}


def _with_status(items: list[dict], sessions: list[dict], plan: list[dict], vma: float | None) -> None:
    """Fait ou pas ? Les séances du coach et celles de son plan, le même jour, se disputent ses séances faites :
    chacune va à la séance prévue qui lui ressemble le plus (nom donné par la montre, durée ; voir appariement).
    Une séance du coach revenue par son calendrier Garmin n'est pas une rivale : c'est la même."""
    rivals = [p for p in plan or [] if p.get("type") != "autre" and not any(
        appariement.same_session(i["titre"], i["date"], p.get("titre") or "", p.get("date") or "") for i in items)]
    candidates = [{"cle": ("coach", i["id"]), "date": i["date"], "titre": i["titre"], "sport": i["sport"],
                   "blocs": i["blocs"]} for i in items]
    candidates += [{"cle": ("plan", n), "date": p["date"], "titre": p.get("titre"), "sport": p.get("sport"),
                    "type": p.get("type"), "blocs": p.get("blocs")} for n, p in enumerate(rivals)]
    done = [{"cle": s["cle"], "date": s["date"], "sport": s.get("sport"), "nom": s.get("nom"),
             "duree_s": s.get("deplacement_s") or s.get("duree_s"), "row": s} for s in sessions]
    matched = appariement.assign(candidates, done, _fits, vma)
    today = _today()
    for item in items:
        found = matched.get(("coach", item["id"]))
        day = date.fromisoformat(item["date"])
        item["statut"] = "fait" if found else "manque" if day < today else "aujourdhui" if day == today else "a_venir"
        item["seance"] = {"cle": found["cle"], "nom": found.get("nom")} if found else None


def students_of(conn: sqlite3.Connection, coach_id: int) -> dict[int, sqlite3.Row]:
    rows = conn.execute("SELECT * FROM comptes WHERE role = 'eleve' AND coach_id = ?", (coach_id,)).fetchall()
    return {row["id"]: row for row in rows}


def create_proposals(conn: sqlite3.Connection, coach_id: int, payload: dict) -> list[dict]:
    mine = students_of(conn, coach_id)
    ids = [int(i) for i in (payload.get("eleves") or []) if str(i).isdigit()]
    if not ids:
        raise RelayError("Choisis au moins un élève.")
    if any(i not in mine for i in ids):
        raise RelayError("Un des élèves choisis n'est pas dans ton groupe.")
    day, title, sport, content = _clean_proposal(payload)
    stamp = now()
    created = []
    for student_id in dict.fromkeys(ids):
        cur = conn.execute("INSERT INTO propositions(coach_id, eleve_id, date, titre, sport, contenu, cree_le, "
                           "modifie_le) VALUES (?,?,?,?,?,?,?,?)",
                           (coach_id, student_id, day, title, sport, json.dumps(content, ensure_ascii=False), stamp,
                            stamp))
        created.append(cur.lastrowid)
    rows = conn.execute(f"SELECT * FROM propositions WHERE id IN ({','.join('?' * len(created))})", created)
    items = [_proposal_dict(row) for row in rows]
    for item in items:
        notifs.proposal_event(conn, "seance", item)
    return items


def update_proposal(conn: sqlite3.Connection, coach_id: int, proposal_id: int, payload: dict) -> dict:
    row = conn.execute("SELECT * FROM propositions WHERE id = ? AND coach_id = ?", (proposal_id, coach_id)).fetchone()
    if row is None:
        raise RelayError("Séance introuvable.")
    day, title, sport, content = _clean_proposal(payload)
    conn.execute("UPDATE propositions SET date = ?, titre = ?, sport = ?, contenu = ?, modifie_le = ? WHERE id = ?",
                 (day, title, sport, json.dumps(content, ensure_ascii=False), now(), proposal_id))
    garmin.follow_update(conn, proposal_id)  # déjà sur la montre : renvoyée telle que modifiée
    item = _proposal_dict(conn.execute("SELECT * FROM propositions WHERE id = ?", (proposal_id,)).fetchone())
    if max(item["date"], row["date"]) >= _today().isoformat():  # une séance passée qu'on range : pas de quoi prévenir
        notifs.proposal_event(conn, "seance_modifiee", item)
    garmin.decorate(conn, item["eleve_id"], [item])
    return item


def delete_proposal(conn: sqlite3.Connection, coach_id: int, proposal_id: int) -> bool:
    row = conn.execute("SELECT * FROM propositions WHERE id = ? AND coach_id = ?", (proposal_id, coach_id)).fetchone()
    if row:
        garmin.withdraw(conn, proposal_id)  # et hors du calendrier Garmin de l'élève
        if row["date"] >= _today().isoformat():
            notifs.proposal_event(conn, "seance_annulee", _proposal_dict(row))
    return conn.execute("DELETE FROM propositions WHERE id = ? AND coach_id = ?",
                        (proposal_id, coach_id)).rowcount > 0


def proposals(conn: sqlite3.Connection, student_id: int, start: date, end: date,
              content: dict | None = None) -> list[dict]:
    """Les séances proposées à un élève sur la période ; avec ce qu'il partage (content), leur état."""
    rows = conn.execute("SELECT * FROM propositions WHERE eleve_id = ? AND date BETWEEN ? AND ? ORDER BY date, id",
                        (student_id, start.isoformat(), end.isoformat())).fetchall()
    items = [_proposal_dict(row) for row in rows]
    if content is not None:
        _with_status(items, content.get("seances") or [], content.get("plan") or [],
                     (content.get("profil") or {}).get("vma_kmh"))
    garmin.decorate(conn, student_id, items)  # déjà envoyée sur sa montre ?
    return items


def templates(conn: sqlite3.Connection, coach_id: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM modeles WHERE coach_id = ? ORDER BY titre COLLATE NOCASE", (coach_id,))
    out = []
    for row in rows:
        content = json.loads(row["contenu"])
        out.append({"id": row["id"], "titre": row["titre"], "sport": row["sport"], "blocs": content.get("blocs", []),
                    "consigne": content.get("consigne")})
    return out


def save_template(conn: sqlite3.Connection, coach_id: int, payload: dict) -> list[dict]:
    title = _txt(payload.get("titre"), 80)
    if not title:
        raise RelayError("Donne un nom au modèle.")
    sport = payload.get("sport") if payload.get("sport") in metrics.SPORTS else "course"
    content = {"blocs": clean_blocks(payload.get("blocs")), "consigne": _txt(payload.get("consigne"), 1500)}
    if conn.execute("SELECT COUNT(*) FROM modeles WHERE coach_id = ?", (coach_id,)).fetchone()[0] >= 100:
        raise RelayError("100 modèles au plus : supprime ceux qui ne servent plus.")
    existing = conn.execute("SELECT id FROM modeles WHERE coach_id = ? AND titre = ?", (coach_id, title)).fetchone()
    if existing:
        conn.execute("UPDATE modeles SET sport = ?, contenu = ? WHERE id = ?",
                     (sport, json.dumps(content, ensure_ascii=False), existing["id"]))
    else:
        conn.execute("INSERT INTO modeles(coach_id, titre, sport, contenu, cree_le) VALUES (?,?,?,?,?)",
                     (coach_id, title, sport, json.dumps(content, ensure_ascii=False), now()))
    return templates(conn, coach_id)


def delete_template(conn: sqlite3.Connection, coach_id: int, template_id: int) -> list[dict]:
    conn.execute("DELETE FROM modeles WHERE id = ? AND coach_id = ?", (template_id, coach_id))
    return templates(conn, coach_id)


def update_template(conn: sqlite3.Connection, coach_id: int, template_id: int, payload: dict) -> list[dict]:
    """Renommer ou modifier un modèle de la bibliothèque (le titre seul suffit pour renommer)."""
    row = conn.execute("SELECT * FROM modeles WHERE id = ? AND coach_id = ?", (template_id, coach_id)).fetchone()
    if row is None:
        raise RelayError("Modèle introuvable.")
    content = json.loads(row["contenu"])
    title = _txt(payload.get("titre"), 80) or row["titre"]
    if conn.execute("SELECT 1 FROM modeles WHERE coach_id = ? AND titre = ? AND id <> ?",
                    (coach_id, title, template_id)).fetchone():
        raise RelayError(f"Tu as déjà un modèle « {title} ».")
    sport = payload.get("sport") if payload.get("sport") in metrics.SPORTS else row["sport"]
    if "blocs" in payload:
        content["blocs"] = clean_blocks(payload.get("blocs"))
    if "consigne" in payload:
        content["consigne"] = _txt(payload.get("consigne"), 1500)
    conn.execute("UPDATE modeles SET titre = ?, sport = ?, contenu = ? WHERE id = ?",
                 (title, sport, json.dumps(content, ensure_ascii=False), template_id))
    return templates(conn, coach_id)


# ------------------------------------------------------------------ groupes de niveau
COLORS = ("bleu", "vert", "jaune", "orange", "rouge", "violet", "gris")
MAX_LEVELS = 12


def levels(conn: sqlite3.Connection, coach_id: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM niveaux WHERE coach_id = ? ORDER BY position, id", (coach_id,)).fetchall()
    return [{"id": r["id"], "nom": r["nom"], "vma_min": r["vma_min"], "vma_max": r["vma_max"], "couleur": r["couleur"]}
            for r in rows]


def save_levels(conn: sqlite3.Connection, coach_id: int, payload: dict) -> dict:
    """Remplace la liste des groupes (ceux qui manquent sont supprimés ; un élève placé à la main dans un groupe
    supprimé retrouve le groupe de sa VMA)."""
    items = payload.get("niveaux")
    if not isinstance(items, list) or len(items) > MAX_LEVELS:
        raise RelayError(f"{MAX_LEVELS} groupes au plus.")
    mine = {r["id"] for r in conn.execute("SELECT id FROM niveaux WHERE coach_id = ?", (coach_id,))}
    kept = set()
    for position, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        name = _txt(raw.get("nom"), 40)
        if not name:
            raise RelayError(f"Donne un nom au groupe n° {position + 1}.")
        low, high = _num(raw.get("vma_min"), 5, 30, 1), _num(raw.get("vma_max"), 5, 30, 1)
        if low is not None and high is not None and low >= high:
            raise RelayError(f"Groupe « {name} » : la VMA mini doit être plus basse que la VMA maxi.")
        color = raw.get("couleur") if raw.get("couleur") in COLORS else COLORS[position % len(COLORS)]
        level_id = raw.get("id") if isinstance(raw.get("id"), int) and raw.get("id") in mine else None
        if level_id:
            conn.execute("UPDATE niveaux SET nom = ?, vma_min = ?, vma_max = ?, couleur = ?, position = ? WHERE id = ?",
                         (name, low, high, color, position, level_id))
        else:
            level_id = conn.execute("INSERT INTO niveaux(coach_id, nom, vma_min, vma_max, couleur, position) "
                                    "VALUES (?,?,?,?,?,?)", (coach_id, name, low, high, color, position)).lastrowid
        kept.add(level_id)
    for gone in mine - kept:
        conn.execute("DELETE FROM niveaux WHERE id = ?", (gone,))
    return level_page(conn, coach_id)


def _follow(conn: sqlite3.Connection, student_ids: list[int]) -> dict[int, sqlite3.Row]:
    if not student_ids:
        return {}
    rows = conn.execute(f"SELECT * FROM eleves_suivi WHERE eleve_id IN ({','.join('?' * len(student_ids))})",
                        student_ids).fetchall()
    return {r["eleve_id"]: r for r in rows}


def level_of(vma: float | None, forced: int | None, groups: list[dict]) -> dict | None:
    """Le groupe d'un élève : celui où le coach l'a placé, sinon le premier dont les bornes contiennent sa VMA
    (mini comprise, maxi non comprise ; une borne vide ne limite pas)."""
    if forced:
        found = next((g for g in groups if g["id"] == forced), None)
        if found:
            return found
    if vma is None:
        return None
    return next((g for g in groups if (g["vma_min"] is None or vma >= g["vma_min"])
                 and (g["vma_max"] is None or vma < g["vma_max"])), None)


def coach_view(conn: sqlite3.Connection, coach_id: int, student_id: int, shared_vma: float | None,
               groups: list[dict] | None = None, follow: sqlite3.Row | None = None) -> dict:
    """VMA de référence (test du club, sinon partagée) et groupe d'un élève, tels que le coach les voit."""
    groups = levels(conn, coach_id) if groups is None else groups
    if follow is None:
        follow = _follow(conn, [student_id]).get(student_id)
    test = follow["vma_test"] if follow else None
    vma = test or shared_vma
    level = level_of(vma, follow["niveau_force"] if follow else None, groups)
    return {"vma_kmh": vma, "vma_partagee": shared_vma, "vma_test": test,
            "vma_test_le": follow["vma_test_le"] if follow else None,
            "vma_source": "test" if test else "partagee" if shared_vma else None,
            "niveau": level, "niveau_force": bool(follow and follow["niveau_force"] and level)}


def level_page(conn: sqlite3.Connection, coach_id: int) -> dict:
    """La page « Réglages coach » : ses groupes et, pour chaque élève, sa VMA et son groupe."""
    groups = levels(conn, coach_id)
    students = students_of(conn, coach_id)
    follow = _follow(conn, list(students))
    out = []
    for sid, row in students.items():
        content, _ = shared(conn, sid)
        out.append({"id": sid, "nom": row["nom"], "actif": bool(row["actif"]),
                    **coach_view(conn, coach_id, sid, content["profil"].get("vma_kmh"), groups, follow.get(sid))})
    out.sort(key=lambda s: (-(s["vma_kmh"] or 0), s["nom"].lower()))
    return {"niveaux": groups, "eleves": out, "couleurs": list(COLORS)}


def set_student_level(conn: sqlite3.Connection, coach_id: int, student_id: int, payload: dict) -> dict:
    """VMA mesurée au club (vide : on reprend celle qu'il partage) et groupe imposé (vide : selon la VMA)."""
    if student_id not in students_of(conn, coach_id):
        raise PermissionError("Élève introuvable dans ton groupe.")
    current = _follow(conn, [student_id]).get(student_id)
    test = current["vma_test"] if current else None
    tested_on = current["vma_test_le"] if current else None
    forced = current["niveau_force"] if current else None
    if "vma_test" in payload:
        raw = payload.get("vma_test")
        test = None if raw in (None, "") else _num(str(raw).replace(",", "."), 5, 30, 1)
        if raw not in (None, "") and test is None:
            raise RelayError("VMA entre 5 et 30 km/h.")
        tested_on = (_txt(payload.get("vma_test_le"), 10) or _today().isoformat()) if test else None
    if "niveau" in payload:
        raw = payload.get("niveau")
        forced = None
        if raw not in (None, ""):
            mine = {g["id"] for g in levels(conn, coach_id)}
            if not str(raw).isdigit() or int(raw) not in mine:
                raise RelayError("Groupe inconnu.")
            forced = int(raw)
    conn.execute("INSERT INTO eleves_suivi(eleve_id, vma_test, vma_test_le, niveau_force, modifie_le) "
                 "VALUES (?,?,?,?,?) ON CONFLICT(eleve_id) DO UPDATE SET vma_test = excluded.vma_test, "
                 "vma_test_le = excluded.vma_test_le, niveau_force = excluded.niveau_force, "
                 "modifie_le = excluded.modifie_le", (student_id, test, tested_on, forced, now()))
    return level_page(conn, coach_id)


# ------------------------------------------------------------------ messages
def thread_access(conn: sqlite3.Connection, account: sqlite3.Row, thread: str) -> tuple[int, int | None]:
    """(groupe = id du coach, élève concerné) si ce compte a droit à ce fil ; sinon refus."""
    if not FIL_RE.match(thread or ""):
        raise RelayError("Fil inconnu.")
    if account["role"] == "coach":
        group = account["id"]
        if thread == "groupe":
            return group, None
        student = int(thread.split("-")[1])
        if student not in students_of(conn, group):
            raise PermissionError("Cet élève n'est pas dans ton groupe.")
        return group, student
    group = account["coach_id"]
    if thread == "groupe":
        return group, None
    student = int(thread.split("-")[1])
    if student != account["id"]:
        raise PermissionError("Ce fil n'est pas le tien.")
    return group, student


def _author(conn: sqlite3.Connection, author_id: int | None, cache: dict) -> dict:
    if author_id not in cache:
        row = conn.execute("SELECT id, nom, role FROM comptes WHERE id = ?", (author_id,)).fetchone() \
            if author_id else None
        cache[author_id] = {"id": row["id"], "nom": row["nom"], "role": row["role"]} if row else \
            {"id": None, "nom": "Compte supprimé", "role": None}
    return cache[author_id]


def _message(row: sqlite3.Row, me: int, conn: sqlite3.Connection, cache: dict) -> dict:
    return {"id": row["id"], "fil": row["fil"], "texte": row["texte"], "cree_le": row["cree_le"],
            "epingle": bool(row["epingle"]), "auteur": _author(conn, row["auteur_id"], cache),
            "moi": row["auteur_id"] == me}


def post(conn: sqlite3.Connection, account: sqlite3.Row, thread: str, text: Any) -> dict:
    group, _ = thread_access(conn, account, thread)
    body = str(text or "").strip()
    if not body:
        raise RelayError("Message vide.")
    if len(body) > MAX_TEXT:
        raise RelayError(f"Message trop long ({MAX_TEXT} caractères au plus).")
    cur = conn.execute("INSERT INTO messages(coach_id, fil, auteur_id, texte, cree_le) VALUES (?,?,?,?,?)",
                       (group, thread, account["id"], body, now()))
    mark_read(conn, account["id"], thread, cur.lastrowid)
    notifs.message_event(conn, account, thread, group, body)
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _message(row, account["id"], conn, {})


def mark_read(conn: sqlite3.Connection, account_id: int, thread: str, last_id: int) -> None:
    conn.execute("INSERT INTO lus(compte_id, fil, dernier_id) VALUES (?,?,?) ON CONFLICT(compte_id, fil) DO UPDATE "
                 "SET dernier_id = MAX(dernier_id, excluded.dernier_id)", (account_id, thread, last_id))


def read_thread(conn: sqlite3.Connection, account: sqlite3.Row, thread: str, after: int = 0) -> dict:
    group, student = thread_access(conn, account, thread)
    rows = conn.execute("SELECT * FROM (SELECT * FROM messages WHERE coach_id = ? AND fil = ? AND id > ? "
                        "ORDER BY id DESC LIMIT 300) ORDER BY id", (group, thread, after)).fetchall()
    cache: dict = {}
    items = [_message(row, account["id"], conn, cache) for row in rows]
    if items:
        mark_read(conn, account["id"], thread, items[-1]["id"])
    out = {"fil": thread, "titre": thread_title(conn, account, thread, group, student), "messages": items}
    if thread.startswith("seance-") and student is not None:
        key = thread.split("-", 2)[2]
        content, _ = shared(conn, student)
        out["seance"] = next((s for s in content["seances"] if s["cle"] == key), None)
    return out


def thread_title(conn: sqlite3.Connection, account: sqlite3.Row, thread: str, group: int,
                 student: int | None, sessions: dict | None = None) -> str:
    if thread == "groupe":
        return "Fil du groupe"
    if thread.startswith("eleve-"):
        other = student if account["role"] == "coach" else group
        row = conn.execute("SELECT nom FROM comptes WHERE id = ?", (other,)).fetchone()
        return row["nom"] if row else "Conversation"
    key = thread.split("-", 2)[2]
    if sessions is None:
        content, _ = shared(conn, student) if student else ({"seances": []}, None)
        sessions = {s["cle"]: s for s in content["seances"]}
    session = sessions.get(key)
    if session:
        return f"{session.get('nom') or 'Séance'} · {date.fromisoformat(session['date']).strftime('%d/%m')}"
    return "Séance"


def threads(conn: sqlite3.Connection, account: sqlite3.Row) -> list[dict]:
    """Les fils de ce compte, avec le dernier message et le nombre de non lus, les plus récents d'abord."""
    me = account["id"]
    group = me if account["role"] == "coach" else account["coach_id"]
    if account["role"] == "coach":
        members = students_of(conn, me)
        wanted = ["groupe"] + [f"eleve-{sid}" for sid in members]
        extra = [row["fil"] for row in conn.execute(
            "SELECT DISTINCT fil FROM messages WHERE coach_id = ? AND fil LIKE 'seance-%'", (me,))
            if int(row["fil"].split("-")[1]) in members]
    else:
        wanted = ["groupe", f"eleve-{me}"]
        extra = [row["fil"] for row in conn.execute(
            "SELECT DISTINCT fil FROM messages WHERE coach_id = ? AND fil LIKE ?", (group, f"seance-{me}-%"))]
    reads = {row["fil"]: row["dernier_id"] for row in conn.execute("SELECT fil, dernier_id FROM lus WHERE compte_id = ?",
                                                                    (me,))}
    cache: dict = {}
    share_cache: dict[int, dict] = {}
    out = []
    for thread in wanted + extra:
        student = None if thread == "groupe" else int(thread.split("-")[1])
        last = conn.execute("SELECT * FROM messages WHERE coach_id = ? AND fil = ? ORDER BY id DESC LIMIT 1",
                            (group, thread)).fetchone()
        unread = conn.execute("SELECT COUNT(*) FROM messages WHERE coach_id = ? AND fil = ? AND id > ? AND "
                              "COALESCE(auteur_id, 0) != ?", (group, thread, reads.get(thread, 0), me)).fetchone()[0]
        sessions = None
        if thread.startswith("seance-") and student is not None:
            if student not in share_cache:
                share_cache[student] = {s["cle"]: s for s in shared(conn, student)[0]["seances"]}
            sessions = share_cache[student]
        out.append({"fil": thread, "titre": thread_title(conn, account, thread, group, student, sessions),
                    "genre": thread.split("-")[0], "eleve_id": student, "non_lus": unread,
                    "dernier": _message(last, me, conn, cache) if last else None})
    out.sort(key=lambda t: (t["fil"] != "groupe", -(t["dernier"]["id"] if t["dernier"] else 0)))
    return out


def unread_total(conn: sqlite3.Connection, account: sqlite3.Row) -> int:
    return sum(t["non_lus"] for t in threads(conn, account))


def pin(conn: sqlite3.Connection, account: sqlite3.Row, message_id: int, pinned: bool) -> None:
    row = conn.execute("SELECT * FROM messages WHERE id = ? AND coach_id = ? AND fil = 'groupe'",
                       (message_id, account["id"])).fetchone()
    if row is None or account["role"] != "coach":
        raise PermissionError("Seul le coach épingle un message du fil du groupe.")
    conn.execute("UPDATE messages SET epingle = ? WHERE id = ?", (int(pinned), message_id))


def delete_message(conn: sqlite3.Connection, account: sqlite3.Row, message_id: int) -> None:
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if row is None:
        raise RelayError("Message introuvable.")
    if row["auteur_id"] != account["id"] and not (account["role"] == "coach" and row["coach_id"] == account["id"]):
        raise PermissionError("Tu ne peux effacer que tes messages.")
    conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))


# ------------------------------------------------------------- vue du coach
def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _session_brief(session: dict | None) -> dict | None:
    if not session:
        return None
    keys = ("cle", "date", "debut", "nom", "sport", "sport_label", "distance_m", "duree_s", "allure", "vitesse_kmh",
            "fc_moy", "denivele_m", "effet_aerobie", "avantage", "charge")
    out = {k: session[k] for k in keys if k in session}
    if session.get("description"):
        out["note"] = session["description"][:160]
    return out


def strip(days: list[dict], today: date) -> list[dict]:
    """La bande des 7 jours de « Mes élèves » : fait, manqué, prévu ou rien, jour par jour."""
    out = []
    for day in days:
        planned = day["prevu"]
        if day["fait"]:
            state = "fait"
        elif any(p.get("statut") == "manque" for p in planned):
            state = "manque"
        elif planned and day["date"] >= today.isoformat():
            state = "prevu"
        else:
            state = "repos"
        names = [s.get("nom") or s.get("sport_label") or "Séance" for s in day["fait"]] or \
            [p.get("titre") or "Séance" for p in planned]
        out.append({"date": day["date"], "etat": state, "titre": " · ".join(names)[:120],
                    "coach": any(p.get("source") == "coach" for p in planned)})
    return out


def week(content: dict, props: list[dict], monday: date) -> list[dict]:
    """Les 7 jours : ce qui était prévu (plan Garmin de l'élève, séances du coach) et ce qui a été fait."""
    days = []
    for offset in range(7):
        day = (monday + timedelta(days=offset)).isoformat()
        done = [_session_brief(s) for s in content["seances"] if s["date"] == day]
        planned = [{"source": "plan", **p} for p in content["plan"] if p["date"] == day and p["type"] != "autre"
                   and not any(appariement.same_session(x["titre"], x["date"], p.get("titre") or "", day) for x in props)]
        planned += [{"source": "coach", "id": p["id"], "titre": p["titre"], "sport": p["sport"],
                     "statut": p["statut"], "blocs": p.get("blocs") or []} for p in props if p["date"] == day]
        days.append({"date": day, "prevu": planned, "fait": sorted(done, key=lambda s: s.get("debut") or "")})
    return days


CALENDAR_MAX_DAYS = 378  # une année entière, des lundis aux dimanches (54 semaines)
CALENDAR_LIGHT_DAYS = 63  # au-delà (la vue à l'année) : pas d'esquisses ni de descriptions, des pastilles suffisent


def calendar(conn: sqlite3.Connection, student_id: int, content: dict, start: date, end: date) -> dict:
    """Du lundi de start au dimanche de end, jour par jour comme week() : le calendrier des pages coach et élève
    (à la semaine, au mois ou à l'année)."""
    start, end = _monday(start), _monday(end) + timedelta(days=6)
    if end < start or (end - start).days + 1 > CALENDAR_MAX_DAYS:
        raise RelayError("Calendrier : une année au plus.")
    props = proposals(conn, student_id, start, end, content)
    days = []
    monday = start
    while monday <= end:
        days += week(content, props, monday)
        monday += timedelta(days=7)
    if (end - start).days + 1 > CALENDAR_LIGHT_DAYS:
        for day in days:
            day["prevu"] = [{k: v for k, v in p.items() if k not in ("blocs", "description")} for p in day["prevu"]]
    return {"debut": start.isoformat(), "fin": end.isoformat(), "jours": days}


def month(conn: sqlite3.Connection, student_id: int, content: dict, today: date) -> dict:
    """Neuf semaines autour d'aujourd'hui (4 passées, la semaine en cours, 4 à venir) : le calendrier tel qu'il
    s'ouvre ; le reste se demande à calendar_range()."""
    start = _monday(today) - timedelta(days=28)
    return calendar(conn, student_id, content, start, start + timedelta(days=62))


def _range(debut: str | None, fin: str | None) -> tuple[date, date]:
    try:
        start, end = date.fromisoformat((debut or "")[:10]), date.fromisoformat((fin or "")[:10])
    except ValueError:
        raise RelayError("Calendrier : dates attendues au format AAAA-MM-JJ.") from None
    return start, end


def calendar_range(conn: sqlite3.Connection, account: sqlite3.Row, student_id: int | None, debut: str | None,
                   fin: str | None) -> dict:
    """Le calendrier sur une période : l'élève le sien, le coach celui d'un élève de son groupe."""
    if student_id is None:
        student_id = account["id"]
    elif conn.execute("SELECT 1 FROM comptes WHERE id = ? AND role = 'eleve' AND coach_id = ?",
                      (student_id, account["id"])).fetchone() is None:
        raise PermissionError("Élève introuvable dans ton groupe.")
    start, end = _range(debut, fin)
    content, _ = shared(conn, student_id)
    return calendar(conn, student_id, content, start, end)


def tally(days: list[dict]) -> dict:
    planned = [p for d in days for p in d["prevu"]]
    return {"prevues": len(planned), "faites": sum(p.get("statut") == "fait" for p in planned),
            "seances": sum(len(d["fait"]) for d in days)}


def overview(conn: sqlite3.Connection, coach: sqlite3.Row) -> list[dict]:
    """La page « Mes élèves » : chaque élève avec sa dernière séance, sa semaine, son objectif, ses alertes."""
    today = _today()
    monday = _monday(today)
    reads = {t["fil"]: t["non_lus"] for t in threads(conn, coach)}
    groups = levels(conn, coach["id"])
    out = []
    rows = conn.execute("SELECT * FROM comptes WHERE role = 'eleve' AND coach_id = ? ORDER BY nom COLLATE NOCASE",
                        (coach["id"],)).fetchall()
    follow = _follow(conn, [r["id"] for r in rows])
    for row in rows:
        content, received = shared(conn, row["id"])
        accord = get_accord(conn, row["id"])
        props = proposals(conn, row["id"], monday, monday + timedelta(days=6), content)
        days = week(content, props, monday)
        sessions = content["seances"]
        last = sessions[0] if sessions else None
        week_ago = (today - timedelta(days=7)).isoformat()
        load7 = sum(s.get("charge") or 0 for s in sessions if s["date"] > week_ago)
        goal = content["profil"].get("objectif")
        if goal and goal.get("date"):
            goal = {**goal, "dans_jours": (date.fromisoformat(goal["date"]) - today).days}
        idle = (today - date.fromisoformat(last["date"])).days if last else None
        unread = reads.get(f"eleve-{row['id']}", 0) + sum(n for fil, n in reads.items()
                                                          if fil.startswith(f"seance-{row['id']}-"))
        out.append({
            "id": row["id"], "nom": row["nom"], "identifiant": row["identifiant"], "actif": bool(row["actif"]),
            "inscrit_le": row["cree_le"], "derniere_connexion": row["derniere_connexion"],
            "accord": accord, "partage_recu_le": received, "derniere_seance": _session_brief(last),
            "semaine": tally(days), "bande": strip(days, today), "charge_7j": round(load7) if sessions else None,
            **coach_view(conn, coach["id"], row["id"], content["profil"].get("vma_kmh"), groups, follow.get(row["id"])),
            "seances_28j": len(sessions), "objectif": goal, "non_lus": unread,
            "montre": garmin.student_flags(conn, row["id"]),
            "prochain": _next_goal(goal, content["profil"], today),
            "renfo": {k: balance[k] for k in ("ratio_texte", "zone", "verdict", "seances")}
            if (balance := renfo_balance(sessions, today)) and balance["zone"] != "vide" else None,
            "alerte": f"{idle} jours sans séance" if idle is not None and idle >= ALERT_DAYS and accord
            and accord.get("seances") else None,
        })
    return out


def student_page(conn: sqlite3.Connection, coach: sqlite3.Row, student_id: int, monday: date | None = None) -> dict:
    row = conn.execute("SELECT * FROM comptes WHERE id = ? AND role = 'eleve' AND coach_id = ?",
                       (student_id, coach["id"])).fetchone()
    if row is None:
        raise PermissionError("Élève introuvable dans ton groupe.")
    today = _today()
    monday = monday or _monday(today)
    content, received = shared(conn, student_id)
    sessions = content["seances"]
    props_week = proposals(conn, student_id, monday, monday + timedelta(days=6), content)
    upcoming = proposals(conn, student_id, today - timedelta(days=14), today + timedelta(days=90), content)
    counts = {row2["fil"]: row2["n"] for row2 in conn.execute(
        "SELECT fil, COUNT(*) AS n FROM messages WHERE coach_id = ? AND fil LIKE ? GROUP BY fil",
        (coach["id"], f"seance-{student_id}-%"))}
    briefs = []
    for session in sessions:
        item = _session_brief(session)
        item["messages"] = counts.get(f"seance-{student_id}-{session['cle']}", 0)
        item["trace"] = "trace" in session
        briefs.append(item)
    goal = content["profil"].get("objectif")
    if goal and goal.get("date"):
        goal = {**goal, "dans_jours": (date.fromisoformat(goal["date"]) - today).days}
    total = {"seances": len(sessions), "distance_m": sum(s.get("distance_m") or 0 for s in sessions),
             "duree_s": sum(s.get("duree_s") or 0 for s in sessions),
             "charge": round(sum(s.get("charge") or 0 for s in sessions)),
             "renfo": sum(s.get("sport") == "renfo" for s in sessions)}
    days = week(content, props_week, monday)
    return {"eleve": {"id": row["id"], "nom": row["nom"], "identifiant": row["identifiant"],
                      "inscrit_le": row["cree_le"], "derniere_connexion": row["derniere_connexion"]},
            "accord": get_accord(conn, student_id), "partage_recu_le": received, "profil": content["profil"],
            "objectif": goal, "objectifs": _upcoming_goals(content["profil"], today),
            "semaine": {"lundi": monday.isoformat(), "jours": days, "bilan": tally(days)},
            "seances": briefs, "jours": content["jours"], "total_28j": total, "propositions": upcoming,
            "mois": month(conn, student_id, content, today),
            "renfo": renfo_balance(sessions, today),
            "suivi": coach_view(conn, coach["id"], student_id, content["profil"].get("vma_kmh")),
            "niveaux": levels(conn, coach["id"]),
            "montre": {**garmin.student_flags(conn, student_id), "disponible": garmin.configured()}}


def _next_goal(goal: dict | None, profile: dict, today: date) -> dict | None:
    """Le plus proche des objectifs à venir, principal ou secondaire (la « prochaine course » du groupe)."""
    candidates = [g for g in [goal, *_upcoming_goals(profile, today)] if g and g.get("dans_jours") is not None
                  and g["dans_jours"] >= 0]
    return min(candidates, key=lambda g: g["dans_jours"]) if candidates else None


def _upcoming_goals(profile: dict, today: date) -> list[dict]:
    """Les objectifs secondaires encore à venir, avec leur compte à rebours."""
    out = []
    for goal in profile.get("objectifs") or []:
        if goal.get("date") and goal["date"] >= today.isoformat():
            out.append({**goal, "dans_jours": (date.fromisoformat(goal["date"]) - today).days})
    return sorted(out, key=lambda g: g["date"])


def student_session(conn: sqlite3.Connection, account: sqlite3.Row, student_id: int, key: str) -> dict:
    thread_access(conn, account, f"seance-{student_id}-{key}")
    content, _ = shared(conn, student_id)
    session = next((s for s in content["seances"] if s["cle"] == key), None)
    if session is None:
        raise RelayError("Séance introuvable : elle n'est plus partagée (plus de 4 semaines, ou partage retiré).")
    props = proposals(conn, student_id, date.fromisoformat(session["date"]), date.fromisoformat(session["date"]),
                      content)
    # ce qui était proposé : la séance du coach à laquelle elle répond (sinon, rien : elle répondait à son plan)
    mine = next((p for p in props if (p.get("seance") or {}).get("cle") == key), None)
    plan = None if mine else next((p for p in content["plan"] if p["date"] == session["date"] and p["type"] != "autre"
                                   and p.get("statut") == "fait"), None)
    return {"seance": session, "prevue": plan, "proposition": mine,
            "vma_kmh": content["profil"].get("vma_kmh"), "fil": f"seance-{student_id}-{key}"}


def my_page(conn: sqlite3.Connection, student: sqlite3.Row) -> dict:
    """Pour l'élève : son coach, ses séances proposées, ce qu'il partage (et quand ça a été reçu)."""
    today = _today()
    content, received = shared(conn, student["id"])
    coach = conn.execute("SELECT id, nom, derniere_connexion FROM comptes WHERE id = ?",
                         (student["coach_id"],)).fetchone()
    return {"coach": {"nom": coach["nom"], "derniere_connexion": coach["derniere_connexion"]} if coach else None,
            "accord": get_accord(conn, student["id"]), "partage_recu_le": received,
            "partage": {"seances": len(content["seances"]), "jours": len(content["jours"]),
                        "traces": sum("trace" in s for s in content["seances"])},
            "propositions": proposals(conn, student["id"], today - timedelta(days=14), today + timedelta(days=90),
                                      content),
            "mois": month(conn, student["id"], content, today),
            "objectifs": [g for g in [_clean_goal(content["profil"]["objectif"]) if content["profil"].get("objectif")
                                      else None, *(content["profil"].get("objectifs") or [])] if g and g.get("date")],
            "montre": garmin.status(conn, student)}


def last_activity(conn: sqlite3.Connection, account: sqlite3.Row) -> str:
    """Repère pour le relevé périodique : change quand un message ou une séance proposée arrive."""
    group = account["id"] if account["role"] == "coach" else account["coach_id"]
    msg = conn.execute("SELECT MAX(id) FROM messages WHERE coach_id = ?", (group,)).fetchone()[0] or 0
    if account["role"] == "coach":
        prop = conn.execute("SELECT MAX(recu_le) FROM partages p JOIN comptes c ON c.id = p.eleve_id "
                            "WHERE c.coach_id = ?", (group,)).fetchone()[0] or ""
    else:
        prop = conn.execute("SELECT MAX(modifie_le) FROM propositions WHERE eleve_id = ?",
                            (account["id"],)).fetchone()[0] or ""
    return f"{msg}|{prop}"


def parse_monday(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return _monday(date.fromisoformat(value[:10]))
    except ValueError:
        return None
