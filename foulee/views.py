"""Vues et tuiles : le catalogue des types de tuiles et les vues par défaut.

Une vue = une grille de tuiles. Une tuile = un type + des réglages + une taille.
Le catalogue ci-dessous décrit chaque type et ses réglages : l'interface en
déduit le formulaire d'édition, et Claude s'en sert pour créer des vues valides.
"""

from __future__ import annotations

import copy
import json
import re
import sqlite3
import uuid
from typing import Any

from . import db, metrics

PERIODES = ["herite", "7", "14", "30", "60", "90", "120", "180", "365", "730"]
SPORT_OPTIONS = ["tous", "pied"] + list(metrics.SPORTS)

TILE_TYPES: list[dict[str, Any]] = [
    {
        "type": "kpi", "label": "Chiffre clé", "icone": "gauge",
        "description": "Dernière valeur d'une métrique, comparée à ta moyenne récente.",
        "taille": {"w": 3, "h": 1},
        "params": [
            {"key": "metrique", "label": "Métrique", "kind": "metric", "default": "sleep_s"},
            {"key": "fenetre", "label": "Fenêtre", "kind": "select", "options": ["auto", "jour", "semaine", "mois"],
             "default": "auto"},
            {"key": "reference_jours", "label": "Comparer aux N derniers jours", "kind": "number", "default": 30},
        ],
    },
    {
        "type": "serie", "label": "Courbe ou barres", "icone": "chart",
        "description": "Une ou plusieurs métriques dans le temps, par jour, semaine ou mois.",
        "taille": {"w": 6, "h": 2},
        "params": [
            {"key": "metriques", "label": "Métriques", "kind": "metrics", "default": ["sleep_s"]},
            {"key": "style", "label": "Style", "kind": "select", "options": ["ligne", "barres", "aire"], "default": "ligne"},
            {"key": "agregation", "label": "Regrouper par", "kind": "select", "options": ["jour", "semaine", "mois"],
             "default": "jour"},
            {"key": "fonction", "label": "Calcul du regroupement", "kind": "select",
             "options": ["auto", "avg", "sum", "max", "min"], "default": "auto"},
            {"key": "lissage", "label": "Moyenne glissante (périodes)", "kind": "number", "default": 0},
            {"key": "sport", "label": "Sport (séances)", "kind": "sport", "default": "tous"},
            {"key": "disposition", "label": "Plusieurs métriques", "kind": "select",
             "options": ["auto", "superposer", "empiler"], "default": "auto"},
            {"key": "bandes_postes", "label": "Griser les semaines du matin", "kind": "bool", "default": False},
            {"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "herite"},
        ],
    },
    {
        "type": "charge", "label": "Forme & fatigue", "icone": "trend",
        "description": "Charge chronique (42 j), aiguë (7 j) et fraîcheur.",
        "taille": {"w": 12, "h": 2},
        "params": [
            {"key": "afficher_ratio", "label": "Afficher le ratio aiguë / chronique", "kind": "bool", "default": False},
            {"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "herite"},
        ],
    },
    {
        "type": "zones", "label": "Zones FC ou allure", "icone": "layers",
        "description": "Temps passé dans chaque zone, par semaine, par mois ou au total.",
        "taille": {"w": 6, "h": 2},
        "params": [
            {"key": "zones", "label": "Zones", "kind": "select", "options": ["fc", "allure"], "default": "fc"},
            {"key": "groupe", "label": "Regrouper par", "kind": "select", "options": ["semaine", "mois", "total"],
             "default": "semaine"},
            {"key": "sport", "label": "Sport", "kind": "sport", "default": "tous"},
            {"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "herite"},
        ],
    },
    {
        "type": "calendrier", "label": "Calendrier thermique", "icone": "calendar",
        "description": "Une case par jour, colorée selon la valeur.",
        "taille": {"w": 6, "h": 2},
        "params": [
            {"key": "metrique", "label": "Métrique", "kind": "metric", "default": "sleep_s"},
            {"key": "mois", "label": "Nombre de mois", "kind": "select", "options": ["3", "6", "12"], "default": "6"},
        ],
    },
    {
        "type": "nuage", "label": "Nuage de points", "icone": "scatter",
        "description": "Croise deux métriques jour par jour (avec un décalage possible).",
        "taille": {"w": 6, "h": 2},
        "params": [
            {"key": "x", "label": "Axe horizontal", "kind": "metric", "default": "sleep_s"},
            {"key": "y", "label": "Axe vertical", "kind": "metric", "default": "hrv_night"},
            {"key": "decalage", "label": "Y mesuré N jours après X", "kind": "select", "options": ["0", "1", "2"],
             "default": "0"},
            {"key": "couleur_postes", "label": "Colorer matin / soir", "kind": "bool", "default": True},
            {"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "herite"},
        ],
    },
    {
        "type": "postes", "label": "Matin vs soir", "icone": "shift",
        "description": "Compare tes métriques entre semaines du matin et semaines du soir.",
        "taille": {"w": 12, "h": 2},
        "params": [
            {"key": "metriques", "label": "Métriques", "kind": "metrics",
             "default": ["sleep_s", "sleep_end_h", "hrv_night", "resting_hr", "bb_wake"]},
            {"key": "jours_ouvres", "label": "Jours ouvrés seulement", "kind": "bool", "default": True},
            {"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "180"},
        ],
    },
    {
        "type": "activites", "label": "Liste des séances", "icone": "list",
        "description": "Tes séances, filtrables ; un clic ouvre le détail.",
        "taille": {"w": 12, "h": 3},
        "params": [
            {"key": "sport", "label": "Sport", "kind": "sport", "default": "tous"},
            {"key": "recherche", "label": "Recherche dans le nom", "kind": "text", "default": ""},
            {"key": "limite", "label": "Nombre de séances", "kind": "number", "default": 20},
            {"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "herite"},
        ],
    },
    {
        "type": "derniere_seance", "label": "Dernière séance", "icone": "run",
        "description": "Carte résumé de ta dernière séance.",
        "taille": {"w": 6, "h": 2},
        "params": [{"key": "sport", "label": "Sport", "kind": "sport", "default": "tous"}],
    },
    {
        "type": "seance_resume", "label": "Séance : résumé", "icone": "info",
        "description": "Chiffres clés de la séance choisie en haut de la vue.",
        "taille": {"w": 12, "h": 1}, "params": [],
    },
    {
        "type": "seance_carte", "label": "Séance : carte", "icone": "map",
        "description": "Tracé GPS de la séance choisie.",
        "taille": {"w": 6, "h": 3}, "params": [],
    },
    {
        "type": "seance_courbes", "label": "Séance : courbes", "icone": "wave",
        "description": "FC, allure, altitude, cadence… synchronisées.",
        "taille": {"w": 6, "h": 3},
        "params": [
            {"key": "courbes", "label": "Courbes", "kind": "multi",
             "options": ["hr", "spd", "alt", "cad", "pwr", "temp"], "default": ["hr", "spd", "alt"]},
            {"key": "axe", "label": "Axe horizontal", "kind": "select", "options": ["temps", "distance"],
             "default": "temps"},
        ],
    },
    {
        "type": "seance_tours", "label": "Séance : tours", "icone": "table",
        "description": "Tours enregistrés par la montre, ou découpage au kilomètre.",
        "taille": {"w": 12, "h": 2},
        "params": [
            {"key": "mode", "label": "Afficher", "kind": "select", "options": ["tours", "kilometres"], "default": "tours"},
        ],
    },
    {
        "type": "objectif", "label": "Objectif course", "icone": "flag",
        "description": "Compte à rebours et allure cible de ton objectif (voir Réglages).",
        "taille": {"w": 4, "h": 2}, "params": [],
    },
    {
        "type": "fractions", "label": "Fractions rapides", "icone": "bolt",
        "description": "Allure moyenne de tes tours rapides, séance par séance, face à l'allure cible.",
        "taille": {"w": 8, "h": 2},
        "params": [{"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "120"}],
    },
    {
        "type": "note", "label": "Note", "icone": "note",
        "description": "Un texte libre (rappel, consigne, idée).",
        "taille": {"w": 4, "h": 1},
        "params": [{"key": "texte", "label": "Texte", "kind": "textarea", "default": ""}],
    },
]
TILE_INDEX = {t["type"]: t for t in TILE_TYPES}
WIDTHS = (3, 4, 6, 8, 12)
ICONS = ["sun", "activity", "map", "moon", "flag", "heart", "chart", "calendar", "star", "bolt", "layers", "run"]


def _tile(kind: str, w: int | None = None, h: int | None = None, titre: str | None = None, **params: Any) -> dict:
    spec = TILE_INDEX[kind]
    tile = {
        "id": uuid.uuid4().hex[:8], "type": kind,
        "w": w or spec["taille"]["w"], "h": h or spec["taille"]["h"],
        "params": {p["key"]: copy.deepcopy(p["default"]) for p in spec["params"]},
    }
    tile["params"].update(params)
    if titre:
        tile["titre"] = titre
    return tile


def default_views() -> list[dict]:
    pied = "pied"
    return [
        {
            "id": "aujourdhui", "name": "Aujourd'hui", "icon": "sun",
            "spec": {"tuiles": [
                _tile("kpi", metrique="sleep_s"),
                _tile("kpi", metrique="hrv_night"),
                _tile("kpi", metrique="resting_hr"),
                _tile("kpi", metrique="bb_wake"),
                _tile("kpi", metrique="sleep_score"),
                _tile("kpi", metrique="stress_avg"),
                _tile("kpi", metrique="act.distance_km", fenetre="semaine", reference_jours=28,
                      titre="Kilomètres sur 7 jours"),
                _tile("kpi", metrique="tsb", titre="Fraîcheur"),
                _tile("derniere_seance", 6, 2),
                _tile("serie", 6, 2, titre="Récupération sur 30 jours", metriques=["hrv_night", "resting_hr"],
                      disposition="empiler", periode="30"),
                _tile("serie", 12, 2, titre="Sommeil sur 60 jours", metriques=["sleep_s"], style="barres",
                      bandes_postes=True, periode="60"),
            ]},
        },
        {
            "id": "entrainement", "name": "Entraînement", "icon": "activity",
            "spec": {"tuiles": [
                _tile("serie", 8, 2, titre="Kilomètres par semaine (course + trail)", metriques=["act.distance_km"],
                      style="barres", agregation="semaine", sport=pied, periode="180"),
                _tile("kpi", 4, 1, titre="Kilomètres sur 7 jours", metrique="act.distance_km", fenetre="semaine",
                      reference_jours=28),
                _tile("kpi", 4, 1, titre="Charge sur 7 jours", metrique="act.load", fenetre="semaine",
                      reference_jours=28),
                _tile("charge", 12, 3, periode="180", afficher_ratio=True),
                _tile("zones", 6, 2, titre="Temps par zone FC", zones="fc", groupe="semaine", periode="90"),
                _tile("zones", 6, 2, titre="Temps par zone d'allure (VMA)", zones="allure", groupe="semaine",
                      sport=pied, periode="90"),
                _tile("activites", 12, 3, limite=25),
            ]},
        },
        {
            "id": "seance", "name": "Séance", "icon": "map",
            "spec": {"tuiles": [
                _tile("seance_resume", 12, 1),
                _tile("seance_carte", 6, 3),
                _tile("seance_courbes", 6, 3),
                _tile("seance_tours", 12, 2),
            ]},
        },
        {
            "id": "recup-postes", "name": "Récup & postes", "icon": "moon",
            "spec": {"tuiles": [
                _tile("postes", 12, 3, metriques=["sleep_s", "sleep_end_h", "sleep_score", "hrv_night",
                                                  "resting_hr", "bb_wake", "stress_avg"], periode="180"),
                _tile("serie", 6, 2, titre="Sommeil (moyenne 7 j)", metriques=["sleep_s"], lissage=7,
                      bandes_postes=True, periode="90"),
                _tile("serie", 6, 2, titre="VFC et FC de repos", metriques=["hrv_night", "resting_hr"],
                      disposition="empiler", bandes_postes=True, periode="90"),
                _tile("nuage", 6, 2, titre="Sommeil → VFC de la nuit", x="sleep_s", y="hrv_night", periode="180"),
                _tile("calendrier", 6, 2, titre="Calendrier du sommeil", metrique="sleep_s", mois="6"),
            ]},
        },
        {
            "id": "cap-semi", "name": "Cap semi de Paris", "icon": "flag",
            "spec": {"tuiles": [
                _tile("objectif", 4, 2),
                _tile("fractions", 8, 2, periode="120"),
                _tile("serie", 6, 2, titre="Kilomètres par semaine", metriques=["act.distance_km"], style="barres",
                      agregation="semaine", sport=pied, periode="120"),
                _tile("charge", 6, 2, periode="120"),
                _tile("zones", 6, 2, titre="Zones d'allure par semaine", zones="allure", groupe="semaine",
                      sport=pied, periode="120"),
                _tile("serie", 6, 2, titre="VO2max estimée par Garmin", metriques=["vo2max"], periode="365"),
            ]},
        },
    ]


# ------------------------------------------------------------------ validation
def _clean_params(kind: str, params: dict | None) -> dict:
    spec = TILE_INDEX[kind]
    clean = {}
    params = params or {}
    for p in spec["params"]:
        value = params.get(p["key"], copy.deepcopy(p["default"]))
        if p["kind"] == "metric":
            value = value if value in metrics.CATALOG else p["default"]
        elif p["kind"] == "metrics":
            value = [v for v in (value if isinstance(value, list) else [value]) if v in metrics.CATALOG] or p["default"]
        elif p["kind"] in ("select", "periode", "sport"):
            options = p.get("options") or (PERIODES if p["kind"] == "periode" else SPORT_OPTIONS)
            value = str(value) if str(value) in options else p["default"]
        elif p["kind"] == "multi":
            value = [v for v in (value if isinstance(value, list) else [value]) if v in p["options"]] or p["default"]
        elif p["kind"] == "number":
            try:
                value = float(value)
                value = int(value) if value.is_integer() else value
            except (TypeError, ValueError):
                value = p["default"]
        elif p["kind"] == "bool":
            value = bool(value)
        else:
            value = str(value or "")[:4000]
        clean[p["key"]] = value
    return clean


def clean_spec(spec: dict) -> dict:
    tiles = []
    for tile in (spec or {}).get("tuiles", []):
        kind = tile.get("type")
        if kind not in TILE_INDEX:
            continue
        w = int(tile.get("w") or TILE_INDEX[kind]["taille"]["w"])
        w = min(WIDTHS, key=lambda candidate: abs(candidate - w))
        h = max(1, min(3, int(tile.get("h") or TILE_INDEX[kind]["taille"]["h"])))
        clean = {"id": str(tile.get("id") or uuid.uuid4().hex[:8])[:16], "type": kind, "w": w, "h": h,
                 "params": _clean_params(kind, tile.get("params"))}
        if tile.get("titre"):
            clean["titre"] = str(tile["titre"])[:120]
        tiles.append(clean)
    return {"tuiles": tiles}


def slugify(text: str) -> str:
    table = str.maketrans("àâäéèêëîïôöùûüç'’ ", "aaaeeeeiioouuuc---")
    slug = re.sub(r"[^a-z0-9-]+", "", text.lower().translate(table)).strip("-")
    return slug[:40] or uuid.uuid4().hex[:8]


# ------------------------------------------------------------------- stockage
def ensure_default_views(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) AS n FROM views").fetchone()["n"]:
        return
    reset_default_views(conn)


def reset_default_views(conn: sqlite3.Connection) -> None:
    for position, view in enumerate(default_views()):
        conn.execute(
            "INSERT INTO views(id, name, icon, position, spec, builtin, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name, icon = excluded.icon, spec = excluded.spec, "
            "builtin = 1, updated_at = excluded.updated_at",
            (view["id"], view["name"], view["icon"], position, json.dumps(view["spec"], ensure_ascii=False),
             db.now_iso()),
        )
    conn.commit()


def list_views(conn: sqlite3.Connection) -> list[dict]:
    return [
        {"id": r["id"], "name": r["name"], "icon": r["icon"], "position": r["position"],
         "builtin": bool(r["builtin"]), "spec": json.loads(r["spec"])}
        for r in conn.execute("SELECT * FROM views ORDER BY position, name")
    ]


def save_view(conn: sqlite3.Connection, view_id: str | None, name: str, spec: dict, icon: str | None = None,
              position: int | None = None) -> dict:
    view_id = view_id or slugify(name)
    clean = clean_spec(spec)
    existing = conn.execute("SELECT position, icon FROM views WHERE id = ?", (view_id,)).fetchone()
    if position is None:
        position = existing["position"] if existing else (
            conn.execute("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM views").fetchone()["p"])
    icon = icon if icon in ICONS else (existing["icon"] if existing else "chart")
    conn.execute(
        "INSERT INTO views(id, name, icon, position, spec, builtin, updated_at) VALUES (?, ?, ?, ?, ?, 0, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name, icon = excluded.icon, position = excluded.position, "
        "spec = excluded.spec, updated_at = excluded.updated_at",
        (view_id, name.strip()[:60] or "Vue", icon, position, json.dumps(clean, ensure_ascii=False), db.now_iso()),
    )
    conn.commit()
    return {"id": view_id, "name": name, "icon": icon, "position": position, "spec": clean}


def delete_view(conn: sqlite3.Connection, view_id: str) -> bool:
    deleted = conn.execute("DELETE FROM views WHERE id = ?", (view_id,)).rowcount
    conn.commit()
    return bool(deleted)


def reorder_views(conn: sqlite3.Connection, ids: list[str]) -> None:
    for position, view_id in enumerate(ids):
        conn.execute("UPDATE views SET position = ? WHERE id = ?", (position, view_id))
    conn.commit()
