"""Données de démonstration : un coureur fictif, 14 mois d'historique.

Sert à découvrir l'interface sans clé API, et à tester Foulée. Tout est
fictif et généré de façon reproductible. La base démo est un fichier séparé
(data/foulee-demo.db) : elle ne se mélange jamais avec tes vraies données.

Le profil simulé suit un rythme en postes alternés (semaines ISO impaires du
matin, paires du soir) pour que la vue « Récup & postes » ait quelque chose
à montrer.
"""

from __future__ import annotations

import json
import math
import random
from datetime import date, datetime, timedelta

from . import analysis, config, db
from .garmin.sync import upsert_activity

HR_MAX = 186
HR_REST = 47
VMA = 16.2 / 3.6  # m/s
BASE_LAT, BASE_LON = 48.4045, 2.6985  # forêt de Fontainebleau
FLOORS = [93, 112, 130, 149, 167]


class Athlete:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.next_id = 91_000_000_000

    # ------------------------------------------------------------- séances
    def plan(self, day: date, race_day: date, prep_start: date) -> list[dict]:
        """Séance(s) prévue(s) ce jour-là selon la phase d'entraînement."""
        rng = self.rng
        weekday = day.weekday()
        days_to_race = (race_day - day).days
        if 0 < days_to_race <= 6:
            phase = "affutage"
        elif days_to_race == 0:
            return [{"kind": "race"}]
        elif -21 < days_to_race < 0:
            phase = "recup"
        elif day >= prep_start:
            phase = "semi"
        else:
            phase = "trail"
        if rng.random() < 0.06:  # imprévu : séance sautée
            return []
        if phase == "recup":
            return [{"kind": "easy", "km": rng.uniform(5, 8)}] if weekday in (2, 5) and days_to_race < -7 else []
        if phase == "affutage":
            return [{"kind": "easy", "km": rng.uniform(6, 8)}] if weekday in (1, 3) else []
        week_factor = 0.85 + 0.3 * ((day.isocalendar()[1] % 4) / 3)  # cycles de 4 semaines
        if weekday == 0:
            return [{"kind": "strength"}] if rng.random() < 0.6 else []
        if weekday == 1:
            return [{"kind": "vma" if phase == "semi" or rng.random() < 0.5 else "hills"}]
        if weekday == 2:
            return [{"kind": "easy", "km": rng.uniform(8, 11) * week_factor}]
        if weekday == 3:
            return [{"kind": "tempo" if phase == "semi" else "easy", "km": rng.uniform(9, 12)}]
        if weekday == 4:
            return [{"kind": "bike"}] if rng.random() < 0.25 else []
        if weekday == 5:
            return [{"kind": "easy", "km": rng.uniform(7, 10)}] if rng.random() < 0.7 else []
        if phase == "trail":
            return [{"kind": "trail", "km": rng.uniform(16, 28) * week_factor}]
        return [{"kind": "long", "km": rng.uniform(15, 21) * week_factor}]

    def segments(self, session: dict) -> tuple[str, str, list[tuple[float, float, str]], float]:
        """(sport, nom, segments [(durée s, vitesse m/s, intensité)], relief en m)."""
        rng = self.rng
        kind = session["kind"]
        easy = VMA * rng.uniform(0.66, 0.71)
        if kind == "easy":
            km = session["km"]
            return "course", "Footing", [(km * 1000 / easy, easy, "active")], 15
        if kind == "long":
            km = session["km"]
            speed = VMA * rng.uniform(0.68, 0.72)
            return "course", f"Sortie longue {round(km)} km", [(km * 1000 / speed, speed, "active")], 25
        if kind == "trail":
            km = session["km"]
            speed = VMA * rng.uniform(0.58, 0.64)
            return "trail", f"Trail {round(km)} km", [(km * 1000 / speed, speed, "active")], rng.uniform(90, 160)
        if kind == "race":
            speed = VMA * 0.47
            return "trail", "Trail longue distance (démo)", [(82_000 / speed, speed, "active")], 180
        if kind == "vma":
            reps, dist = rng.choice([(10, 400), (8, 500), (6, 800), (5, 1000)])
            fast = VMA * (1.0 if dist <= 500 else 0.95) * rng.uniform(0.97, 1.02)
            segs = [(900, easy, "warmup")]
            for i in range(reps):
                segs.append((dist / fast, fast, "active"))
                if i < reps - 1:
                    segs.append((90 if dist <= 500 else 120, VMA * 0.45, "rest"))
            segs.append((600, easy, "cooldown"))
            return "course", f"Fractionné {reps} × {dist} m", segs, 10
        if kind == "hills":
            fast = VMA * 0.85
            segs = [(900, easy, "warmup")]
            for _ in range(8):
                segs += [(60, fast, "active"), (75, VMA * 0.4, "rest")]
            segs.append((600, easy, "cooldown"))
            return "course", "Côtes 8 × 1 min", segs, 40
        if kind == "tempo":
            reps = rng.choice([2, 3])
            speed = VMA * rng.uniform(0.86, 0.9)
            segs = [(1200, easy, "warmup")]
            for i in range(reps):
                segs.append((3000 / speed, speed, "active"))
                if i < reps - 1:
                    segs.append((150, VMA * 0.5, "rest"))
            segs.append((600, easy, "cooldown"))
            return "course", f"Seuil {reps} × 3 km", segs, 12
        if kind == "bike":
            return "velo", "Vélo tranquille", [(rng.uniform(3000, 4800), rng.uniform(6.5, 7.5), "active")], 60
        return "renfo", "Renforcement", [(rng.uniform(1800, 2700), 0.0, "active")], 0

    def simulate(self, day: date, session: dict, fatigue: float, with_streams: bool) -> dict:
        rng = self.rng
        sport, name, segs, relief = self.segments(session)
        start = datetime(day.year, day.month, day.day, rng.choice([7, 12, 18]) if day.weekday() < 5 else 9,
                         rng.randint(0, 50))
        step = 2 if sum(s[0] for s in segs) < 4 * 3600 else 5
        t = 0.0
        dist = 0.0
        hr = HR_REST + 30.0
        lat, lon = BASE_LAT + rng.uniform(-0.02, 0.02), BASE_LON + rng.uniform(-0.03, 0.03)
        heading = rng.uniform(0, 2 * math.pi)
        phase1, phase2 = rng.uniform(0, 6), rng.uniform(0, 6)
        streams = {k: [] for k in ("t", "hr", "spd", "alt", "cad", "dist", "lat", "lon")}
        laps = []
        alt0 = rng.uniform(60, 140)
        total_duration = sum(s[0] for s in segs)
        track: list[tuple[float, float]] = []
        for intensity_index, (duration, target, intensity) in enumerate(segs):
            lap_start_t, lap_start_d = t, dist
            lap_hr = []
            elapsed = 0.0
            while elapsed < duration:
                x = dist / 1000
                alt = alt0 + relief * (0.6 * math.sin(x / 1.7 + phase1) + 0.4 * math.sin(x / 0.6 + phase2))
                grade = relief * (0.6 / 1.7 * math.cos(x / 1.7 + phase1) + 0.4 / 0.6 * math.cos(x / 0.6 + phase2)) / 1000
                factor = 1 - (4.0 if sport == "trail" else 1.5) * grade
                speed = target * min(1.12, max(0.55, factor)) if target else 0.0
                speed = max(0.0, speed * rng.uniform(0.97, 1.03)) if target else 0.0
                pct = target / VMA if sport in ("course", "trail") else (0.55 if sport == "velo" else 0.45)
                climb = min(0.12, max(-0.06, 3 * grade)) if sport == "trail" else 0.0
                reserve = min(1.0, max(0.15, 0.18 + 1.25 * (pct - 0.45) + 0.06 * (t / 3600) + 0.01 * fatigue
                                       + climb))
                target_hr = HR_REST + reserve * (HR_MAX - HR_REST)
                hr += (target_hr - hr) * (1 - math.exp(-step / 25))
                value_hr = round(hr + rng.gauss(0, 1.5))
                dist += speed * step
                if sport != "renfo":
                    heading += rng.gauss(0, 0.08)
                    if t > total_duration / 2 and track:
                        back = int((t - total_duration / 2) / step)
                        lat, lon = track[max(0, len(track) - 1 - back)]
                        lat += 0.00004 * math.sin(back / 7)  # retour légèrement décalé, comme sur l'autre trottoir
                    else:
                        lat += speed * step * math.cos(heading) / 111_320
                        lon += speed * step * math.sin(heading) / (111_320 * math.cos(math.radians(lat)))
                        track.append((lat, lon))
                if with_streams:
                    streams["t"].append(int(t))
                    streams["hr"].append(value_hr)
                    streams["spd"].append(round(speed, 3) if sport != "renfo" else None)
                    streams["alt"].append(round(alt, 1) if sport != "renfo" else None)
                    cadence = (150 + 7 * speed + rng.gauss(0, 1.5)) if sport in ("course", "trail") else (
                        85 + rng.gauss(0, 3) if sport == "velo" else None)
                    streams["cad"].append(round(cadence, 1) if cadence else None)
                    streams["dist"].append(round(dist, 1))
                    streams["lat"].append(round(lat, 6) if sport != "renfo" else None)
                    streams["lon"].append(round(lon, 6) if sport != "renfo" else None)
                lap_hr.append(value_hr)
                t += step
                elapsed += step
            laps.append({"duration": t - lap_start_t, "distance": dist - lap_start_d, "hr": lap_hr,
                         "intensity": intensity, "start": lap_start_t})
        # Tours : par segment pour les séances structurées, au kilomètre sinon.
        if len(segs) == 1 and sport in ("course", "trail") and with_streams:
            laps = self._auto_laps(streams)
        return {"sport": sport, "name": name, "start": start, "duration": t, "distance": dist,
                "streams": streams if with_streams else None, "laps": laps, "relief": relief}

    @staticmethod
    def _auto_laps(streams: dict) -> list[dict]:
        laps, mark, start_i = [], 1000.0, 0
        dist, times, hrs = streams["dist"], streams["t"], streams["hr"]
        for i, d in enumerate(dist):
            if d >= mark or i == len(dist) - 1:
                laps.append({"duration": times[i] - times[start_i], "distance": d - dist[start_i],
                             "hr": hrs[start_i:i + 1], "intensity": "active", "start": times[start_i]})
                start_i = i
                mark += 1000
        return [lap for lap in laps if lap["duration"] > 0]


def build(days: int = 430, seed: int = 7) -> dict:
    """(Re)construit la base démo. Renvoie quelques compteurs."""
    config.set_demo(True)
    path = config.db_path()
    for suffix in ("", "-wal", "-shm"):
        candidate = path.with_name(path.name + suffix)
        if candidate.exists():
            candidate.unlink()
    rng = random.Random(seed)
    athlete = Athlete(rng)
    today = date.today()
    start = today - timedelta(days=days)
    race_day = today - timedelta(days=24)
    prep_start = today - timedelta(days=3)
    settings_patch = {"historique_depuis": start.isoformat()}

    with db.session() as conn:
        db.set_meta(conn, "garmin_hr_zones", json.dumps({"floors": FLOORS, "max": HR_MAX, "rest": HR_REST,
                                                         "method": "HR_MAX"}))
        for key, value in settings_patch.items():
            db.set_setting(conn, key, value)
        settings = db.get_settings(conn)
        stream_cutoff = today - timedelta(days=int(settings.get("fit_auto_jours") or 180))
        loads: dict[str, float] = {}
        hrv_history: list[float] = []
        weight = 72.4
        n_activities = 0
        fatigue = 0.0
        for day in analysis.days_between(start, today):
            key = day.isoformat()
            iso_week = day.isocalendar()[1]
            weekday = day.weekday()
            morning = iso_week % 2 == 1 and weekday < 5
            evening = iso_week % 2 == 0 and weekday < 5
            # ----- séances du jour
            day_load = 0.0
            for session in athlete.plan(day, race_day, prep_start):
                sim = athlete.simulate(day, session, fatigue, with_streams=day >= stream_cutoff)
                n_activities += 1
                athlete.next_id += rng.randint(3, 400)
                activity_id = f"garmin:{athlete.next_id}"
                hrs = [h for lap in sim["laps"] for h in lap["hr"]]
                avg_hr = sum(hrs) / len(hrs)
                gain = sim["relief"] * sim["distance"] / 1000 * 0.25 if sim["sport"] != "renfo" else None
                trimp = analysis.trimp_from_summary(sim["duration"], avg_hr, HR_REST, HR_MAX, 1.92) or 0
                row = {
                    "id": activity_id, "source": "garmin", "source_id": str(athlete.next_id),
                    "start_local": sim["start"].strftime("%Y-%m-%d %H:%M:%S"),
                    "start_utc": (sim["start"] - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
                    "date": key, "sport": sim["sport"],
                    "type_key": {"course": "running", "trail": "trail_running", "velo": "road_biking",
                                 "renfo": "strength_training"}[sim["sport"]],
                    "name": sim["name"], "description": None,
                    "duration_s": round(sim["duration"]), "moving_s": round(sim["duration"] * 0.98),
                    "elapsed_s": round(sim["duration"] * 1.02),
                    "distance_m": round(sim["distance"]) if sim["sport"] != "renfo" else None,
                    "elev_gain_m": round(gain) if gain else None, "elev_loss_m": round(gain) if gain else None,
                    "avg_hr": round(avg_hr), "max_hr": max(hrs),
                    "avg_speed": round(sim["distance"] / sim["duration"], 3) if sim["distance"] else None,
                    "max_speed": None, "avg_gap_speed": None,
                    "avg_cadence": 172 if sim["sport"] in ("course", "trail") else None, "avg_power": None,
                    "calories": round(sim["duration"] / 60 * (11 if sim["sport"] != "renfo" else 6)),
                    "te_aerobic": round(min(5.0, 1.5 + trimp / 60), 1), "te_anaerobic": round(rng.uniform(0, 2.5), 1),
                    "garmin_load": round(trimp * 1.15), "vo2max": 52 + round((day - start).days / days * 2) if sim["sport"] in ("course", "trail") else None,
                    "hr_zones": None, "start_lat": BASE_LAT, "start_lon": BASE_LON, "lap_count": len(sim["laps"]),
                }
                upsert_activity(conn, row)
                day_load += row["garmin_load"]
                if sim["streams"]:
                    laps = []
                    for index, lap in enumerate(sim["laps"]):
                        laps.append({
                            "idx": index, "start_s": lap["start"], "duration_s": lap["duration"],
                            "elapsed_s": lap["duration"], "distance_m": round(lap["distance"], 1),
                            "avg_hr": round(sum(lap["hr"]) / len(lap["hr"])), "max_hr": max(lap["hr"]),
                            "avg_speed": round(lap["distance"] / lap["duration"], 3) if lap["duration"] else None,
                            "max_speed": None, "avg_cadence": None, "avg_power": None, "elev_gain_m": None,
                            "elev_loss_m": None, "intensity": lap["intensity"],
                        })
                    decoded = {"streams": {k: v for k, v in sim["streams"].items() if any(x is not None for x in v)},
                               "laps": laps}
                    analysis.store_activity_streams(
                        conn, activity_id, decoded, None, settings,
                        {"max": HR_MAX, "rest": HR_REST, "floors": FLOORS},
                    )
                else:
                    analysis.update_activity_derived(conn, activity_id, settings,
                                                     {"max": HR_MAX, "rest": HR_REST, "floors": FLOORS})
            loads[key] = day_load
            fatigue = fatigue * 0.8 + day_load / 40
            yesterday = loads.get((day - timedelta(days=1)).isoformat(), 0.0)

            # ----- nuit qui se termine ce matin
            if morning:
                wake = 3.9 + rng.gauss(0, 0.12)
                bed = 21.9 + rng.gauss(0, 0.45)
            elif evening:
                wake = 7.15 + rng.gauss(0, 0.2)
                bed = 23.2 + rng.gauss(0, 0.5)
            else:
                wake = 8.2 + rng.gauss(0, 0.5)
                bed = 23.6 + rng.gauss(0, 0.5)
            in_bed = (wake + 24 - bed) if bed > wake else wake - bed
            awake = rng.uniform(0.05, 0.12) * in_bed
            sleep_h = max(3.5, in_bed - awake)
            deep, rem = sleep_h * rng.uniform(0.14, 0.2), sleep_h * rng.uniform(0.19, 0.25)
            score = max(35, min(96, 42 + 6.2 * sleep_h - 0.04 * yesterday + rng.gauss(0, 5)))
            hrv = 63 - (5 if morning else 0) - 0.05 * yesterday - 1.2 * max(0, 7 - sleep_h) + rng.gauss(0, 5)
            hrv_history.append(hrv)
            week = hrv_history[-7:]
            base = hrv_history[-60:]
            mean_base = sum(base) / len(base)
            sd_base = (sum((x - mean_base) ** 2 for x in base) / len(base)) ** 0.5 if len(base) > 1 else 4
            rhr = HR_REST + (1.8 if morning else 0) + 0.03 * yesterday + 0.6 * max(0, 7 - sleep_h) + rng.gauss(0, 1.2)
            bb_wake = max(12, min(100, 18 + 9 * sleep_h - 0.08 * yesterday + rng.gauss(0, 6)))
            steps = 7800 + rng.gauss(0, 2200) + (3500 if morning or evening else 0) + day_load * 30
            values = {
                "sleep_s": round(sleep_h * 3600), "sleep_deep_s": round(deep * 3600), "sleep_rem_s": round(rem * 3600),
                "sleep_light_s": round((sleep_h - deep - rem) * 3600), "sleep_awake_s": round(awake * 3600),
                "sleep_score": round(score), "sleep_start_h": round(bed if bed > 12 else bed + 24, 3),
                "sleep_end_h": round(wake, 3), "sleep_hr": round(rhr + 4 + rng.gauss(0, 1)),
                "sleep_stress": round(12 + rng.gauss(0, 4), 1), "sleep_resp": round(14 + rng.gauss(0, 0.6), 1),
                "hrv_night": round(hrv), "hrv_week": round(sum(week) / len(week)),
                "hrv_high": round(hrv + rng.uniform(8, 20)),
                "hrv_bl_low": round(mean_base - 0.9 * sd_base), "hrv_bl_high": round(mean_base + 0.9 * sd_base),
                "resting_hr": round(rhr), "bb_wake": round(bb_wake),
                "bb_max": round(min(100, bb_wake + rng.uniform(0, 6))), "bb_min": round(max(5, rng.gauss(22, 6))),
                "bb_charged": round(bb_wake - 20 + rng.gauss(0, 5)), "bb_drained": round(bb_wake - 15 + rng.gauss(0, 6)),
                "stress_avg": round(max(10, 27 + (4 if morning else 0) + rng.gauss(0, 5))),
                "stress_max": round(min(99, 85 + rng.gauss(0, 8))),
                "steps": round(max(1500, steps)), "floors": round(max(0, rng.gauss(9, 4))),
                "cal_total": round(2350 + day_load * 4 + rng.gauss(0, 120)), "cal_active": round(450 + day_load * 4),
                "int_minutes": round(day_load / 3 + rng.uniform(0, 15)),
                "resp_avg": round(15 + rng.gauss(0, 0.7), 1),
            }
            low, high = values["hrv_bl_low"], values["hrv_bl_high"]
            values["hrv_status"] = 3 if low <= values["hrv_week"] <= high else 2
            if rng.random() < 0.35:
                weight += rng.gauss(-0.01, 0.25)
                values["weight_kg"] = round(weight, 1)
                values["body_fat_pct"] = round(14.5 + rng.gauss(0, 0.4), 1)
            db.put_daily(conn, key, values)
            if day == today:
                db.put_daily(conn, key, {"fitness_age": 34.5})
            if weekday == 6:
                conn.commit()
        analysis.recompute_daily_calc(conn)
        db.set_meta(conn, "last_sync", db.now_iso())
        db.set_meta(conn, "demo", "1")
        conn.commit()
        counts = db.table_counts(conn)
    counts["seances_generees"] = n_activities
    return counts
