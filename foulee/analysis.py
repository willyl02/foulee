"""Moteur d'analyse : tous les calculs dérivés vivent ici.

L'interface web et Claude (serveur MCP) appellent les mêmes fonctions : ils
donnent donc toujours les mêmes chiffres.
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from . import db, fitfile, metrics

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

def hr_profile(conn: sqlite3.Connection, settings: dict) -> dict:
    """FC max, FC de repos et bornes des zones FC utilisées dans les calculs."""
    garmin = None
    raw = db.get_meta(conn, "garmin_hr_zones")
    if raw:
        try:
            garmin = json.loads(raw)
        except json.JSONDecodeError:
            garmin = None

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

    floors = (garmin or {}).get("floors")
    if not floors or settings.get("fc_max"):
        floors = [round(hr_max * p) for p in (0.5, 0.6, 0.7, 0.8, 0.9)]
    return {
        "max": float(hr_max),
        "rest": float(hr_rest),
        "floors": [float(f) for f in floors],
        "source_max": source_max,
        "source_rest": source_rest,
    }


def trimp_coef(settings: dict) -> float:
    return 1.67 if str(settings.get("sexe", "H")).upper().startswith("F") else 1.92


def pace_bounds(settings: dict) -> list[float]:
    """Bornes des zones d'allure (vitesses en m/s) à partir de la VMA."""
    vma = float(settings.get("vma_kmh") or 16)
    pcts = settings.get("zones_allure_pct_vma") or [70, 80, 88, 95]
    return [vma * float(p) / 100 / 3.6 for p in pcts]


def shift_of(day: date, settings: dict, weekdays_only: bool | None = None) -> str | None:
    """« matin » ou « soir » selon la parité de la semaine ISO, ou None si exclu."""
    postes = settings.get("postes") or {}
    if not postes.get("actif", True):
        return None
    if weekdays_only is None:
        weekdays_only = bool(postes.get("jours_ouvres", True))
    if weekdays_only and day.weekday() >= 5:
        return None
    year, week, _ = day.isocalendar()
    if f"{year}-W{week:02d}" in set(postes.get("semaines_exclues") or []):
        return None
    return postes.get("impaires", "matin") if week % 2 == 1 else postes.get("paires", "soir")


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
        pz = pace_zone_seconds(streams, pace_bounds(settings))
        pace_zones = json.dumps(pz) if pz else None
    hr_zones = row["hr_zones"]
    if not hr_zones and streams:
        hz = hr_zone_seconds(streams, hrp["floors"])
        hr_zones = json.dumps(hz) if hz else None
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
    raise KeyError(key)


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


def series(conn: sqlite3.Connection, key: str, start: date, end: date, agg: str = "jour",
           fn: str | None = None, sport: str | None = None, smooth: int = 0) -> dict:
    metric = metrics.get(key)
    keys = period_keys(start, end, agg)
    if metric.kind == "activity":
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
    postes = settings.get("postes") or {}
    labels = sorted({postes.get("impaires", "matin"), postes.get("paires", "soir")})
    days_count = {label: 0 for label in labels}
    for day in days_between(start, end):
        label = shift_of(day, settings, weekdays_only)
        if label:
            days_count[label] = days_count.get(label, 0) + 1
    result = []
    for key in keys:
        metric = metrics.get(key)
        values = daily_values(conn, key, start, end)
        groups: dict[str, list[float]] = defaultdict(list)
        for day_text, value in values.items():
            label = shift_of(to_date(day_text), settings, weekdays_only)
            if label:
                groups[label].append(value)
        a, b = groups.get("matin", []), groups.get("soir", [])
        stats_a, stats_b = _stats(a), _stats(b)
        diff = None
        if stats_a["moyenne"] is not None and stats_b["moyenne"] is not None:
            diff = stats_a["moyenne"] - stats_b["moyenne"]
        result.append({
            "metric": key, "label": metric.label, "unit": metric.unit, "fmt": metric.fmt, "better": metric.better,
            "matin": stats_a, "soir": stats_b,
            "matin_affiche": metrics.format_value(key, stats_a["moyenne"]),
            "soir_affiche": metrics.format_value(key, stats_b["moyenne"]),
            "ecart_matin_moins_soir": round(diff, 3) if diff is not None else None,
            "ecart_pct": round(diff / stats_b["moyenne"] * 100, 1) if diff is not None and stats_b["moyenne"] else None,
            "effet": _effect(a, b),
        })
    return {"debut": iso(start), "fin": iso(end), "jours": days_count, "metriques": result,
            "jours_ouvres_seulement": weekdays_only if weekdays_only is not None else bool(postes.get("jours_ouvres", True))}


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
    vx = daily_values(conn, x, start, end)
    vy = daily_values(conn, y, start, end + timedelta(days=lag))
    points = []
    for day_text, value_x in sorted(vx.items()):
        day = to_date(day_text)
        target = iso(day + timedelta(days=lag))
        if target in vy:
            points.append({"date": day_text, "x": value_x, "y": vy[target], "poste": shift_of(day, settings, False)})
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
            "lag": lag, "points": points, "r": r, "n": len(points)}


# ======================================================================
#  Zones
# ======================================================================

def zones(conn: sqlite3.Connection, kind: str, start: date, end: date, group: str, sport: str | None,
          settings: dict) -> dict:
    column = "pace_zones" if kind == "allure" else "hr_zones"
    if kind == "allure" and not sport:
        sport = "pied"
    rows = fetch_activities(conn, start, end, sport)
    if kind == "allure":
        pcts = settings.get("zones_allure_pct_vma") or [70, 80, 88, 95]
        vma = float(settings.get("vma_kmh") or 16)
        names = list(db.ZONE_NAMES_PACE)
        speeds = [vma * p / 100 / 3.6 for p in pcts]
        bounds = [f"< {metrics.fmt_pace(speeds[0])}"] + [
            f"{metrics.fmt_pace(speeds[i])[:-4]} à {metrics.fmt_pace(speeds[i + 1])}" for i in range(len(speeds) - 1)
        ] + [f"> {metrics.fmt_pace(speeds[-1])}"]
    else:
        hrp = hr_profile(conn, settings)
        floors = [int(f) for f in hrp["floors"]]
        names = ["Z1 Échauffement", "Z2 Facile", "Z3 Aérobie", "Z4 Seuil", "Z5 Maximum"]
        bounds = [f"{floors[i]}–{floors[i + 1] - 1} bpm" for i in range(4)] + [f"≥ {floors[4]} bpm"]
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
    return {"kind": kind, "noms": names, "bornes": bounds, "series": series_rows,
            "seances": sum(1 for r in rows if r[column])}


# ======================================================================
#  Séances
# ======================================================================

def activity_public(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in ("hr_zones", "pace_zones"):
        data[key] = json.loads(data[key]) if data.get(key) else None
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
