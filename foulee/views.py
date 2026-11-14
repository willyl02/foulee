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
        "description": "FC de repos, VFC, sommeil, Body Battery, fraîcheur : chacun face à tes habitudes, avec "
                       "sa petite courbe des dernières semaines.",
        "taille": {"w": 9, "h": 3}, "params": [],
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
        "description": "Les 7 jours de la semaine : postes, séances faites et prévues (calendrier d'entraînement), "
                       "volume et charge face aux 4 semaines d'avant.",
        "taille": {"w": 12, "h": 2}, "params": [],
    },
    {
        "type": "a_venir", "label": "Prochaines séances", "icone": "flag", "categorie": "Entraînement",
        "description": "Ta prochaine course (compte à rebours) et tes prochaines séances prévues, d'après ton "
                       "calendrier d'entraînement (Réglages → Calendrier).",
        "taille": {"w": 12, "h": 1},
        "params": [
            {"key": "jours", "label": "Séances des N prochains jours", "kind": "select", "options": ["7", "14", "28"],
             "default": "14"},
        ],
    },
    {
        "type": "agenda", "label": "Calendrier d'entraînement", "icone": "calendar", "categorie": "Entraînement",
        "description": "Le mois en un coup d'œil : séances prévues et courses de ton calendrier (Garmin Connect ou "
                       "agenda iCal) face à ce que tu as fait, jour par jour. Un clic sur un jour donne le détail.",
        "taille": {"w": 12, "h": 3}, "params": [],
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
        "type": "renfo", "label": "Renfo : muscles travaillés", "icone": "dumbbell", "categorie": "Entraînement",
        "description": "Les muscles que tes séances de renfo ont fait travailler (carte du corps, face et dos), "
                       "tes séances et ta régularité semaine après semaine, d'après les exercices enregistrés "
                       "par ta montre.",
        "taille": {"w": 12, "h": 4},
        "params": [
            {"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "herite"},
            {"key": "objectif", "label": "Objectif : séances de renfo par semaine (0 = aucun)", "kind": "number",
             "default": 2},
        ],
    },
    {
        "type": "renfo_exercices", "label": "Renfo : exercices et progression", "icone": "dumbbell",
        "categorie": "Entraînement",
        "description": "Chaque exercice de la période : séances, séries, répétitions, charge, et son évolution "
                       "d'une séance à l'autre.",
        "taille": {"w": 12, "h": 3},
        "params": [{"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "herite"}],
    },
    {
        "type": "renfo_equilibre", "label": "Renfo : équilibre avant / arrière", "icone": "balance",
        "categorie": "Entraînement",
        "description": "Séries de la chaîne antérieure (squats, pompes, abdos…) face à la chaîne postérieure "
                       "(soulevé de terre, tirage, lombaires, mollets…) : le rapport 1:x et la cible du coureur "
                       "(1:1 à 1:2), paire par paire (genou / hanche, poussée / tirage…) avec un conseil, et "
                       "semaine après semaine.",
        "taille": {"w": 12, "h": 2},
        "params": [{"key": "periode", "label": "Période (jours)", "kind": "periode", "default": "herite"}],
    },
    {
        "type": "seance_renfo", "label": "Séance : exercices de renfo", "icone": "dumbbell", "categorie": "Séances",
        "description": "Les exercices de la séance choisie (séries, répétitions, charge), les muscles travaillés "
                       "et l'équilibre avant / arrière de la séance. La tuile s'efface pour les séances sans renfo.",
        "taille": {"w": 12, "h": 3}, "params": [],
    },
    {
        "type": "seance_effet", "label": "Séance : effet d'entraînement", "icone": "gauge", "categorie": "Séances",
        "description": "Effet aérobie et effet anaérobie de la séance (Training Effect de Garmin, de 0 à 5), son "
                       "avantage principal (base, tempo, seuil, VO2 max…) et sa place parmi tes séances du même "
                       "sport des 4 semaines précédentes. La tuile s'efface pour les séances sans effet "
                       "d'entraînement.",
        "taille": {"w": 12, "h": 2}, "params": [],
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
WIDTHS = (3, 4, 6, 8, 9, 12)
ICONS = ["home", "sun", "activity", "map", "moon", "flag", "heart", "chart", "calendar", "star", "bolt", "layers",
         "run", "trophy", "clock", "user", "club", "scale", "dumbbell"]
CLUB_VIEW = "club"
WITHINGS_VIEW = "withings"
RENFO_VIEW = "renfo"
CALENDAR_VIEW = "calendrier"


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
            _tile("forme", 9, 3),
            _tile("objectif", 3, 3),
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
                _tile("seance_renfo", 12, 3),
                _tile("seance_effet", 12, 2),
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
def _insert_tile(conn: sqlite3.Connection, view_id: str, kind: str, w: int, h: int, after: tuple[str, ...]) -> None:
    """Ajoute une tuile à une vue déjà en place (mise à niveau), juste après la première tuile trouvée parmi
    ``after`` (en tête sinon) ; rien si la vue n'existe plus ou a déjà la tuile."""
    row = conn.execute("SELECT spec FROM views WHERE id = ?", (view_id,)).fetchone()
    if not row:
        return
    spec = json.loads(row["spec"])
    tiles = spec.setdefault("tuiles", [])
    if any(t.get("type") == kind for t in tiles):
        return
    at = 0
    for anchor in after:
        found = next((i + 1 for i, t in enumerate(tiles) if t.get("type") == anchor), None)
        if found is not None:
            at = found
            break
    tiles.insert(at, _tile(kind, w, h))
    conn.execute("UPDATE views SET spec = ?, updated_at = ? WHERE id = ?",
                 (json.dumps(spec, ensure_ascii=False), db.now_iso(), view_id))


def ensure_default_views(conn: sqlite3.Connection) -> None:
    if not conn.execute("SELECT COUNT(*) AS n FROM views").fetchone()["n"]:
        reset_default_views(conn)
        db.set_meta(conn, "vue_accueil", "1")
        db.set_meta(conn, "vue_seance_renfo", "1")
        db.set_meta(conn, "vue_effet_entrainement", "1")
        db.set_meta(conn, "vue_renfo_equilibre", "1")
        db.set_meta(conn, "vue_forme_large", "1")
        conn.commit()
        return
    if db.get_meta(conn, "vue_seance_renfo") is None:
        # 0.6 : les exercices de renfo dans la vue « Séance » déjà en place, une seule fois
        row = conn.execute("SELECT spec FROM views WHERE id = 'seance'").fetchone()
        if row:
            spec = json.loads(row["spec"])
            tiles = spec.get("tuiles", [])
            if not any(t.get("type") == "seance_renfo" for t in tiles):
                at = next((i + 1 for i, t in enumerate(tiles) if t.get("type") == "seance_resume"), 0)
                tiles.insert(at, _tile("seance_renfo", 12, 3))
                conn.execute("UPDATE views SET spec = ?, updated_at = ? WHERE id = 'seance'",
                             (json.dumps(spec, ensure_ascii=False), db.now_iso()))
        db.set_meta(conn, "vue_seance_renfo", "1")
        conn.commit()
    if db.get_meta(conn, "vue_effet_entrainement") is None:
        # 0.7 : l'effet d'entraînement dans la vue « Séance » déjà en place (après les exercices de renfo)
        _insert_tile(conn, "seance", "seance_effet", 12, 2, after=("seance_renfo", "seance_resume"))
        db.set_meta(conn, "vue_effet_entrainement", "1")
        conn.commit()
    if db.get_meta(conn, "vue_renfo_equilibre") is None:
        # 0.7 : l'équilibre avant / arrière dans la vue « Renfo » déjà en place (sous les muscles travaillés)
        _insert_tile(conn, RENFO_VIEW, "renfo_equilibre", 12, 2, after=("renfo",))
        db.set_meta(conn, "vue_renfo_equilibre", "1")
        conn.commit()
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
    if db.get_meta(conn, "vue_forme_large") is None:
        # 0.8 : la forme du jour s'élargit et grandit d'une rangée (ses petites courbes), l'objectif cède un cran
        # de largeur, si l'Accueil a encore les tailles d'origine (8 × 2 et 4 × 2) ; une page arrangée autrement
        # n'est pas touchée
        row = conn.execute("SELECT spec FROM views WHERE id = 'accueil'").fetchone()
        if row:
            spec = json.loads(row["spec"])
            tiles = spec.get("tuiles", [])
            form = next((t for t in tiles if t.get("type") == "forme"), None)
            goal = next((t for t in tiles if t.get("type") == "objectif"), None)
            if form and goal and (form.get("w"), form.get("h"), goal.get("w"), goal.get("h")) == (8, 2, 4, 2) and \
                    abs(tiles.index(form) - tiles.index(goal)) == 1:
                form.update(w=9, h=3)
                goal.update(w=3, h=3)
                conn.execute("UPDATE views SET spec = ?, updated_at = ? WHERE id = 'accueil'",
                             (json.dumps(spec, ensure_ascii=False), db.now_iso()))
        db.set_meta(conn, "vue_forme_large", "1")
        conn.commit()
    if db.get_meta(conn, "renfo_vue") is None and sync_renfo_view(conn):
        # 0.6 : exercices retrouvés par la mise à niveau de la base, la vue « Renfo » sans attendre une synchro
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


def calendar_view(view_id: str = CALENDAR_VIEW) -> dict:
    """La vue « Calendrier » : la prochaine course et les prochaines séances, puis le mois en entier."""
    return {"id": view_id, "name": "Calendrier", "icon": "calendar", "spec": {"tuiles": [
        _tile("a_venir", 12, 1),
        _tile("agenda", 12, 3),
    ]}}


def sync_calendar_view(conn: sqlite3.Connection, enabled: bool) -> str | None:
    """La vue « Calendrier » arrive avec le lien du calendrier (juste après l'Accueil) et repart avec lui. Son
    identifiant est retenu (« calendrier_vue ») : une vue que tu aurais appelée « Calendrier » toi-même n'est
    jamais touchée. Renvoie l'identifiant de la vue (None quand elle s'en va)."""
    mine = db.get_meta(conn, "calendrier_vue")
    exists = mine and conn.execute("SELECT 1 FROM views WHERE id = ?", (mine,)).fetchone()
    if not enabled:
        if exists:
            conn.execute("DELETE FROM views WHERE id = ?", (mine,))
        db.delete_meta(conn, "calendrier_vue")
        return None
    if exists:
        return mine
    view_id, n = CALENDAR_VIEW, 2
    while conn.execute("SELECT 1 FROM views WHERE id = ?", (view_id,)).fetchone():
        view_id, n = f"{CALENDAR_VIEW}-{n}", n + 1
    view = calendar_view(view_id)
    home = conn.execute("SELECT position FROM views WHERE id = 'accueil'").fetchone()
    position = (home["position"] + 1) if home else 0
    conn.execute("UPDATE views SET position = position + 1 WHERE position >= ?", (position,))
    conn.execute(
        "INSERT INTO views(id, name, icon, position, spec, builtin, updated_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
        (view["id"], view["name"], view["icon"], position, json.dumps(view["spec"], ensure_ascii=False), db.now_iso()),
    )
    db.set_meta(conn, "calendrier_vue", view_id)
    return view_id


def renfo_view() -> dict:
    """La vue « Renfo » : muscles travaillés, exercices et leur progression, régularité, séances."""
    return {"id": RENFO_VIEW, "name": "Renfo", "icon": "dumbbell", "spec": {"tuiles": [
        _tile("renfo", 12, 4),
        _tile("renfo_equilibre", 12, 2),
        _tile("renfo_exercices", 12, 3),
        _tile("serie", 6, 2, titre="Temps de renfo par semaine", metriques=["act.duration_s"], style="barres",
              agregation="semaine", sport="renfo", periode="180"),
        _tile("serie", 6, 2, titre="Séries et tonnage par semaine", metriques=["act.sets", "act.volume"],
              style="barres", agregation="semaine", disposition="empiler", periode="180"),
        _tile("activites", 12, 3, titre="Séances de renfo", sport="renfo", limite=20),
    ]}}


def sync_renfo_view(conn: sqlite3.Connection, present: bool | None = None) -> bool:
    """La vue « Renfo » arrive une fois, avec les premiers exercices de renfo (après « Entraînement »).
    Si on la supprime, elle ne revient pas : « renfo_vue » le retient. ``present`` : des exercices venus
    d'ailleurs que la base (description d'une séance Strava)."""
    from . import renfo  # import local : renfo ne dépend pas des vues

    if db.get_meta(conn, "renfo_vue") or not (present if present is not None else renfo.has_any(conn)):
        return False
    if not conn.execute("SELECT 1 FROM views WHERE id = ?", (RENFO_VIEW,)).fetchone():
        view = renfo_view()
        anchor = conn.execute("SELECT position FROM views WHERE id IN ('entrainement', 'accueil') "
                              "ORDER BY id = 'accueil' LIMIT 1").fetchone()
        position = (anchor["position"] + 1) if anchor else 0
        conn.execute("UPDATE views SET position = position + 1 WHERE position >= ?", (position,))
        conn.execute(
            "INSERT INTO views(id, name, icon, position, spec, builtin, updated_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (view["id"], view["name"], view["icon"], position, json.dumps(view["spec"], ensure_ascii=False),
             db.now_iso()),
        )
    db.set_meta(conn, "renfo_vue", "1")
    return True


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
