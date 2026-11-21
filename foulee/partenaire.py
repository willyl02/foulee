"""Application partenaire et sites externes : des sites web ouverts dans Foulée.

L'application partenaire (l'appli du club, par défaut Club en ligne) : réglage {"actif", "nom", "adresse"}. Cochée,
une entrée s'ajoute dans la colonne de gauche, sous « Nouvelle vue » ; la page affiche le site dans un cadre, avec
précédent, suivant, recharger et « ouvrir dans le navigateur ». L'adresse peut aller jusqu'à une page précise.

Les sites externes (réglage « sites_externes ») : d'autres sites, tiers, sur le même modèle, chacun avec son entrée
sous l'application partenaire et, au choix, son logo (un PNG importé, sinon le petit globe) ; l'application
partenaire peut avoir le sien aussi (identifiant « partenaire »). Les logos sont rangés avec les données du profil,
réduits à 96 pixels.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import config

DEFAULT = {"actif": False, "nom": "Club en ligne", "adresse": "https://app.clubenligne.fr/"}
MAX_NAME = 30
MAX_URL = 500


class PartnerError(ValueError):
    pass


def _url(raw: Any, label: str, example: str = "https://app.clubenligne.fr/") -> str:
    """Une adresse de site web (https:// ajouté s'il manque) ; refuse javascript:, mailto:… et le reste."""
    url = str(raw or "").strip()
    message = f"{label} : l'adresse doit être celle d'un site web (https://…), par exemple {example}"
    if "://" not in url:
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:(?!\d)", url):  # « javascript:… », « mailto:… »
            raise PartnerError(message)
        url = "https://" + url
    parts = urlsplit(url)
    if (parts.scheme not in ("http", "https") or not re.fullmatch(r"[A-Za-z0-9.-]+(:\d{1,5})?", parts.netloc or "")
            or any(c.isspace() for c in url) or len(url) > MAX_URL):
        raise PartnerError(message)
    return url


def clean(value: Any) -> dict | None:
    """Contrôle le réglage ; None le remet par défaut."""
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        raise PartnerError("Application partenaire : réglage illisible.")
    name = " ".join(str(value.get("nom") or "").split())[:MAX_NAME] or DEFAULT["nom"]
    url = _url(value.get("adresse") or DEFAULT["adresse"], "Application partenaire")
    return {"actif": bool(value.get("actif")), "nom": name, "adresse": url}


def resolve(value: Any) -> dict:
    """Le réglage tel que l'interface l'utilise (les valeurs par défaut si rien n'est enregistré), avec la date de
    son logo (None : le petit globe)."""
    try:
        app = clean(value) or dict(DEFAULT)
    except PartnerError:
        app = dict(DEFAULT)
    return {**app, "logo": logo_version(PARTNER_LOGO)}


# ------------------------------------------------------------------ sites externes
MAX_SITES = 8
SITE_ID = re.compile(r"s\d{1,3}")
PARTNER_LOGO = "partenaire"             # le logo de l'application partenaire, rangé avec ceux des sites
LOGO_MIN, LOGO_MAX = 64, 512            # côtés acceptés, en pixels
LOGO_BYTES = 200 * 1024                 # 200 Ko au plus
LOGO_KEPT = 96                          # côté gardé (net sur un écran haute définition)
LOGO_RULES = ("PNG carré (ou presque), entre 64 × 64 et 512 × 512 pixels, 200 Ko au plus ; fond transparent "
              "conseillé. Sans logo, le petit globe.")


def clean_sites(value: Any) -> list[dict] | None:
    """La liste des sites externes, dans l'ordre du menu ; un site sans identifiant en reçoit un (s1, s2…)."""
    if value in (None, ""):
        return None
    if not isinstance(value, list):
        raise PartnerError("Sites externes : réglage illisible.")
    if len(value) > MAX_SITES:
        raise PartnerError(f"Sites externes : {MAX_SITES} au plus.")
    taken = {str(item.get("id")) for item in value if isinstance(item, dict) and SITE_ID.fullmatch(str(item.get("id") or ""))}
    sites, seen, counter = [], set(), 1
    for item in value:
        if not isinstance(item, dict):
            raise PartnerError("Sites externes : réglage illisible.")
        name = " ".join(str(item.get("nom") or "").split())[:MAX_NAME]
        if not name:
            raise PartnerError("Sites externes : donne un nom à chaque site.")
        site_id = str(item.get("id") or "")
        if not SITE_ID.fullmatch(site_id) or site_id in seen:
            while f"s{counter}" in taken or f"s{counter}" in seen:
                counter += 1
            site_id = f"s{counter}"
        seen.add(site_id)
        sites.append({"id": site_id, "nom": name, "adresse": _url(item.get("adresse"), f"« {name} »", "https://www.athle.fr/"),
                      "actif": bool(item.get("actif", True))})
    return sites


def resolve_sites(value: Any) -> list[dict]:
    """Les sites tels que l'interface les utilise, avec la date de leur logo (None : le globe)."""
    try:
        sites = clean_sites(value) or []
    except PartnerError:
        return []
    return [{**site, "logo": logo_version(site["id"])} for site in sites]


class LogoError(ValueError):
    """Logo refusé, expliqué en français."""


def _logo_dir() -> Path:
    return config.data_dir() / ("sites-logos-demo" if config.is_demo() else "sites-logos")


def logo_path(site_id: str) -> Path:
    if site_id != PARTNER_LOGO and not SITE_ID.fullmatch(site_id or ""):
        raise LogoError("Site inconnu.")
    return _logo_dir() / f"{site_id}.png"


def logo_version(site_id: str) -> int | None:
    path = logo_path(site_id)
    return int(path.stat().st_mtime_ns // 1_000_000) if path.exists() else None


def save_logo(site_id: str, data: bytes) -> dict:
    """Contrôle le PNG (dimensions, poids), le réduit à 96 pixels sans métadonnées et le range."""
    path = logo_path(site_id)
    if not data:
        raise LogoError("Fichier vide.")
    if len(data) > LOGO_BYTES:
        raise LogoError(f"Logo trop lourd ({len(data) // 1024} Ko) : 200 Ko au plus.")
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as probe:
            kind, (width, height) = probe.format, probe.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise LogoError("Ce fichier n'est pas une image PNG lisible.") from exc
    if kind != "PNG":
        raise LogoError(f"Format {kind} : le logo doit être un PNG.")
    if not (LOGO_MIN <= width <= LOGO_MAX and LOGO_MIN <= height <= LOGO_MAX):
        raise LogoError(f"Logo de {width} × {height} pixels : entre {LOGO_MIN} et {LOGO_MAX} pixels de côté.")
    if max(width, height) > 1.25 * min(width, height):
        raise LogoError(f"Logo de {width} × {height} pixels : il doit être carré (ou presque).")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert("RGBA")
            image.thumbnail((LOGO_KEPT, LOGO_KEPT), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, "PNG", optimize=True)
    except (OSError, ValueError) as exc:
        raise LogoError("Image abîmée : impossible de la lire jusqu'au bout.") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(out.getvalue())
    tmp.replace(path)
    return {"id": site_id, "logo": logo_version(site_id)}


def delete_logo(site_id: str) -> dict:
    logo_path(site_id).unlink(missing_ok=True)
    return {"id": site_id, "logo": None}
