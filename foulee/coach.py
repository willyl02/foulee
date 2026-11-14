"""Le lien entre ce Foulée et le relais du club (coach et élèves).

Chaque profil peut se connecter à un relais : comme coach (il invite ses élèves) ou comme élève (il rejoint son
coach avec un code d'invitation). L'adresse du relais et le compte (identifiant, nom, rôle) sont gardés dans la
base du profil ; le jeton de session, lui, va dans le coffre, comme la clé Garmin, et ne repart jamais vers
l'interface ni vers Claude.

Le relais ne parle qu'en HTTPS (sauf sur la machine elle-même, pour les essais).
"""

from __future__ import annotations

import json
import logging
import platform
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import requests

from . import __version__, db, vault
from .relais import API_VERSION

log = logging.getLogger("foulee.coach")

TIMEOUT = 20
META_URL = "relais_adresse"
META_ACCOUNT = "relais_compte"
META_SINCE = "relais_relie_le"


class CoachError(RuntimeError):
    """Problème expliqué en français ; ``status`` = code HTTP du relais (0 : injoignable)."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


def clean_url(value: str | None) -> str:
    """« relais.mon-club.com » → « https://relais.mon-club.com » ; HTTPS obligatoire hors de la machine."""
    text = (value or "").strip().rstrip("/")
    if not text:
        raise ValueError("Indique l'adresse du relais (par exemple relais.mon-club.com).")
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    if not host or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Adresse du relais illisible : colle seulement son nom, par exemple relais.mon-club.com.")
    local = host in ("localhost", "127.0.0.1", "::1")
    if parts.scheme != "https" and not (parts.scheme == "http" and local):
        raise ValueError("Le relais doit être en HTTPS (adresse en https://).")
    path = parts.path.rstrip("/")
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}{path}"


def device_name() -> str:
    return f"Foulée {__version__} · {platform.node() or 'ordinateur'}"[:80]


# Transport HTTP, remplaçable dans les tests (le relais tourne alors dans le même processus)
def _send(method: str, url: str, *, headers: dict, payload: dict | None) -> tuple[int, dict]:
    response = requests.request(method, url, headers=headers, json=payload, timeout=TIMEOUT)
    try:
        data = response.json()
    except ValueError:
        data = {}
    return response.status_code, data if isinstance(data, dict) else {}


transport = _send


def call(base: str, method: str, path: str, *, token: str | None = None, payload: dict | None = None) -> dict:
    headers = {"Accept": "application/json", "X-Foulee-Version": __version__, "X-Foulee-Api": str(API_VERSION),
               "User-Agent": f"Foulee/{__version__}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        status, data = transport(method, f"{base}{path}", headers=headers, payload=payload)
    except requests.RequestException as exc:
        log.info("Relais injoignable (%s) : %s", base, exc)
        raise CoachError("Relais injoignable : vérifie l'adresse et ta connexion à Internet.") from None
    if status >= 400:
        detail = data.get("detail") if isinstance(data.get("detail"), str) else None
        if status == 404 and not detail:
            detail = "Cette adresse ne répond pas comme un relais Foulée."
        if status in (502, 503, 504, 530):
            detail = "Le relais ne répond pas pour l'instant (arrêté ou en cours de mise à jour) : réessaie plus tard."
        raise CoachError(detail or f"Le relais a refusé la demande (HTTP {status}).", status)
    return data


# ------------------------------------------------------------------ état local
def linked() -> bool:
    return bool(vault.get_secret("relais"))


def status(conn: sqlite3.Connection) -> dict:
    """État du lien, sans jamais le jeton."""
    raw = db.get_meta(conn, META_ACCOUNT)
    account = json.loads(raw) if raw else None
    url = db.get_meta(conn, META_URL)
    if not (account and url and linked()):
        return {"relie": False, "adresse": url}
    return {"relie": True, "adresse": url, "compte": account, "relie_le": db.get_meta(conn, META_SINCE)}


def light(conn: sqlite3.Connection) -> dict | None:
    """Ce que l'interface affiche dans la colonne : le rôle et le nom (ou None)."""
    info = status(conn)
    if not info.get("relie"):
        return None
    account = info["compte"]
    return {"role": account.get("role"), "nom": account.get("nom"), "coach": (account.get("coach") or {}).get("nom")}


def _save(conn: sqlite3.Connection, url: str, token: str, account: dict) -> None:
    vault.set_secret("relais", token)
    db.set_meta(conn, META_URL, url)
    db.set_meta(conn, META_ACCOUNT, json.dumps(_public(account), ensure_ascii=False))
    db.set_meta(conn, META_SINCE, db.now_iso())
    conn.commit()


def _public(account: dict) -> dict:
    keys = ("id", "identifiant", "nom", "role", "admin", "coach")
    return {key: account.get(key) for key in keys if key in account}


def forget(conn: sqlite3.Connection) -> None:
    vault.delete_secret("relais")
    for key in (META_ACCOUNT, META_SINCE, "relais_accord", "relais_envoye_le", "relais_propositions"):
        db.delete_meta(conn, key)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'calendar_events'").fetchone():
        conn.execute("DELETE FROM calendar_events WHERE uid LIKE 'coach:%'")  # séances proposées par le coach
    conn.commit()  # l'adresse reste : on la repropose à la prochaine connexion


def _session(conn: sqlite3.Connection) -> tuple[str, str]:
    url, token = db.get_meta(conn, META_URL), vault.get_secret("relais")
    if not (url and token):
        raise CoachError("Ce profil n'est relié à aucun relais.", 401)
    return url, token


def _authed(conn: sqlite3.Connection, method: str, path: str, payload: dict | None = None) -> dict:
    url, token = _session(conn)
    try:
        return call(url, method, path, token=token, payload=payload)
    except CoachError as exc:
        if exc.status == 401:  # session fermée sur le relais (mot de passe changé, compte retiré…)
            forget(conn)
        raise


# ------------------------------------------------------------------ actions
def check_relay(url: str) -> dict:
    info = call(url, "GET", "/api/v1/sante")
    if info.get("service") != "foulee-relais":
        raise CoachError("Cette adresse ne répond pas comme un relais Foulée.")
    if int(info.get("api") or 0) != API_VERSION:
        raise CoachError("Ce relais n'a pas la même version que ton Foulée : mets à jour Foulée (ou le relais).")
    return info


def login(conn: sqlite3.Connection, url: str, ident: str, password: str) -> dict:
    url = clean_url(url)
    check_relay(url)
    data = call(url, "POST", "/api/v1/connexion",
                payload={"identifiant": ident, "mot_de_passe": password, "appareil": device_name()})
    _save(conn, url, data["jeton"], data["compte"])
    return status(conn)


def join(conn: sqlite3.Connection, url: str, *, code: str, ident: str, name: str, password: str) -> dict:
    url = clean_url(url)
    check_relay(url)
    data = call(url, "POST", "/api/v1/inscription",
                payload={"code": code, "identifiant": ident, "nom": name, "mot_de_passe": password,
                         "appareil": device_name()})
    _save(conn, url, data["jeton"], data["compte"])
    return status(conn)


def refresh(conn: sqlite3.Connection) -> dict:
    """Relit le compte sur le relais (nom du coach, rôle) ; une session fermée délie le profil."""
    data = _authed(conn, "GET", "/api/v1/moi")
    db.set_meta(conn, META_ACCOUNT, json.dumps(_public(data["compte"]), ensure_ascii=False))
    conn.commit()
    return status(conn)


def logout(conn: sqlite3.Connection) -> dict:
    try:
        url, token = _session(conn)
        call(url, "POST", "/api/v1/deconnexion", token=token)
    except CoachError:
        pass  # relais injoignable : on oublie quand même la session ici
    forget(conn)
    return status(conn)


def change_password(conn: sqlite3.Connection, current: str, new: str) -> None:
    _authed(conn, "POST", "/api/v1/moi/mot-de-passe", {"actuel": current, "nouveau": new})


def leave(conn: sqlite3.Connection, password: str) -> dict:
    _authed(conn, "POST", "/api/v1/moi/quitter", {"mot_de_passe": password})
    forget(conn)
    return status(conn)


def students(conn: sqlite3.Connection) -> list[dict]:
    return _authed(conn, "GET", "/api/v1/eleves")["eleves"]


def remove_student(conn: sqlite3.Connection, student_id: int) -> list[dict]:
    return _authed(conn, "DELETE", f"/api/v1/eleves/{int(student_id)}")["eleves"]


def invitations(conn: sqlite3.Connection) -> list[dict]:
    return _authed(conn, "GET", "/api/v1/invitations")["invitations"]


def create_invitation(conn: sqlite3.Connection) -> dict:
    return _authed(conn, "POST", "/api/v1/invitations")


def cancel_invitation(conn: sqlite3.Connection, code: str) -> list[dict]:
    safe = "".join(ch for ch in (code or "").upper() if ch.isalnum() or ch == "-")[:12]
    return _authed(conn, "DELETE", f"/api/v1/invitations/{safe}")["invitations"]


# =================================================================== partage
# Ce que l'élève partage avec son coach (l'« accord ») : gardé ici et sur le relais. L'extrait des 4 dernières
# semaines est construit ici, selon l'accord, puis envoyé ; le relais le refiltre de toute façon.
META_ACCORD = "relais_accord"
META_PUSHED = "relais_envoye_le"
META_PROPOSALS = "relais_propositions"
SHARE_DAYS = 28
TRACE_POINTS = 400
MASK_RADIUS_M = 500
ACCORD_DEFAULT = {"seances": True, "objectif": True, "gps": False, "masquer": True, "sante": False, "poids": False}
KEEP_META = ("relais_adresse", "relais_compte", "relais_relie_le", "relais_accord")


def role(conn: sqlite3.Connection) -> str | None:
    info = status(conn)
    return info["compte"].get("role") if info.get("relie") else None


def local_accord(conn: sqlite3.Connection) -> dict | None:
    raw = db.get_meta(conn, META_ACCORD)
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        data = None
    return {k: bool(data.get(k, v)) for k, v in ACCORD_DEFAULT.items()} if isinstance(data, dict) else None


def set_accord(conn: sqlite3.Connection, payload: dict) -> dict:
    """Enregistre les choix de l'élève (ici et sur le relais), puis envoie l'extrait qui va avec."""
    accord = {k: bool(payload.get(k, v)) for k, v in ACCORD_DEFAULT.items()}
    saved = _authed(conn, "PUT", "/api/v1/partage/accord", accord)["accord"]
    db.set_meta(conn, META_ACCORD, json.dumps(saved))
    conn.commit()
    result = exchange(conn, force=True)
    return {"accord": saved, "echange": result}


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    import math

    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(min(1.0, math.sqrt(h)))


def trace_points(streams: dict | None, mask: bool) -> list[list[float]] | None:
    """Le tracé GPS allégé (400 points au plus) ; masqué, sans rien à moins de 500 m du départ ni de l'arrivée."""
    if not streams:
        return None
    lats, lons = streams.get("lat") or [], streams.get("lon") or []
    points = [(la, lo) for la, lo in zip(lats, lons) if la is not None and lo is not None and (la or lo)]
    if len(points) < 2:
        return None
    if mask:
        start, end = points[0], points[-1]
        points = [p for p in points if _haversine(p, start) > MASK_RADIUS_M and _haversine(p, end) > MASK_RADIUS_M]
        if len(points) < 2:
            return None
    step = max(1, -(-len(points) // TRACE_POINTS))
    return [[round(la, 5), round(lo, 5)] for la, lo in points[::step]]


def _shared_session(conn: sqlite3.Connection, row: sqlite3.Row, accord: dict) -> dict:
    from . import analysis, metrics, renfo

    extra = json.loads(row["extra"]) if row["extra"] else {}
    running = row["sport"] in metrics.RUNNING_SPORTS + ("marche", "rando")
    benefit = analysis.te_benefit(extra.get("te_label"))
    item = {
        "cle": row["id"], "date": row["date"], "debut": row["start_local"], "sport": row["sport"],
        "sport_label": metrics.SPORTS.get(row["sport"]), "nom": row["name"], "description": row["description"],
        "duree_s": row["duration_s"], "deplacement_s": row["moving_s"], "distance_m": row["distance_m"],
        "denivele_m": row["elev_gain_m"], "fc_moy": row["avg_hr"], "fc_max": row["max_hr"],
        "vitesse_kmh": round(row["avg_speed"] * 3.6, 1) if row["avg_speed"] else None,
        "allure": metrics.fmt_pace(row["avg_speed"]) if running and row["avg_speed"] else None,
        "cadence": row["avg_cadence"], "puissance": row["avg_power"], "calories": row["calories"],
        "effet_aerobie": row["te_aerobic"], "effet_anaerobie": row["te_anaerobic"],
        "avantage": benefit["libelle"] if benefit else None, "charge": row["load"],
    }
    laps = []
    for lap in conn.execute("SELECT * FROM laps WHERE activity_id = ? ORDER BY idx", (row["id"],)):
        laps.append({"duree_s": lap["duration_s"], "distance_m": lap["distance_m"], "fc_moy": lap["avg_hr"],
                     "vitesse_kmh": round(lap["avg_speed"] * 3.6, 1) if lap["avg_speed"] else None,
                     "allure": metrics.fmt_pace(lap["avg_speed"]) if running and lap["avg_speed"] else None,
                     "denivele_m": lap["elev_gain_m"], "intensite": lap["intensity"]})
    if len(laps) > 1:
        item["tours"] = laps
    sets = []
    for e in conn.execute("SELECT * FROM exercises WHERE activity_id = ? ORDER BY idx", (row["id"],)):
        info = renfo.describe(dict(e))
        sets.append({"exercice": info["nom"], "series": info["series"], "reps": info["repetitions"],
                     "kg": info["charge_max_kg"], "chaine": (info["chaine"] or {}).get("court")})
    if sets:
        item["renfo"] = sets
    if accord.get("gps") and row["has_streams"]:
        trace = trace_points(analysis.load_streams(conn, row["id"]), accord.get("masquer", True))
        if trace:
            item["trace"] = trace
    return {k: v for k, v in item.items() if v is not None}


def snapshot(conn: sqlite3.Connection, accord: dict, today: date | None = None) -> dict:
    """L'extrait des 4 dernières semaines, selon l'accord. Jamais les séances venues de Strava (ses règles
    l'interdisent), jamais de clé ni de jeton."""
    from . import calendrier

    today = today or date.today()
    since = (today - timedelta(days=SHARE_DAYS)).isoformat()
    out: dict[str, Any] = {"seances": [], "jours": [], "profil": {}, "plan": []}
    if accord.get("seances"):
        rows = conn.execute("SELECT * FROM activities WHERE date >= ? AND source <> 'strava' AND id NOT LIKE "
                            "'strava:%' ORDER BY start_local DESC", (since,)).fetchall()
        out["seances"] = [_shared_session(conn, row, accord) for row in rows]
        planned = calendrier.plan(conn, today - timedelta(days=SHARE_DAYS), today + timedelta(days=28), today)
        out["plan"] = [{"date": p["date"], "heure": p["heure"], "titre": p["titre"], "type": p["type"],
                        "sport": p["sport"], "statut": p["statut"]} for p in planned if not p.get("coach")]
    if accord.get("objectif"):
        settings = db.get_settings(conn)
        goal = settings.get("objectif") if isinstance(settings.get("objectif"), dict) else None
        out["profil"] = {"vma_kmh": settings.get("vma_kmh"), "fc_max": settings.get("fc_max"),
                         "objectif": goal if goal and goal.get("nom") else None}
    wanted = (["sleep_s", "sleep_score", "hrv_night", "resting_hr"] if accord.get("sante") else []) + \
        (["weight_kg"] if accord.get("poids") else [])
    if wanted:
        days: dict[str, dict] = {}
        rows = conn.execute(f"SELECT date, metric, value FROM daily WHERE date >= ? AND metric IN "
                            f"({','.join('?' * len(wanted))}) ORDER BY date, source", (since, *wanted))
        names = {"sleep_s": "sommeil_h", "sleep_score": "sommeil_score", "hrv_night": "vfc", "resting_hr": "fc_repos",
                 "weight_kg": "poids_kg"}
        for row in rows:
            value = row["value"] / 3600 if row["metric"] == "sleep_s" else row["value"]
            days.setdefault(row["date"], {"date": row["date"]})[names[row["metric"]]] = round(value, 1)
        out["jours"] = list(days.values())
    return out


def store_proposals(conn: sqlite3.Connection, items: list[dict]) -> None:
    """Les séances proposées par le coach rejoignent le calendrier (uid « coach:ID »), comme le plan Garmin."""
    from . import calendrier, metrics

    db.set_meta(conn, META_PROPOSALS, json.dumps(items, ensure_ascii=False))
    if not calendrier.ready(conn):
        return
    conn.execute("DELETE FROM calendar_events WHERE uid LIKE 'coach:%'")
    stamp = db.now_iso()
    for item in items:
        lines = [block_text(b, None) for b in item.get("blocs", [])]
        if item.get("consigne"):
            lines.append(f"« {item['consigne']} »")
        conn.execute(calendrier.INSERT, (item["date"], None, None, 1, f"{item['titre']} (coach)"[:200],
                                         "\n".join(lines)[:2000] or None, None, "seance",
                                         item.get("sport") if item.get("sport") in metrics.SPORTS else None,
                                         f"coach:{item['id']}", stamp))


def pace_for(vma_kmh: float | None, pct: float | None) -> str | None:
    if not vma_kmh or not pct:
        return None
    seconds = 3600 / (vma_kmh * pct / 100)
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}:{secs:02d} /km"


def block_text(block: dict, vma_kmh: float | None) -> str:
    reps = block.get("repetitions") or 1
    size = []
    if block.get("duree_min"):
        minutes = block["duree_min"]
        size.append(f"{minutes:g} min" if minutes >= 1 else f"{round(minutes * 60)} s")
    if block.get("distance_m"):
        meters = block["distance_m"]
        size.append(f"{meters / 1000:g} km" if meters >= 1000 else f"{meters:g} m")
    text = f"{block.get('nom') or 'Bloc'} : " + (f"{reps} × " if reps > 1 else "") + " / ".join(size)
    if block.get("pct_vma"):
        pace = pace_for(vma_kmh, block["pct_vma"])
        text += f" à {block['pct_vma']:g} % VMA" + (f" ({pace})" if pace else "")
    elif block.get("zone_fc"):
        text += f" en zone FC {block['zone_fc']:g}"
    if reps > 1 and (block.get("recup_min") or block.get("recup_texte")):
        rest = f"{block['recup_min']:g} min" if block.get("recup_min") else ""
        text += f", récup {rest} {block.get('recup_texte') or ''}".rstrip()
    if block.get("note"):
        text += f" — {block['note']}"
    return text


def exchange(conn: sqlite3.Connection, *, force: bool = False) -> dict:
    """Pour un élève relié : envoie l'extrait (après une synchro, ou un changement de choix) et relit les séances
    proposées par le coach. Ne fait rien pour un coach ni sans accord."""
    if role(conn) != "eleve":
        return {"fait": False}
    accord = local_accord(conn)
    result: dict[str, Any] = {"fait": True}
    if accord is not None:
        data = _authed(conn, "PUT", "/api/v1/partage", snapshot(conn, accord))
        db.set_meta(conn, META_PUSHED, db.now_iso())
        result["envoi"] = data
    page = _authed(conn, "GET", "/api/v1/moi/coach")
    if page.get("accord") and accord is None:  # accord donné depuis un autre appareil
        db.set_meta(conn, META_ACCORD, json.dumps(page["accord"]))
    store_proposals(conn, page.get("propositions") or [])
    conn.commit()
    result["propositions"] = len(page.get("propositions") or [])
    return result


def exchange_quietly(conn: sqlite3.Connection) -> None:
    """Après une synchro : l'échange avec le relais ne doit jamais la faire échouer."""
    try:
        if linked():
            exchange(conn)
    except Exception as exc:  # relais injoignable, session fermée…
        log.info("Échange avec le relais impossible : %s", exc)


def my_page(conn: sqlite3.Connection) -> dict:
    """« Mon coach » : relit le relais (et envoie l'extrait s'il date de plus de 10 minutes)."""
    pushed = db.get_meta(conn, META_PUSHED)
    stale = not pushed or (datetime.now() - datetime.fromisoformat(pushed)).total_seconds() > 600
    exchanged = None
    if stale:
        try:
            exchanged = exchange(conn)
        except CoachError as exc:
            if exc.status == 401:
                raise
    page = _authed(conn, "GET", "/api/v1/moi/coach")
    store_proposals(conn, page.get("propositions") or [])  # le calendrier suit aussitôt
    conn.commit()
    settings = db.get_settings(conn)
    vma = settings.get("vma_kmh")
    for item in page.get("propositions") or []:
        item["lignes"] = [block_text(b, vma) for b in item.get("blocs", [])]
        for block in item.get("blocs", []):
            block["allure"] = pace_for(vma, block.get("pct_vma"))
    page["vma_kmh"] = vma
    page["envoye_le"] = db.get_meta(conn, META_PUSHED)
    page["echange"] = exchanged
    page["accord_local"] = local_accord(conn)
    return page


# ------------------------------------------------------- passerelle vers le relais
PROXY_PATHS = re.compile(r"^(groupe|eleves/\d+/fiche|eleves/\d+/seances/[A-Za-z0-9:_.-]+|propositions(/\d+)?|"
                         r"modeles(/\d+)?|fils(/[A-Za-z0-9:_.-]+)?|messages/\d+(/epingle)?|nouveautes|"
                         r"moi/seances/[A-Za-z0-9:_.-]+|partage/accord)$")


def proxy(conn: sqlite3.Connection, method: str, path: str, payload: dict | None = None,
          query: dict | None = None) -> dict:
    """Relaie vers le relais une page de l'interface (Mes élèves, messages, séances…), avec le jeton de ce profil.
    Seules les routes connues passent ; c'est le relais qui vérifie les droits."""
    if method not in ("GET", "POST", "PUT", "DELETE") or not PROXY_PATHS.match(path or ""):
        raise CoachError("Demande inconnue.", 404)
    suffix = ""
    if query:
        allowed = {k: str(v) for k, v in query.items() if k in ("semaine", "apres") and re.fullmatch(r"[0-9-]{1,12}",
                                                                                                   str(v))}
        if allowed:
            suffix = "?" + "&".join(f"{k}={v}" for k, v in allowed.items())
    from urllib.parse import quote

    return _authed(conn, method, "/api/v1/" + quote(path, safe="/:_.-") + suffix, payload)
