"""Logothèque : les logos de club du profil, au choix dans un menu déroulant.

Deux usages, chacun avec son logo choisi dans la même liste :
- « club » : « Mon club », le bandeau de l'Accueil (case « accueil ») et la page « Mon coach » ;
- « partenaire » : l'application partenaire (par défaut Club en ligne), dans la colonne de gauche.

Deux sortes de logos :
- intégrés : livrés avec Foulée (dossier static/logos), ceux de l'ACCT ;
- importés : nommés à l'import, rangés avec les données du profil (dossier « logos »), transparence comprise,
  marges transparentes retirées, réduits à 500 pixels de côté au plus, sans métadonnées. Le même fichier
  importé deux fois n'apparaît qu'une fois.

Le fichier « logos.json » du dossier garde la liste des importés, les deux choix et la case de l'Accueil. Les
logos d'avant la 0.8.3b14 (club-logo.png, sites-logos/partenaire.png) y entrent tout seuls à la première lecture.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import re
import threading
import zlib
from pathlib import Path
from typing import Any

from . import config

SIDE = 500                    # côté maximal gardé, en pixels (sans rognage : proportions conservées)
MAX_UPLOAD = 5 * 1024 * 1024  # 5 Mo à l'envoi
MAX_SIDE = 6000               # au-delà, on refuse d'ouvrir l'image (fichier piégé ou démesuré)
FORMATS = {"PNG", "WEBP", "JPEG"}
RULES = (f"PNG à fond transparent de préférence ({SIDE} × {SIDE} pixels conseillés), WebP ou JPEG, "
         f"{MAX_UPLOAD // (1024 * 1024)} Mo au plus. Il reste sur ta machine.")
MAX_IMPORTED = 30
MAX_NAME = 40
USES = ("club", "partenaire")
LEGACY_NAMES = {"club": "Logo de mon club", "partenaire": "Logo de l'application partenaire"}

BUILTIN_DIR = Path(__file__).resolve().parent / "static" / "logos"
BUILTIN = (
    {"id": "acct", "nom": "ACCT Château-Thierry (bandeau)", "fichier": "acct.png"},
    {"id": "acct-1904", "nom": "ACCT Château-Thierry (rond, 1904-2024)", "fichier": "acct-1904.png"},
)
IMPORTED_ID = re.compile(r"u\d{1,5}")
_LOCK = threading.RLock()


class LogoError(ValueError):
    """Logo refusé ou inconnu, expliqué en français."""


# ------------------------------------------------------------------ image
def normalize(data: bytes) -> tuple[bytes, bool]:
    """Le PNG gardé (transparence comprise, marges transparentes retirées) et s'il a un fond transparent."""
    if not data:
        raise LogoError("Fichier vide.")
    if len(data) > MAX_UPLOAD:
        raise LogoError(f"Image trop lourde ({len(data) / 1024 / 1024:.1f} Mo) : {MAX_UPLOAD // (1024 * 1024)} Mo au plus.")
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as probe:
            kind = probe.format
            width, height = probe.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise LogoError("Ce fichier n'est pas une image lisible (PNG, WebP ou JPEG).") from exc
    if kind not in FORMATS:
        raise LogoError(f"Format {kind} non accepté : PNG (idéalement à fond transparent), WebP ou JPEG.")
    if width > MAX_SIDE or height > MAX_SIDE or width < 32 or height < 32:
        raise LogoError(f"Image de {width} × {height} pixels : entre 32 et {MAX_SIDE} pixels de côté.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image).convert("RGBA")
            alpha = image.getchannel("A")
            transparent = alpha.getextrema()[0] < 255
            box = alpha.getbbox()  # le dessin, sans les marges entièrement transparentes
            if box is None:
                raise LogoError("Cette image est entièrement transparente : il n'y a rien à afficher.")
            image = image.crop(box)
            image.thumbnail((SIDE, SIDE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, "PNG", optimize=True)  # sans métadonnées
    except LogoError:
        raise
    except (OSError, ValueError) as exc:
        raise LogoError("Image abîmée : impossible de la lire jusqu'au bout.") from exc
    return out.getvalue(), transparent


# ------------------------------------------------------------------ rangement
def _dir() -> Path:
    # Le mode démo garde ses propres logos : ils ne se mêlent jamais aux tiens
    return config.data_dir() / ("logos-demo" if config.is_demo() else "logos")


def _index_path() -> Path:
    return _dir() / "logos.json"


def _legacy(use: str) -> Path:
    demo = config.is_demo()
    if use == "club":
        return config.data_dir() / ("club-logo-demo.png" if demo else "club-logo.png")
    return config.data_dir() / ("sites-logos-demo" if demo else "sites-logos") / "partenaire.png"


def _empty() -> dict:
    return {"importes": [], "club": None, "partenaire": None, "accueil": True}


def _read() -> dict:
    path = _index_path()
    state = _empty()
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        if isinstance(saved, dict):
            items = saved.get("importes")
            state["importes"] = [{"id": str(x["id"]), "nom": str(x.get("nom") or "Logo"), "empreinte": str(x.get("empreinte") or "")}
                                 for x in (items if isinstance(items, list) else [])
                                 if isinstance(x, dict) and IMPORTED_ID.fullmatch(str(x.get("id") or ""))]
            for use in USES:
                state[use] = saved.get(use) if isinstance(saved.get(use), str) else None
            state["accueil"] = saved.get("accueil") is not False
    return state


def _write(state: dict) -> None:
    folder = _dir()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "logos.json.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(folder / "logos.json")


def _file(logo_id: str) -> Path:
    return _dir() / f"{logo_id}.png"


def _builtin(logo_id: str) -> dict | None:
    return next((b for b in BUILTIN if b["id"] == logo_id), None)


def _store(state: dict, nom: str, clean: bytes) -> dict:
    """Range un PNG déjà nettoyé ; le même fichier n'entre qu'une fois (on garde son premier nom)."""
    print_ = hashlib.sha1(clean).hexdigest()
    same = next((x for x in state["importes"] if x["empreinte"] == print_ and _file(x["id"]).exists()), None)
    if same:
        return same
    if len(state["importes"]) >= MAX_IMPORTED:
        raise LogoError(f"{MAX_IMPORTED} logos importés au plus : retires-en un de la liste d'abord.")
    taken = {x["id"] for x in state["importes"]}
    number = 1
    while f"u{number}" in taken or _file(f"u{number}").exists():
        number += 1
    entry = {"id": f"u{number}", "nom": nom, "empreinte": print_}
    folder = _dir()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f"{entry['id']}.tmp"
    tmp.write_bytes(clean)
    tmp.replace(_file(entry["id"]))
    state["importes"].append(entry)
    return entry


def _state() -> dict:
    """L'état de la logothèque ; y fait entrer les logos d'avant la 0.8.3b14."""
    with _LOCK:
        state = _read()
        moved = False
        for use in USES:
            legacy = _legacy(use)
            if not legacy.exists():
                continue
            try:
                entry = _store(state, LEGACY_NAMES[use], legacy.read_bytes())
            except (OSError, LogoError):
                continue
            if not state[use]:
                state[use] = entry["id"]
            legacy.unlink(missing_ok=True)
            moved = True
        if moved:
            _write(state)
        return state


def _clean_name(nom: Any) -> str:
    name = " ".join(str(nom or "").split())[:MAX_NAME]
    if not name:
        raise LogoError("Donne un nom à ce logo : c'est lui qui s'affiche dans la liste.")
    return name


def _known(state: dict, logo_id: str) -> bool:
    if _builtin(logo_id):
        return (BUILTIN_DIR / _builtin(logo_id)["fichier"]).exists()
    return any(x["id"] == logo_id for x in state["importes"]) and _file(logo_id).exists()


# ------------------------------------------------------------------ lecture
def path(logo_id: str) -> Path:
    """Le fichier d'un logo de la liste ; LogoError s'il n'existe pas."""
    builtin = _builtin(logo_id or "")
    if builtin:
        found = BUILTIN_DIR / builtin["fichier"]
    elif IMPORTED_ID.fullmatch(logo_id or ""):
        found = _file(logo_id)
    else:
        raise LogoError("Logo inconnu.")
    if not found.exists():
        raise LogoError("Logo introuvable.")
    return found


def version(logo_id: str) -> int | None:
    """Repère qui change avec le logo (pour l'adresse de l'image, que le navigateur ne garde pas en cache)."""
    try:
        found = path(logo_id)
    except LogoError:
        return None
    return zlib.crc32(f"{logo_id}:{found.stat().st_mtime_ns}".encode()) or 1


def listing() -> dict:
    """La liste du menu déroulant (intégrés, puis importés dans l'ordre d'arrivée), les choix et la case de l'Accueil."""
    state = _state()
    logos = [{"id": b["id"], "nom": b["nom"], "integre": True, "v": version(b["id"])} for b in BUILTIN
             if (BUILTIN_DIR / b["fichier"]).exists()]
    logos += [{"id": x["id"], "nom": x["nom"], "integre": False, "v": version(x["id"])} for x in state["importes"]
              if _file(x["id"]).exists()]
    return {"logos": logos, **{use: chosen(use, state) for use in USES}, "accueil": state["accueil"], "regles": RULES,
            "max": MAX_IMPORTED}


def chosen(use: str, state: dict | None = None) -> str | None:
    state = state or _state()
    logo_id = state.get(use)
    return logo_id if logo_id and _known(state, logo_id) else None


def chosen_path(use: str) -> Path | None:
    logo_id = chosen(use)
    return path(logo_id) if logo_id else None


def chosen_version(use: str) -> int | None:
    logo_id = chosen(use)
    return version(logo_id) if logo_id else None


def home() -> bool:
    """Le logo du club s'affiche-t-il aussi dans le bandeau de l'Accueil ?"""
    return _state()["accueil"]


# ------------------------------------------------------------------ changements
def add(nom: Any, data: bytes, *, use: str | None = None) -> dict:
    """Importe un logo nommé (et le choisit pour « club » ou « partenaire » si demandé)."""
    if use is not None and use not in USES:
        raise LogoError("Usage inconnu : « club » ou « partenaire ».")
    name = _clean_name(nom)
    clean, transparent = normalize(data)
    with _LOCK:
        state = _state()
        entry = _store(state, name, clean)
        if use:
            state[use] = entry["id"]
        _write(state)
    return {**listing(), "ajoute": entry["id"], "transparent": transparent}


def choose(use: str, logo_id: str | None) -> dict:
    """Choisit un logo de la liste pour un usage (None : aucun logo)."""
    if use not in USES:
        raise LogoError("Usage inconnu : « club » ou « partenaire ».")
    with _LOCK:
        state = _state()
        if logo_id and not _known(state, logo_id):
            raise LogoError("Ce logo n'est pas dans la liste.")
        state[use] = logo_id or None
        _write(state)
    return listing()


def set_home(show: bool) -> dict:
    with _LOCK:
        state = _state()
        state["accueil"] = bool(show)
        _write(state)
    return listing()


def remove(logo_id: str) -> dict:
    """Retire un logo importé de la liste (et des usages qui le prenaient) ; les logos intégrés restent."""
    if _builtin(logo_id or ""):
        raise LogoError("Ce logo est livré avec Foulée : il reste dans la liste.")
    with _LOCK:
        state = _state()
        if not any(x["id"] == logo_id for x in state["importes"]):
            raise LogoError("Ce logo n'est pas dans la liste.")
        state["importes"] = [x for x in state["importes"] if x["id"] != logo_id]
        for use in USES:
            if state[use] == logo_id:
                state[use] = None
        _write(state)
        _file(logo_id).unlink(missing_ok=True)
    return listing()


# ------------------------------------------------------------------ sauvegarde des réglages
def export_data() -> dict | None:
    """Les logos importés (en base64) et les choix, pour l'export des réglages ; None s'il n'y a rien à garder."""
    state = _state()
    items = [x for x in state["importes"] if _file(x["id"]).exists()]
    ref = {x["id"]: f"importe:{i}" for i, x in enumerate(items)}

    def keep(use: str) -> str | None:
        logo_id = chosen(use, state)
        return logo_id if logo_id and _builtin(logo_id) else ref.get(logo_id or "")

    if not items and not any(chosen(use, state) for use in USES) and state["accueil"]:
        return None
    return {"importes": [{"nom": x["nom"], "image": base64.b64encode(_file(x["id"]).read_bytes()).decode("ascii")}
                         for x in items],
            **{use: keep(use) for use in USES}, "accueil": state["accueil"]}


def import_data(data: Any) -> tuple[int, list[str]]:
    """Reprend les logos et les choix d'un export ; renvoie (nombre de logos repris, ce qui a été ignoré)."""
    if not isinstance(data, dict):
        return 0, ["logos (illisibles)"]
    ids: list[str | None] = []
    ignored: list[str] = []
    for item in data.get("importes") or []:
        try:
            raw = base64.b64decode(str((item or {}).get("image") or ""), validate=True)
            ids.append(add((item or {}).get("nom") or "Logo importé", raw)["ajoute"])
        except (binascii.Error, ValueError, AttributeError) as exc:
            ids.append(None)
            ignored.append(f"logo « {(item or {}).get('nom', '?') if isinstance(item, dict) else '?'} » ({exc})")
    for use in USES:
        ref = data.get(use)
        target = None
        if isinstance(ref, str) and ref.startswith("importe:") and ref[8:].isdigit() and int(ref[8:]) < len(ids):
            target = ids[int(ref[8:])]
        elif isinstance(ref, str) and _builtin(ref):
            target = ref
        if target:
            choose(use, target)
    if "accueil" in data:
        set_home(data.get("accueil") is not False)
    return sum(1 for x in ids if x), ignored
