"""Serveur MCP : la façade de Foulée pour Claude Desktop.

Claude Desktop lance ce programme lui-même (« foulee mcp ») et dialogue avec
lui par l'entrée/sortie standard. Chaque outil ci-dessous lit la base locale
via le moteur d'analyse : Claude voit exactement les mêmes chiffres que
l'interface. La clé API n'est jamais exposée.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import date
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from . import __version__, analysis, config, db, metrics, vault, views
from . import sync as sync_module

INSTRUCTIONS = """\
Foulée est le hub local de données sport et santé de l'utilisateur (montre Garmin,
via l'API personnelle officielle). Les données sont dans une base SQLite sur son PC.

Repères :
- Dates au format AAAA-MM-JJ. Sans dates, les outils prennent une période par défaut.
- Les métriques ont une clé (ex. sleep_s, hrv_night, resting_hr, act.distance_km) :
  appelle catalogue_metriques en cas de doute. Les durées sont en secondes, les vitesses
  en m/s ; les champs « affiche » / « allure » sont déjà mis en forme (allure réelle,
  min/km, pas ajustée à la pente).
- Une nuit de sommeil est rattachée au jour du réveil.
- Postes alternés : semaines ISO impaires = poste du matin, paires = poste du soir
  (réglable). comparer_postes les compare, jours ouvrés seulement par défaut.
- La charge (charge chronique 42 j, aiguë 7 j, fraîcheur) est calculée par Foulée à partir
  de la charge Garmin de chaque séance (ou d'un TRIMP fréquence cardiaque à défaut).
- Avant d'analyser une séance, lis son nom et sa description : l'utilisateur y note
  parfois des informations et ses ressentis.
- Les données ne datent que de la dernière synchro : regarde statut, et propose
  synchroniser si elles sont anciennes.
"""

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

mcp = MCPServer(name="Foulée", instructions=INSTRUCTIONS, version=__version__)


def _period(debut: str | None, fin: str | None, jours: int = 30) -> tuple[date, date]:
    return analysis.resolve_period(debut, fin, jours)


def _check_metrics(keys: list[str]) -> list[str]:
    unknown = [k for k in keys if k not in metrics.CATALOG]
    if unknown:
        raise ValueError(f"Métrique(s) inconnue(s) : {', '.join(unknown)}. Voir catalogue_metriques.")
    return keys


# ------------------------------------------------------------------- état
@mcp.tool(annotations=READ)
def statut() -> dict[str, Any]:
    """État du hub : dernière synchro, période couverte, volumes, réglages utiles (VMA, objectif, FC)."""
    with db.session() as conn:
        settings = db.get_settings(conn)
        first = conn.execute("SELECT MIN(date) AS a, MAX(date) AS b FROM daily WHERE source = 'garmin'").fetchone()
        acts = conn.execute("SELECT COUNT(*) AS n, MIN(date) AS a, MAX(date) AS b FROM activities").fetchone()
        return {
            "version": __version__,
            "mode_demo": config.is_demo(),
            "cle_api_garmin": "présente" if vault.has_key() else "absente",
            "synchro": sync_module.last_sync_info(conn),
            "donnees_quotidiennes": {"du": first["a"], "au": first["b"]},
            "seances": {"nombre": acts["n"], "du": acts["a"], "au": acts["b"]},
            "aujourdhui": date.today().isoformat(),
            "vma_kmh": settings.get("vma_kmh"),
            "objectif": analysis.objective(settings),
            "profil_fc": analysis.hr_profile(conn, settings),
            "postes": settings.get("postes"),
        }


@mcp.tool(annotations=WRITE)
def synchroniser(depuis: str | None = None) -> dict[str, Any]:
    """Lance une synchro Garmin (incrémentale, ou depuis une date AAAA-MM-JJ). Attend jusqu'à ~50 s."""
    if config.is_demo():
        return {"statut": "demo", "message": "Mode démo : pas de synchro."}
    if not vault.has_key():
        return {"statut": "erreur", "message": "Aucune clé API Garmin : l'utilisateur doit lancer « foulee setup »."}
    box: dict[str, Any] = {}

    def work() -> None:
        try:
            box["resultat"] = sync_module.run(since=analysis.to_date(depuis) if depuis else None)
        except Exception as exc:
            box["erreur"] = str(exc)

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(timeout=50)
    if thread.is_alive():
        return {"statut": "en_cours", "message": "La synchro continue en arrière-plan ; rappelle statut dans un moment."}
    if "erreur" in box:
        return {"statut": "erreur", "message": box["erreur"]}
    return box["resultat"]


@mcp.tool(annotations=READ)
def catalogue_metriques() -> dict[str, Any]:
    """Liste des métriques disponibles (clé, libellé, unité, catégorie) et des familles de sport."""
    return {
        "metriques": [
            {k: v for k, v in m.items() if k in ("key", "label", "unit", "category", "kind", "description") and v}
            for m in metrics.catalog_json()
        ],
        "sports": metrics.SPORTS,
        "note": "Les métriques act.* agrègent les séances et acceptent un filtre sport "
                "(ex. 'course', 'trail', 'pied' = course + trail).",
    }


# ------------------------------------------------------------------ séries
@mcp.tool(annotations=READ)
def serie(metrique: str, debut: str | None = None, fin: str | None = None, regroupement: str = "jour",
          sport: str | None = None, lissage: int = 0) -> dict[str, Any]:
    """Valeurs d'une métrique dans le temps. regroupement : jour, semaine ou mois. lissage : moyenne glissante."""
    _check_metrics([metrique])
    a, b = _period(debut, fin, 30 if regroupement == "jour" else 180)
    with db.session(readonly=True) as conn:
        data = analysis.series(conn, metrique, a, b, regroupement, None, sport, lissage)
    points = data["points"]
    if len(points) > 400:
        return {"erreur": f"{len(points)} points : réduis la période ou regroupe par semaine/mois."}
    data["points"] = [{"periode": p, "valeur": v, "affiche": metrics.format_value(metrique, v)} for p, v in points]
    return data


@mcp.tool(annotations=READ)
def resume_periode(debut: str | None = None, fin: str | None = None) -> dict[str, Any]:
    """Résumé d'une période : sommeil, VFC, FC de repos, Body Battery, stress, pas, séances par sport, charge."""
    a, b = _period(debut, fin, 7)
    with db.session(readonly=True) as conn:
        return analysis.period_summary(conn, a, b, db.get_settings(conn))


@mcp.tool(annotations=READ)
def comparer_periodes(metriques: list[str], debut_a: str, fin_a: str, debut_b: str, fin_b: str) -> dict[str, Any]:
    """Compare des métriques entre deux périodes (moyennes, ou totaux et totaux par semaine pour les séances)."""
    _check_metrics(metriques)
    with db.session(readonly=True) as conn:
        return analysis.compare_periods(conn, metriques, _period(debut_a, fin_a), _period(debut_b, fin_b))


@mcp.tool(annotations=READ)
def comparer_postes(metriques: list[str] | None = None, debut: str | None = None, fin: str | None = None,
                    jours_ouvres: bool = True) -> dict[str, Any]:
    """Compare semaines du matin et semaines du soir (moyenne, médiane, écart-type, taille d'effet)."""
    keys = _check_metrics(metriques or ["sleep_s", "sleep_end_h", "sleep_score", "hrv_night", "resting_hr",
                                         "bb_wake", "stress_avg"])
    a, b = _period(debut, fin, 180)
    with db.session(readonly=True) as conn:
        return analysis.shift_compare(conn, keys, a, b, db.get_settings(conn), jours_ouvres)


@mcp.tool(annotations=READ)
def correlation(x: str, y: str, debut: str | None = None, fin: str | None = None, decalage_jours: int = 0) -> dict[str, Any]:
    """Corrélation jour par jour entre deux métriques (y mesuré N jours après x). Renvoie r et le nombre de jours."""
    _check_metrics([x, y])
    a, b = _period(debut, fin, 180)
    with db.session(readonly=True) as conn:
        data = analysis.scatter(conn, x, y, a, b, db.get_settings(conn), decalage_jours)
    data["points"] = data["points"][-120:]
    return data


# ----------------------------------------------------------------- séances
def _compact(activity: dict) -> dict:
    return {
        "id": activity["id"], "date": activity["date"], "heure": activity["start_local"][11:16],
        "nom": activity["name"], "description": activity.get("description"), "sport": activity["sport_label"],
        "distance_km": activity["distance_km"], "duree": activity["duree"], "allure": activity.get("allure"),
        "vitesse_kmh": activity.get("vitesse_kmh"), "fc_moy": activity.get("avg_hr"), "fc_max": activity.get("max_hr"),
        "d_plus_m": activity.get("elev_gain_m"), "charge": activity.get("load"),
        "effet_aerobie": activity.get("te_aerobic"), "courbes": activity.get("has_streams") == 1,
    }


@mcp.tool(annotations=READ)
def lister_seances(debut: str | None = None, fin: str | None = None, sport: str | None = None,
                   recherche: str | None = None, limite: int = 20) -> dict[str, Any]:
    """Séances (plus récentes d'abord) avec nom, description, distance, durée, allure, FC, D+, charge, id."""
    a, b = _period(debut, fin, 30) if (debut or fin) else (None, None)
    with db.session(readonly=True) as conn:
        rows = analysis.activities_list(conn, a, b, sport, recherche, min(limite, 100))
    return {"seances": [_compact(r) for r in rows]}


@mcp.tool(annotations=READ)
def detail_seance(seance_id: str) -> dict[str, Any]:
    """Détail d'une séance : résumé, tours, découpage au km, zones, découplage cardiaque.

    Télécharge le fichier FIT chez Garmin si la séance n'a pas encore de courbes.
    """
    with db.session() as conn:
        row = conn.execute("SELECT has_streams FROM activities WHERE id = ?", (seance_id,)).fetchone()
        if not row:
            return {"erreur": "Séance introuvable (utilise l'id donné par lister_seances)."}
        status = None
        if row["has_streams"] == 0 and vault.has_key() and not config.is_demo():
            from .garmin.sync import ensure_streams

            try:
                status = ensure_streams(conn, seance_id)
            except Exception as exc:
                status = f"téléchargement impossible : {exc}"
        detail = analysis.activity_detail(conn, seance_id, db.get_settings(conn))
    tours = [
        {"n": t["idx"] + 1, "type": t.get("intensity"), "duree": t["duree"], "distance_m": round(t["distance_m"] or 0),
         "allure": t.get("allure"), "fc_moy": t.get("avg_hr"), "fc_max": t.get("max_hr"),
         "cadence": t.get("avg_cadence"), "d_plus_m": t.get("elev_gain_m")}
        for t in detail.pop("tours")
    ]
    compact = _compact(detail)
    compact.update({
        "zones_fc_s": detail.get("hr_zones"), "zones_fc_bornes_bpm": detail.get("zones_fc_bornes"),
        "zones_allure_s": detail.get("pace_zones"), "pct_vma": detail.get("pct_vma"),
        "trimp": detail.get("trimp"), "charge_garmin": detail.get("garmin_load"), "vo2max": detail.get("vo2max"),
        "tours": tours[:80], "km": detail.get("splits_km", [])[:100], "decouplage_cardiaque": detail.get("decouplage"),
        "telechargement_fit": status,
    })
    return compact


@mcp.tool(annotations=READ)
def charge_entrainement(debut: str | None = None, fin: str | None = None) -> dict[str, Any]:
    """Charge chronique (42 j), aiguë (7 j), fraîcheur et ratio, semaine par semaine, + valeurs du dernier jour."""
    a, b = _period(debut, fin, 84)
    with db.session(readonly=True) as conn:
        weekly = {k: analysis.series(conn, k, a, b, "semaine", "last")["points"] for k in ("ctl", "atl", "tsb", "acwr")}
        load = analysis.series(conn, "load_day", a, b, "semaine", "sum")["points"]
        last = {k: analysis.kpi(conn, k, b)["value"] for k in ("ctl", "atl", "tsb", "acwr")}
    rows = [{"semaine_du": p, "charge_semaine": l, "chronique": c, "aigue": at, "fraicheur": t, "ratio": r}
            for (p, l), (_, c), (_, at), (_, t), (_, r) in zip(load, weekly["ctl"], weekly["atl"], weekly["tsb"],
                                                              weekly["acwr"])]
    return {"dernier_jour": last, "semaines": rows,
            "lecture": "fraîcheur négative = tu encaisses ; ratio > 1,5 = hausse de charge brutale"}


@mcp.tool(annotations=READ)
def zones_temps(type: str = "fc", debut: str | None = None, fin: str | None = None, regroupement: str = "total",
                sport: str | None = None) -> dict[str, Any]:
    """Temps passé par zone : type 'fc' (zones Garmin) ou 'allure' (zones calées sur la VMA)."""
    a, b = _period(debut, fin, 28)
    with db.session(readonly=True) as conn:
        data = analysis.zones(conn, type, a, b, regroupement, sport, db.get_settings(conn))
    for row in data["series"]:
        row["affiche"] = [metrics.fmt_duration(s) for s in row["secondes"]]
    return data


@mcp.tool(annotations=READ)
def fractions_rapides(debut: str | None = None, fin: str | None = None) -> dict[str, Any]:
    """Pour chaque séance de course, allure moyenne des tours rapides (au-dessus du seuil % VMA des réglages)."""
    a, b = _period(debut, fin, 120)
    with db.session(readonly=True) as conn:
        settings = db.get_settings(conn)
        data = analysis.fast_laps(conn, a, b, settings)
    data["objectif"] = analysis.objective(settings)
    return data


@mcp.tool(annotations=READ)
def objectif() -> dict[str, Any]:
    """Objectif course des réglages : date, jours restants, temps cible, allure cible, % de VMA."""
    with db.session(readonly=True) as conn:
        return analysis.objective(db.get_settings(conn))


# --------------------------------------------------------------------- SQL
SCHEMA_HELP = {
    "daily": "Métriques quotidiennes au format long : date, metric (voir catalogue), value, source "
             "('garmin' ou 'calc' pour les valeurs calculées).",
    "activities": "Une ligne par séance : id, date, start_local, sport, type_key, name, description, duration_s, "
                  "distance_m, elev_gain_m, avg_hr, max_hr, avg_speed (m/s), avg_cadence, te_aerobic, "
                  "garmin_load, trimp, load, vo2max, hr_zones (JSON s), pace_zones (JSON s), has_streams.",
    "laps": "Tours des séances : activity_id, idx, start_s, duration_s, distance_m, avg_hr, max_hr, "
            "avg_speed, avg_cadence, elev_gain_m, intensity (warmup, active, rest, cooldown).",
    "views": "Vues de l'interface (spec JSON).",
    "settings": "Réglages (valeurs JSON).",
}


@mcp.tool(annotations=READ)
def schema_base() -> dict[str, Any]:
    """Tables et colonnes de la base, pour écrire une requête avec requete_sql."""
    with db.session(readonly=True) as conn:
        tables = {}
        for name in SCHEMA_HELP:
            cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({name})")]
            tables[name] = {"colonnes": cols, "description": SCHEMA_HELP[name]}
    return {"tables": tables}


@mcp.tool(annotations=READ)
def requete_sql(sql: str, limite: int = 200) -> dict[str, Any]:
    """Requête SQL en LECTURE SEULE (SELECT / WITH) sur la base SQLite. Pratique pour les questions sur mesure."""
    text = sql.strip().rstrip(";").strip()
    if not re.match(r"^(select|with)\b", text, re.I) or ";" in text:
        return {"erreur": "Seules les requêtes SELECT ou WITH (une seule instruction) sont acceptées."}
    if not config.db_path().exists():
        return {"erreur": "Base absente."}
    conn = db.connect(readonly=True)
    try:
        conn.execute("PRAGMA query_only = ON")
        cursor = conn.execute(text)
        columns = [c[0] for c in cursor.description or []]
        rows = cursor.fetchmany(max(1, min(limite, 1000)) + 1)
    except sqlite3.Error as exc:
        return {"erreur": f"SQLite : {exc}"}
    finally:
        conn.close()
    truncated = len(rows) > limite
    return {"colonnes": columns, "lignes": [list(r) for r in rows[:limite]], "tronque": truncated}


# -------------------------------------------------------------------- vues
@mcp.tool(annotations=READ)
def lister_vues() -> dict[str, Any]:
    """Vues de l'interface Foulée et leurs tuiles."""
    with db.session(readonly=True) as conn:
        return {"vues": views.list_views(conn)}


@mcp.tool(annotations=READ)
def types_de_tuiles() -> dict[str, Any]:
    """Types de tuiles disponibles et leurs réglages, pour composer une vue avec enregistrer_vue."""
    return {
        "tuiles": views.TILE_TYPES,
        "tailles": "w = largeur sur 12 colonnes (3, 4, 6, 8 ou 12) ; h = hauteur (1, 2 ou 3).",
        "periode": "'herite' suit le sélecteur de période de la vue, sinon un nombre de jours.",
        "sports": views.SPORT_OPTIONS,
        "icones": views.ICONS,
    }


@mcp.tool(annotations=WRITE)
def enregistrer_vue(nom: str, tuiles: list[dict[str, Any]], vue_id: str | None = None,
                    icone: str | None = None) -> dict[str, Any]:
    """Crée ou remplace une vue de l'interface.

    tuiles : liste de {"type", "w", "h", "titre" (facultatif), "params": {...}} — voir types_de_tuiles.
    L'interface affichera la vue au prochain rafraîchissement de la page.
    """
    with db.session() as conn:
        saved = views.save_view(conn, vue_id, nom, {"tuiles": tuiles}, icone)
    return {"vue": saved, "adresse": f"http://127.0.0.1:{config.DEFAULT_PORT}/#/vue/{saved['id']}",
            "tuiles_retenues": len(saved["spec"]["tuiles"]), "tuiles_demandees": len(tuiles)}


# ----------------------------------------------------------------- réglages
@mcp.tool(annotations=READ)
def reglages() -> dict[str, Any]:
    """Réglages actuels (VMA, FC, objectif, postes, zones d'allure…)."""
    with db.session(readonly=True) as conn:
        return db.get_settings(conn)


@mcp.tool(annotations=WRITE)
def modifier_reglages(changements: dict[str, Any]) -> dict[str, Any]:
    """Modifie des réglages (ex. {"vma_kmh": 16.5} ou {"objectif": {"temps_cible": "1:24:00"}}).

    Les calculs dépendants (zones, TRIMP, charge) sont refaits aussitôt.
    """
    allowed = set(db.DEFAULT_SETTINGS)
    unknown = [k for k in changements if k not in allowed]
    if unknown:
        return {"erreur": f"Réglage(s) inconnu(s) : {', '.join(unknown)}", "reglages_possibles": sorted(allowed)}
    with db.session() as conn:
        current = db.get_settings(conn)
        for key, value in changements.items():
            if isinstance(current.get(key), dict) and isinstance(value, dict):
                merged = dict(current[key])
                merged.update(value)
                value = merged
            db.set_setting(conn, key, value)
        conn.commit()
        settings = db.get_settings(conn)
        recalcul = bool({"vma_kmh", "fc_max", "fc_repos", "sexe", "zones_allure_pct_vma", "charge_source"}
                        & set(changements))
        if recalcul:
            analysis.refresh_all_activities(conn, settings)
    return {"reglages": settings, "recalcul_effectue": recalcul}


def serve() -> None:
    with db.session():
        pass  # crée la base si besoin
    mcp.run()


if __name__ == "__main__":
    serve()
