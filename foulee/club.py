"""Mon club : le club FFA de chaque profil, ses coordonnées, sa licence, et les liens vers athle.fr.

La FFA ne propose pas d'accès pour les applications, et athle.fr refuse la lecture automatique :
Foulée ne lit donc rien sur athle.fr. Il garde ce que l'utilisateur saisit, ou colle depuis la fiche
« Coordonnées et contacts » de son club, et construit les liens vers les pages officielles (le
classement du club se retrouve par son numéro, celui de la licence), que le navigateur ouvre.

Saisons FFA : du 1er septembre au 31 août ; la saison « 2027 » va de septembre 2026 à août 2027.

« Fier de ton club ? » : le logo du club, importé par l'utilisateur (PNG à fond transparent de préférence), est
gardé à côté des données du profil, transparence comprise, réduit à 500 pixels de côté au plus.
"""

from __future__ import annotations

import datetime as dt
import io
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from . import config

CLASSEMENT_URL = ("https://www.athle.fr/bases/liste.aspx?frmbase=cclubs&frmmode=2&frmespace=&frmtypeclub=M"
                  "&frmsaison={saison}&frmnclub={numero}&frmruptures=")
FIND_URL = "https://www.athle.fr/trouver-un-club/"
LICENCE_TYPES = ["Athlé Compétition", "Athlé Running", "Athlé Santé", "Athlé Découverte", "Athlé Encadrement",
                 "Athlé Entreprise", "Autre"]
LICENCE_WARNING_DAYS = 30
LOGO_SIDE = 500                   # côté maximal du logo gardé, en pixels (sans rognage : proportions conservées)
LOGO_MAX_UPLOAD = 5 * 1024 * 1024  # 5 Mo à l'envoi
LOGO_MAX_SIDE = 6000               # au-delà, on refuse d'ouvrir l'image (fichier piégé ou démesuré)
LOGO_FORMATS = {"PNG", "WEBP", "JPEG"}
LOGO_RULES = (f"PNG à fond transparent de préférence ({LOGO_SIDE} × {LOGO_SIDE} pixels conseillés), WebP ou JPEG, "
              f"{LOGO_MAX_UPLOAD // (1024 * 1024)} Mo au plus. Il reste sur ta machine.")
TEXT_FIELDS = {"nom": 80, "president": 80, "adresse": 160, "code_postal": 10, "ville": 80, "telephone": 30,
               "email": 120, "site": 300, "page": 300}


class ClubError(ValueError):
    """Valeur de club impossible, expliquée en français."""


# ------------------------------------------------------------------ saisons
def season(day: dt.date | None = None) -> int:
    """Saison FFA du jour : l'année où elle se termine (septembre 2026 → saison 2027)."""
    day = day or dt.date.today()
    return day.year + 1 if day.month >= 9 else day.year


def season_label(year: int) -> str:
    return f"{year - 1}-{year}"


def classement_url(number: str, year: int) -> str:
    return CLASSEMENT_URL.format(saison=year, numero=number)


# ------------------------------------------------------------------ saisie
def clean_number(value: object) -> str:
    """Numéro de club de la licence : jusqu'à 6 chiffres, complété par des zéros (12345 → 012345)."""
    digits = re.sub(r"\s", "", str(value or ""))
    if not digits:
        raise ClubError("Indique le numéro de club : il figure sur ta licence (« N° Club »).")
    if not digits.isdigit() or len(digits) > 6:
        raise ClubError("Le numéro de club a 6 chiffres au plus, comme sur la licence (012345).")
    return digits.zfill(6)


def _url(value: object, *, athle: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not re.match(r"^https?://", text, re.IGNORECASE):
        text = f"https://{text}"
    parts = urlparse(text)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or "." not in host or " " in text:
        raise ClubError(f"Adresse web illisible : « {value} ».")
    if athle and not (host == "athle.fr" or host.endswith(".athle.fr")):
        raise ClubError("La page du club doit être une adresse du site de la FFA (athle.fr).")
    return text


def _date(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError:
        raise ClubError("Date de fin de licence illisible.") from None


def clean(value: Any) -> dict | None:
    """Contrôle le réglage « club » d'un profil."""
    if value in (None, "", {}):
        return None
    if not isinstance(value, dict):
        raise ClubError("Réglage de club illisible.")
    active = bool(value.get("actif"))
    out: dict[str, Any] = {"actif": active}
    number = str(value.get("numero") or "").strip()
    out["numero"] = clean_number(number) if (number or active) else ""
    for key, limit in TEXT_FIELDS.items():
        if key in ("site", "page"):
            continue
        text = " ".join(str(value.get(key) or "").split())
        if len(text) > limit:
            raise ClubError(f"Texte trop long ({key}) : {limit} caractères au plus.")
        out[key] = text
    if out["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", out["email"]):
        raise ClubError(f"Adresse e-mail illisible : « {out['email']} ».")
    out["site"] = _url(value.get("site")) or ""
    out["page"] = _url(value.get("page"), athle=True) or ""
    licence = value.get("licence") if isinstance(value.get("licence"), dict) else {}
    kind = str(licence.get("type") or "").strip()
    out["licence"] = {
        "numero": re.sub(r"\s", "", str(licence.get("numero") or ""))[:20],
        "type": kind if kind in LICENCE_TYPES else ("Autre" if kind else ""),
        "expire": _date(licence.get("expire")) or "",
    }
    return out


# -------------------------------------------------------------- fiche collée
def _fold(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower().strip()


LABELS = {  # étiquettes de la fiche « Coordonnées et contacts » d'athle.fr (sans accents)
    "president": "president", "presidente": "president", "president(e)": "president", "president du club": "president",
    "adresse du siege": "adresse", "adresse": "adresse", "siege": "adresse", "siege social": "adresse",
    "adresse postale": "adresse", "adresse du club": "adresse",
    "code postal": "code_postal", "cp": "code_postal", "ville": "ville", "commune": "ville",
    "telephone": "telephone", "tel": "telephone", "tel.": "telephone", "portable": "telephone", "mobile": "telephone",
    "telephone portable": "telephone", "telephone fixe": "telephone",
    "site internet": "site", "site web": "site", "site": "site", "internet": "site", "site internet du club": "site",
    "email": "email", "e-mail": "email", "mail": "email", "courriel": "email", "adresse e-mail": "email",
    "adresse mail": "email", "adresse email": "email",
}
# Étiquettes reconnues même sans deux-points (« Président DUPONT Jean ») : jamais un début de nom de club
LEADING = {"president", "presidente", "president(e)", "telephone", "tel.", "email", "e-mail", "courriel"}
NOISE = {"retour", "classement", "coordonnees et contacts", "coordonnees", "nos pratiques detaillees", "trouver un club",
         "jeunes", "piste", "running", "sante", "contact", "contacts", "correspondant", "correspondante",
         "accueil", "clubs", "partager", "imprimer", "voir sur la carte", "itineraire"}
EMPTY = {"-", "--", "—", "non renseigne", "non communique", "aucun", "aucune", "n/a", "nc", "neant"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?:\+33\s?(?:\(0\)\s?)?|0)[1-9](?:[\s.-]?\d{2}){4}")
URL = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
DOMAIN = re.compile(r"^(?:https?://)?[\w-]+(?:\.[\w-]+)+(?:[/?#]\S*)?$", re.IGNORECASE)
CIVILITY = re.compile(r"^(?:m|mr|mme|mlle|monsieur|madame|m\.)\s", re.IGNORECASE)
POSTAL = re.compile(r"(?:^|[\s,])(\d{5})\s+([^\d,]{2,80})$")
SEASON = re.compile(r"\b(?:19|20)\d{2}\s*[-/]\s*(?:19|20)\d{2}\b")
NUMBER = re.compile(r"(?:\bn\s*(?:de\s+|du\s+)?club|\bclub\s+n|\bnumero\s+(?:de\s+|du\s+)?club)\s*:?\s*(\d{4,6})\b")


def _labelled(raw: str) -> tuple[str | None, str]:
    """« Étiquette : valeur » (ou une tabulation, dans un tableau copié), l'étiquette seule, ou rien."""
    for sep in (":", "\t"):
        label, cut, rest = raw.partition(sep)
        if cut and (key := LABELS.get(_fold(" ".join(label.split())).rstrip(" *"))):
            return key, " ".join(rest.split()).lstrip(": ")
    line = " ".join(raw.split())
    folded = _fold(line).rstrip(" :*").strip()
    if folded in LABELS:
        return LABELS[folded], ""
    words = line.split()
    for size in (3, 2, 1):  # « Site internet http://… » : étiquette sans deux-points
        head = _fold(" ".join(words[:size]))
        if len(words) > size and head in LABELS and (size > 1 or head in LEADING):
            return LABELS[head], " ".join(words[size:])
    return None, ""


def _name(line: str) -> str | None:
    """Le titre de la page (le nom du club), s'il ressemble à un nom."""
    line = re.split(r"\s[>›]\s", line)[-1].strip()  # fil d'Ariane : « Accueil > Clubs > AC Exemple »
    folded = _fold(line).rstrip(" :")
    if (not line or len(line) > 80 or folded in NOISE or line[0].isdigit() or URL.search(line) or EMAIL.search(line)
            or PHONE.search(line) or NUMBER.search(folded) or folded.startswith("licence") or SEASON.search(line)
            or ":" in line):
        return None
    return line


def parse_sheet(text: str) -> dict:
    """Champs reconnus dans la fiche du club copiée depuis athle.fr (« Coordonnées et contacts »).

    Accepte aussi bien « Étiquette : valeur » que l'étiquette sur une ligne et la valeur sur la suivante,
    ou un tableau copié (tabulations). Ce qui n'est pas reconnu est laissé de côté."""
    found: dict[str, str] = {}
    address: list[str] = []

    def add_address(piece: str) -> None:
        if CIVILITY.match(piece):  # « Mr Jean Dupont 1 rue… » : le destinataire n'est pas l'adresse
            piece = re.sub(r"^\D*", "", piece)
        if match := POSTAL.search(piece):  # « … 75001 Paris »
            found.setdefault("code_postal", match.group(1))
            found.setdefault("ville", match.group(2).strip(" -"))
            piece = piece[:match.start()]
        piece = piece.strip(" ,-")
        if piece:
            address.append(piece)

    def store(key: str, value: str) -> None:
        if _fold(value) in EMPTY:
            return
        if key == "adresse":
            add_address(value)
        elif key == "site" and not DOMAIN.match(value):
            return
        elif key == "email" and not EMAIL.fullmatch(value):
            if match := EMAIL.search(value):
                found.setdefault(key, match.group(0))
        elif key == "telephone" and len(re.sub(r"\D", "", value)) < 8:
            return
        else:
            found.setdefault(key, value)

    pending: str | None = None  # étiquette seule sur sa ligne : la valeur suit
    before_labels = True  # le nom du club vient avant les coordonnées
    raw_lines = [raw for raw in str(text or "").replace("\r", "").split("\n") if raw.strip()][:200]
    for raw in raw_lines:
        line = " ".join(raw.split())
        if _fold(line).rstrip(" :*").strip() in NOISE:
            pending = None
            continue
        key, value = _labelled(raw)
        if key:
            before_labels = False
            if value:
                store(key, value)
                pending = None
            else:
                pending = key
            continue
        if pending == "adresse" and not (URL.search(line) or EMAIL.search(line) or PHONE.fullmatch(line)):
            add_address(line)  # l'adresse tient parfois sur plusieurs lignes
            continue
        if pending and pending != "adresse":
            store(pending, line)
            pending = None
            continue
        pending = None
        if before_labels and "nom" not in found and (name := _name(line)):
            found["nom"] = name

    joined = "\n".join(" ".join(raw.split()) for raw in raw_lines)
    for url in URL.findall(joined):
        url = url.rstrip(".,;)")
        url = url if url.lower().startswith("http") else f"https://{url}"
        host = (urlparse(url).hostname or "").lower()
        if host == "athle.fr" or host.endswith(".athle.fr"):
            if "/clubs/" in url:
                found.setdefault("page", url)
        else:
            found.setdefault("site", url)
    if "email" not in found and (match := EMAIL.search(joined)):
        found["email"] = match.group(0)
    if "telephone" not in found and (match := PHONE.search(joined)):
        found["telephone"] = match.group(0)
    if "telephone" in found:
        digits = re.sub(r"\D", "", found["telephone"])
        if digits.startswith("33") and len(digits) in (11, 12):
            digits = "0" + digits[-9:]
        if len(digits) == 10:
            found["telephone"] = " ".join(digits[i:i + 2] for i in range(0, 10, 2))
    if "code_postal" in found:
        found["code_postal"] = re.sub(r"\D", "", found["code_postal"])[:5]
    if address and "adresse" not in found:
        found["adresse"] = ", ".join(address)
    if "site" in found and not found["site"].lower().startswith("http"):
        found["site"] = f"https://{found['site']}"
    out = {k: v[:TEXT_FIELDS[k]].strip() for k, v in found.items() if k in TEXT_FIELDS and v.strip()}
    if match := NUMBER.search(_fold(joined)):  # « N° Club : 012345 », sur la licence ou la page du club
        out["numero"] = match.group(1).zfill(6)
    if set(out) == {"nom"}:  # une ligne de texte quelconque, pas une fiche de club
        return {}
    return out


# ------------------------------------------------------------------ résumé
def summary(value: dict | None, today: dt.date | None = None) -> dict | None:
    """Ce que montrent la vue « Mon club » et l'accueil : le club, la saison, les liens, la licence."""
    if not value or not value.get("actif") or not value.get("numero"):
        return None
    today = today or dt.date.today()
    year = season(today)
    licence = dict(value.get("licence") or {})
    known = bool(licence.get("numero") or licence.get("type") or licence.get("expire"))
    expire = licence.get("expire") or dt.date(year, 8, 31).isoformat()  # une licence vaut pour la saison
    days = (dt.date.fromisoformat(expire) - today).days
    licence.update({"expire": expire, "jours_restants": days, "renseignee": known,
                    "a_renouveler": known and days <= LICENCE_WARNING_DAYS, "expiree": known and days < 0})
    address = ", ".join(p for p in [value.get("adresse"), " ".join(filter(None, [value.get("code_postal"), value.get("ville")]))] if p)
    phone = re.sub(r"\D", "", value.get("telephone") or "")
    return {
        **value,
        "saison": year, "saison_label": season_label(year),
        "adresse_complete": address,
        "liens": {
            "classement": classement_url(value["numero"], year),
            "classement_precedent": classement_url(value["numero"], year - 1),
            "saison_precedente": season_label(year - 1),
            "page": value.get("page") or None,
            "trouver": FIND_URL,
            "site": value.get("site") or None,
            "telephone": f"tel:+33{phone[1:]}" if len(phone) == 10 and phone.startswith("0") else (f"tel:{phone}" if phone else None),
            "email": f"mailto:{value['email']}" if value.get("email") else None,
            "carte": f"https://www.openstreetmap.org/search?query={quote(address)}" if address else None,
        },
        "licence": licence,
    }


# ------------------------------------------------------------------- logo
class LogoError(ValueError):
    """Image de logo refusée, expliquée en français."""


def logo_path() -> Path:
    # Le mode démo garde son propre logo : il ne remplace jamais le tien
    return config.data_dir() / ("club-logo-demo.png" if config.is_demo() else "club-logo.png")


def logo_version() -> int | None:
    """La date du fichier (pour l'adresse de l'image, qui change à chaque nouveau logo), ou None sans logo."""
    path = logo_path()
    return int(path.stat().st_mtime) if path.exists() else None


def logo_info() -> dict:
    return {"logo": logo_version() is not None, "logo_maj": logo_version(), "regles": LOGO_RULES, "taille": LOGO_SIDE}


def _normalize_logo(data: bytes) -> tuple[bytes, bool]:
    """Le PNG gardé (transparence comprise, marges transparentes retirées) et s'il a un fond transparent."""
    if not data:
        raise LogoError("Fichier vide.")
    if len(data) > LOGO_MAX_UPLOAD:
        raise LogoError(f"Image trop lourde ({len(data) / 1024 / 1024:.1f} Mo) : "
                        f"{LOGO_MAX_UPLOAD // (1024 * 1024)} Mo au plus.")
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as probe:
            kind = probe.format
            width, height = probe.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise LogoError("Ce fichier n'est pas une image lisible (PNG, WebP ou JPEG).") from exc
    if kind not in LOGO_FORMATS:
        raise LogoError(f"Format {kind} non accepté : PNG (idéalement à fond transparent), WebP ou JPEG.")
    if width > LOGO_MAX_SIDE or height > LOGO_MAX_SIDE or width < 32 or height < 32:
        raise LogoError(f"Image de {width} × {height} pixels : entre 32 et {LOGO_MAX_SIDE} pixels de côté.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image).convert("RGBA")
            alpha = image.getchannel("A")
            transparent = alpha.getextrema()[0] < 255
            box = alpha.getbbox()  # le dessin, sans les marges entièrement transparentes
            if box is None:
                raise LogoError("Cette image est entièrement transparente : il n'y a rien à afficher.")
            image = image.crop(box)
            image.thumbnail((LOGO_SIDE, LOGO_SIDE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, "PNG", optimize=True)  # sans métadonnées
    except LogoError:
        raise
    except (OSError, ValueError) as exc:
        raise LogoError("Image abîmée : impossible de la lire jusqu'au bout.") from exc
    return out.getvalue(), transparent


def save_logo(data: bytes) -> dict:
    clean, transparent = _normalize_logo(data)
    path = logo_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(clean)
    tmp.replace(path)
    return {**logo_info(), "transparent": transparent}


def delete_logo() -> dict:
    logo_path().unlink(missing_ok=True)
    return logo_info()
