"""Profil de l'interface : prénom, logo au choix et photo.

La photo est recadrée en carré par le navigateur avant l'envoi ; ici, on la contrôle et on la
réenregistre (JPEG 256 × 256, sans métadonnées) pour ne garder qu'une image propre et légère.
Elle peut aussi venir de Garmin Connect : les réponses de Garmin donnent l'adresse de ta photo.
"""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

import requests

from . import config, db

PHOTO_SIZE = 256           # côté de l'image gardée, en pixels
MAX_UPLOAD = 8 * 1024 * 1024  # 8 Mo à l'envoi (le navigateur réduit déjà l'image)
MAX_SIDE = 6000            # au-delà, on refuse d'ouvrir l'image (fichier piégé ou démesuré)
FORMATS = {"JPEG", "PNG", "WEBP"}
LOGOS = {
    "foulee": "Foulée (bandeau)",
    "chaussure": "Chaussure",
    "chrono": "Chrono",
    "montagne": "Montagne",
    "coeur": "Cœur",
    "eclair": "Éclair",
    "piste": "Piste",
    "photo": "Ma photo de profil",
}
RULES = (f"JPEG, PNG ou WebP, {MAX_UPLOAD // (1024 * 1024)} Mo au plus. L'image est recadrée en carré et "
         f"réduite à {PHOTO_SIZE} × {PHOTO_SIZE} pixels ; elle reste sur ta machine.")


class PhotoError(ValueError):
    pass


def photo_path() -> Path:
    # Le mode démo garde sa propre photo : elle ne remplace jamais la tienne
    return config.data_dir() / ("profil-demo.jpg" if config.is_demo() else "profil.jpg")


def info() -> dict:
    path = photo_path()
    exists = path.exists()
    return {"photo": exists, "photo_maj": int(path.stat().st_mtime) if exists else None, "logos": LOGOS,
            "regles": RULES, "taille": PHOTO_SIZE}


def _normalize(data: bytes) -> bytes:
    if not data:
        raise PhotoError("Fichier vide.")
    if len(data) > MAX_UPLOAD:
        raise PhotoError(f"Image trop lourde ({len(data) / 1024 / 1024:.1f} Mo) : {MAX_UPLOAD // (1024 * 1024)} Mo au plus.")
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as probe:
            kind = probe.format
            width, height = probe.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PhotoError("Ce fichier n'est pas une image lisible (JPEG, PNG ou WebP).") from exc
    if kind not in FORMATS:
        raise PhotoError(f"Format {kind} non accepté : JPEG, PNG ou WebP.")
    if width > MAX_SIDE or height > MAX_SIDE or width < 32 or height < 32:
        raise PhotoError(f"Image de {width} × {height} pixels : entre 32 et {MAX_SIDE} pixels de côté.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)  # photo prise de travers par un téléphone
            image = image.convert("RGB")
            side = min(image.size)
            left, top = (image.width - side) // 2, (image.height - side) // 2
            image = image.crop((left, top, left + side, top + side)).resize((PHOTO_SIZE, PHOTO_SIZE),
                                                                           Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, "JPEG", quality=88, optimize=True)  # sans EXIF : ni lieu ni appareil
    except (OSError, ValueError) as exc:
        raise PhotoError("Image abîmée : impossible de la lire jusqu'au bout.") from exc
    return out.getvalue()


def save_photo(data: bytes) -> dict:
    clean = _normalize(data)
    path = photo_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(clean)
    tmp.replace(path)
    return info()


def delete_photo() -> dict:
    photo_path().unlink(missing_ok=True)
    return info()


# --------------------------------------------------------------- Garmin
def garmin_identity(conn: sqlite3.Connection) -> dict:
    """Nom et adresse de la photo de profil, tels que Garmin les met dans chaque séance."""
    row = conn.execute("SELECT payload FROM raw WHERE source = 'garmin' AND kind = 'activity' "
                       "ORDER BY fetched_at DESC LIMIT 1").fetchone()
    if not row:
        return {"nom": None, "photo_url": None}
    try:
        payload = json.loads(row["payload"])
    except ValueError:
        return {"nom": None, "photo_url": None}
    url = payload.get("ownerProfileImageUrlLarge") or payload.get("ownerProfileImageUrlMedium")
    return {"nom": payload.get("ownerFullName") or None, "photo_url": url if _trusted(url) else None}


def _trusted(url: str | None) -> bool:
    if not url:
        return False
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host.endswith(".amazonaws.com") or host.endswith(".garmin.com")
                                        or host.endswith(".garmincdn.com"))


def fetch_garmin_photo(conn: sqlite3.Connection) -> dict:
    url = garmin_identity(conn)["photo_url"]
    if not url:
        raise PhotoError("Aucune photo de profil Garmin connue : il faut au moins une séance synchronisée.")
    try:
        with requests.get(url, timeout=20, stream=True) as response:
            if response.status_code != 200:
                raise PhotoError(f"Garmin n'a pas fourni la photo (HTTP {response.status_code}).")
            data = b""
            for chunk in response.iter_content(65536):
                data += chunk
                if len(data) > MAX_UPLOAD:
                    raise PhotoError("Photo Garmin trop lourde.")
    except requests.RequestException as exc:
        raise PhotoError(f"Photo Garmin injoignable ({exc.__class__.__name__}).") from exc
    return save_photo(data)


def first_name(conn: sqlite3.Connection, settings: dict) -> str | None:
    """Prénom affiché : celui des réglages, sinon le premier mot du nom Garmin."""
    chosen = str((settings.get("profil") or {}).get("prenom") or "").strip()
    if chosen:
        return chosen
    name = garmin_identity(conn)["nom"]
    return name.split()[0] if name else None


def clean_profile(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    logo = data.get("logo") if data.get("logo") in LOGOS else "foulee"
    return {"prenom": str(data.get("prenom") or "").strip()[:40], "logo": logo}


def touch(conn: sqlite3.Connection) -> None:
    """Note la date de modification (l'interface recharge la photo)."""
    db.set_meta(conn, "profil_maj", db.now_iso())
