"""La journée en détail : FC minute par minute, Body Battery, phases du sommeil, VFC de la nuit.

Ces courbes ne font pas partie de la synchro (un appel par jour et par donnée) : elles sont
demandées à Garmin quand une tuile les affiche, puis gardées dans la table ``raw``. Un jour
passé ne change plus ; celui du jour est redemandé au plus toutes les 15 minutes.

Body Battery fait exception : la synchro garde déjà ses relevés de la journée.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from .. import config, db, vault
from . import parse
from .client import GarminError, GarminSession

LOG = logging.getLogger("foulee.garmin")
SOURCE = "garmin"
FRESH_FOR = timedelta(minutes=15)

KINDS = {  # donnée de la tuile → (flux rangé dans raw, méthode du client officiel)
    "fc": ("hr_day", "get_daily_heart_rate"),
    "sommeil": ("sleep_day", "get_daily_sleep"),
    "vfc": ("hrv_day", "get_daily_hrv"),
    "body_battery": ("body_battery", None),
}
PHASES = {"deep": "profond", "light": "léger", "rem": "paradoxal", "awake": "éveil"}


class IntradayError(Exception):
    pass


# --------------------------------------------------------------------- dates
def _local(moment: datetime | None) -> str | None:
    return moment.strftime("%Y-%m-%dT%H:%M:%S") if moment else None


def _offset(gmt: Any, local: Any) -> timedelta:
    """Décalage heure locale − UTC, d'après une paire d'horodatages de la réponse."""
    a, b = parse.to_datetime(gmt), parse.to_datetime(local)
    if a is None or b is None:
        return timedelta(0)
    return b - a


def _from_gmt(value: Any, offset: timedelta) -> str | None:
    moment = parse.to_datetime(value)
    return _local(moment + offset) if moment else None


# --------------------------------------------------------------- lectures
def heart_rate_day(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {"points": []}
    offset = _offset(payload.get("startTimestampGMT"), payload.get("startTimestampLocal"))
    index_ts, index_hr = 0, 1
    for descriptor in payload.get("heartRateValueDescriptors") or []:
        key = str(descriptor.get("key", "")).lower()
        if "timestamp" in key:
            index_ts = descriptor.get("index", 0)
        elif "heart" in key or "rate" in key:
            index_hr = descriptor.get("index", 1)
    points = []
    for row in payload.get("heartRateValues") or []:
        if not isinstance(row, list) or len(row) <= max(index_ts, index_hr):
            continue
        hr = parse.positive(row[index_hr])
        when = _from_gmt(row[index_ts], offset)
        if hr is not None and when:
            points.append([when, hr])
    return {"points": points, "repos": parse.positive(payload.get("restingHeartRate")),
            "min": parse.positive(payload.get("minHeartRate")), "max": parse.positive(payload.get("maxHeartRate"))}


def body_battery_day(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {"points": []}
    offset = _offset(payload.get("startTimestampGMT"), payload.get("startTimestampLocal"))
    points = [[_from_gmt(ts, offset), level] for ts, level in parse.body_battery_samples(payload)]
    return {"points": [p for p in points if p[0]], "rechargee": parse.num(payload.get("charged")),
            "depensee": parse.num(payload.get("drained"))}


def _level_names(levels: list[dict], summary: dict) -> dict[float, str]:
    """Garmin numérote les phases (activityLevel) ; on vérifie la numérotation sur les totaux de la nuit."""
    spent: dict[float, float] = {}
    for item in levels:
        start, end = parse.to_datetime(item.get("startGMT")), parse.to_datetime(item.get("endGMT"))
        level = parse.num(item.get("activityLevel"))
        if start and end and level is not None:
            spent[level] = spent.get(level, 0.0) + (end - start).total_seconds()
    totals = {"deep": parse.num(summary.get("deepSleepSeconds")), "light": parse.num(summary.get("lightSleepSeconds")),
              "rem": parse.num(summary.get("remSleepSeconds")), "awake": parse.num(summary.get("awakeSleepSeconds"))}
    candidates = [{0.0: "deep", 1.0: "light", 2.0: "rem", 3.0: "awake"},
                  {0.0: "deep", 1.0: "light", 2.0: "awake", 3.0: "awake"}]

    def error(mapping: dict[float, str]) -> float:
        grouped: dict[str, float] = {}
        for level, seconds in spent.items():
            grouped[mapping.get(level, "awake")] = grouped.get(mapping.get(level, "awake"), 0.0) + seconds
        return sum(abs(grouped.get(k, 0.0) - (v or 0.0)) for k, v in totals.items())

    return min(candidates, key=error) if any(totals.values()) else candidates[0]


def sleep_day(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {"phases": []}
    summary = payload.get("dailySleepDTO") if isinstance(payload.get("dailySleepDTO"), dict) else payload
    gmt, local = summary.get("sleepStartTimestampGMT"), summary.get("sleepStartTimestampLocal")
    offset = _offset(gmt, local)
    levels = [x for x in payload.get("sleepLevels") or [] if isinstance(x, dict)]
    names = _level_names(levels, summary)
    phases = []
    for item in levels:
        level = parse.num(item.get("activityLevel"))
        start, end = _from_gmt(item.get("startGMT"), offset), _from_gmt(item.get("endGMT"), offset)
        if level is None or not start or not end:
            continue
        phases.append({"debut": start, "fin": end, "phase": PHASES[names.get(level, "awake")]})

    def samples(key: str, value_key: str = "value", time_key: str = "startGMT") -> list:
        out = []
        for item in payload.get(key) or []:
            if not isinstance(item, dict):
                continue
            value = parse.num(item.get(value_key))
            when = _from_gmt(item.get(time_key), offset)
            if value is not None and value >= 0 and when:
                out.append([when, value])
        return out

    _, totals = parse.parse_sleep(summary) if summary.get("sleepTimeSeconds") else (None, {})
    return {
        "phases": phases,
        "fc": samples("sleepHeartRate"),
        "vfc": samples("hrvData"),
        "body_battery": samples("sleepBodyBattery"),
        "stress": samples("sleepStress"),
        "respiration": samples("wellnessEpochRespirationDataDTOList", "respirationValue", "startTimeGMT"),
        "spo2": samples("wellnessEpochSPO2DataDTOList", "spo2Reading", "epochTimestamp"),
        "debut": _from_gmt(gmt, offset), "fin": _from_gmt(summary.get("sleepEndTimestampGMT"), offset),
        "resume": {k: v for k, v in totals.items() if v is not None},
    }


def hrv_day(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {"points": []}
    points = []
    for item in payload.get("hrvReadings") or []:
        if not isinstance(item, dict):
            continue
        value = parse.positive(item.get("hrvValue"))
        when = parse.to_datetime(item.get("readingTimeLocal"))
        if value is not None and when:
            points.append([_local(when), value])
    summary = payload.get("hrvSummary") if isinstance(payload.get("hrvSummary"), dict) else {}
    _, values = parse.parse_hrv(summary) if summary else (None, {})
    return {"points": points, "resume": {k: v for k, v in values.items() if v is not None}}


READERS = {"fc": heart_rate_day, "sommeil": sleep_day, "vfc": hrv_day, "body_battery": body_battery_day}


# ------------------------------------------------------------------ accès
def _stored(conn: sqlite3.Connection, raw_kind: str, day: date) -> tuple[Any, datetime | None]:
    row = conn.execute("SELECT payload, fetched_at FROM raw WHERE source = ? AND kind = ? AND key = ?",
                       (SOURCE, raw_kind, day.isoformat())).fetchone()
    if not row:
        return None, None
    try:
        fetched = datetime.fromisoformat(row["fetched_at"])
    except (TypeError, ValueError):
        fetched = None
    return json.loads(row["payload"]), fetched


def day_detail(conn: sqlite3.Connection, kind: str, day: date, *, fetch: bool = True) -> dict:
    """Courbe d'une journée (ou d'une nuit), depuis la base ou, si besoin, depuis Garmin."""
    if kind not in KINDS:
        raise IntradayError(f"Donnée inconnue : {kind}.")
    raw_kind, method = KINDS[kind]
    payload, fetched = _stored(conn, raw_kind, day)
    stale = payload is None or (day >= date.today() and (fetched is None or datetime.now() - fetched > FRESH_FOR))
    note = None
    if stale and fetch and not config.is_demo() and vault.has_key():
        try:
            with GarminSession() as session:
                if method is None:  # Body Battery : la synchro sait déjà le ranger
                    fresh = parse.body_battery_items(session.call("get_daily_body_battery", day, day))
                    fresh = fresh[0] if fresh else None
                else:
                    fresh = session.call(method, day)
            if fresh:
                db.put_raw(conn, SOURCE, raw_kind, day.isoformat(), fresh)
                conn.commit()
                payload = fresh
        except GarminError as exc:
            LOG.info("Journée %s du %s indisponible : %s", kind, day, exc)
            note = f"Garmin n'a pas répondu ({exc})" if payload is None else "Données de la dernière synchro."
    if payload is None:
        message = note or ("Pas de donnée pour ce jour." if config.is_demo() or vault.has_key()
                           else "Ajoute ta clé API Garmin pour voir le détail de la journée.")
        return {"donnee": kind, "date": day.isoformat(), "vide": True, "message": message}
    try:
        data = READERS[kind](payload)
    except Exception as exc:  # format inattendu : la réponse brute reste gardée pour plus tard
        LOG.warning("Lecture %s du %s impossible : %s", kind, day, exc)
        return {"donnee": kind, "date": day.isoformat(), "vide": True,
                "message": "Réponse de Garmin dans un format inattendu (elle est gardée pour une prochaine version)."}
    empty = not any(data.get(k) for k in ("points", "phases"))
    return {"donnee": kind, "date": day.isoformat(), "vide": empty, "message": note, **data}
