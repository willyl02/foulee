"""Profils : plusieurs personnes sur la même installation de Foulée.

Chaque profil a ses données (base, fichiers FIT, photo), ses vues, ses réglages, sa clé
Garmin et sa synchro. L'utilisateur principal (celui qui a installé Foulée) garde les siens
à la racine du dossier des données, comme avant les profils ; lui seul gère les autres
profils et les réglages de l'installation (mises à jour, dossier, accès réseau…).

La liste des profils est rangée dans « utilisateurs.json », à la racine du dossier des données
(« utilisateurs-demo.json » en mode démo). Elle n'est écrite qu'au moment où elle sert : avec
un seul profil, sans code, Foulée marche exactement comme avant.

- Prénom, logo, photo : ceux des réglages de chaque profil (sa base) ; la liste ne garde le
  prénom qu'en secours.
- Code facultatif à 4 chiffres : seule son empreinte est gardée (PBKDF2). L'interface retient le
  profil choisi sur chaque appareil par un cookie signé ; changer de code l'invalide.
- Claude Desktop ne lit que les profils qui l'autorisent (case cochée d'office pour le
  principal, décochée pour les autres).
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from . import config

PRINCIPAL_ID = "p0"
COOKIE = "foulee_profil"
COOKIE_DAYS = 365
CODE_ITERATIONS = 200_000
CODE_DIGITS = re.compile(r"^\d{4}$")
MAX_PROFILES = 12
NAME_MAX = 30

_lock = threading.RLock()
_cache: dict[str, tuple[int, dict]] = {}


class ProfileError(ValueError):
    """Opération impossible sur un profil, expliquée en français."""


# ------------------------------------------------------------------ registre
def registry_path() -> Path:
    return config.root_dir() / ("utilisateurs-demo.json" if config.is_demo() else "utilisateurs.json")


def _principal_entry() -> dict:
    return {"id": PRINCIPAL_ID, "prenom": None, "principal": True, "dossier": "", "cree_le": None,
            "code": None, "claude": True}


def _default() -> dict:
    return {"version": 1, "secret": None, "profils": [_principal_entry()]}


def _valid(data: object) -> bool:
    if not isinstance(data, dict) or not isinstance(data.get("profils"), list) or not data["profils"]:
        return False
    ids = [p.get("id") for p in data["profils"] if isinstance(p, dict)]
    principals = [p for p in data["profils"] if isinstance(p, dict) and p.get("principal")]
    return len(ids) == len(data["profils"]) == len(set(ids)) and len(principals) == 1


def load() -> dict:
    """La liste des profils (copie : la modifier ne change rien tant qu'on ne l'enregistre pas)."""
    path = registry_path()
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return _default()
    cached = _cache.get(str(path))
    if cached and cached[0] == stamp:
        return copy.deepcopy(cached[1])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not _valid(data):
        # Fichier abîmé : on retombe sur le seul profil principal, sans rien effacer des autres dossiers
        return _default()
    _cache[str(path)] = (stamp, data)
    return copy.deepcopy(data)


def _save(data: dict) -> None:
    if not data.get("secret"):
        data["secret"] = secrets.token_hex(32)  # signe les cookies de choix de profil
    for entry in data["profils"]:
        if entry.get("principal") and not entry.get("cree_le"):
            entry["cree_le"] = _now()
    path = registry_path()
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)
    _cache.pop(str(path), None)


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def profiles() -> list[dict]:
    return load()["profils"]


def principal() -> dict:
    return next(p for p in profiles() if p.get("principal"))


def get(profile_id: str | None) -> dict | None:
    return next((p for p in profiles() if p["id"] == profile_id), None) if profile_id else None


def current() -> dict:
    """Profil courant (celui de la requête, de la synchro en cours…), le principal par défaut."""
    chosen = config.current_profile()
    return (get(chosen.get("id")) if chosen else None) or principal()


def is_principal(profile: dict | None = None) -> bool:
    return bool((profile or current()).get("principal"))


def protected() -> bool:
    """Faut-il choisir son profil sur un nouvel appareil ? (plusieurs profils, ou un code)

    En démo, seulement s'il y a un code : on découvre d'abord le profil principal.
    """
    entries = profiles()
    return (len(entries) > 1 and not config.is_demo()) or any(p.get("code") for p in entries)


def cookie_name() -> str:
    """La démo a son propre cookie : y changer de profil ne touche pas au choix fait hors démo."""
    return f"{COOKIE}_demo" if config.is_demo() else COOKIE


# -------------------------------------------------------------------- noms
def clean_name(text: object) -> str:
    name = " ".join(str(text or "").split())
    if not name:
        raise ProfileError("Indique un prénom.")
    if len(name) > NAME_MAX:
        raise ProfileError(f"Prénom trop long : {NAME_MAX} caractères au plus.")
    if any(ord(ch) < 32 for ch in name):
        raise ProfileError("Prénom illisible.")
    return name


def card(entry: dict, *, current_id: str | None = None, details: bool = False) -> dict:
    """Ce que l'interface montre d'un profil : prénom, logo ou photo, code, accès de Claude…"""
    from . import db, profile, sync, vault

    with config.using_profile(entry):
        photo = profile.info()
        with db.session(readonly=True) as conn:
            settings = db.get_settings(conn)
            name = profile.first_name(conn, settings) or entry.get("prenom") or ("Moi" if entry.get("principal") else "Sans nom")
            extra: dict = {}
            if details:
                counts = db.table_counts(conn)
                last = sync.last_sync_info(conn)
                extra = {"seances": counts.get("activities", 0), "valeurs": counts.get("daily", 0),
                         "derniere_synchro": last.get("derniere_reussie"), "cle": vault.has_key(),
                         "cle_refusee": bool(sync.key_refused(conn)), "dossier": str(config.data_dir()),
                         "cree_le": entry.get("cree_le")}
        logo = (settings.get("profil") or {}).get("logo") or "foulee"
    return {"id": entry["id"], "prenom": name, "principal": bool(entry.get("principal")),
            "code": bool(entry.get("code")), "claude": claude_allowed(entry), "logo": logo,
            "photo": photo["photo"], "photo_maj": photo["photo_maj"], "courant": entry["id"] == current_id, **extra}


def cards(current_id: str | None = None, *, details: bool = False) -> list[dict]:
    return [card(p, current_id=current_id, details=details) for p in profiles()]


# ---------------------------------------------------------------- cookies
def _code_version(entry: dict) -> str:
    return (entry.get("code") or {}).get("sel") or "-"


def _sign(secret: str, payload: str) -> str:
    return hmac.new(bytes.fromhex(secret), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_cookie(entry: dict, now: float | None = None) -> str:
    """Cookie « ce navigateur utilise tel profil », signé, invalidé si le code du profil change."""
    with _lock:
        data = load()
        if not data.get("secret"):
            _save(data)
            data = load()
    expiry = int((now or time.time()) + COOKIE_DAYS * 86400)
    payload = f"{entry['id']}.{expiry}"
    return f"{payload}.{_sign(data['secret'], f'{payload}.{_code_version(entry)}')}"


def from_cookie(value: str | None, now: float | None = None) -> dict | None:
    data = load()
    if not value or not data.get("secret") or value.count(".") != 2:
        return None
    profile_id, expiry, signature = value.split(".")
    entry = next((p for p in data["profils"] if p["id"] == profile_id), None)
    if not entry or not expiry.isdigit() or int(expiry) < (now or time.time()):
        return None
    expected = _sign(data["secret"], f"{profile_id}.{expiry}.{_code_version(entry)}")
    return entry if hmac.compare_digest(expected, signature) else None


def resolve(cookie: str | None) -> tuple[dict | None, bool]:
    """(profil de ce navigateur, faut-il le choisir ?) d'après le cookie de la requête."""
    entry = from_cookie(cookie)
    if entry:
        return entry, False
    if not protected():
        return principal(), False
    return None, True


# ------------------------------------------------------------------- codes
def _digest(code: str, salt: bytes, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), salt, iterations).hex()


def _new_code(code: str) -> dict:
    if not CODE_DIGITS.match(str(code or "")):
        raise ProfileError("Le code fait 4 chiffres.")
    salt = secrets.token_bytes(16)
    return {"sel": salt.hex(), "empreinte": _digest(code, salt, CODE_ITERATIONS), "iterations": CODE_ITERATIONS}


def check_code(entry: dict, code: str | None) -> bool:
    stored = entry.get("code")
    if not stored:
        return True
    if not code or not CODE_DIGITS.match(str(code)):
        return False
    actual = _digest(str(code), bytes.fromhex(stored["sel"]), int(stored["iterations"]))
    return hmac.compare_digest(stored["empreinte"], actual)


def _update(profile_id: str, change) -> dict:
    with _lock:
        data = load()
        entry = next((p for p in data["profils"] if p["id"] == profile_id), None)
        if not entry:
            raise ProfileError("Profil introuvable.")
        change(entry)
        _save(data)
        return entry


def set_code(profile_id: str, code: str | None) -> dict:
    """Pose, change (code) ou retire (None) le code d'un profil."""
    new = _new_code(code) if code is not None else None
    return _update(profile_id, lambda entry: entry.__setitem__("code", new))


def claude_allowed(entry: dict) -> bool:
    return bool(entry.get("claude", entry.get("principal")))


def set_claude(profile_id: str, allowed: bool) -> dict:
    return _update(profile_id, lambda entry: entry.__setitem__("claude", bool(allowed)))


# ----------------------------------------------------------- gestion (principal)
def create(name: str, code: str | None = None) -> dict:
    """Nouveau profil : son dossier, sa base (prénom déjà réglé), et son code s'il en a un."""
    from . import db

    name = clean_name(name)
    new_code = _new_code(code) if code else None
    with _lock:
        data = load()
        if len(data["profils"]) >= MAX_PROFILES:
            raise ProfileError(f"{MAX_PROFILES} profils au plus.")
        taken = {c["prenom"].casefold() for c in cards()}
        if name.casefold() in taken:
            raise ProfileError(f"Il y a déjà un profil « {name} ».")
        principal_entry = next(p for p in data["profils"] if p.get("principal"))
        if not principal_entry.get("prenom"):
            principal_entry["prenom"] = card(principal_entry)["prenom"]  # secours, si sa base disparaissait
        ids = {p["id"] for p in data["profils"]}
        profile_id = next(i for i in (f"p{secrets.token_hex(3)}" for _ in range(100)) if i not in ids)
        entry = {"id": profile_id, "prenom": name, "principal": False,
                 "dossier": f"profils{'-demo' if config.is_demo() else ''}/{profile_id}", "cree_le": _now(),
                 "code": new_code, "claude": False}
        data["profils"].append(entry)
        _save(data)
    with config.using_profile(entry), db.session() as conn:
        db.set_setting(conn, "profil", {"prenom": name, "logo": "foulee"})
    return entry


def rename(profile_id: str, name: str) -> dict:
    from . import db

    name = clean_name(name)
    if any(c["prenom"].casefold() == name.casefold() and c["id"] != profile_id for c in cards()):
        raise ProfileError(f"Il y a déjà un profil « {name} ».")
    entry = _update(profile_id, lambda e: e.__setitem__("prenom", name))
    with config.using_profile(entry), db.session() as conn:
        current_profile = db.get_settings(conn).get("profil") or {}
        db.set_setting(conn, "profil", {**current_profile, "prenom": name})
    return entry


def delete(profile_id: str) -> dict:
    """Supprime un profil : sa base, ses fichiers FIT, sa photo, sa clé Garmin. Ses données restent chez Garmin."""
    from . import sync, vault

    entry = get(profile_id)
    if not entry:
        raise ProfileError("Profil introuvable.")
    if entry.get("principal"):
        raise ProfileError("L'utilisateur principal ne peut pas être supprimé.")
    with config.using_profile(entry):
        if sync.is_running():
            raise ProfileError("Une synchro de ce profil est en cours : réessaie quand elle sera terminée.")
        name = card(entry)["prenom"]
        vault.delete_key()  # sa clé Garmin et son jeton temporaire
        folder = config.data_dir()
    with _lock:
        data = load()
        data["profils"] = [p for p in data["profils"] if p["id"] != profile_id]
        _save(data)
    root = config.root_dir().resolve()
    target = folder.resolve()
    if target != root and root in target.parents:  # jamais la racine, jamais en dehors du dossier des données
        shutil.rmtree(target, ignore_errors=True)
    return {"id": profile_id, "prenom": name}


# --------------------------------------------------------------- Claude Desktop
def claude_profiles() -> list[dict]:
    return [p for p in profiles() if claude_allowed(p)]


def check_claude_access() -> None:
    """Appelé à chaque lecture de la base par Claude Desktop : le profil choisi l'autorise-t-il ?"""
    chosen = config.current_profile()
    entry = get(chosen["id"]) if chosen else principal()
    if not entry or not claude_allowed(entry):
        allowed = claude_profiles()
        names = ", ".join(card(p)["prenom"] for p in allowed)
        raise PermissionError(
            "Ce profil n'autorise pas Claude à lire ses données (case à cocher dans Foulée : Réglages → Profil et logo)."
            + (f" Profils accessibles : {names} (outil changer_utilisateur)." if names else ""))
