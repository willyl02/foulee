"""« Ma séance du jour » (la vue Aujourd'hui) : avant la séance, ce qui est prévu, le verdict de la nuit en une
phrase, le meilleur créneau selon le poste et la météo ; après, le débrief (prévu face au fait) et le ressenti.

La météo vient d'Open-Meteo (gratuit, sans clé) : la position envoyée est arrondie à 0,1° (une dizaine de
kilomètres), prise au départ de la dernière sortie en extérieur ; la réponse est gardée une heure.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta

import requests

from . import analysis, appariement, calendrier, config, db, metrics, schedule

FORECAST = "https://api.open-meteo.com/v1/forecast"
CACHE_KEY = "meteo_cache"
CACHE_MINUTES = 60
DAY_START, DAY_END = 6, 21  # créneaux proposés de 6 h à 21 h (début de séance)
FOOT = ("course", "trail")
MAX_NOTE = 500


class DayError(ValueError):
    pass


# ------------------------------------------------------------------ verdict et conseil
def advice(verdict: str | None, planned: list[dict]) -> dict:
    """Une phrase, pas six chiffres : feu vert, doucement ou repos, selon la nuit et ce qui est prévu."""
    hard = any((b.get("pct_vma") or 0) >= 88 or (b.get("zone_fc") or 0) >= 4
               for p in planned for b in p.get("blocs") or [])
    if verdict == "alerte":
        if hard:
            return {"niveau": "repos", "titre": "Récupération incomplète : allège la séance",
                    "texte": "Remplace l'intensité par un footing facile, ou décale la séance à demain."}
        return {"niveau": "repos", "titre": "Journée facile", "texte": "Ta nuit n'a pas suffi : reste en endurance, ou repose-toi."}
    if verdict == "moyen":
        return {"niveau": "doucement", "titre": "Vas-y, sans forcer",
                "texte": "Fais la séance, mais garde de la marge sur les allures et écoute tes sensations."
                if hard else "Une séance tranquille passe très bien aujourd'hui."}
    if verdict == "bon":
        return {"niveau": "feu", "titre": "Feu vert", "texte": "Bien récupéré : la séance peut se faire comme prévu."}
    return {"niveau": None, "titre": "Pas encore de mesures de la nuit", "texte": "Synchronise ta montre pour le verdict du jour."}


# ------------------------------------------------------------------ la journée
def _feel(conn: sqlite3.Connection, activity_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM ressentis WHERE activity_id = ?", (activity_id,)).fetchone()
    return {"rpe": row["rpe"], "note": row["note"], "envoye_le": row["envoye_le"]} if row else None


def day_page(conn: sqlite3.Connection, settings: dict, day: date | None = None) -> dict:
    day = day or date.today()
    rows = analysis.fetch_activities(conn, day, day)
    planned = [p for p in calendrier.plan(conn, day, day, activities=rows) if p["type"] != "autre"]
    vma = settings.get("vma_kmh") or None
    for p in planned:
        p["minutes"] = round(appariement.estimated_minutes(p.get("blocs"), vma)) if p.get("blocs") else None
    form = analysis.day_form(conn, day, settings)
    done = []
    for r in rows:
        done.append({"id": r["id"], "nom": r["name"], "sport": r["sport"], "sport_label": metrics.SPORTS.get(r["sport"], r["sport"]),
                     "heure": (r["start_local"] or "")[11:16] or None,
                     "distance_km": round((r["distance_m"] or 0) / 1000, 2) or None,
                     "duree": metrics.fmt_duration(r["moving_s"] or r["duration_s"]),
                     "duree_s": r["moving_s"] or r["duration_s"],
                     "fc_moy": round(r["avg_hr"]) if r["avg_hr"] else None,
                     "allure": metrics.fmt_pace(r["avg_speed"]) if r["avg_speed"] and r["sport"] in FOOT else None,
                     "prevue": next((p["id"] for p in planned if p.get("seance_id") == r["id"]), None),
                     "ressenti": _feel(conn, r["id"])})
    plan = schedule.Schedule.of(settings).day(day)
    return {"date": day.isoformat(), "poste": plan, "vma": vma,
            "forme": {"verdict": form.get("verdict"), "resume": form.get("resume")},
            "conseil": advice(form.get("verdict"), [p for p in planned if p["statut"] != "fait"]),
            "prevues": planned, "faites": done}


# ------------------------------------------------------------------ météo et créneau
def _place(conn: sqlite3.Connection) -> tuple[float, float] | None:
    row = conn.execute("SELECT start_lat, start_lon FROM activities WHERE start_lat IS NOT NULL AND start_lon IS NOT "
                       "NULL AND date >= ? ORDER BY start_local DESC LIMIT 1",
                       ((date.today() - timedelta(days=90)).isoformat(),)).fetchone()
    if not row:
        return None
    return round(row["start_lat"], 1), round(row["start_lon"], 1)


def _forecast(lat: float, lon: float) -> dict:
    params = {"latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2,
              "hourly": "temperature_2m,apparent_temperature,precipitation_probability,precipitation,wind_speed_10m,"
                        "weather_code,is_day"}
    response = requests.get(FORECAST, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def weather(conn: sqlite3.Connection, day: date) -> dict | None:
    """Les heures de la journée (température, pluie, vent, jour ou nuit), ou None sans position ni réseau."""
    if config.is_demo():
        return _demo_weather(day)
    place = _place(conn)
    if place is None:
        return None
    key = f"{place[0]},{place[1]}"
    try:
        cached = json.loads(db.get_meta(conn, CACHE_KEY) or "{}")
    except ValueError:
        cached = {}
    fresh = cached.get("cle") == key and cached.get("le") and \
        datetime.fromisoformat(cached["le"]) > datetime.now() - timedelta(minutes=CACHE_MINUTES)
    data = cached.get("donnees") if fresh else None
    if data is None:
        try:
            data = _forecast(*place)
        except (requests.RequestException, ValueError):
            data = cached.get("donnees") if cached.get("cle") == key else None  # hors ligne : la dernière lue
            if data is None:
                return None
        else:
            try:
                db.set_meta(conn, CACHE_KEY, json.dumps({"cle": key, "le": datetime.now().isoformat(timespec="seconds"),
                                                         "donnees": data}))
            except sqlite3.Error:
                pass
    return _hours(data, day)


def _hours(data: dict, day: date) -> dict | None:
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    out = []
    for i, stamp in enumerate(times):
        if not stamp.startswith(day.isoformat()):
            continue
        hour = int(stamp[11:13])
        row = {k: (hourly.get(k) or [None] * len(times))[i] for k in
               ("temperature_2m", "apparent_temperature", "precipitation_probability", "precipitation", "wind_speed_10m",
                "weather_code", "is_day")}
        out.append({"heure": hour, "temp": row["temperature_2m"], "ressentie": row["apparent_temperature"],
                    "pluie_pct": row["precipitation_probability"], "pluie_mm": row["precipitation"],
                    "vent": row["wind_speed_10m"], "code": row["weather_code"], "jour": bool(row["is_day"])})
    if not out:
        return None
    return {"heures": out, "source": "Open-Meteo", "lien": "https://open-meteo.com/"}


def _demo_weather(day: date) -> dict:
    hours = []
    for h in range(24):
        hours.append({"heure": h, "temp": round(4 + 6 * max(0, 1 - abs(h - 15) / 9), 1), "ressentie": round(2 + 6 * max(0, 1 - abs(h - 15) / 9), 1),
                      "pluie_pct": 70 if 7 <= h <= 10 else 20 if h < 13 else 5, "pluie_mm": 0.6 if 7 <= h <= 10 else 0,
                      "vent": 14 if h < 12 else 8, "code": 61 if 7 <= h <= 10 else 3 if h < 14 else 1, "jour": 8 <= h <= 17})
    return {"heures": hours, "source": "Open-Meteo (démo)", "lien": "https://open-meteo.com/"}


def _busy(plan: dict) -> list[tuple[float, float]]:
    """Heures prises par le travail (avec 1 h pour s'y rendre et souffler), en heures décimales."""
    if not plan.get("debut") or not plan.get("fin"):
        return []
    start = int(plan["debut"][:2]) + int(plan["debut"][3:]) / 60 - 1
    end = int(plan["fin"][:2]) + int(plan["fin"][3:]) / 60 + 1
    return [(start, end)] if end > start else [(start, 24), (0, end)]  # poste de nuit


def best_slot(plan: dict, hours: list[dict] | None, minutes: int | None, now: datetime | None = None,
              day: date | None = None) -> dict | None:
    """Le meilleur moment pour courir : hors du travail, de 6 h à 21 h, le moins de pluie, de vent et de nuit."""
    now = now or datetime.now()
    day = day or now.date()
    length = max(1, -(-int(minutes or 60) // 60))
    busy = _busy(plan)
    by_hour = {h["heure"]: h for h in hours or []}
    best = None
    for start in range(DAY_START, DAY_END + 1):
        if day == now.date() and start < now.hour + (1 if now.minute > 30 else 0):
            continue
        span = [start + i for i in range(length)]
        if any(a < h + 1 and h < b for h in span for a, b in busy):
            continue
        cost = 0.0
        for h in span:
            w = by_hour.get(h)
            if not w:
                continue
            cost += (w["pluie_pct"] or 0) / 10 + max(0, (w["vent"] or 0) - 15) / 5
            temp = w["ressentie"] if w["ressentie"] is not None else w["temp"]
            if temp is not None:
                cost += max(0, 5 - temp) / 2 + max(0, temp - 24) / 1.5
            cost += 0 if w["jour"] else 3
        if best is None or cost < best[0] - 0.01:
            best = (cost, start, span)
    if best is None:
        return None
    _, start, span = best
    weather_hours = [by_hour[h] for h in span if h in by_hour]
    why = []
    if plan.get("debut") and plan.get("fin"):
        why.append(f"après ton poste ({plan['debut']}–{plan['fin']})" if start >= int(plan["fin"][:2])
                   else f"avant ton poste ({plan['debut']}–{plan['fin']})")
    if weather_hours:
        rain = max(h["pluie_pct"] or 0 for h in weather_hours)
        temps = [h["temp"] for h in weather_hours if h["temp"] is not None]
        why.append("sans pluie annoncée" if rain < 20 else f"{rain} % de risque de pluie")
        if temps:
            why.append(f"{round(min(temps))} à {round(max(temps))} °C" if round(min(temps)) != round(max(temps))
                       else f"{round(temps[0])} °C")
        if not all(h["jour"] for h in weather_hours):
            why.append("à la frontale")
    return {"debut": f"{start:02d}:00", "fin": f"{(start + length) % 24:02d}:00", "raison": ", ".join(why)}


def weather_page(conn: sqlite3.Connection, settings: dict, day: date | None = None) -> dict:
    day = day or date.today()
    plan = schedule.Schedule.of(settings).day(day)
    rows = analysis.fetch_activities(conn, day, day)
    planned = [p for p in calendrier.plan(conn, day, day, activities=rows)
               if p["type"] != "autre" and p["statut"] != "fait"]
    minutes = max((appariement.estimated_minutes(p.get("blocs"), settings.get("vma_kmh")) for p in planned
                   if p.get("blocs")), default=None)
    data = weather(conn, day)
    return {"meteo": data, "creneau": best_slot(plan, data["heures"] if data else None, minutes, day=day) if planned
            or not rows else None}


# ------------------------------------------------------------------ ressenti
def save_feel(conn: sqlite3.Connection, activity_id: str, payload: dict) -> dict:
    if not conn.execute("SELECT 1 FROM activities WHERE id = ?", (activity_id,)).fetchone():
        raise DayError("Séance introuvable.")
    rpe = payload.get("rpe")
    if rpe not in (None, ""):
        try:
            rpe = int(rpe)
        except (TypeError, ValueError):
            raise DayError("Ressenti : une note de 1 à 10.") from None
        if not 1 <= rpe <= 10:
            raise DayError("Ressenti : une note de 1 à 10.")
    else:
        rpe = None
    note = " ".join(str(payload.get("note") or "").split())[:MAX_NOTE] or None
    conn.execute("INSERT INTO ressentis(activity_id, rpe, note, modifie_le) VALUES (?,?,?,?) ON CONFLICT(activity_id) "
                 "DO UPDATE SET rpe = excluded.rpe, note = excluded.note, modifie_le = excluded.modifie_le",
                 (activity_id, rpe, note, db.now_iso()))
    return _feel(conn, activity_id) or {}


def mark_sent(conn: sqlite3.Connection, activity_id: str) -> None:
    conn.execute("UPDATE ressentis SET envoye_le = ? WHERE activity_id = ?", (db.now_iso(), activity_id))


def coach_text(conn: sqlite3.Connection, activity_id: str) -> str:
    """Le mot pour le coach : la séance, le ressenti et la note."""
    row = conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
    feel = _feel(conn, activity_id) or {}
    if row is None:
        raise DayError("Séance introuvable.")
    parts = [f"Séance du {date.fromisoformat(row['date']).strftime('%d/%m')} : {row['name'] or 'séance'}"]
    figures = []
    if row["distance_m"]:
        figures.append(f"{row['distance_m'] / 1000:.1f} km".replace(".", ","))
    if row["duration_s"]:
        figures.append(metrics.fmt_duration(row["moving_s"] or row["duration_s"]))
    if figures:
        parts[0] += f" ({', '.join(figures)})"
    if feel.get("rpe"):
        parts.append(f"Ressenti : {feel['rpe']}/10")
    if feel.get("note"):
        parts.append(feel["note"])
    return "\n".join(parts)

