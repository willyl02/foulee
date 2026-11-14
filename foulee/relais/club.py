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

from .. import metrics
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
           "vitesse_kmh": (0, 120, 1), "denivele_m": (0, 10000, 0)}
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
            sets.append({"exercice": _txt(row.get("exercice"), 80), "series": _num(row.get("series"), 0, 200, 0),
                         "reps": _num(row.get("reps"), 0, 5000, 0), "kg": _num(row.get("kg"), 0, 1000, 1),
                         "chaine": _txt(row.get("chaine"), 20)})
    if sets:
        out["renfo"] = sets
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
        profile["objectif"] = {"nom": _txt(goal.get("nom"), 80), "date": _day(goal.get("date")),
                               "distance_km": _num(goal.get("distance_km"), 0, 1000, 3),
                               "temps_cible": _txt(goal.get("temps_cible"), 12)}
    plan = []
    for raw in (payload.get("plan") or [])[:120]:
        if isinstance(raw, dict) and (day := _day(raw.get("date"))) and raw.get("titre"):
            plan.append({"date": day, "heure": _txt(raw.get("heure"), 5), "titre": _txt(raw.get("titre"), 120),
                         "type": raw.get("type") if raw.get("type") in ("seance", "course", "autre") else "seance",
                         "sport": _txt(raw.get("sport"), 20),
                         "statut": raw.get("statut") if raw.get("statut") in
                         ("fait", "manque", "aujourdhui", "a_venir", "passe") else None})
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
def clean_blocks(raw: Any) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise RelayError("Ajoute au moins un bloc à la séance.")
    blocks = []
    for item in raw[:30]:
        if not isinstance(item, dict):
            continue
        block = {"nom": _txt(item.get("nom"), 60) or "Bloc",
                 "repetitions": int(_num(item.get("repetitions"), 1, 50, 0) or 1),
                 "duree_min": _num(item.get("duree_min"), 0.1, 600, 2),
                 "distance_m": _num(item.get("distance_m"), 1, 200000, 0),
                 "pct_vma": _num(item.get("pct_vma"), 30, 140, 0),
                 "zone_fc": _num(item.get("zone_fc"), 1, 5, 0),
                 "recup_min": _num(item.get("recup_min"), 0.1, 60, 2),
                 "recup_texte": _txt(item.get("recup_texte"), 40),
                 "note": _txt(item.get("note"), 200),
                 "genre": item.get("genre") if item.get("genre") in ("echauffement", "corps", "calme", "libre")
                 else "corps"}
        if block["duree_min"] is None and block["distance_m"] is None and not block["note"]:
            raise RelayError(f"Bloc « {block['nom']} » : indique une durée ou une distance.")
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


def _proposal_dict(row: sqlite3.Row, sessions: list[dict] | None = None) -> dict:
    content = json.loads(row["contenu"])
    item = {"id": row["id"], "eleve_id": row["eleve_id"], "date": row["date"], "titre": row["titre"],
            "sport": row["sport"], "sport_label": metrics.SPORTS.get(row["sport"]), "blocs": content.get("blocs", []),
            "consigne": content.get("consigne"), "cree_le": row["cree_le"], "modifie_le": row["modifie_le"]}
    if sessions is not None:
        done = next((s for s in sessions if s["date"] == row["date"] and _fits(row["sport"], s.get("sport"))), None)
        day = date.fromisoformat(row["date"])
        item["statut"] = "fait" if done else "manque" if day < _today() else \
            "aujourdhui" if day == _today() else "a_venir"
        item["seance"] = {"cle": done["cle"], "nom": done.get("nom")} if done else None
    return item


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
    return [_proposal_dict(row) for row in rows]


def update_proposal(conn: sqlite3.Connection, coach_id: int, proposal_id: int, payload: dict) -> dict:
    row = conn.execute("SELECT * FROM propositions WHERE id = ? AND coach_id = ?", (proposal_id, coach_id)).fetchone()
    if row is None:
        raise RelayError("Séance introuvable.")
    day, title, sport, content = _clean_proposal(payload)
    conn.execute("UPDATE propositions SET date = ?, titre = ?, sport = ?, contenu = ?, modifie_le = ? WHERE id = ?",
                 (day, title, sport, json.dumps(content, ensure_ascii=False), now(), proposal_id))
    return _proposal_dict(conn.execute("SELECT * FROM propositions WHERE id = ?", (proposal_id,)).fetchone())


def delete_proposal(conn: sqlite3.Connection, coach_id: int, proposal_id: int) -> bool:
    return conn.execute("DELETE FROM propositions WHERE id = ? AND coach_id = ?",
                        (proposal_id, coach_id)).rowcount > 0


def proposals(conn: sqlite3.Connection, student_id: int, start: date, end: date,
              sessions: list[dict] | None = None) -> list[dict]:
    rows = conn.execute("SELECT * FROM propositions WHERE eleve_id = ? AND date BETWEEN ? AND ? ORDER BY date, id",
                        (student_id, start.isoformat(), end.isoformat())).fetchall()
    return [_proposal_dict(row, sessions) for row in rows]


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
        planned = [{"source": "plan", **p} for p in content["plan"] if p["date"] == day and p["type"] != "autre"]
        planned += [{"source": "coach", "id": p["id"], "titre": p["titre"], "sport": p["sport"],
                     "statut": p["statut"]} for p in props if p["date"] == day]
        days.append({"date": day, "prevu": planned, "fait": sorted(done, key=lambda s: s.get("debut") or "")})
    return days


def tally(days: list[dict]) -> dict:
    planned = [p for d in days for p in d["prevu"]]
    return {"prevues": len(planned), "faites": sum(p.get("statut") == "fait" for p in planned),
            "seances": sum(len(d["fait"]) for d in days)}


def overview(conn: sqlite3.Connection, coach: sqlite3.Row) -> list[dict]:
    """La page « Mes élèves » : chaque élève avec sa dernière séance, sa semaine, son objectif, ses alertes."""
    today = _today()
    monday = _monday(today)
    reads = {t["fil"]: t["non_lus"] for t in threads(conn, coach)}
    out = []
    for row in conn.execute("SELECT * FROM comptes WHERE role = 'eleve' AND coach_id = ? ORDER BY nom COLLATE NOCASE",
                            (coach["id"],)).fetchall():
        content, received = shared(conn, row["id"])
        accord = get_accord(conn, row["id"])
        props = proposals(conn, row["id"], monday, monday + timedelta(days=6), content["seances"])
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
            "vma_kmh": content["profil"].get("vma_kmh"),
            "seances_28j": len(sessions), "objectif": goal, "non_lus": unread,
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
    props_week = proposals(conn, student_id, monday, monday + timedelta(days=6), sessions)
    upcoming = proposals(conn, student_id, today - timedelta(days=14), today + timedelta(days=90), sessions)
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
            "objectif": goal, "semaine": {"lundi": monday.isoformat(), "jours": days, "bilan": tally(days)},
            "seances": briefs, "jours": content["jours"], "total_28j": total, "propositions": upcoming}


def student_session(conn: sqlite3.Connection, account: sqlite3.Row, student_id: int, key: str) -> dict:
    thread_access(conn, account, f"seance-{student_id}-{key}")
    content, _ = shared(conn, student_id)
    session = next((s for s in content["seances"] if s["cle"] == key), None)
    if session is None:
        raise RelayError("Séance introuvable : elle n'est plus partagée (plus de 4 semaines, ou partage retiré).")
    plan = next((p for p in content["plan"] if p["date"] == session["date"] and p["type"] != "autre"), None)
    props = proposals(conn, student_id, date.fromisoformat(session["date"]), date.fromisoformat(session["date"]),
                      content["seances"])
    return {"seance": session, "prevue": plan, "proposition": props[0] if props else None,
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
                                      content["seances"])}


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
