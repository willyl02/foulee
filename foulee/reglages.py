"""Réglages : contrôles avant enregistrement, et export / import pour aligner deux installations.

Chaque installation (le PC, le serveur) a sa propre base, donc ses propres réglages. Un export
les met dans un fichier ; l'import les reprend ailleurs. La clé Garmin, le mot de passe du
réseau local et le jeton GitHub n'y figurent jamais : ils ne sont pas rangés dans les réglages.
"""

from __future__ import annotations

import base64
import binascii
import copy
import sqlite3
from typing import Any

from . import __version__, analysis, club, db, profile, schedule, views, zones

# Réglages dont dépendent TRIMP, zones et charge : les changer relance le recalcul des séances
DERIVED = {"vma_kmh", "fc_max", "fc_repos", "sexe", "zones_allure_pct_vma", "charge_source", "zones_fc",
           "zones_allure"}
NOT_EXPORTED = {"historique_depuis", "canal_maj"}  # propres à chaque installation
EXPORT_FORMAT = 1


class SettingsError(ValueError):
    pass


def _number(value: Any, low: float, high: float, label: str, *, optional: bool = False) -> float | None:
    if value in (None, "") and optional:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise SettingsError(f"{label} : « {value} » n'est pas un nombre.") from None
    if not low <= number <= high:
        raise SettingsError(f"{label} : entre {low:g} et {high:g}.")
    return int(number) if number.is_integer() else number


def clean(key: str, value: Any) -> Any:
    """Contrôle une valeur de réglage ; lève SettingsError avec un message compréhensible."""
    try:
        if key == "horaires":
            return schedule.clean(value)
        if key == "zones_fc":
            return zones.clean_hr(value)
        if key == "zones_allure":
            return zones.clean_pace(value)
    except ValueError as exc:
        raise SettingsError(str(exc)) from None
    if key == "profil":
        return profile.clean_profile(value)
    if key == "club":
        try:
            return club.clean(value)
        except club.ClubError as exc:
            raise SettingsError(str(exc)) from None
    if key == "vma_kmh":
        return _number(value, 6, 30, "VMA")
    if key == "fc_max":
        return _number(value, 120, 230, "FC max", optional=True)
    if key == "fc_repos":
        return _number(value, 30, 100, "FC de repos", optional=True)
    if key == "fractions_seuil_pct_vma":
        return _number(value, 50, 130, "Seuil des fractions rapides")
    if key == "zones_allure_pct_vma":
        try:
            return zones.clean_pace({"methode": "pct_vma", "pct": value})["pct"]
        except ValueError as exc:
            raise SettingsError(str(exc)) from None
    if key == "vameval":
        if value in (None, ""):
            return None
        test = analysis.vameval(value)
        if not test:
            raise SettingsError("Temps du test VAMEVAL illisible : de 2:00 à 59:59 (minutes:secondes).")
        return test["temps"]
    if key == "synchro_auto":
        from . import sync

        if not isinstance(value, dict):
            raise SettingsError("Synchro automatique : un délai par source, en minutes.")
        cleaned = {}
        for name, minutes in value.items():
            if name not in sync.SOURCES:
                raise SettingsError(f"Synchro automatique : source inconnue « {name} ».")
            label = f"Synchro automatique {sync.LABELS.get(name, name)}"
            cleaned[name] = int(_number(minutes, sync.MIN_INTERVAL, sync.MAX_INTERVAL, f"{label} (minutes)"))
        return cleaned
    if key == "canal_maj":
        from . import updates

        if value not in updates.CHANNELS:
            raise SettingsError("Canal inconnu : « stable » ou « beta ».")
    if key == "sexe" and value not in ("H", "F"):
        raise SettingsError("Formule du TRIMP : « H » ou « F ».")
    if key == "charge_source" and value not in ("garmin", "trimp"):
        raise SettingsError("Charge d'une séance : « garmin » ou « trimp ».")
    if key == "carte_fond" and value not in ("osm", "ign", "aucun"):
        raise SettingsError("Fond de carte : « osm », « ign » ou « aucun ».")
    return value


def apply(conn: sqlite3.Connection, changes: dict, *, merge: bool = False) -> tuple[dict, bool]:
    """Enregistre des réglages contrôlés. merge=True complète un réglage composé (dict) au lieu de le remplacer.
    Renvoie (réglages, recalcul nécessaire)."""
    allowed = set(db.DEFAULT_SETTINGS)
    unknown = [k for k in changes if k not in allowed]
    if unknown:
        raise SettingsError(f"Réglage(s) inconnu(s) : {', '.join(unknown)}.")
    current = db.get_settings(conn)
    cleaned = {}
    for key, value in changes.items():
        if merge and isinstance(current.get(key), dict) and isinstance(value, dict):
            merged = copy.deepcopy(current[key])
            merged.update(value)
            value = merged
        cleaned[key] = clean(key, value)
    for key, value in cleaned.items():
        db.set_setting(conn, key, value)
    if "club" in cleaned:  # la vue « Mon club » suit la case « Je fais partie d'un club »
        views.sync_club_view(conn, bool((cleaned["club"] or {}).get("actif")))
    conn.commit()
    return db.get_settings(conn), bool(DERIVED & set(cleaned))


# ------------------------------------------------------------- export / import
def export(conn: sqlite3.Connection, *, with_views: bool = True, with_photo: bool = True,
           with_logo: bool = True) -> dict:
    settings = db.get_settings(conn)
    data: dict[str, Any] = {
        "foulee_reglages": EXPORT_FORMAT, "version": __version__, "exporte_le": db.now_iso(),
        "reglages": {k: v for k, v in settings.items() if k not in NOT_EXPORTED and k in db.DEFAULT_SETTINGS},
    }
    if with_views:
        data["vues"] = [{k: v[k] for k in ("id", "name", "icon", "position", "spec")} for v in views.list_views(conn)]
    if with_photo and profile.photo_path().exists():
        data["photo"] = base64.b64encode(profile.photo_path().read_bytes()).decode("ascii")
    if with_logo and club.logo_path().exists():
        data["logo_club"] = base64.b64encode(club.logo_path().read_bytes()).decode("ascii")
    return data


def import_(conn: sqlite3.Connection, data: Any, *, parts: set[str] | None = None) -> dict:
    """Reprend un export. parts : {"reglages", "vues", "photo", "logo"} (tout par défaut).
    Les vues de même identifiant sont remplacées, les autres ajoutées ; aucune vue n'est supprimée."""
    if not isinstance(data, dict) or data.get("foulee_reglages") != EXPORT_FORMAT:
        raise SettingsError("Ce fichier n'est pas un export de réglages Foulée.")
    parts = parts or {"reglages", "vues", "photo", "logo"}
    report: dict[str, Any] = {"reglages": 0, "vues": 0, "photo": False, "logo": False, "ignores": [], "recalcul": False}
    if "reglages" in parts and isinstance(data.get("reglages"), dict):
        changes = {}
        for key, value in data["reglages"].items():
            if key in NOT_EXPORTED or key not in db.DEFAULT_SETTINGS:
                report["ignores"].append(key)
                continue
            try:
                changes[key] = clean(key, value)
            except SettingsError as exc:
                report["ignores"].append(f"{key} ({exc})")
        if changes:
            _, report["recalcul"] = apply(conn, changes)
            report["reglages"] = len(changes)
    if "vues" in parts and isinstance(data.get("vues"), list):
        for view in data["vues"]:
            if isinstance(view, dict) and isinstance(view.get("spec"), dict):
                views.save_view(conn, str(view.get("id") or "") or None, str(view.get("name") or "Vue"),
                                view["spec"], view.get("icon"), view.get("position"))
                report["vues"] += 1
    if "photo" in parts and data.get("photo"):
        try:
            profile.save_photo(base64.b64decode(data["photo"], validate=True))
            report["photo"] = True
        except (binascii.Error, ValueError) as exc:
            report["ignores"].append(f"photo ({exc})")
    if "logo" in parts and data.get("logo_club"):
        try:
            club.save_logo(base64.b64decode(data["logo_club"], validate=True))
            report["logo"] = True
        except (binascii.Error, ValueError) as exc:
            report["ignores"].append(f"logo du club ({exc})")
    return report

