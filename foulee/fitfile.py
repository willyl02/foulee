"""Décodage des fichiers FIT avec le SDK officiel de Garmin (garmin-fit-sdk).

Un fichier FIT contient la séance seconde par seconde (messages « record »),
les tours (« lap ») et le résumé (« session »). On en tire :
- des courbes alignées sur le temps : FC, vitesse, altitude, cadence, puissance,
  distance, GPS, température ;
- la liste des tours, avec leur intensité (échauffement, actif, récupération…).
"""

from __future__ import annotations

import gzip
import io
import json
import zipfile
from datetime import datetime
from typing import Any

from garmin_fit_sdk import Decoder, Stream

SEMICIRCLE = 180 / 2**31
STEP_SPORTS = {"running", "walking", "hiking", "trail_running", "ultra_running"}
STREAM_KEYS = ("t", "hr", "spd", "alt", "cad", "pwr", "dist", "lat", "lon", "temp")


def extract_fit(data: bytes) -> bytes | None:
    """Garmin livre l'original dans un ZIP : on en sort le premier fichier .fit."""
    if not data:
        return None
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".fit")]
            if not names:
                return None
            return archive.read(names[0])
    if len(data) > 12 and data[8:12] == b".FIT":
        return data
    return None


def _first(record: dict, *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and not isinstance(value, (list, dict)):
            return value
    return None


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def decode(data: bytes) -> dict:
    """Décode un FIT (octets bruts) en dictionnaire de courbes, tours et résumé."""
    decoder = Decoder(Stream.from_byte_array(bytearray(data)))
    if not decoder.is_fit():
        raise ValueError("Ce fichier n'est pas un fichier FIT")
    messages, errors = decoder.read(enable_crc_check=False)
    records = messages.get("record_mesgs") or []
    sessions = messages.get("session_mesgs") or []
    laps_raw = messages.get("lap_mesgs") or []
    if not records and errors:
        raise ValueError(f"Décodage FIT impossible : {errors[0]}")

    session = sessions[0] if sessions else {}
    sport = str(session.get("sport") or "").lower() or None
    sub_sport = str(session.get("sub_sport") or "").lower() or None
    doubles_cadence = (sport or "") in STEP_SPORTS

    start = session.get("start_time")
    if not isinstance(start, datetime):
        stamps = [r.get("timestamp") for r in records if isinstance(r.get("timestamp"), datetime)]
        start = min(stamps) if stamps else None
    if start is None:
        raise ValueError("Séance sans horodatage")

    streams: dict[str, list] = {key: [] for key in STREAM_KEYS}
    last_t = None
    for record in records:
        stamp = record.get("timestamp")
        if not isinstance(stamp, datetime):
            continue
        t = int(round((stamp - start).total_seconds()))
        if t < 0:
            continue
        cadence = _num(_first(record, "cadence"))
        if cadence is not None and doubles_cadence:
            cadence = 2 * (cadence + (_num(record.get("fractional_cadence")) or 0))
        lat = _num(record.get("position_lat"))
        lon = _num(record.get("position_long"))
        row = {
            "t": t,
            "hr": _num(record.get("heart_rate")),
            "spd": _num(_first(record, "enhanced_speed", "speed")),
            "alt": _num(_first(record, "enhanced_altitude", "altitude")),
            "cad": round(cadence, 1) if cadence is not None else None,
            "pwr": _num(record.get("power")),
            "dist": _num(record.get("distance")),
            "lat": round(lat * SEMICIRCLE, 6) if lat is not None else None,
            "lon": round(lon * SEMICIRCLE, 6) if lon is not None else None,
            "temp": _num(record.get("temperature")),
        }
        if last_t is not None and t == last_t:
            for key in STREAM_KEYS:  # même seconde : on garde la dernière valeur connue
                if row[key] is not None:
                    streams[key][-1] = row[key]
            continue
        for key in STREAM_KEYS:
            streams[key].append(row[key])
        last_t = t

    # On retire les courbes entièrement vides pour alléger le stockage.
    streams = {k: v for k, v in streams.items() if k == "t" or any(x is not None for x in v)}

    laps = []
    for index, lap in enumerate(laps_raw):
        lap_start = lap.get("start_time")
        offset = (lap_start - start).total_seconds() if isinstance(lap_start, datetime) else None
        cadence = _num(_first(lap, "avg_running_cadence", "avg_cadence"))
        if cadence is not None and doubles_cadence:
            cadence = 2 * (cadence + (_num(lap.get("avg_fractional_cadence")) or 0))
        laps.append({
            "idx": index,
            "start_s": offset,
            "duration_s": _num(lap.get("total_timer_time")),
            "elapsed_s": _num(lap.get("total_elapsed_time")),
            "distance_m": _num(lap.get("total_distance")),
            "avg_hr": _num(lap.get("avg_heart_rate")),
            "max_hr": _num(lap.get("max_heart_rate")),
            "avg_speed": _num(_first(lap, "enhanced_avg_speed", "avg_speed")),
            "max_speed": _num(_first(lap, "enhanced_max_speed", "max_speed")),
            "avg_cadence": round(cadence, 1) if cadence is not None else None,
            "avg_power": _num(lap.get("avg_power")),
            "elev_gain_m": _num(lap.get("total_ascent")),
            "elev_loss_m": _num(lap.get("total_descent")),
            "intensity": str(lap.get("intensity")).lower() if lap.get("intensity") is not None else None,
        })

    return {
        "sport": sport,
        "sub_sport": sub_sport,
        "start_utc": start.strftime("%Y-%m-%d %H:%M:%S"),
        "streams": streams,
        "laps": laps,
        "session": {
            "distance_m": _num(session.get("total_distance")),
            "timer_s": _num(session.get("total_timer_time")),
            "elapsed_s": _num(session.get("total_elapsed_time")),
            "avg_hr": _num(session.get("avg_heart_rate")),
            "max_hr": _num(session.get("max_heart_rate")),
            "ascent_m": _num(session.get("total_ascent")),
            "descent_m": _num(session.get("total_descent")),
        },
        "warnings": [str(e) for e in errors[:3]],
    }


def pack_streams(streams: dict) -> bytes:
    return gzip.compress(json.dumps(streams, separators=(",", ":")).encode("utf-8"), compresslevel=6)


def unpack_streams(blob: bytes) -> dict:
    return json.loads(gzip.decompress(blob).decode("utf-8"))
