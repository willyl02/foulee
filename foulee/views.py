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

TILE_CATEGORIES = ["Accueil", "Chiffres et courbes", "Entraînement", "Séances", "Journée en détail", "Travail",
                   "Divers"]

TILE_TYPES: list[dict[str, Any]] = [
    {
        "type": "profil", "label": "En-tête : bonjour", "icone": "user", "categorie": "Accueil",
        "description": "Ta photo, la date, ton poste du jour, ton objectif et la dernière synchro.",
        "taille": {"w": 12, "h": 1}, "params": [],
    },
    {
        "type": "forme", "label": "Forme du jour", "icone": "heart", "categorie": "Accueil",
        "description": "FC de repos, VFC, sommeil, Body Battery, fraîcheur : chacun face à tes habitudes.",
        "taille": {"w": 8, "h": 2}, "params": [],
    },
    {
        "type": "allures", "label": "Allures selon ta VMA", "icone": "run", "categorie": "Accueil",
        "description": "Le tableau du club : allures et vitesses de 55 à 120 % de VMA, temps de passage sur "
                       "piste, test VAMEVAL.",
        "taille": {"w": 12, "h": 3},
        "params": [
            {"key": "onglet", "label": "Onglet affiché d'abord", "kind": "select",
             "options": ["tableau", "vameval"], "default": "tableau"},
            {"key": "comparer", "label": "Comparer avec une autre VMA (km/h, 0 = non)", "kind": "number",
             "default": 0},
        ],
    },
    {
        "type": "club", "label": "Mon club", "icone": "club", "categorie": "Accueil",
        "description": "Ton club FFA : coordonnées, site, ta licence, et son classement sur athle.fr en un clic.",
        "taille": {"w": 12, "h": 3}, "params": [],
    },
    {
        "type": "withings", "label": "Withings : dernières mesures", "icone": "scale", "categorie": "Accueil",
        "description": "Ta dernière pesée et ta composition corporelle, ta dernière tension, ta dernière nuit et ta "
                       "journée, d'après tes appareils Withings, face à tes habitudes.",
        "taille": {"w": 12, "h": 3}, "params": [],
    },
    {
        "type": "semaine", "label": "Ta semaine", "icone": "calendar", "categorie": "Accueil",
        "description": "Les 7 jours de la semaine : postes, séances, volume et charge face aux 4 semaines d'avant.",
        "taille": {"w": 12, "h": 2}, "params": [],
    },
    {
        "type": "kpi", "label": "Chiffre clé", "icone": "gauge", "categorie": "Chiffres et courbes",
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
        "type": "serie", "label": "Courbe ou barres", "icone": "chart", "categorie": "Chiffres et courbes",
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
            {"key": "bandes_postes", "label": "Colorer le fond selon le poste de travail", "kind": "bool",
             "default": False},
            {"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "herite"},
        ],
    },
    {
        "type": "charge", "label": "Forme & fatigue", "icone": "trend", "categorie": "Entraînement",
        "description": "Charge chronique (42 j), aiguë (7 j) et fraîcheur.",
        "taille": {"w": 12, "h": 2},
        "params": [
            {"key": "afficher_ratio", "label": "Afficher le ratio aiguë / chronique", "kind": "bool", "default": False},
            {"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "herite"},
        ],
    },
    {
        "type": "zones", "label": "Zones FC ou allure", "icone": "layers", "categorie": "Entraînement",
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
        "type": "calendrier", "label": "Calendrier thermique", "icone": "calendar", "categorie": "Chiffres et courbes",
        "description": "Une case par jour, colorée selon la valeur.",
        "taille": {"w": 6, "h": 2},
        "params": [
            {"key": "metrique", "label": "Métrique", "kind": "metric", "default": "sleep_s"},
            {"key": "mois", "label": "Nombre de mois", "kind": "select", "options": ["3", "6", "12"], "default": "6"},
        ],
    },
    {
        "type": "nuage", "label": "Nuage de points", "icone": "scatter", "categorie": "Chiffres et courbes",
        "description": "Croise deux métriques jour par jour (avec un décalage possible).",
        "taille": {"w": 6, "h": 2},
        "params": [
            {"key": "x", "label": "Axe horizontal", "kind": "metric", "default": "sleep_s"},
            {"key": "y", "label": "Axe vertical", "kind": "metric", "default": "hrv_night"},
            {"key": "decalage", "label": "Y mesuré N jours après X", "kind": "select", "options": ["0", "1", "2"],
             "default": "0"},
            {"key": "couleur_postes", "label": "Colorer selon le poste de travail", "kind": "bool", "default": True},
            {"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "herite"},
        ],
    },
    {
        "type": "postes", "label": "Comparaison par poste", "icone": "shift", "categorie": "Travail",
        "description": "Compare tes métriques d'un poste à l'autre (matin, soir, nuit…), d'après tes horaires.",
        "taille": {"w": 12, "h": 2},
        "params": [
            {"key": "metriques", "label": "Métriques", "kind": "metrics",
             "default": ["sleep_s", "sleep_end_h", "hrv_night", "resting_hr", "bb_wake"]},
            {"key": "jours_ouvres", "label": "Jours travaillés seulement", "kind": "bool", "default": True},
            {"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "180"},
        ],
    },
    {
        "type": "activites", "label": "Liste des séances", "icone": "list", "categorie": "Séances",
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
        "type": "derniere_seance", "label": "Dernière séance", "icone": "run", "categorie": "Séances",
        "description": "Carte résumé de ta dernière séance.",
        "taille": {"w": 6, "h": 2},
        "params": [{"key": "sport", "label": "Sport", "kind": "sport", "default": "tous"}],
    },
    {
        "type": "seance_resume", "label": "Séance : résumé", "icone": "info", "categorie": "Séances",
        "description": "Chiffres clés de la séance choisie en haut de la vue.",
        "taille": {"w": 12, "h": 1}, "params": [],
    },
    {
        "type": "seance_mesures", "label": "Séance : autres mesures", "icone": "gauge", "categorie": "Séances",
        "description": "Dynamique de course, puissance, respiration, température, Body Battery, meilleurs temps "
                       "de la sortie.",
        "taille": {"w": 12, "h": 2}, "params": [],
    },
    {
        "type": "seance_carte", "label": "Séance : carte", "icone": "map", "categorie": "Séances",
        "description": "Tracé GPS de la séance choisie.",
        "taille": {"w": 6, "h": 3}, "params": [],
    },
    {
        "type": "seance_courbes", "label": "Séance : courbes", "icone": "wave", "categorie": "Séances",
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
        "type": "seance_tours", "label": "Séance : tours", "icone": "table", "categorie": "Séances",
        "description": "Tours enregistrés par la montre, ou découpage au kilomètre.",
        "taille": {"w": 12, "h": 2},
        "params": [
            {"key": "mode", "label": "Afficher", "kind": "select", "options": ["tours", "kilometres"], "default": "tours"},
        ],
    },
    {
        "type": "objectif", "label": "Objectif course", "icone": "flag", "categorie": "Entraînement",
        "description": "Compte à rebours et allure cible de ton objectif (voir Réglages).",
        "taille": {"w": 4, "h": 2}, "params": [],
    },
    {
        "type": "fractions", "label": "Fractions rapides", "icone": "bolt", "categorie": "Entraînement",
        "description": "Allure moyenne de tes tours rapides, séance par séance, face à l'allure cible.",
        "taille": {"w": 8, "h": 2},
        "params": [{"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "120"}],
    },
    {
        "type": "records", "label": "Records", "icone": "trophy", "categorie": "Entraînement",
        "description": "Tes meilleurs temps (1 km, 5 km, 10 km, semi…) sur la période, face à tes records.",
        "taille": {"w": 6, "h": 2},
        "params": [
            {"key": "sport", "label": "Sport", "kind": "sport", "default": "pied"},
            {"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "365"},
        ],
    },
    {
        "type": "journee", "label": "Journée en détail", "icone": "clock", "categorie": "Journée en détail",
        "description": "Heure par heure : FC de la journée, Body Battery, phases de sommeil ou VFC de la nuit.",
        "taille": {"w": 12, "h": 2},
        "params": [
            {"key": "donnee", "label": "Donnée", "kind": "select",
             "options": ["body_battery", "fc", "sommeil", "vfc"], "default": "body_battery"},
            {"key": "jour", "label": "Jour affiché d'abord", "kind": "select", "options": ["aujourdhui", "hier"],
             "default": "aujourdhui"},
        ],
    },
    {
        "type": "note", "label": "Note", "icone": "note", "categorie": "Divers",
        "description": "Un texte libre (rappel, consigne, idée).",
        "taille": {"w": 4, "h": 1},
        "params": [{"key": "texte", "label": "Texte", "kind": "textarea", "default": ""}],
    },
]
TILE_INDEX = {t["type"]: t for t in TILE_TYPES}
WIDTHS = (3, 4, 6, 8, 12)
ICONS = ["home", "sun", "activity", "map", "moon", "flag", "heart", "chart", "calendar", "star", "bolt", "layers",
         "run", "trophy", "clock", "user", "club", "scale"]
CLUB_VIEW = "club"
WITHINGS_VIEW = "withings"


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


def home_view() -> dict:
    """Page d'accueil : la journée en un coup d'œil, et les allures du club selon ta VMA."""
    return {
        "id": "accueil", "name": "Accueil", "icon": "home",
        "spec": {"tuiles": [
            _tile("profil", 12, 1),
            _tile("forme", 8, 2),
            _tile("objectif", 4, 2),
            _tile("semaine", 12, 2),
            _tile("allures", 12, 3),
            _tile("journee", 6, 2, donnee="body_battery"),
            _tile("records", 6, 2),
        ]},
    }


def default_views() -> list[dict]:
    pied = "pied"
    return [
        home_view(),
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
                _tile("seance_mesures", 12, 2),
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
            value = value if isinstance(value, str) and metrics.exists(value) else p["default"]
        elif p["kind"] == "metrics":
            value = [v for v in (value if isinstance(value, list) else [value])
                     if isinstance(v, str) and metrics.exists(v)] or p["default"]
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
    if not conn.execute("SELECT COUNT(*) AS n FROM views").fetchone()["n"]:
        reset_default_views(conn)
        db.set_meta(conn, "vue_accueil", "1")
        conn.commit()
        return
    if db.get_meta(conn, "vue_accueil") is None:
        # 0.5 : la page d'accueil arrive en tête des vues déjà en place, une seule fois
        if not conn.execute("SELECT 1 FROM views WHERE id = 'accueil'").fetchone():
            view = home_view()
            first = conn.execute("SELECT COALESCE(MIN(position), 0) AS p FROM views").fetchone()["p"]
            conn.execute(
                "INSERT INTO views(id, name, icon, position, spec, builtin, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (view["id"], view["name"], view["icon"], first - 1, json.dumps(view["spec"], ensure_ascii=False),
                 db.now_iso()),
            )
        db.set_meta(conn, "vue_accueil", "1")
        conn.commit()


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


def club_view() -> dict:
    return {"id": CLUB_VIEW, "name": "Mon club", "icon": "club", "spec": {"tuiles": [_tile("club")]}}


def sync_club_view(conn: sqlite3.Connection, enabled: bool) -> None:
    """La vue « Mon club » apparaît juste après l'Accueil quand on coche son club, et s'en va quand on décoche."""
    exists = conn.execute("SELECT 1 FROM views WHERE id = ?", (CLUB_VIEW,)).fetchone()
    if enabled and not exists:
        home = conn.execute("SELECT position FROM views WHERE id = 'accueil'").fetchone()
        position = (home["position"] + 1) if home else 0
        conn.execute("UPDATE views SET position = position + 1 WHERE position >= ?", (position,))
        view = club_view()
        conn.execute(
            "INSERT INTO views(id, name, icon, position, spec, builtin, updated_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (view["id"], view["name"], view["icon"], position, json.dumps(view["spec"], ensure_ascii=False), db.now_iso()),
        )
    elif not enabled and exists:
        conn.execute("DELETE FROM views WHERE id = ?", (CLUB_VIEW,))


def withings_view(families: list[str] | None = None) -> dict:
    """La vue « Withings » : le résumé, puis une courbe par famille de mesures présente
    (corps, tension, sommeil, activité). Sans mesure encore : le corps, le cas le plus courant."""
    present = [f for f in ("corps", "tension", "sommeil", "activite") if f in (families or [])] or ["corps"]
    tiles = [_tile("withings", 12, 3)]
    for family in present:
        if family == "corps":
            tiles += [
                _tile("serie", 6, 2, titre="Poids", metriques=["wi_weight_kg"], lissage=0, periode="365"),
                _tile("serie", 6, 2, titre="Composition corporelle", metriques=["wi_fat_pct", "wi_muscle_kg"],
                      disposition="empiler", periode="365"),
            ]
        elif family == "tension":
            tiles += [
                _tile("serie", 6, 2, titre="Tension artérielle", metriques=["wi_bp_sys", "wi_bp_dia"],
                      disposition="superposer", periode="180"),
                _tile("serie", 6, 2, titre="Pouls au repos (tensiomètre, balance)", metriques=["wi_pulse"],
                      periode="180"),
            ]
        elif family == "sommeil":
            tiles += [
                _tile("serie", 6, 2, titre="Sommeil (Withings)", metriques=["wi_sleep_s"], style="barres",
                      bandes_postes=True, periode="60"),
                _tile("serie", 6, 2, titre="Nuits : FC et respiration", metriques=["wi_sleep_hr", "wi_sleep_resp"],
                      disposition="empiler", periode="60"),
            ]
        elif family == "activite":
            tiles += [
                _tile("serie", 6, 2, titre="Pas par jour (Withings)", metriques=["wi_steps"], style="barres",
                      periode="60"),
                _tile("serie", 6, 2, titre="Temps actif par semaine (Withings)", metriques=["wi_active_s"],
                      style="barres", agregation="semaine", periode="180"),
            ]
    return {"id": WITHINGS_VIEW, "name": "Withings", "icon": "scale", "spec": {"tuiles": tiles}}


def sync_withings_view(conn: sqlite3.Connection, enabled: bool, families: list[str] | None = None) -> None:
    """La vue « Withings » arrive quand on connecte son compte (après « Mon club » s'il existe, sinon après
    l'Accueil) et repart quand on le déconnecte. Ses tuiles suivent les mesures présentes tant qu'on ne l'a
    pas modifiée : la dernière version créée d'office est gardée dans « withings_vue_auto »."""
    row = conn.execute("SELECT spec FROM views WHERE id = ?", (WITHINGS_VIEW,)).fetchone()
    if not enabled:
        if row:
            conn.execute("DELETE FROM views WHERE id = ?", (WITHINGS_VIEW,))
        db.delete_meta(conn, "withings_vue_auto")
        return
    view = withings_view(families)
    shape = [(t["type"], t.get("titre")) for t in view["spec"]["tuiles"]]
    spec = json.dumps(view["spec"], ensure_ascii=False)
    if row:
        auto = db.get_meta(conn, "withings_vue_auto")
        if auto != row["spec"]:
            return  # modifiée par l'utilisateur : on n'y touche plus
        if [(t["type"], t.get("titre")) for t in json.loads(row["spec"]).get("tuiles", [])] == shape:
            return  # rien de nouveau
        conn.execute("UPDATE views SET spec = ?, updated_at = ? WHERE id = ?", (spec, db.now_iso(), WITHINGS_VIEW))
    else:
        anchor = conn.execute("SELECT position FROM views WHERE id IN (?, 'accueil') ORDER BY id = 'accueil' LIMIT 1",
                              (CLUB_VIEW,)).fetchone()
        position = (anchor["position"] + 1) if anchor else 0
        conn.execute("UPDATE views SET position = position + 1 WHERE position >= ?", (position,))
        conn.execute(
            "INSERT INTO views(id, name, icon, position, spec, builtin, updated_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (view["id"], view["name"], view["icon"], position, spec, db.now_iso()),
        )
    db.set_meta(conn, "withings_vue_auto", spec)


def reorder_views(conn: sqlite3.Connection, ids: list[str]) -> None:
    for position, view_id in enumerate(ids):
        conn.execute("UPDATE views SET position = ? WHERE id = ?", (position, view_id))
    conn.commit()


def raw_metrics_in_use(conn: sqlite3.Connection) -> list[dict]:
    """Métriques « données brutes de Garmin » choisies dans des tuiles : l'interface a besoin de leur libellé."""
    from dataclasses import asdict

    keys: set[str] = set()
    for view in list_views(conn):
        for tile in view["spec"].get("tuiles", []):
            for value in (tile.get("params") or {}).values():
                for item in value if isinstance(value, list) else [value]:
                    if isinstance(item, str) and metrics.raw_parts(item):
                        keys.add(item)
    return [asdict(metrics.raw_metric(k)) for k in sorted(keys)]
