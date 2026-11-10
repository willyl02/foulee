"""Moteur d'analyse : tous les calculs dérivés vivent ici.

L'interface web et Claude (serveur MCP) appellent les mêmes fonctions : ils
donnent donc toujours les mêmes chiffres.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from . import db, fitfile, metrics, schedule, zones as zone_methods

# ======================================================================
#  Dates
# ======================================================================

def to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def iso(value: date) -> str:
    return value.isoformat()


def days_between(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def resolve_period(start: Any = None, end: Any = None, days: int | None = None) -> tuple[date, date]:
    """Période par défaut : les 90 derniers jours jusqu'à aujourd'hui."""
    end_d = to_date(end) if end else date.today()
    if start:
        start_d = to_date(start)
    else:
        start_d = end_d - timedelta(days=(days or 90) - 1)
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    return start_d, end_d


def period_key(day: date, agg: str) -> date:
    if agg in ("semaine", "week"):
        return day - timedelta(days=day.weekday())
    if agg in ("mois", "month"):
        return day.replace(day=1)
    return day


def period_keys(start: date, end: date, agg: str) -> list[date]:
    keys, seen = [], set()
    for day in days_between(start, end):
        key = period_key(day, agg)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


# ======================================================================
#  Profil : FC, VMA, postes
# ======================================================================

def _meta_json(conn: sqlite3.Connection, key: str) -> dict | None:
    raw = db.get_meta(conn, key)
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def garmin_profile(conn: sqlite3.Connection) -> dict:
    """Ce que Garmin dit du profil : zones FC de la montre, seuil lactique, VO2max (relus à chaque synchro)."""
    return {"zones_fc": _meta_json(conn, "garmin_hr_zones"), "profil": _meta_json(conn, "garmin_profil")}


def hr_profile(conn: sqlite3.Connection, settings: dict) -> dict:
    """FC max, FC de repos, zones FC (selon la méthode choisie) et zones d'allure utilisées dans les calculs."""
    garmin = _meta_json(conn, "garmin_hr_zones")
    profile = _meta_json(conn, "garmin_profil") or {}
    if garmin is not None and not garmin.get("lthr") and profile.get("seuil_fc"):
        garmin = {**garmin, "lthr": profile["seuil_fc"]}

    hr_max = settings.get("fc_max") or (garmin or {}).get("max")
    source_max = "réglage" if settings.get("fc_max") else ("zones Garmin" if hr_max else None)
    if not hr_max:
        row = conn.execute(
            "SELECT MAX(max_hr) AS m FROM activities WHERE max_hr IS NOT NULL AND date >= ?",
            (iso(date.today() - timedelta(days=730)),),
        ).fetchone()
        hr_max = row["m"] if row and row["m"] else 190
        source_max = "FC max observée" if row and row["m"] else "valeur par défaut"

    hr_rest = settings.get("fc_repos")
    source_rest = "réglage" if hr_rest else None
    if not hr_rest:
        values = [r["value"] for r in conn.execute(
            "SELECT value FROM daily WHERE metric = 'resting_hr' AND date >= ? ORDER BY date",
            (iso(date.today() - timedelta(days=30)),),
        )]
        hr_rest = statistics.median(values) if values else 50
        source_rest = "médiane 30 j" if values else "valeur par défaut"

    if garmin is None and profile.get("seuil_fc"):
        garmin = {"lthr": profile["seuil_fc"]}
    hz = zone_methods.hr_floors(settings.get("zones_fc"), float(hr_max), float(hr_rest), garmin,
                                max_from_settings=bool(settings.get("fc_max")))
    return {
        "max": float(hr_max),
        "rest": float(hr_rest),
        "floors": hz["floors"],
        "source_max": source_max,
        "source_rest": source_rest,
        "methode": hz["methode"],
        "pct": hz["pct"],
        "seuil": hz["seuil"],
        "noms": hz["noms"],
        "bornes": zone_methods.hr_bounds_text(hz["floors"]),
        "garmin": garmin,
        "allure": pace_profile(settings, profile),
    }


def pace_profile(settings: dict, garmin_profile_data: dict | None = None) -> dict:
    """Zones d'allure : quatre vitesses (m/s) entre les cinq zones, selon la méthode choisie."""
    vma = float(settings.get("vma_kmh") or 16)
    result = zone_methods.pace_bounds(settings.get("zones_allure"), vma, settings.get("zones_allure_pct_vma"),
                                      (garmin_profile_data or {}).get("seuil_vitesse"))
    speeds = result["vitesses"]
    result["bornes"] = [f"plus lent que {metrics.fmt_pace(speeds[0])}"] + [
        f"{metrics.fmt_pace(speeds[i])[:-4]} à {metrics.fmt_pace(speeds[i + 1])}" for i in range(3)
    ] + [f"plus rapide que {metrics.fmt_pace(speeds[3])}"]
    return result


def trimp_coef(settings: dict) -> float:
    return 1.67 if str(settings.get("sexe", "H")).upper().startswith("F") else 1.92


def pace_bounds(settings: dict, garmin_profile_data: dict | None = None) -> list[float]:
    """Bornes des zones d'allure (vitesses en m/s)."""
    return pace_profile(settings, garmin_profile_data)["vitesses"]


def shift_of(day: date, settings: dict, weekdays_only: bool | None = None) -> str | None:
    """Poste du jour selon les horaires (ou « repos »), None pour un jour exclu (congés, repos non compté)."""
    include_rest = None if weekdays_only is None else not weekdays_only
    return schedule.Schedule.of(settings).shift_of(day, include_rest)


# ======================================================================
#  Séance : calculs à partir des courbes
# ======================================================================

def _pairs(streams: dict, key: str) -> Iterable[tuple[float, float, float]]:
    """(t, dt, valeur) en ignorant les pauses (écarts > 10 s)."""
    times = streams.get("t") or []
    values = streams.get(key) or []
    for i in range(1, min(len(times), len(values))):
        dt = times[i] - times[i - 1]
        if dt <= 0 or dt > 10 or values[i] is None:
            continue
        yield times[i], dt, values[i]


def trimp_from_streams(streams: dict, hr_rest: float, hr_max: float, coef: float) -> float | None:
    if not streams.get("hr") or hr_max <= hr_rest:
        return None
    total = 0.0
    seen = False
    for _, dt, hr in _pairs(streams, "hr"):
        reserve = (hr - hr_rest) / (hr_max - hr_rest)
        if reserve <= 0:
            continue
        reserve = min(reserve, 1.1)
        total += (dt / 60) * reserve * 0.64 * math.exp(coef * reserve)
        seen = True
    return round(total, 1) if seen else None


def trimp_from_summary(duration_s: float | None, avg_hr: float | None, hr_rest: float, hr_max: float,
                       coef: float) -> float | None:
    if not duration_s or not avg_hr or hr_max <= hr_rest:
        return None
    reserve = (avg_hr - hr_rest) / (hr_max - hr_rest)
    if reserve <= 0:
        return 0.0
    return round(duration_s / 60 * reserve * 0.64 * math.exp(coef * reserve), 1)


def pace_zone_seconds(streams: dict, bounds: list[float]) -> list[float] | None:
    if not streams.get("spd"):
        return None
    zones = [0.0] * 5
    for _, dt, speed in _pairs(streams, "spd"):
        if speed < 0.8:  # arrêt ou marche très lente : on ne compte pas
            continue
        index = sum(1 for b in bounds if speed >= b)
        zones[min(index, 4)] += dt
    return [round(z) for z in zones] if any(zones) else None


def hr_zone_seconds(streams: dict, floors: list[float]) -> list[float] | None:
    if not streams.get("hr"):
        return None
    zones = [0.0] * 5
    for _, dt, hr in _pairs(streams, "hr"):
        if hr < floors[0]:
            continue
        index = sum(1 for f in floors[1:] if hr >= f)
        zones[min(index, 4)] += dt
    return [round(z) for z in zones] if any(zones) else None


def km_splits(streams: dict, step_m: float = 1000) -> list[dict]:
    times, dist = streams.get("t") or [], streams.get("dist") or []
    hr, alt = streams.get("hr") or [], streams.get("alt") or []
    if not dist or not any(d for d in dist if d):
        return []
    splits, mark, start_i = [], step_m, 0
    for i, d in enumerate(dist):
        if d is None:
            continue
        if d >= mark or i == len(dist) - 1:
            seg_t = times[i] - times[start_i]
            seg_d = (d or 0) - (dist[start_i] or 0)
            if seg_d < 50 or seg_t <= 0:
                break
            hr_values = [h for h in hr[start_i:i + 1] if h]
            alt_values = [a for a in alt[start_i:i + 1] if a is not None]
            gain = sum(max(0, b - a) for a, b in zip(alt_values, alt_values[1:])) if alt_values else None
            splits.append({
                "km": round(mark / 1000, 2) if d >= mark else round(d / 1000, 2),
                "distance_m": round(seg_d),
                "temps_s": round(seg_t),
                "allure": metrics.fmt_pace(seg_d / seg_t),
                "fc_moy": round(sum(hr_values) / len(hr_values)) if hr_values else None,
                "d_plus_m": round(gain) if gain is not None else None,
            })
            start_i = i
            mark += step_m
    return splits


def decoupling(streams: dict) -> dict | None:
    """Découplage cardiaque : dérive du rapport vitesse/FC entre 1re et 2de moitié."""
    times = streams.get("t") or []
    speeds, hrs = streams.get("spd") or [], streams.get("hr") or []
    points = [(t, s, h) for t, s, h in zip(times, speeds, hrs) if s and h and s > 1.0]
    if len(points) < 600:
        return None
    half = len(points) // 2

    def efficiency(chunk):
        return sum(s for _, s, _ in chunk) / sum(h for _, _, h in chunk)

    first, second = efficiency(points[:half]), efficiency(points[half:])
    drift = (first - second) / first * 100
    return {
        "derive_pct": round(drift, 1),
        "lecture": "faible (< 5 %)" if drift < 5 else ("modérée (5 à 10 %)" if drift < 10 else "marquée (> 10 %)"),
    }


def downsample(streams: dict, max_points: int = 1500) -> dict:
    times = streams.get("t") or []
    n = len(times)
    if n <= max_points:
        return streams
    step = math.ceil(n / max_points)
    result: dict[str, list] = {}
    for key, values in streams.items():
        out = []
        for i in range(0, n, step):
            chunk = values[i:i + step]
            if key in ("t", "lat", "lon", "dist"):
                out.append(chunk[0])
            else:
                nums = [v for v in chunk if v is not None]
                out.append(round(sum(nums) / len(nums), 2) if nums else None)
        result[key] = out
    return result


# ======================================================================
#  Mise à jour des données dérivées
# ======================================================================

def store_activity_streams(conn: sqlite3.Connection, activity_id: str, decoded: dict, fit_path: str | None,
                           settings: dict, hrp: dict) -> None:
    """Range courbes + tours d'une séance et calcule ce qui en dépend."""
    conn.execute(
        "INSERT INTO streams(activity_id, payload) VALUES (?, ?) "
        "ON CONFLICT(activity_id) DO UPDATE SET payload = excluded.payload",
        (activity_id, fitfile.pack_streams(decoded["streams"])),
    )
    conn.execute("DELETE FROM laps WHERE activity_id = ?", (activity_id,))
    for lap in decoded.get("laps") or []:
        conn.execute(
            "INSERT INTO laps(activity_id, idx, start_s, duration_s, elapsed_s, distance_m, avg_hr, max_hr, "
            "avg_speed, max_speed, avg_cadence, avg_power, elev_gain_m, elev_loss_m, intensity) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (activity_id, lap["idx"], lap.get("start_s"), lap.get("duration_s"), lap.get("elapsed_s"),
             lap.get("distance_m"), lap.get("avg_hr"), lap.get("max_hr"), lap.get("avg_speed"),
             lap.get("max_speed"), lap.get("avg_cadence"), lap.get("avg_power"), lap.get("elev_gain_m"),
             lap.get("elev_loss_m"), lap.get("intensity")),
        )
    conn.execute(
        "UPDATE activities SET has_streams = 1, fit_path = COALESCE(?, fit_path), updated_at = ? WHERE id = ?",
        (fit_path, db.now_iso(), activity_id),
    )
    update_activity_derived(conn, activity_id, settings, hrp, streams=decoded["streams"])


def update_activity_derived(conn: sqlite3.Connection, activity_id: str, settings: dict, hrp: dict,
                            streams: dict | None = None) -> None:
    row = conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
    if not row:
        return
    if streams is None and row["has_streams"]:
        blob = conn.execute("SELECT payload FROM streams WHERE activity_id = ?", (activity_id,)).fetchone()
        streams = fitfile.unpack_streams(blob["payload"]) if blob else None
    coef = trimp_coef(settings)
    trimp = trimp_from_streams(streams, hrp["rest"], hrp["max"], coef) if streams else None
    if trimp is None:
        trimp = trimp_from_summary(row["duration_s"], row["avg_hr"], hrp["rest"], hrp["max"], coef)
    pace_zones = None
    if streams and row["sport"] in metrics.RUNNING_SPORTS:
        bounds = (hrp.get("allure") or pace_profile(settings, _meta_json(conn, "garmin_profil")))["vitesses"]
        pz = pace_zone_seconds(streams, bounds)
        pace_zones = json.dumps(pz) if pz else None
    # Zones FC : celles comptées par la montre si l'on suit les zones Garmin, sinon recalculées
    # depuis la courbe de FC ; sans courbe, on garde le décompte de Garmin (meilleure approximation).
    garmin_zones = row["hr_zones_garmin"]
    hr_zones = garmin_zones
    if streams and (hrp.get("methode", "garmin") != "garmin" or not garmin_zones):
        hz = hr_zone_seconds(streams, hrp["floors"])
        hr_zones = json.dumps(hz) if hz else garmin_zones
    if settings.get("charge_source", "garmin") == "garmin" and row["garmin_load"] is not None:
        load = row["garmin_load"]
    else:
        load = trimp
    conn.execute(
        "UPDATE activities SET trimp = ?, pace_zones = ?, hr_zones = ?, load = ? WHERE id = ?",
        (trimp, pace_zones, hr_zones, load, activity_id),
    )


def refresh_all_activities(conn: sqlite3.Connection, settings: dict) -> int:
    """Recalcule TRIMP, zones et charge de toutes les séances (après un changement de réglage)."""
    hrp = hr_profile(conn, settings)
    ids = [r["id"] for r in conn.execute("SELECT id FROM activities")]
    for activity_id in ids:
        update_activity_derived(conn, activity_id, settings, hrp)
    recompute_daily_calc(conn)
    return len(ids)


def recompute_daily_calc(conn: sqlite3.Connection) -> None:
    """Charge du jour, chronique (42 j), aiguë (7 j), fraîcheur et ratio, + VO2max par jour."""
    conn.execute("DELETE FROM daily WHERE source = 'calc'")
    rows = conn.execute(
        "SELECT date, SUM(COALESCE(load, 0)) AS load FROM activities GROUP BY date ORDER BY date"
    ).fetchall()
    if rows:
        loads = {r["date"]: r["load"] for r in rows}
        start = to_date(rows[0]["date"])
        k_ctl, k_atl = 1 - math.exp(-1 / 42), 1 - math.exp(-1 / 7)
        ctl = atl = 0.0
        for day in days_between(start, date.today()):
            key = iso(day)
            load = loads.get(key, 0.0) or 0.0
            tsb = ctl - atl
            ctl += (load - ctl) * k_ctl
            atl += (load - atl) * k_atl
            values = {"load_day": load, "ctl": round(ctl, 1), "atl": round(atl, 1), "tsb": round(tsb, 1)}
            if ctl >= 5:
                values["acwr"] = round(atl / ctl, 2)
            db.put_daily(conn, key, values, source="calc")
    for r in conn.execute(
        "SELECT date, MAX(vo2max) AS v FROM activities WHERE vo2max IS NOT NULL GROUP BY date"
    ).fetchall():
        db.put_daily(conn, r["date"], {"vo2max": r["v"]}, source="calc")


# ======================================================================
#  Séries
# ======================================================================

def _sport_list(sport: str | None) -> list[str] | None:
    if not sport or sport in ("tous", "all", "*"):
        return None
    if sport in ("pied", "courses"):
        return list(metrics.RUNNING_SPORTS)
    return [s.strip() for s in sport.split(",") if s.strip()]


def fetch_activities(conn: sqlite3.Connection, start: date, end: date, sport: str | None = None) -> list[sqlite3.Row]:
    sports = _sport_list(sport)
    sql = "SELECT * FROM activities WHERE date BETWEEN ? AND ?"
    params: list[Any] = [iso(start), iso(end)]
    if sports:
        sql += f" AND sport IN ({','.join('?' for _ in sports)})"
        params += sports
    return conn.execute(sql + " ORDER BY start_local", params).fetchall()


def _activity_value(key: str, rows: list[sqlite3.Row]) -> float | None:
    if key == "act.count":
        return float(len(rows))
    if key == "act.distance_km":
        return round(sum(r["distance_m"] or 0 for r in rows) / 1000, 2)
    if key == "act.duration_s":
        return sum(r["duration_s"] or 0 for r in rows)
    if key == "act.elev_gain":
        return sum(r["elev_gain_m"] or 0 for r in rows)
    if key == "act.load":
        return round(sum(r["load"] or 0 for r in rows), 1)
    if key == "act.calories":
        return sum(r["calories"] or 0 for r in rows)
    if key == "act.pace":
        dist = sum(r["distance_m"] or 0 for r in rows if r["distance_m"])
        dur = sum((r["moving_s"] or r["duration_s"] or 0) for r in rows if r["distance_m"])
        return round(dist / dur, 3) if dist > 0 and dur > 0 else None
    if key == "act.avg_hr":
        pairs = [(r["avg_hr"], r["duration_s"] or 0) for r in rows if r["avg_hr"]]
        weight = sum(w for _, w in pairs)
        return round(sum(h * w for h, w in pairs) / weight, 1) if weight else None
    if key.startswith("act.z") and key.endswith("_s"):
        index = int(key[5]) - 1
        total = 0.0
        for r in rows:
            if r["hr_zones"]:
                zones = json.loads(r["hr_zones"])
                if index < len(zones) and zones[index]:
                    total += zones[index]
        return total
    if key == "act.gap":
        pairs = [(r["avg_gap_speed"], r["distance_m"]) for r in rows if r["avg_gap_speed"] and r["distance_m"]]
        weight = sum(w for _, w in pairs)
        return round(sum(v * w for v, w in pairs) / weight, 3) if weight else None
    source = metrics.ACTIVITY_SOURCES.get(key)
    if source is None:
        raise KeyError(key)
    kind, field, how, factor = source
    values: list[tuple[float, float]] = []
    for r in rows:
        if kind == "col":
            value = r[field]
        elif kind == "az":
            zones = json.loads(r["pace_zones"]) if r["pace_zones"] else None
            value = zones[field] if zones and field < len(zones) else None
        else:
            value = _extra(r).get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append((float(value) * factor, float(r["moving_s"] or r["duration_s"] or 0)))
    if not values:
        return 0.0 if how == "sum" and rows and kind == "az" else None
    if how == "sum":
        return round(sum(v for v, _ in values), 3)
    if how == "max":
        return max(v for v, _ in values)
    if how == "min":
        return min(v for v, _ in values)
    weight = sum(w for _, w in values)
    if weight <= 0:
        return round(sum(v for v, _ in values) / len(values), 3)
    return round(sum(v * w for v, w in values) / weight, 3)


def _extra(row: sqlite3.Row) -> dict:
    try:
        raw = row["extra"]
    except (IndexError, KeyError):
        return {}
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _aggregate(values: list[float], fn: str) -> float | None:
    if not values:
        return None
    if fn == "sum":
        return sum(values)
    if fn == "max":
        return max(values)
    if fn == "min":
        return min(values)
    if fn == "last":
        return values[-1]
    return sum(values) / len(values)


def _smooth(points: list[list], window: int) -> list[list]:
    if window <= 1:
        return points
    out, buffer = [], []
    for key, value in points:
        if value is not None:
            buffer.append(value)
            buffer = buffer[-window:]
        out.append([key, round(sum(buffer) / len(buffer), 3) if buffer and value is not None else None])
    return out


def raw_daily_values(conn: sqlite3.Connection, key: str, start: date, end: date,
                     sport: str | None = None) -> dict[str, float]:
    """Valeur brute de Garmin jour par jour (moyenne des séances du jour pour le flux « activity »)."""
    kind, path = metrics.raw_parts(key)
    json_path = "$." + path
    if kind == "activity":
        sql = ("SELECT a.date AS date, json_extract(r.payload, ?) AS value FROM raw r "
               "JOIN activities a ON a.source = 'garmin' AND a.source_id = r.key "
               "WHERE r.source = 'garmin' AND r.kind = 'activity' AND a.date BETWEEN ? AND ?")
        params: list[Any] = [json_path, iso(start), iso(end)]
        sports = _sport_list(sport)
        if sports:
            sql += f" AND a.sport IN ({','.join('?' for _ in sports)})"
            params += sports
    else:
        sql = ("SELECT key AS date, json_extract(payload, ?) AS value FROM raw "
               "WHERE source = 'garmin' AND kind = ? AND key BETWEEN ? AND ?")
        params = [json_path, kind, iso(start), iso(end)]
    groups: dict[str, list[float]] = defaultdict(list)
    for row in conn.execute(sql, params):
        value = row["value"]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            groups[str(row["date"])[:10]].append(float(value))
    return {day: sum(v) / len(v) for day, v in groups.items()}


def series(conn: sqlite3.Connection, key: str, start: date, end: date, agg: str = "jour",
           fn: str | None = None, sport: str | None = None, smooth: int = 0) -> dict:
    metric = metrics.get(key)
    keys = period_keys(start, end, agg)
    if metric.kind == "raw":
        daily_raw: dict[date, list[float]] = defaultdict(list)
        for day_text, value in raw_daily_values(conn, key, start, end, sport).items():
            daily_raw[period_key(to_date(day_text), agg)].append(value)
        how = "avg" if agg in ("jour", "day") else (fn or metric.agg)
        points = []
        for k in keys:
            value = _aggregate(daily_raw.get(k, []), how)
            points.append([iso(k), round(value, 3) if value is not None else None])
    elif metric.kind == "activity":
        groups: dict[date, list] = defaultdict(list)
        for row in fetch_activities(conn, start, end, sport):
            groups[period_key(to_date(row["date"]), agg)].append(row)
        points = [[iso(k), _activity_value(key, groups.get(k, []))] for k in keys]
    else:
        daily: dict[date, list[float]] = defaultdict(list)
        for row in conn.execute(
            "SELECT date, AVG(value) AS value FROM daily WHERE metric = ? AND date BETWEEN ? AND ? "
            "GROUP BY date ORDER BY date", (key, iso(start), iso(end)),
        ):
            daily[period_key(to_date(row["date"]), agg)].append(row["value"])
        how = fn or metric.agg
        if agg in ("jour", "day"):
            how = "avg"
        points = []
        for k in keys:
            value = _aggregate(daily.get(k, []), how)
            points.append([iso(k), round(value, 3) if value is not None else None])
    if smooth:
        points = _smooth(points, int(smooth))
    return {
        "metric": key, "label": metric.label, "unit": metric.unit, "fmt": metric.fmt,
        "agg": agg, "points": points,
    }


def daily_values(conn: sqlite3.Connection, key: str, start: date, end: date) -> dict[str, float]:
    metric = metrics.get(key)
    if metric.kind == "raw":
        return raw_daily_values(conn, key, start, end)
    if metric.kind == "activity":
        out = {}
        groups: dict[str, list] = defaultdict(list)
        for row in fetch_activities(conn, start, end):
            groups[row["date"]].append(row)
        for day, rows in groups.items():
            value = _activity_value(key, rows)
            if value is not None:
                out[day] = value
        return out
    return {
        r["date"]: r["value"]
        for r in conn.execute(
            "SELECT date, AVG(value) AS value FROM daily WHERE metric = ? AND date BETWEEN ? AND ? GROUP BY date",
            (key, iso(start), iso(end)),
        )
    }


# ======================================================================
#  Chiffres clés
# ======================================================================

def kpi(conn: sqlite3.Connection, key: str, as_of: date | None = None, baseline_days: int = 30,
        window: str | None = None) -> dict:
    metric = metrics.get(key)
    as_of = as_of or date.today()
    window = window or ("semaine" if metric.kind == "activity" else "jour")
    span = {"jour": 1, "semaine": 7, "mois": 30}.get(window, 1)
    history_start = as_of - timedelta(days=baseline_days + span + 7)
    values = daily_values(conn, key, history_start, as_of)

    additive = metric.agg == "sum" or (metric.kind == "activity" and key not in ("act.pace", "act.avg_hr"))

    def window_value(end_day: date) -> float | None:
        days = [iso(end_day - timedelta(days=i)) for i in range(span)]
        nums = [values[d] for d in days if d in values]
        if not nums:
            return 0.0 if additive and metric.kind == "activity" else None
        return sum(nums) if additive else sum(nums) / len(nums)

    value_date = None
    value = None
    if span == 1:
        for back in range(0, 4):
            day = as_of - timedelta(days=back)
            if iso(day) in values:
                value, value_date = values[iso(day)], day
                break
    else:
        value, value_date = window_value(as_of), as_of

    baseline = None
    spark = []
    if value_date is not None:
        if span == 1:
            prior = [values[iso(value_date - timedelta(days=i))] for i in range(1, baseline_days + 1)
                     if iso(value_date - timedelta(days=i)) in values]
            baseline = sum(prior) / len(prior) if prior else None
            spark = [[iso(value_date - timedelta(days=i)), values.get(iso(value_date - timedelta(days=i)))]
                     for i in range(min(baseline_days, 30), -1, -1)]
        else:
            windows = max(1, baseline_days // span)
            prior = [window_value(value_date - timedelta(days=span * i)) for i in range(1, windows + 1)]
            prior = [p for p in prior if p is not None]
            baseline = sum(prior) / len(prior) if prior else None
            spark = [[iso(value_date - timedelta(days=span * i)), window_value(value_date - timedelta(days=span * i))]
                     for i in range(windows, -1, -1)]
    delta = (value - baseline) if value is not None and baseline is not None else None
    pct_meaningful = metric.fmt not in ("clock",) and key not in ("tsb", "hrv_status") and baseline and abs(baseline) > 1e-6
    return {
        "metric": key, "label": metric.label, "unit": metric.unit, "fmt": metric.fmt, "better": metric.better,
        "window": window, "value": value, "date": iso(value_date) if value_date else None,
        "baseline": round(baseline, 3) if baseline is not None else None, "baseline_days": baseline_days,
        "delta": round(delta, 3) if delta is not None else None,
        "delta_pct": round(delta / baseline * 100, 1) if delta is not None and pct_meaningful else None,
        "display": metrics.format_value(key, value),
        "spark": spark,
    }


# ======================================================================
#  Comparaisons
# ======================================================================

def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "moyenne": None, "mediane": None, "ecart_type": None}
    return {
        "n": len(values),
        "moyenne": round(sum(values) / len(values), 3),
        "mediane": round(statistics.median(values), 3),
        "ecart_type": round(statistics.stdev(values), 3) if len(values) > 1 else None,
    }


def _effect(a: list[float], b: list[float]) -> dict:
    if len(a) < 3 or len(b) < 3:
        return {"d": None, "lecture": "pas assez de jours"}
    sa, sb = statistics.stdev(a), statistics.stdev(b)
    pooled = math.sqrt(((len(a) - 1) * sa**2 + (len(b) - 1) * sb**2) / (len(a) + len(b) - 2))
    if pooled == 0:
        return {"d": None, "lecture": "valeurs identiques"}
    d = (sum(a) / len(a) - sum(b) / len(b)) / pooled
    size = abs(d)
    label = "négligeable" if size < 0.2 else "faible" if size < 0.5 else "moyen" if size < 0.8 else "net"
    return {"d": round(d, 2), "lecture": label}


def shift_compare(conn: sqlite3.Connection, keys: list[str], start: date, end: date, settings: dict,
                  weekdays_only: bool | None = None) -> dict:
    """Compare des métriques entre postes de travail (matin, soir, nuit…), d'après les horaires.

    weekdays_only : True = jours travaillés seulement, False = jours de repos compris (rattachés au poste
    de leur semaine, ou groupe « repos » pour un cycle en jours), None = réglage des horaires.
    """
    plan = schedule.Schedule.of(settings)
    include_rest = None if weekdays_only is None else not weekdays_only
    groups_def = plan.groups(include_rest)
    ids = [g["id"] for g in groups_def]
    labels = {}
    for day in days_between(start, end):
        labels[iso(day)] = plan.shift_of(day, include_rest)
    days_count = {gid: sum(1 for v in labels.values() if v == gid) for gid in ids}
    result = []
    for key in keys:
        metric = metrics.get(key)
        values = daily_values(conn, key, start, end)
        groups: dict[str, list[float]] = defaultdict(list)
        for day_text, value in values.items():
            label = labels.get(day_text)
            if label:
                groups[label].append(value)
        stats = {gid: _stats(groups.get(gid, [])) for gid in ids}
        present = [gid for gid in ids if stats[gid]["moyenne"] is not None]
        entry: dict[str, Any] = {
            "metric": key, "label": metric.label, "unit": metric.unit, "fmt": metric.fmt, "better": metric.better,
            "groupes": {gid: {**stats[gid], "affiche": metrics.format_value(key, stats[gid]["moyenne"])} for gid in ids},
            "ecart": None, "ecart_pct": None, "effet": {"d": None, "lecture": "pas assez de jours"}, "entre": None,
        }
        if len(present) >= 2:
            # Écart entre les deux postes extrêmes (le premier moins le second pour deux postes)
            if len(present) == 2:
                a, b = present
            else:
                a = max(present, key=lambda g: stats[g]["moyenne"])
                b = min(present, key=lambda g: stats[g]["moyenne"])
            diff = stats[a]["moyenne"] - stats[b]["moyenne"]
            entry.update(ecart=round(diff, 3), entre=[a, b], effet=_effect(groups[a], groups[b]),
                         ecart_pct=round(diff / stats[b]["moyenne"] * 100, 1) if stats[b]["moyenne"] else None)
        # Champs historiques (0.1 à 0.4) quand les postes s'appellent encore « matin » et « soir »
        for legacy in ("matin", "soir"):
            if legacy in stats:
                entry[legacy] = stats[legacy]
                entry[f"{legacy}_affiche"] = metrics.format_value(key, stats[legacy]["moyenne"])
        if entry["entre"] == ["matin", "soir"]:
            entry["ecart_matin_moins_soir"] = entry["ecart"]
        result.append(entry)
    return {"debut": iso(start), "fin": iso(end), "groupes": groups_def, "jours": days_count, "metriques": result,
            "jours_ouvres_seulement": (not include_rest) if include_rest is not None
            else bool(plan.h.get("jours_ouvres", True)),
            "modele": schedule.MODELES.get(plan.h.get("modele"), plan.h.get("modele"))}


def compare_periods(conn: sqlite3.Connection, keys: list[str], a: tuple[date, date], b: tuple[date, date]) -> dict:
    rows = []
    for key in keys:
        metric = metrics.get(key)
        va = list(daily_values(conn, key, *a).values())
        vb = list(daily_values(conn, key, *b).values())
        if metric.kind == "activity" and key not in ("act.pace", "act.avg_hr"):
            total_a, total_b = sum(va), sum(vb)
            weeks_a = ((a[1] - a[0]).days + 1) / 7
            weeks_b = ((b[1] - b[0]).days + 1) / 7
            entry = {"total_a": round(total_a, 2), "total_b": round(total_b, 2),
                     "par_semaine_a": round(total_a / weeks_a, 2), "par_semaine_b": round(total_b / weeks_b, 2)}
        else:
            entry = {"a": _stats(va), "b": _stats(vb),
                     "a_affiche": metrics.format_value(key, _stats(va)["moyenne"]),
                     "b_affiche": metrics.format_value(key, _stats(vb)["moyenne"])}
        rows.append({"metric": key, "label": metric.label, "unit": metric.unit, "fmt": metric.fmt, **entry})
    return {"periode_a": [iso(a[0]), iso(a[1])], "periode_b": [iso(b[0]), iso(b[1])], "metriques": rows}


def scatter(conn: sqlite3.Connection, x: str, y: str, start: date, end: date, settings: dict, lag: int = 0) -> dict:
    plan = schedule.Schedule.of(settings)
    vx = daily_values(conn, x, start, end)
    vy = daily_values(conn, y, start, end + timedelta(days=lag))
    points = []
    for day_text, value_x in sorted(vx.items()):
        day = to_date(day_text)
        target = iso(day + timedelta(days=lag))
        if target in vy:
            points.append({"date": day_text, "x": value_x, "y": vy[target], "poste": plan.shift_of(day, True)})
    r = None
    if len(points) >= 5:
        xs, ys = [p["x"] for p in points], [p["y"] for p in points]
        try:
            r = round(statistics.correlation(xs, ys), 2)
        except statistics.StatisticsError:
            r = None
    mx, my = metrics.get(x), metrics.get(y)
    return {"x": {"metric": x, "label": mx.label, "fmt": mx.fmt, "unit": mx.unit},
            "y": {"metric": y, "label": my.label, "fmt": my.fmt, "unit": my.unit},
            "lag": lag, "points": points, "r": r, "n": len(points), "groupes": plan.groups(True)}


# ======================================================================
#  Zones
# ======================================================================

def zones(conn: sqlite3.Connection, kind: str, start: date, end: date, group: str, sport: str | None,
          settings: dict) -> dict:
    column = "pace_zones" if kind == "allure" else "hr_zones"
    if kind == "allure" and not sport:
        sport = "pied"
    rows = fetch_activities(conn, start, end, sport)
    hrp = hr_profile(conn, settings)
    if kind == "allure":
        pace = hrp["allure"]
        speeds = pace["vitesses"]
        names = list(pace["noms"])
        bounds = [f"< {metrics.fmt_pace(speeds[0])}"] + [
            f"{metrics.fmt_pace(speeds[i])[:-4]} à {metrics.fmt_pace(speeds[i + 1])}" for i in range(len(speeds) - 1)
        ] + [f"> {metrics.fmt_pace(speeds[-1])}"]
        method = pace["methode"]
    else:
        names = list(hrp["noms"])
        bounds = list(hrp["bornes"])
        method = hrp["methode"]
    groups: dict[str, list[float]] = defaultdict(lambda: [0.0] * 5)
    for row in rows:
        if not row[column]:
            continue
        values = json.loads(row[column])
        key = iso(period_key(to_date(row["date"]), group)) if group != "total" else "total"
        for i, v in enumerate(values[:5]):
            groups[key][i] += v or 0
    if group == "total":
        series_rows = [{"periode": "total", "secondes": [round(v) for v in groups.get("total", [0.0] * 5)]}]
    else:
        series_rows = [{"periode": iso(k), "secondes": [round(v) for v in groups.get(iso(k), [0.0] * 5)]}
                       for k in period_keys(start, end, group)]
    return {"kind": kind, "noms": names, "bornes": bounds, "series": series_rows, "methode": method,
            "seances": sum(1 for r in rows if r[column])}


# ======================================================================
#  Séances
# ======================================================================

TRAINING_EFFECT_LABELS = {
    "RECOVERY": "Récupération", "BASE": "Endurance de base", "TEMPO": "Tempo", "LACTATE_THRESHOLD": "Seuil lactique",
    "VO2MAX": "VO2max", "ANAEROBIC_CAPACITY": "Capacité anaérobie", "SPEED": "Vitesse", "NONE": "–",
}


def activity_measures(row: sqlite3.Row | dict, extra: dict) -> list[dict]:
    """Valeurs d'une séance au-delà du résumé (dynamique de course, puissance, respiration…), mises en forme."""
    def num(value: float | None, unit: str, digits: int = 0) -> str | None:
        if value is None:
            return None
        text = f"{value:.{digits}f}".replace(".", ",")
        return f"{text} {unit}".strip()

    sport = row["sport"]
    running = sport in metrics.RUNNING_SPORTS
    cadence = row["avg_cadence"]
    items = [
        ("cadence", "Cadence", num(cadence, "pas/min" if running else "tr/min")),
        ("gct", "Temps de contact au sol", num(extra.get("gct"), "ms")),
        ("gcb", "Équilibre gauche / droite", f"{extra['gcb']:.1f} % / {100 - extra['gcb']:.1f} %".replace(".", ",")
         if extra.get("gcb") else None),
        ("vo", "Oscillation verticale", num(extra.get("vo"), "cm", 1)),
        ("vr", "Ratio vertical", num(extra.get("vr"), "%", 1)),
        ("stride", "Longueur de foulée", num(extra["stride"] / 100, "m", 2) if extra.get("stride") else None),
        ("ssl_pct", "Perte de vitesse par pas", num(extra.get("ssl_pct"), "%", 1)),
        ("power", "Puissance moyenne", num(row["avg_power"], "W")),
        ("np", "Puissance normalisée", num(extra.get("np"), "W")),
        ("pmax", "Puissance max", num(extra.get("pmax"), "W")),
        ("resp", "Respiration", num(extra.get("resp"), "resp/min", 1)),
        ("temp", "Température", f"{extra['temp_min']:.0f} à {extra['temp_max']:.0f} °C"
         if extra.get("temp_min") is not None and extra.get("temp_max") is not None else None),
        ("sweat", "Perte hydrique estimée", num(extra.get("sweat"), "ml")),
        ("bb_impact", "Effet sur la Body Battery", num(extra.get("bb_impact"), "") if extra.get("bb_impact") is not None
         else None),
        ("steps", "Pas", f"{round(extra['steps']):,}".replace(",", " ") if extra.get("steps") else None),
        ("te_label", "Bénéfice principal", TRAINING_EFFECT_LABELS.get(extra.get("te_label"), extra.get("te_label"))
         if extra.get("te_label") else None),
        ("lieu", "Lieu", extra.get("lieu")),
    ]
    best = sorted((int(k[5:]), v) for k, v in extra.items() if k.startswith("best_") and isinstance(v, (int, float)))
    for meters, seconds in best:
        items.append((f"best_{meters}", f"Meilleur {RECORD_NAMES.get(meters, f'{meters / 1000:g} km')}",
                      race_time(seconds)))
    return [{"cle": key, "label": label, "affiche": text} for key, label, text in items if text]


def activity_public(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in ("hr_zones", "pace_zones", "hr_zones_garmin"):
        data[key] = json.loads(data[key]) if data.get(key) else None
    data["extra"] = _extra(row)
    speed = row["avg_speed"]
    data["allure"] = metrics.fmt_pace(speed) if row["sport"] in metrics.RUNNING_SPORTS + ("marche", "rando") else None
    data["vitesse_kmh"] = round(speed * 3.6, 1) if speed else None
    data["duree"] = metrics.fmt_duration(row["duration_s"])
    data["distance_km"] = round((row["distance_m"] or 0) / 1000, 2)
    data["sport_label"] = metrics.SPORTS.get(row["sport"], row["sport"])
    data.pop("fit_path", None)
    return data


def activities_list(conn: sqlite3.Connection, start: date | None = None, end: date | None = None,
                    sport: str | None = None, search: str | None = None, limit: int = 50,
                    offset: int = 0) -> list[dict]:
    sql = "SELECT * FROM activities WHERE 1 = 1"
    params: list[Any] = []
    if start:
        sql += " AND date >= ?"
        params.append(iso(start))
    if end:
        sql += " AND date <= ?"
        params.append(iso(end))
    sports = _sport_list(sport)
    if sports:
        sql += f" AND sport IN ({','.join('?' for _ in sports)})"
        params += sports
    if search:
        sql += " AND (name LIKE ? OR description LIKE ? OR type_key LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    sql += " ORDER BY start_local DESC LIMIT ? OFFSET ?"
    params += [int(limit), int(offset)]
    return [activity_public(r) for r in conn.execute(sql, params)]


def load_streams(conn: sqlite3.Connection, activity_id: str) -> dict | None:
    blob = conn.execute("SELECT payload FROM streams WHERE activity_id = ?", (activity_id,)).fetchone()
    return fitfile.unpack_streams(blob["payload"]) if blob else None


def activity_laps(conn: sqlite3.Connection, activity_id: str, sport: str) -> list[dict]:
    laps = []
    for lap in conn.execute("SELECT * FROM laps WHERE activity_id = ? ORDER BY idx", (activity_id,)):
        data = dict(lap)
        data["allure"] = metrics.fmt_pace(lap["avg_speed"]) if sport in metrics.RUNNING_SPORTS + ("marche", "rando") else None
        data["vitesse_kmh"] = round(lap["avg_speed"] * 3.6, 1) if lap["avg_speed"] else None
        data["duree"] = metrics.fmt_duration(lap["duration_s"])
        laps.append(data)
    return laps


def activity_detail(conn: sqlite3.Connection, activity_id: str, settings: dict) -> dict | None:
    row = conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
    if not row:
        return None
    data = activity_public(row)
    data["tours"] = activity_laps(conn, activity_id, row["sport"])
    streams = load_streams(conn, activity_id) if row["has_streams"] else None
    data["splits_km"] = km_splits(streams) if streams and row["sport"] in metrics.RUNNING_SPORTS + ("marche", "rando") else []
    data["decouplage"] = decoupling(streams) if streams else None
    data["courbes_disponibles"] = sorted(k for k in (streams or {}) if k != "t")
    hrp = hr_profile(conn, settings)
    data["zones_fc_bornes"] = hrp["floors"]
    data["zones_fc_noms"] = hrp["bornes"]
    data["zones_allure_noms"] = hrp["allure"]["bornes"]
    data["mesures"] = activity_measures(row, data["extra"])
    if row["sport"] in metrics.RUNNING_SPORTS:
        vma = float(settings.get("vma_kmh") or 16)
        if row["avg_speed"]:
            data["pct_vma"] = round(row["avg_speed"] * 3.6 / vma * 100)
    return data


def activity_streams(conn: sqlite3.Connection, activity_id: str, max_points: int = 1500) -> dict | None:
    streams = load_streams(conn, activity_id)
    if not streams:
        return None
    return downsample(streams, max_points)


FAST_LAP_LONG_S = 150  # au-delà de 2 min 30, une fraction compte comme « longue » (seuil, allure semi)


def fast_laps(conn: sqlite3.Connection, start: date, end: date, settings: dict) -> dict:
    vma = float(settings.get("vma_kmh") or 16)
    pct = float(settings.get("fractions_seuil_pct_vma") or 85)
    threshold = vma * pct / 100 / 3.6
    # Course sur route/piste uniquement : en trail, une descente rapide n'est pas une fraction.
    rows = conn.execute(
        "SELECT a.id, a.date, a.name, a.sport, l.duration_s, l.distance_m, l.avg_speed, l.avg_hr "
        "FROM laps l JOIN activities a ON a.id = l.activity_id "
        "WHERE a.date BETWEEN ? AND ? AND a.sport = 'course' "
        "AND COALESCE(l.intensity, 'active') NOT IN ('rest', 'warmup', 'cooldown', 'recovery') ORDER BY a.date",
        (iso(start), iso(end)),
    ).fetchall()
    long_s = FAST_LAP_LONG_S

    def bucket() -> dict:
        return {"distance_m": 0.0, "duree_s": 0.0, "fractions": 0, "fc": []}

    per_activity: dict[str, dict] = {}
    for r in rows:
        if not r["avg_speed"] or r["avg_speed"] < threshold:
            continue
        if (r["duration_s"] or 0) < 45 or (r["distance_m"] or 0) < 150:
            continue
        entry = per_activity.setdefault(r["id"], {"id": r["id"], "date": r["date"], "nom": r["name"],
                                                  "tout": bucket(), "courts": bucket(), "longs": bucket()})
        for key in ("tout", "longs" if r["duration_s"] >= long_s else "courts"):
            b = entry[key]
            b["distance_m"] += r["distance_m"]
            b["duree_s"] += r["duration_s"]
            b["fractions"] += 1
            if r["avg_hr"]:
                b["fc"].append(r["avg_hr"])

    def summary(b: dict) -> dict | None:
        if not b["fractions"]:
            return None
        speed = b["distance_m"] / b["duree_s"] if b["duree_s"] else None
        return {"fractions": b["fractions"], "distance_m": round(b["distance_m"]),
                "vitesse": round(speed, 3) if speed else None, "allure": metrics.fmt_pace(speed),
                "fc_moy": round(sum(b["fc"]) / len(b["fc"])) if b["fc"] else None}

    sessions = []
    for entry in per_activity.values():
        whole = summary(entry["tout"]) or {}
        sessions.append({"id": entry["id"], "date": entry["date"], "nom": entry["nom"], **whole,
                         "courts": summary(entry["courts"]), "longs": summary(entry["longs"])})
    return {"seuil_pct_vma": pct, "seuil_allure": metrics.fmt_pace(threshold),
            "duree_longue_s": long_s, "seances": sessions}


# ======================================================================
#  Objectif
# ======================================================================

def parse_hms(text: str) -> int | None:
    try:
        parts = [int(p) for p in str(text).strip().split(":")]
    except ValueError:
        return None
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3:]
    return h * 3600 + m * 60 + s


def objective(settings: dict) -> dict:
    goal = settings.get("objectif") or {}
    target_s = parse_hms(goal.get("temps_cible", ""))
    distance = float(goal.get("distance_km") or 0)
    result: dict[str, Any] = {"nom": goal.get("nom"), "date": goal.get("date"), "distance_km": distance,
                              "temps_cible": goal.get("temps_cible")}
    try:
        race_day = to_date(goal.get("date"))
        days_left = (race_day - date.today()).days
        result["jours_restants"] = days_left
        result["semaines_restantes"] = round(days_left / 7, 1)
    except (TypeError, ValueError):
        pass
    if target_s and distance:
        speed = distance * 1000 / target_s
        vma = float(settings.get("vma_kmh") or 16)
        result.update({
            "vitesse_cible": round(speed, 3),
            "allure_cible": metrics.fmt_pace(speed),
            "vitesse_cible_kmh": round(speed * 3.6, 2),
            "pct_vma": round(speed * 3.6 / vma * 100, 1),
        })
    return result


# ======================================================================
#  Résumé d'une période (pratique pour Claude)
# ======================================================================

SUMMARY_METRICS = ["sleep_s", "sleep_score", "hrv_night", "resting_hr", "bb_max", "bb_wake", "stress_avg", "steps"]


def period_summary(conn: sqlite3.Connection, start: date, end: date, settings: dict) -> dict:
    wellness = {}
    for key in SUMMARY_METRICS:
        values = list(daily_values(conn, key, start, end).values())
        stats = _stats(values)
        wellness[key] = {"libelle": metrics.get(key).label, "moyenne": stats["moyenne"],
                         "affiche": metrics.format_value(key, stats["moyenne"]), "jours": stats["n"]}
    rows = fetch_activities(conn, start, end)
    by_sport: dict[str, list] = defaultdict(list)
    for row in rows:
        by_sport[row["sport"]].append(row)
    training = {}
    for sport, items in sorted(by_sport.items()):
        training[metrics.SPORTS.get(sport, sport)] = {
            "seances": len(items),
            "distance_km": round(sum(r["distance_m"] or 0 for r in items) / 1000, 1),
            "duree": metrics.fmt_duration(sum(r["duration_s"] or 0 for r in items)),
            "d_plus_m": round(sum(r["elev_gain_m"] or 0 for r in items)),
            "charge": round(sum(r["load"] or 0 for r in items)),
        }
    load = {}
    for key in ("ctl", "atl", "tsb", "acwr"):
        row = conn.execute(
            "SELECT value FROM daily WHERE metric = ? AND source = 'calc' AND date <= ? ORDER BY date DESC LIMIT 1",
            (key, iso(end)),
        ).fetchone()
        load[metrics.get(key).label] = round(row["value"], 2) if row else None
    return {"debut": iso(start), "fin": iso(end), "recuperation": wellness, "entrainement": training,
            "charge_fin_de_periode": load}


# ======================================================================
#  Allures selon la VMA (tableau du club) et test VAMEVAL
# ======================================================================

VMA_BANDS = [
    {"id": "recup", "nom": "Endurance récup", "pct": [55], "usage": "footing, récupération"},
    {"id": "ef", "nom": "Endurance fondamentale", "pct": [60, 65, 70],
     "usage": "footing, endurance fondamentale, sorties longues"},
    {"id": "es", "nom": "Endurance soutenue", "pct": [75, 80], "usage": "endurance active : blocs de 20 à 40 min"},
    {"id": "seuil", "nom": "Seuil", "pct": [85], "usage": "seuil : blocs de 20 à 40 min"},
    {"id": "pa", "nom": "Puissance aérobie", "pct": [90], "usage": "puissance aérobie : fractions de 30 s à 3 min"},
    {"id": "vma", "nom": "VMA", "pct": [95, 100, 105], "usage": "VMA : fractions de 30 s à 3 min"},
    {"id": "lactique", "nom": "Système lactique", "pct": [110, 115, 120],
     "usage": "travail lactique et vitesse : efforts de moins de 30 s"},
]
VMA_USES = [
    {"pct": "55 – 70 %", "usage": "footing, endurance fondamentale, sorties longues"},
    {"pct": "75 – 85 %", "usage": "endurance active puis seuil : blocs de 20 à 40 min"},
    {"pct": "90 – 105 %", "usage": "puissance aérobie et VMA : fractions de 30 s à 3 min"},
    {"pct": "110 – 120 %", "usage": "travail lactique et vitesse : efforts de moins de 30 s"},
]
TRACK_DISTANCES = [200, 300, 400, 500, 600, 800]
TRACK_PCTS = [85, 90, 95, 100, 105, 110, 115, 120]


def clock_text(seconds: float | None) -> str:
    """Temps en m:ss, secondes tronquées comme dans le classeur du club (07:16 pour 7 min 16,4 s)."""
    if seconds is None:
        return "–"
    whole = int(seconds + 1e-9)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def race_time(seconds: float) -> str:
    """Temps de course : 4:33, 23:36, 1:32:10 (secondes tronquées, comme une montre)."""
    whole = int(seconds + 1e-9)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def vma_row(label: str, vma: float) -> dict:
    pcts = [p for band in VMA_BANDS for p in band["pct"]]
    paces = [3600 / (vma * p / 100) for p in pcts]
    return {
        "libelle": label, "vma": round(vma, 2),
        "allures_s": [round(x, 2) for x in paces], "allures": [clock_text(x) for x in paces],
        "vitesses": [round(vma * p / 100, 2) for p in pcts],
    }


def track_times(vma: float) -> dict:
    return {
        "vma": round(vma, 2), "pct": TRACK_PCTS,
        "distances": [{"m": d, "temps_s": [round(d / 1000 * 3600 / (vma * p / 100), 2) for p in TRACK_PCTS],
                       "temps": [clock_text(d / 1000 * 3600 / (vma * p / 100)) for p in TRACK_PCTS]}
                      for d in TRACK_DISTANCES],
    }


def vameval(test: Any) -> dict | None:
    """Test VAMEVAL du club : départ à 8 km/h puis +0,5 km/h par minute (paliers d'une minute après
    deux minutes d'échauffement). Renvoie palier, vitesse courue et les deux lectures de la VMA."""
    seconds = parse_hms(str(test)) if not isinstance(test, (int, float)) else float(test)
    if not seconds or seconds < 120 or seconds > 3600:
        return None
    minutes = seconds / 60
    return {
        "temps": clock_text(seconds), "secondes": round(seconds),
        "palier": int(minutes) - 1,
        "vitesse_courue": round(8 + 0.5 * (minutes - 1), 1),
        "vma_palier": round(8 + 0.5 * (int(minutes) - 2), 2),
        "vma_interpolee": round(8 + 0.5 * (minutes - 2), 2),
        "lecture": "VMA interpolée = vitesse courue − 0,5 (règle du barème appliquée en continu) ; "
                   "VMA palier validé = lecture stricte, dernier palier entièrement bouclé.",
    }


def paces_table(settings: dict, compare: float | None = None, test: Any = None) -> dict:
    """Tout le classeur « Allures d'entraînement selon la VMA » : allures, vitesses, temps de passage."""
    vma = float(settings.get("vma_kmh") or 16)
    rows = [vma_row("Ma VMA", vma)]
    vam = vameval(test or settings.get("vameval")) if (test or settings.get("vameval")) else None
    if vam:
        exact = 8 + 0.5 * (vam["secondes"] / 60 - 2)  # sans arrondi, comme le classeur
        rows.append(vma_row("VMA du test (interpolée)", exact))
        rows.append(vma_row("Palier validé", vam["vma_palier"]))
    if compare and 6 <= float(compare) <= 30:
        rows.append(vma_row("Autre VMA", float(compare)))
    return {"vma": vma, "bandes": VMA_BANDS, "pct": [p for band in VMA_BANDS for p in band["pct"]],
            "lignes": rows, "piste": track_times(float(compare) if compare and 6 <= float(compare) <= 30 else vma),
            "usages": VMA_USES, "test": vam}


# ======================================================================
#  Records (meilleurs temps calculés par Garmin pour chaque sortie)
# ======================================================================

RECORD_NAMES = {400: "400 m", 800: "800 m", 1000: "1 km", 1609: "1 mile", 3000: "3 km", 5000: "5 km",
                10000: "10 km", 15000: "15 km", 21097: "Semi-marathon", 21098: "Semi-marathon",
                30000: "30 km", 42195: "Marathon", 50000: "50 km", 100000: "100 km"}


def records(conn: sqlite3.Connection, start: date | None, end: date | None, sport: str | None = "pied") -> dict:
    """Meilleur temps sur chaque distance dans la période, face au meilleur de tout l'historique."""
    sports = _sport_list(sport)
    sql = "SELECT id, date, name, sport, extra FROM activities WHERE extra LIKE '%best_%'"
    params: list[Any] = []
    if sports:
        sql += f" AND sport IN ({','.join('?' for _ in sports)})"
        params += sports
    best_all: dict[int, dict] = {}
    best_period: dict[int, dict] = {}
    for row in conn.execute(sql + " ORDER BY date", params):
        for key, value in _extra(row).items():
            if not key.startswith("best_") or not isinstance(value, (int, float)):
                continue
            meters = int(key[5:])
            meters = 21098 if meters == 21097 else meters
            entry = {"temps_s": float(value), "date": row["date"], "seance_id": row["id"], "seance_nom": row["name"]}
            if meters not in best_all or value < best_all[meters]["temps_s"]:
                best_all[meters] = entry
            inside = (start is None or row["date"] >= iso(start)) and (end is None or row["date"] <= iso(end))
            if inside and (meters not in best_period or value < best_period[meters]["temps_s"]):
                best_period[meters] = entry
    rows = []
    for meters in sorted(set(best_all) | set(best_period)):
        record = best_all[meters]
        current = best_period.get(meters)

        def show(entry: dict | None) -> dict | None:
            if not entry:
                return None
            speed = meters / entry["temps_s"]
            return {**entry, "temps": race_time(entry["temps_s"]), "allure": metrics.fmt_pace(speed)}

        rows.append({"distance_m": meters, "nom": RECORD_NAMES.get(meters, f"{meters / 1000:g} km"),
                     "periode": show(current), "record": show(record),
                     "egale_record": bool(current and current["seance_id"] == record["seance_id"])})
    return {"debut": iso(start) if start else None, "fin": iso(end) if end else None, "records": rows}


# ======================================================================
#  Forme du jour et semaine en cours (page d'accueil)
# ======================================================================

def _latest(conn: sqlite3.Connection, key: str, day: date, back: int = 2) -> tuple[float | None, str | None]:
    row = conn.execute(
        "SELECT date, AVG(value) AS value FROM daily WHERE metric = ? AND date BETWEEN ? AND ? "
        "GROUP BY date ORDER BY date DESC LIMIT 1", (key, iso(day - timedelta(days=back)), iso(day)),
    ).fetchone()
    return (row["value"], row["date"]) if row and row["value"] is not None else (None, None)


def _mean(conn: sqlite3.Connection, key: str, end: date, days: int) -> float | None:
    row = conn.execute("SELECT AVG(value) AS m FROM daily WHERE metric = ? AND date BETWEEN ? AND ?",
                       (key, iso(end - timedelta(days=days)), iso(end - timedelta(days=1)))).fetchone()
    return row["m"] if row and row["m"] is not None else None


def day_form(conn: sqlite3.Connection, day: date | None, settings: dict) -> dict:
    """Signaux de récupération du jour, chacun lu face à ta référence, et une phrase de synthèse."""
    day = day or date.today()
    items = []

    def add(key: str, value: float | None, when: str | None, state: str | None, reference: str, note: str) -> None:
        if value is None:
            return
        meta = metrics.get(key)
        items.append({"metric": key, "label": meta.label, "valeur": value, "affiche": metrics.format_value(key, value),
                      "date": when, "etat": state, "reference": reference, "explication": note})

    rhr, when = _latest(conn, "resting_hr", day)
    if rhr is not None:
        base = _mean(conn, "resting_hr", to_date(when), 30)
        delta = rhr - base if base else 0
        state = "bon" if delta <= 2 else "moyen" if delta <= 5 else "alerte"
        add("resting_hr", rhr, when, state, f"moyenne 30 j : {metrics.format_value('resting_hr', base)}",
            "dans tes habitudes" if delta <= 2 else f"{delta:+.0f} bpm par rapport à d'habitude")
    hrv, when = _latest(conn, "hrv_night", day)
    if hrv is not None:
        low, _ = _latest(conn, "hrv_bl_low", to_date(when), 0)
        high, _ = _latest(conn, "hrv_bl_high", to_date(when), 0)
        if low:
            state = "bon" if hrv >= low else "moyen" if hrv >= low * 0.9 else "alerte"
            reference = f"ta zone : {round(low)}–{round(high or low)} ms"
            note = "dans ta zone habituelle" if low <= hrv <= (high or hrv) else (
                "au-dessus de ta zone" if high and hrv > high else "sous ta zone habituelle")
        else:
            base = _mean(conn, "hrv_night", to_date(when), 30)
            state = None if not base else "bon" if hrv >= base * 0.95 else "moyen" if hrv >= base * 0.85 else "alerte"
            reference = f"moyenne 30 j : {metrics.format_value('hrv_night', base)}"
            note = "face à ta moyenne"
        add("hrv_night", hrv, when, state, reference, note)
    sleep, when = _latest(conn, "sleep_s", day)
    if sleep is not None:
        need, _ = _latest(conn, "sleep_need_min", to_date(when), 0)
        target = (need or 420) * 60
        state = "bon" if sleep >= target - 15 * 60 else "moyen" if sleep >= target - 75 * 60 else "alerte"
        add("sleep_s", sleep, when, state, f"besoin : {metrics.fmt_duration(target)}",
            "besoin couvert" if state == "bon" else f"{metrics.fmt_duration(target - sleep)} de moins que ton besoin")
    score, when = _latest(conn, "sleep_score", day)
    if score is not None:
        state = "bon" if score >= 80 else "moyen" if score >= 60 else "alerte"
        add("sleep_score", score, when, state, "Garmin : 80 et plus = bon", "")
    battery, when = _latest(conn, "bb_wake", day)
    if battery is not None:
        state = "bon" if battery >= 70 else "moyen" if battery >= 40 else "alerte"
        add("bb_wake", battery, when, state, "70 et plus = bien rechargé", "")
    tsb, when = _latest(conn, "tsb", day, 0)
    if tsb is not None:
        state = "bon" if tsb > -10 else "moyen" if tsb >= -30 else "alerte"
        note = ("frais" if tsb > 5 else "équilibré" if tsb > -10 else "tu encaisses ta charge" if tsb >= -30
                else "fatigue accumulée")
        add("tsb", tsb, when, state, "−10 à −30 = charge productive", note)
    spo2, when = _latest(conn, "sleep_spo2_avg", day)
    if spo2 is not None:
        add("sleep_spo2_avg", spo2, when, "bon" if spo2 >= 94 else "moyen" if spo2 >= 90 else "alerte",
            "95 % et plus = habituel", "")
    states = [i["etat"] for i in items if i["etat"]]
    watch = [i["label"].lower() for i in items if i["etat"] in ("moyen", "alerte")]
    if not states:
        verdict, summary = None, "Pas encore de mesures de la nuit : synchronise ta montre."
    elif states.count("alerte") >= 2 or (states.count("alerte") and states.count("moyen") >= 2):
        verdict = "alerte"
        summary = f"Récupération incomplète ({', '.join(watch)}) : une journée facile serait prudente."
    elif states.count("alerte") or states.count("moyen") >= 2:
        verdict = "moyen"
        summary = f"Récupération correcte, à surveiller : {', '.join(watch)}."
    else:
        verdict = "bon"
        summary = "Bien récupéré : tous les signaux sont dans tes habitudes." if not watch else \
            f"Bien récupéré dans l'ensemble (à surveiller : {', '.join(watch)})."
    return {"date": iso(day), "verdict": verdict, "resume": summary, "signaux": items,
            "note": "Indications tirées de tes propres moyennes, pas un avis médical."}


def week_summary(conn: sqlite3.Connection, day: date | None, settings: dict) -> dict:
    """Semaine en cours (lundi → dimanche) : séances, volume et charge face aux 4 semaines précédentes."""
    day = day or date.today()
    monday = day - timedelta(days=day.weekday())
    plan = schedule.Schedule.of(settings)
    rows = fetch_activities(conn, monday, monday + timedelta(days=6))
    days = []
    for offset in range(7):
        current = monday + timedelta(days=offset)
        items = [r for r in rows if r["date"] == iso(current)]
        days.append({
            "date": iso(current), "jour": schedule.WEEKDAYS[offset], "passe": current <= day,
            "planning": plan.day(current),
            "seances": [{"id": r["id"], "sport": r["sport"], "sport_label": metrics.SPORTS.get(r["sport"], r["sport"]),
                         "nom": r["name"], "distance_km": round((r["distance_m"] or 0) / 1000, 1),
                         "duree": metrics.fmt_duration(r["duration_s"]), "charge": round(r["load"] or 0)}
                        for r in items],
        })

    def totals(items: list) -> dict:
        running = [r for r in items if r["sport"] in metrics.RUNNING_SPORTS]
        return {"seances": len(items), "km_course": round(sum(r["distance_m"] or 0 for r in running) / 1000, 1),
                "km": round(sum(r["distance_m"] or 0 for r in items) / 1000, 1),
                "duree_s": round(sum(r["duration_s"] or 0 for r in items)),
                "d_plus": round(sum(r["elev_gain_m"] or 0 for r in items)),
                "charge": round(sum(r["load"] or 0 for r in items))}

    now = totals(rows)
    previous = [totals(fetch_activities(conn, monday - timedelta(days=7 * k), monday - timedelta(days=7 * k - 6)))
                for k in range(1, 5)]
    average = {key: round(sum(p[key] for p in previous) / 4, 1) for key in now}
    now["duree"] = metrics.fmt_duration(now["duree_s"])
    average["duree"] = metrics.fmt_duration(average["duree_s"])
    return {"lundi": iso(monday), "semaine_iso": monday.isocalendar()[1], "jours": days, "totaux": now,
            "moyenne_4_semaines": average}


# ======================================================================
#  Données brutes de Garmin : toutes les valeurs numériques disponibles
# ======================================================================

_SKIP_FIELD = re.compile(r"(Id|ID|Pk|PK|pk|Uuid|uuid|Timestamp|timestamp|TimestampGMT|Version|version|Gmt|GMT|Local)$")


def raw_fields(conn: sqlite3.Connection, sample: int = 20) -> list[dict]:
    """Chaque valeur numérique trouvée dans les dernières réponses de Garmin, prête à servir de métrique."""
    fields = []
    for kind in metrics.RAW_KINDS:
        rows = conn.execute(
            "WITH p AS (SELECT payload FROM raw WHERE source = 'garmin' AND kind = ? "
            "ORDER BY fetched_at DESC, key DESC LIMIT ?) "
            "SELECT t.fullkey AS path, MAX(t.value) AS example, COUNT(*) AS n FROM p, json_tree(p.payload) t "
            "WHERE t.type IN ('integer', 'real') AND t.fullkey NOT LIKE '%[%' GROUP BY t.fullkey ORDER BY t.fullkey",
            (kind, sample),
        ).fetchall()
        for row in rows:
            path = row["path"][2:].replace('"', "") if row["path"].startswith("$.") else ""
            key = f"garmin:{kind}:{path}"
            if not metrics.raw_parts(key) or any(_SKIP_FIELD.search(part) for part in path.split(".")):
                continue
            example = row["example"]
            if isinstance(example, (int, float)) and abs(example) > 1e11:  # horodatage en millisecondes
                continue
            meta = metrics.raw_metric(key)
            fields.append({"key": key, "label": meta.label, "category": meta.category, "kind": "raw",
                           "fmt": "num", "unit": "", "exemple": example, "reponses": row["n"]})
    return fields
