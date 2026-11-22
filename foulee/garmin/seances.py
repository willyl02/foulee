"""Les séances prévues du calendrier Garmin, lues étape par étape.

Le calendrier iCal de Garmin ne donne que le nom d'une séance prévue (« Endurance de Force : Avis de tempête »),
sans son contenu. Mais son identifiant (UID « …Z-1763763857@… ») porte le numéro de la séance dans Garmin
Connect : la synchro demande cette séance à Garmin (une fois, puis de temps en temps tant qu'elle est à venir),
la garde telle quelle (table garmin_workouts), et le calendrier la dessine fidèlement : échauffement, 7 × 30 s
rapides et leurs 3 min de récup, retour au calme… au lieu d'un profil deviné du nom.

Si la clé API de Garmin ne donne pas accès aux séances, Garmin répond par un refus : on le note, on ne redemande
pas avant une semaine, et le calendrier garde son profil deviné.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from .. import db
from .client import GarminError

LOG = logging.getLogger("foulee.garmin")

WORKOUT_ID = re.compile(r"-(\d{6,12})@")  # UID d'un événement du calendrier Garmin
PAST_DAYS = 35       # les séances prévues relues : un mois en arrière (séances faites ou manquées) …
AHEAD_DAYS = 70      # … et dix semaines devant
MAX_CALLS = 40       # par synchro : de quoi rattraper un plan entier sans peser sur Garmin
REFRESH_DAYS = 3     # une séance à venir est relue tous les 3 jours (le coach ou le plan peut l'avoir changée)
REFUSAL_KEY = "garmin_seances_essai"  # (0.8.3b8 : le refus noté par la b7 ne bloque plus)
REFUSAL_PAUSE = timedelta(days=7)

SCHEMA = """
CREATE TABLE IF NOT EXISTS garmin_workouts (
    id          TEXT PRIMARY KEY,         -- numéro de la séance dans Garmin Connect
    fetched_at  TEXT NOT NULL,
    status      INTEGER,                  -- 200, ou le refus de Garmin (404 : séance supprimée)
    json        TEXT                      -- la séance telle que Garmin l'envoie
);
"""

SPORTS = {  # sportTypeKey de Garmin → famille Foulée
    "running": "course", "trail_running": "trail", "treadmill_running": "course", "track_running": "course",
    "cycling": "velo", "road_biking": "velo", "mountain_biking": "velo", "indoor_cycling": "velo",
    "swimming": "natation", "lap_swimming": "natation", "open_water_swimming": "natation",
    "strength_training": "renfo", "cardio_training": "cardio", "hiit": "cardio", "yoga": "souplesse",
    "pilates": "souplesse", "walking": "marche", "hiking": "rando",
}
GENRES = {"warmup": "echauffement", "cooldown": "calme"}
RESTS = ("recovery", "rest")


def workout_id(uid: str | None) -> str | None:
    match = WORKOUT_ID.search(uid or "")
    return match.group(1) if match else None


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


# ------------------------------------------------------------------ lecture d'une séance Garmin
def _key(value: Any, field: str) -> str:
    return str((value or {}).get(field) or "").lower() if isinstance(value, dict) else ""


def _amount(step: dict) -> dict:
    """La durée ou la distance d'une étape ; rien pour « jusqu'au bouton Lap »."""
    cond = _key(step.get("endCondition"), "conditionTypeKey")
    value = step.get("endConditionValue")
    try:
        value = float(value) if value is not None else None
    except (TypeError, ValueError):
        value = None
    if cond == "time" and value:
        return {"duree_min": round(value / 60, 2)}
    if cond == "distance" and value:
        return {"distance_m": round(value)}
    if cond == "lap.button":
        return {"libre": True}
    return {}


def _intensity(step: dict, vma: float | None) -> dict:
    """La cible : % de VMA (fourchette d'allure ou de vitesse, en m/s) ou zone de FC."""
    target = _key(step.get("targetType"), "workoutTargetTypeKey")
    low, high = step.get("targetValueOne"), step.get("targetValueTwo")
    if target in ("pace.zone", "speed.zone") and vma:
        try:
            speeds = [float(v) for v in (low, high) if v]
        except (TypeError, ValueError):
            speeds = []
        if speeds:
            kmh = sum(speeds) / len(speeds) * 3.6
            return {"pct_vma": max(40, min(130, round(kmh / vma * 100)))}
    if target == "heart.rate.zone":
        zone = step.get("zoneNumber")
        if isinstance(zone, (int, float)) and 1 <= int(zone) <= 5:
            return {"zone_fc": int(zone)}
    return {}


def _block(step: dict, vma: float | None) -> dict | None:
    kind = _key(step.get("stepType"), "stepTypeKey")
    amount = _amount(step)
    if not amount:
        return None
    block = {"genre": GENRES.get(kind, "corps"), **amount, **_intensity(step, vma)}
    if kind in RESTS:
        block["_recup"] = True
        if "pct_vma" not in block and "zone_fc" not in block:
            block["pct_vma"] = 55
    return block


def _steps(steps: list, vma: float | None, out: list[dict], depth: int = 0) -> None:
    for step in sorted((s for s in steps or [] if isinstance(s, dict)), key=lambda s: s.get("stepOrder") or 0):
        if len(out) >= 60:
            return
        inner = step.get("workoutSteps")
        if isinstance(inner, list) and inner:  # une boucle : N fois les mêmes étapes
            try:
                reps = max(1, min(50, int(step.get("numberOfIterations") or step.get("endConditionValue") or 1)))
            except (TypeError, ValueError):
                reps = 1
            parts: list[dict] = []
            _steps(inner, vma, parts, depth + 1)
            efforts = [p for p in parts if not p.get("_recup")]
            rests = [p for p in parts if p.get("_recup")]
            if len(efforts) == 1 and len(rests) <= 1:
                block = dict(efforts[0], repetitions=reps) if reps > 1 else dict(efforts[0])
                if rests and rests[0].get("duree_min"):
                    block["recup_min"] = rests[0]["duree_min"]
                elif rests:
                    block["recup_libre"] = True
                out.append(block)
            else:  # une boucle plus riche : déroulée telle quelle
                for _ in range(reps):
                    out.extend(dict(p) for p in parts)
                    if len(out) >= 60:
                        return
            continue
        block = _block(step, vma)
        if block:
            out.append(block)


def blocks_of(workout: dict | None, vma: float | None) -> list[dict]:
    """Les blocs de Foulée (ceux de l'esquisse) d'une séance Garmin : échauffement, boucles, récup, retour au calme."""
    if not isinstance(workout, dict):
        return []
    if sport_of(workout) not in (None, "course", "trail"):
        vma = None  # une allure de vélo ou de nage ne se lit pas en % de la VMA de course
    out: list[dict] = []
    for segment in sorted((s for s in workout.get("workoutSegments") or [] if isinstance(s, dict)),
                          key=lambda s: s.get("segmentOrder") or 0):
        _steps(segment.get("workoutSteps") or [], vma, out)
    return [{k: v for k, v in b.items() if k != "_recup"} for b in out[:60]]


def sport_of(workout: dict | None) -> str | None:
    if not isinstance(workout, dict):
        return None
    return SPORTS.get(_key(workout.get("sportType"), "sportTypeKey"))


def stored(conn: sqlite3.Connection, ids: list[str]) -> dict[str, dict]:
    """Les séances Garmin déjà lues, par numéro."""
    if not ids:
        return {}
    try:
        rows = conn.execute(f"SELECT id, json FROM garmin_workouts WHERE status = 200 AND id IN "
                            f"({','.join('?' * len(ids))})", ids).fetchall()
    except sqlite3.OperationalError:  # table pas encore créée (aucune synchro depuis la mise à jour)
        return {}
    out = {}
    for row in rows:
        try:
            out[row["id"]] = json.loads(row["json"])
        except (TypeError, ValueError):
            continue
    return out


# ------------------------------------------------------------------ pendant la synchro
def refused_recently(conn: sqlite3.Connection, now: datetime | None = None) -> bool:
    raw = db.get_meta(conn, REFUSAL_KEY)
    if not raw:
        return False
    try:
        since = datetime.fromisoformat(json.loads(raw)["le"])
    except (KeyError, TypeError, ValueError):
        return False
    now = now or datetime.now(since.tzinfo)
    return now - since < REFUSAL_PAUSE


def _workout_in(payload: Any) -> dict | None:
    """La séance (avec ses étapes) dans une réponse de Garmin : la séance elle-même, ou la séance d'une planification."""
    if isinstance(payload, dict):
        if payload.get("workoutSegments"):
            return payload
        inner = payload.get("workout")
        if isinstance(inner, dict) and inner.get("workoutSegments"):
            return inner
    return None


# Le numéro de l'UID est celui de la séance planifiée (il change quand on la déplace d'un jour à l'autre) ou celui de
# la séance elle-même : on essaie les deux chemins, et on retient celui qui répond
ROUTES = (("planifiée", "/workout-service/schedule/{}"), ("séance", "/workout-service/workout/{}"))
ROUTE_KEY = "garmin_seances_chemin"


def _norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _store(conn: sqlite3.Connection, wid: str, status: int, workout: dict | None) -> None:
    conn.execute("INSERT OR REPLACE INTO garmin_workouts(id, fetched_at, status, json) VALUES (?, ?, ?, ?)",
                 (wid, db.now_iso(), status, json.dumps(workout, ensure_ascii=False) if workout else None))


def _ask(session: Any, path: str) -> tuple[Any, int]:
    """(réponse, statut HTTP) ; 404 quand Garmin ne trouve rien (le client rend alors None)."""
    try:
        payload = session.call("get", path)
    except GarminError as exc:
        return None, exc.status or 0
    return payload, 200 if payload is not None else 404


def sync(conn: sqlite3.Connection, session: Any, today: date | None = None) -> dict:
    """Les séances suivies (lues dans les activités du mois, sans appel à Garmin), puis les séances prévues."""
    ensure_table(conn)
    followed = followed_sync(conn, today)
    result = planned_sync(conn, session, today)
    if followed:
        result["suivies"] = followed
    return result


def planned_sync(conn: sqlite3.Connection, session: Any, today: date | None = None) -> dict:
    """Lit les séances prévues du calendrier Garmin qui manquent (ou à rafraîchir). Ne lève jamais : un souci ici
    ne doit pas faire échouer la synchro ; il est résumé et écrit dans le journal (statut HTTP de chaque chemin)."""
    ensure_table(conn)
    today = today or date.today()
    if refused_recently(conn):
        return {"lues": 0, "refus": True}
    rows = conn.execute("SELECT DISTINCT uid, date, title FROM calendar_events WHERE kind = 'seance' AND date BETWEEN ? AND ?",
                        ((today - timedelta(days=PAST_DAYS)).isoformat(),
                         (today + timedelta(days=AHEAD_DAYS)).isoformat())).fetchall()
    rows = [r for r in rows if workout_id(r["uid"])]
    wanted: dict[str, str] = {}
    for row in rows:
        wid = workout_id(row["uid"])
        wanted[wid] = max(wanted.get(wid, ""), row["date"])
    if not wanted:
        return {"lues": 0}
    known = {r["id"]: r for r in conn.execute(
        f"SELECT id, fetched_at, status FROM garmin_workouts WHERE id IN ({','.join('?' * len(wanted))})",
        list(wanted)).fetchall()}
    stale = (datetime.now().astimezone() - timedelta(days=REFRESH_DAYS)).isoformat()
    todo = [wid for wid, day in sorted(wanted.items(), key=lambda kv: kv[1], reverse=True)
            if wid not in known or (day >= today.isoformat() and (known[wid]["fetched_at"] or "") < stale
                                    and known[wid]["status"] in (200, None))]
    if not todo:
        return {"lues": 0}
    statuses: dict[str, int] = {}
    read = missing = 0
    route = db.get_meta(conn, ROUTE_KEY) or ""
    routes = [r for r in ROUTES if r[0] == route] or list(ROUTES)
    for wid in todo[:MAX_CALLS]:
        workout = None
        for name, path in routes:
            payload, status = _ask(session, path.format(wid))
            statuses[name] = status
            workout = _workout_in(payload)
            if workout:
                if len(routes) > 1:
                    routes = [(name, path)]
                    db.set_meta(conn, ROUTE_KEY, name)
                break
        if workout:
            _store(conn, wid, 200, workout)
            read += 1
            continue
        missing += 1
        if not read and missing >= 3:
            break  # aucun chemin ne répond : inutile d'insister séance par séance
        if read:
            _store(conn, wid, 404, None)  # le chemin marche : cette séance-là a été supprimée de Garmin Connect
    from_acts = 0
    summary = ", ".join(f"{name} HTTP {status}" for name, status in statuses.items())
    if not read and not from_acts:
        db.set_meta(conn, ROUTE_KEY, "")
        db.set_meta(conn, REFUSAL_KEY, json.dumps({"le": db.now_iso(), "chemins": statuses}, ensure_ascii=False))
        conn.commit()
        LOG.info("Séances prévues Garmin : rien de lisible (%s), nouvel essai dans 7 jours", summary)
        return {"lues": 0, "refus": True, "statut": next(iter(statuses.values()), None)}
    db.set_meta(conn, REFUSAL_KEY, "")
    conn.commit()
    LOG.info("Séances prévues Garmin : %s lue(s) (%s)", read, summary)
    return {"lues": read + from_acts}


def _done(conn: sqlite3.Connection, wid: str | None) -> bool:
    return bool(wid) and conn.execute("SELECT 1 FROM garmin_workouts WHERE id = ? AND status = 200", (wid,)).fetchone() is not None


# ------------------------------------------------------------------ les séances suivies
# Une séance structurée faite avec la montre laisse sa trace dans l'activité : les étapes de la séance dans le
# fichier FIT (messages workout_step : durées, allures ou zones visées, boucles), et à défaut le résumé des
# intervalles que Garmin donne avec l'activité (échauffement, N efforts, N récups, retour au calme). Garmin ne
# donne pas les séances à venir à une clé API personnelle : celles-là gardent leur profil deviné du nom.
FIT_INTENSITY = {"warmup": "warmup", "cooldown": "cooldown", "active": "interval", "interval": "interval",
                 "rest": "rest", "recovery": "recovery"}
FIT_SPORTS = {"running": "running", "trail_running": "trail_running", "cycling": "cycling", "training": "strength_training",
              "walking": "walking", "hiking": "hiking", "swimming": "lap_swimming"}


def _fit_step(m: dict) -> dict:
    kind = FIT_INTENSITY.get(str(m.get("intensity") or "active"), "interval")
    duration = str(m.get("duration_type") or "")
    if duration == "time" and m.get("duration_time"):
        cond, value = "time", float(m["duration_time"])
    elif duration == "distance" and m.get("duration_distance"):
        cond, value = "distance", float(m["duration_distance"])
    else:
        cond, value = "lap.button", None
    step = {"type": "ExecutableStepDTO", "stepType": {"stepTypeKey": kind}, "endCondition": {"conditionTypeKey": cond},
            "endConditionValue": value, "targetType": {"workoutTargetTypeKey": "no.target"}}
    target = str(m.get("target_type") or "")
    if target == "speed" and m.get("custom_target_speed_low") and m.get("custom_target_speed_high"):
        step.update(targetType={"workoutTargetTypeKey": "pace.zone"}, targetValueOne=m["custom_target_speed_low"],
                    targetValueTwo=m["custom_target_speed_high"])
    elif target == "heart_rate" and isinstance(m.get("target_hr_zone"), int) and 1 <= m["target_hr_zone"] <= 5:
        step.update(targetType={"workoutTargetTypeKey": "heart.rate.zone"}, zoneNumber=m["target_hr_zone"])
    return step


def workout_from_fit(messages: dict) -> dict | None:
    """La séance suivie, telle que la montre l'a enregistrée dans le FIT, au format des séances de Garmin Connect."""
    steps = sorted((m for m in messages.get("workout_step_mesgs") or [] if isinstance(m, dict)),
                   key=lambda m: m.get("message_index") or 0)
    if not steps:
        return None
    out: list[tuple[int, dict]] = []
    for m in steps:
        index = int(m.get("message_index") or 0)
        if str(m.get("duration_type") or "").startswith("repeat"):
            first = int(m.get("duration_step") or 0)
            reps = int(m.get("repeat_steps") or m.get("target_value") or 1)
            inner = [item for i, item in out if i >= first]
            out = [(i, item) for i, item in out if i < first]
            if inner:
                out.append((first, {"type": "RepeatGroupDTO", "stepType": {"stepTypeKey": "repeat"},
                                    "numberOfIterations": reps, "workoutSteps": [
                                        dict(step, stepOrder=k) for k, step in enumerate(inner, 1)]}))
            continue
        out.append((index, dict(_fit_step(m), stepOrder=index + 1)))
    head = (messages.get("workout_mesgs") or [{}])[0] or {}
    return {"workoutName": head.get("wkt_name"), "sportType": {"sportTypeKey": FIT_SPORTS.get(str(head.get("sport")), "running")},
            "workoutSegments": [{"segmentOrder": 1, "workoutSteps": [dict(item, stepOrder=k) for k, (_, item) in enumerate(out, 1)]}],
            "_source": "fit"}


def workout_from_intervals(activity: dict) -> dict | None:
    """À défaut du FIT : le résumé des intervalles de l'activité (durées et vitesses réellement courues)."""
    parts = {str(s.get("splitType")): s for s in activity.get("splitSummaries") or [] if isinstance(s, dict)}
    active = parts.get("INTERVAL_ACTIVE")
    if not active or not active.get("noOfSplits") or not active.get("duration"):
        return None

    def step(kind: str, seconds: float, speed: float | None) -> dict:
        out = {"type": "ExecutableStepDTO", "stepType": {"stepTypeKey": kind}, "endCondition": {"conditionTypeKey": "time"},
               "endConditionValue": round(seconds), "targetType": {"workoutTargetTypeKey": "no.target"}}
        if speed and kind not in RESTS:
            out.update(targetType={"workoutTargetTypeKey": "pace.zone"}, targetValueOne=speed, targetValueTwo=speed)
        return out

    reps = int(active["noOfSplits"])
    effort = step("interval", float(active["duration"]) / reps, active.get("averageSpeed"))
    rest_seconds = sum(float(parts[k].get("duration") or 0) for k in ("INTERVAL_REST", "INTERVAL_RECOVERY") if k in parts)
    inner = [effort] + ([step("recovery", rest_seconds / reps, None)] if rest_seconds else [])
    steps = []
    for key, kind in (("INTERVAL_WARMUP", "warmup"),):
        if key in parts and parts[key].get("duration"):
            steps.append(step(kind, float(parts[key]["duration"]), parts[key].get("averageSpeed")))
    steps.append({"type": "RepeatGroupDTO", "numberOfIterations": reps, "workoutSteps": inner} if reps > 1 else effort)
    if "INTERVAL_COOLDOWN" in parts and parts["INTERVAL_COOLDOWN"].get("duration"):
        steps.append(step("cooldown", float(parts["INTERVAL_COOLDOWN"]["duration"]), parts["INTERVAL_COOLDOWN"].get("averageSpeed")))
    for k, item in enumerate(steps, 1):
        item["stepOrder"] = k
    sport = (activity.get("activityType") or {}).get("typeKey") or "running"
    return {"workoutName": activity.get("activityName"), "sportType": {"sportTypeKey": sport},
            "workoutSegments": [{"segmentOrder": 1, "workoutSteps": steps}], "_source": "intervalles"}


def followed_key(activity_id: str) -> str:
    return f"activite:{activity_id}"


def followed_sync(conn: sqlite3.Connection, today: date | None = None, limit: int = 40) -> int:
    """Lit la séance suivie des activités Garmin du mois (FIT déjà sur le disque, sinon résumé des intervalles)."""
    from pathlib import Path

    today = today or date.today()
    acts = conn.execute("SELECT id, source_id, fit_path FROM activities WHERE source = 'garmin' AND date >= ? "
                        "ORDER BY date DESC", ((today - timedelta(days=PAST_DAYS)).isoformat(),)).fetchall()
    if not acts:
        return 0
    keys = [followed_key(a["id"]) for a in acts]
    seen = {r["id"]: r for r in conn.execute(
        f"SELECT id, status, json FROM garmin_workouts WHERE id IN ({','.join('?' * len(keys))})", keys).fetchall()}
    found = done = 0
    for act in acts:
        key = followed_key(act["id"])
        old = seen.get(key)
        has_fit = bool(act["fit_path"]) and Path(act["fit_path"]).exists()
        if old and not (has_fit and old["json"] and '"_source": "intervalles"' in old["json"]):
            continue  # déjà lue (ou rien à lire) ; seul un FIT arrivé depuis peut l'améliorer
        if done >= limit:
            break
        done += 1
        workout = None
        if has_fit:
            try:
                from garmin_fit_sdk import Decoder, Stream
                messages, _errors = Decoder(Stream.from_byte_array(bytearray(Path(act["fit_path"]).read_bytes()))).read()
                workout = workout_from_fit(messages)
            except Exception as exc:  # noqa: BLE001
                LOG.info("Séance suivie illisible dans le FIT de %s (%s)", act["id"], type(exc).__name__)
        if workout is None:
            raw = conn.execute("SELECT payload FROM raw WHERE source = 'garmin' AND kind = 'activity' AND key = ?",
                               (str(act["source_id"]),)).fetchone()
            try:
                workout = workout_from_intervals(json.loads(raw["payload"])) if raw else None
            except (TypeError, ValueError):
                workout = None
        _store(conn, key, 200 if workout else 204, workout)
        found += bool(workout)
    if done:
        conn.commit()
        LOG.info("Séances suivies : %s lue(s) dans %s activité(s) Garmin", found, done)
    return found


def followed(conn: sqlite3.Connection, activity_ids: list[str]) -> dict[str, dict]:
    """La séance suivie de chaque activité qui en a une, par identifiant d'activité."""
    out = stored(conn, [followed_key(a) for a in activity_ids])
    return {k.split(":", 1)[1]: v for k, v in out.items()}
