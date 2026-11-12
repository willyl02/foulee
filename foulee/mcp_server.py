"""Serveur MCP : la façade de Foulée pour Claude Desktop.

Claude Desktop lance ce programme lui-même (« foulee mcp ») et dialogue avec
lui par l'entrée/sortie standard. Chaque outil ci-dessous lit la base locale
via le moteur d'analyse : Claude voit exactement les mêmes chiffres que
l'interface. La clé API n'est jamais exposée.

Profils : Claude ne lit que ceux qui l'autorisent (case « Claude Desktop peut lire mes
données » dans les Réglages de chacun). Il commence par le profil principal s'il l'autorise ;
changer_utilisateur passe sur un autre profil autorisé. Chaque ouverture de base revérifie
l'autorisation (voir utilisateurs.check_claude_access).
"""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import date, timedelta
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from . import (__version__, analysis, calendrier, club, config, db, metrics, reglages, renfo, schedule, utilisateurs,
               vault, views)
from . import sync as sync_module
from .garmin import intraday

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
- Horaires de travail (réglage « horaires ») : bureau, 2x8 (matin / soir selon la parité des
  semaines ISO), 3x8, 5x8 ou cycle personnalisé, avec les congés. horaires donne le planning
  jour par jour ; comparer_postes compare les métriques d'un poste à l'autre (jours travaillés
  seulement par défaut).
- Au-delà du catalogue, toute valeur numérique gardée des réponses de Garmin est une métrique :
  « garmin:<flux>:<chemin> » (ex. garmin:daily:pulseOx.avgValue, garmin:activity:avgVerticalRatio).
  champs_garmin les liste.
- allures_vma reprend le tableau d'allures du club (55 à 120 % de VMA, temps de passage sur
  piste, test VAMEVAL) ; forme_du_jour lit les signaux de récupération face aux habitudes.
- La charge (charge chronique 42 j, aiguë 7 j, fraîcheur) est calculée par Foulée à partir
  de la charge Garmin de chaque séance (ou d'un TRIMP fréquence cardiaque à défaut).
- Avant d'analyser une séance, lis son nom et sa description : l'utilisateur y note
  parfois des informations et ses ressentis.
- Les données ne datent que de la dernière synchro : regarde statut, et propose
  synchroniser si elles sont anciennes.
- Profils : plusieurs personnes peuvent utiliser Foulée. Tu ne lis que les profils qui t'y
  autorisent ; tous les outils visent le profil en cours (statut donne son prénom). Si la
  question porte sur quelqu'un d'autre, appelle utilisateurs puis changer_utilisateur, et
  dis toujours de qui tu parles.
- Withings (si l'utilisateur a connecté son compte : statut → withings) : balance, tensiomètre,
  Sleep Analyzer, montre. Métriques « wi_… » de la catégorie Withings (wi_weight_kg, wi_fat_pct,
  wi_muscle_kg, wi_bp_sys, wi_bp_dia, wi_pulse, wi_sleep_s…), source « withings » dans la table
  daily. Pour le corps, la dernière pesée du jour ; pour la tension, la moyenne du jour. Ces
  chiffres sont des repères : tu ne poses pas de diagnostic médical.
- Renfo : les exercices de renforcement enregistrés par la montre, d'après le résumé de Garmin
  Connect (corrections faites dans l'appli comprises). Outil renfo pour une période (séances,
  exercices et leur progression, muscles travaillés, régularité) ; detail_seance → renfo pour une
  séance. Muscles : 1 série compte pour 1 sur un muscle principal, ½ sur un secondaire. Métriques
  act.sets (séries), act.reps, act.volume (tonnage en kg), act.sets_effort (temps d'effort).
- Calendrier d'entraînement (si l'utilisateur a relié son calendrier : statut → calendrier) : les séances
  prévues et les courses de son calendrier Garmin Connect (ou d'un agenda iCal). Outil calendrier pour
  une période (passée ou à venir), chaque séance prévue avec son état : fait (une séance du même sport
  ce jour-là, seance_id), manque, aujourdhui, a_venir. semaine les donne aussi jour par jour (prevu).
  Le calendrier publié par Garmin ne contient que l'avenir : Foulée garde les jours passés tels qu'il
  les a lus.
"""

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

mcp = MCPServer(name="Foulée", instructions=INSTRUCTIONS, version=__version__)


def _period(debut: str | None, fin: str | None, jours: int = 30) -> tuple[date, date]:
    return analysis.resolve_period(debut, fin, jours)


def _check_metrics(keys: list[str]) -> list[str]:
    unknown = [k for k in keys if not metrics.exists(k)]
    if unknown:
        raise ValueError(f"Métrique(s) inconnue(s) : {', '.join(unknown)}. Voir catalogue_metriques.")
    return keys


# ----------------------------------------------------------------- profils
def _who() -> str:
    return utilisateurs.card(utilisateurs.current())["prenom"]


@mcp.tool(name="utilisateurs", annotations=READ)
def lister_utilisateurs() -> dict[str, Any]:
    """Profils que Claude peut lire, et celui sur lequel portent les outils en ce moment."""
    current = utilisateurs.current()["id"]
    allowed = utilisateurs.claude_profiles()
    others = len(utilisateurs.profiles()) - len(allowed)
    return {
        "profils": [{"prenom": c["prenom"], "principal": c["principal"], "en_cours": c["id"] == current}
                    for c in (utilisateurs.card(p) for p in allowed)],
        "non_accessibles": others,
        "note": ("Les autres profils n'autorisent pas Claude à lire leurs données." if others else
                 "Tous les profils de Foulée sont accessibles."),
    }


@mcp.tool(annotations=WRITE)
def changer_utilisateur(prenom: str) -> dict[str, Any]:
    """Fait porter les outils sur un autre profil (prénom), s'il autorise Claude à lire ses données."""
    wanted = " ".join(prenom.split()).casefold()
    for entry in utilisateurs.claude_profiles():
        if utilisateurs.card(entry)["prenom"].casefold() == wanted:
            config.set_process_profile(entry)
            return {"utilisateur": _who(), "message": f"Les outils portent maintenant sur le profil de {_who()}."}
    names = ", ".join(utilisateurs.card(p)["prenom"] for p in utilisateurs.claude_profiles())
    raise ValueError(f"Pas de profil accessible nommé « {prenom} ». Profils accessibles : {names or 'aucun'}.")


# ------------------------------------------------------------------- état
def _withings_state(conn) -> dict[str, Any]:
    from .withings import vue

    info = vue.status(conn)
    first = conn.execute("SELECT MIN(date) AS a, MAX(date) AS b FROM daily WHERE source = 'withings'").fetchone()
    return {"connecte": info["connecte"], "mesures": info["familles"], "derniere_synchro": info["derniere_synchro"],
            "acces_refuse_depuis": (info["refus"] or {}).get("depuis"), "du": first["a"], "au": first["b"]}


def _strava_state() -> dict[str, Any]:
    """Strava est-il branché ? Ses séances ne sont jamais transmises à Claude par Foulée."""
    from .strava import client as strava_client

    return {"connecte": strava_client.connected(),
            "note": "Foulée ne transmet aucune donnée Strava à Claude : l'API de Strava l'interdit (API Policy, § 5.3). "
                    "Les séances Strava s'affichent dans l'interface de Foulée ; pour en parler avec Claude, "
                    "l'utilisateur peut brancher le connecteur Strava officiel dans Claude."}


@mcp.tool(annotations=READ)
def statut() -> dict[str, Any]:
    """État du hub : dernière synchro, période couverte, volumes, réglages utiles (VMA, objectif, FC)."""
    with db.session() as conn:
        settings = db.get_settings(conn)
        first = conn.execute("SELECT MIN(date) AS a, MAX(date) AS b FROM daily WHERE source = 'garmin'").fetchone()
        acts = conn.execute("SELECT COUNT(*) AS n, MIN(date) AS a, MAX(date) AS b FROM activities").fetchone()
        return {
            "version": __version__,
            "utilisateur": _who(),
            "mode_demo": config.is_demo(),
            "cle_api_garmin": "présente" if vault.has_key() else "absente",
            "withings": _withings_state(conn),
            "strava": _strava_state(),
            # relié ou non, dernière lecture, ce qui vient (jamais le lien du calendrier : il est secret)
            "calendrier": calendrier.status(conn),
            "synchro": sync_module.last_sync_info(conn),
            # état de chaque source (ok, ko, attente) avec le message de la dernière synchro qui n'a pas abouti
            "connexions": [{k: c.get(k) for k in ("nom", "etat", "texte", "erreur", "derniere_reussie")}
                           for c in sync_module.connections(conn)],
            "donnees_quotidiennes": {"du": first["a"], "au": first["b"]},
            "seances": {"nombre": acts["n"], "du": acts["a"], "au": acts["b"]},
            "aujourdhui": date.today().isoformat(),
            "vma_kmh": settings.get("vma_kmh"),
            "objectif": analysis.objective(settings),
            "profil_fc": {k: v for k, v in analysis.hr_profile(conn, settings).items() if k != "garmin"},
            "horaires": schedule.describe(settings["horaires"]),
        }


@mcp.tool(annotations=WRITE)
def synchroniser(depuis: str | None = None) -> dict[str, Any]:
    """Lance une synchro Garmin (incrémentale, ou depuis une date AAAA-MM-JJ). Attend jusqu'à ~50 s."""
    if config.is_demo():
        return {"statut": "demo", "message": "Mode démo : pas de synchro."}
    if not vault.has_key():
        return {"statut": "erreur", "message": "Aucune clé API Garmin : l'utilisateur doit l'ajouter dans Foulée (Réglages → Clé API Garmin)."}
    box: dict[str, Any] = {}
    # Strava n'est jamais synchronisé depuis Claude : ses données ne sont pas pour l'IA (règles de Strava)
    sources = [s for s in sync_module.active_sources() if s != "strava"]

    def work() -> None:
        try:
            box["resultat"] = sync_module.run(since=analysis.to_date(depuis) if depuis else None, sources=sources)
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
                "(ex. 'course', 'trail', 'pied' = course + trail). Toute valeur brute de Garmin s'utilise aussi "
                "comme métrique (« garmin:<flux>:<chemin> ») : voir champs_garmin.",
    }


@mcp.tool(annotations=READ)
def champs_garmin() -> dict[str, Any]:
    """Toutes les valeurs numériques trouvées dans les réponses de Garmin gardées par Foulée, avec un exemple.
    Chaque clé (« garmin:<flux>:<chemin> ») s'utilise comme une métrique dans serie, correlation, etc."""
    with db.session(readonly=True) as conn:
        fields = analysis.raw_fields(conn)
    return {"champs": [{k: f[k] for k in ("key", "label", "exemple")} for f in fields], "flux": metrics.RAW_KINDS}


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
    """Compare les métriques d'un poste de travail à l'autre (matin, soir, nuit… d'après les horaires) :
    moyenne, médiane, écart-type par poste, écart et taille d'effet entre les postes extrêmes.
    jours_ouvres=False compte aussi les jours de repos (rattachés au poste de leur semaine)."""
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
        "autres_mesures": {m["label"]: m["affiche"] for m in detail.get("mesures", [])},
        "telechargement_fit": status,
    })
    if detail.get("renfo"):
        compact["renfo"] = _renfo_session(detail["renfo"])
    return compact


def _set_text(e: dict) -> str:
    """« 4 × 8 répétitions », « 4 × 30 s », « 64 répétitions en 10 séries », avec la charge."""
    d = e["detail"]
    if d.get("mode") == "temps":
        text = f"{e['series']} × {metrics.fmt_duration(d['par_serie_s'])}"
    elif d.get("par_serie"):
        text = f"{e['series']} × {d['par_serie']} répétitions"
    elif e["repetitions"]:
        text = f"{e['repetitions']} répétitions en {e['series']} séries"
    else:
        text = f"{e['series']} série{'s' if e['series'] > 1 else ''}"
    if e.get("charge_max_kg"):
        text += f", {e['charge_max_kg']:g} kg"
    return text


def _muscles_text(load: dict[str, float]) -> dict[str, float]:
    return {renfo.MUSCLE_LABELS[m]: v for m, v in sorted(load.items(), key=lambda kv: -kv[1])}


def _renfo_session(data: dict) -> dict[str, Any]:
    return {
        "exercices": [{"nom": e["nom"], "nom_garmin": e["nom_garmin"], "series": _set_text(e),
                       "tonnage_kg": e["tonnage_kg"], "temps_effort": metrics.fmt_duration(e["duree_s"]),
                       "muscles": [m["nom"] + ("" if m["role"] == "principal" else " (secondaire)")
                                   for m in e["muscles"]]}
                      for e in data["exercices"]],
        "muscles_series": _muscles_text(data["muscles"]),
        "totaux": {"series": data["series"], "repetitions": data["repetitions"], "tonnage_kg": data["tonnage_kg"],
                   "temps_effort": metrics.fmt_duration(data["effort_s"]) if data["effort_s"] else None},
    }


@mcp.tool(name="renfo", annotations=READ)
def renfo_period(debut: str | None = None, fin: str | None = None) -> dict[str, Any]:
    """Renfo sur une période (30 jours par défaut) : séances, exercices (séries, répétitions, charge, et leur
    évolution séance après séance), muscles travaillés (en séries : 1 si muscle principal, ½ si secondaire),
    muscles peu ou pas travaillés, et séances de renfo par semaine sur les 12 dernières semaines."""
    a, b = _period(debut, fin, 30)
    with db.session(readonly=True) as conn:
        data = renfo.period(conn, a, b)
    exercises = []
    for e in data["exercices"]:
        exercises.append({
            "nom": e["nom"], "nom_garmin": e["nom_garmin"], "seances": e["seances"], "series": e["series"],
            "repetitions": e["repetitions"], "charge_max_kg": e["charge_max_kg"], "tonnage_kg": e["tonnage_kg"],
            "muscles_principaux": [m["nom"] for m in e["muscles"] if m["role"] == "principal"],
            "evolution": [{"date": h["date"], "series": h["series"], "repetitions": h["repetitions"],
                           "par_serie": h["par_serie"], "par_serie_s": h["par_serie_s"], "charge_kg": h["charge_kg"]}
                          for h in e["historique"]][-12:],
        })
    worked = data["muscles"]
    return {
        "periode": {"debut": data["debut"], "fin": data["fin"]},
        "totaux": {"seances": data["nb_seances"], "series": data["series"], "repetitions": data["repetitions"],
                   "tonnage_kg": data["tonnage_kg"],
                   "temps_effort": metrics.fmt_duration(data["effort_s"]) if data["effort_s"] else None},
        "seances": [{k: s[k] for k in ("id", "date", "nom", "exercices", "series", "tonnage_kg")}
                    for s in data["seances"]],
        "muscles_series": _muscles_text(worked),
        "muscles_non_travailles": [label for key, label in renfo.MUSCLES if not worked.get(key)],
        "exercices": exercises,
        "semaines": [{"semaine_du": w["debut"], "seances": w["seances"], "series": w["series"]}
                     for w in data["semaines"]],
        "lecture": "Séries par muscle : 1 série compte pour 1 sur un muscle principal, ½ sur un secondaire ; "
                   "échauffement et étirements comptent au plus ½.",
    }


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


# ------------------------------------------------------------- accueil
@mcp.tool(annotations=READ)
def allures_vma(vma: float | None = None, test_vameval: str | None = None, comparer: float | None = None) -> dict[str, Any]:
    """Tableau d'allures du club : allures (min/km, secondes tronquées) et vitesses de 55 à 120 % de la VMA,
    temps de passage sur piste (200 à 800 m, 85 à 120 %) et lecture d'un test VAMEVAL (« 12:40 »).
    vma : VMA à utiliser (par défaut celle des réglages) ; comparer : une seconde VMA à mettre en regard."""
    with db.session(readonly=True) as conn:
        settings = db.get_settings(conn)
    if vma:
        settings = {**settings, "vma_kmh": vma}
    return analysis.paces_table(settings, comparer, test_vameval)


@mcp.tool(annotations=READ)
def forme_du_jour(date_jour: str | None = None) -> dict[str, Any]:
    """Signaux de récupération d'un jour (FC de repos, VFC, sommeil, Body Battery, fraîcheur, SpO2),
    chacun face aux habitudes de l'utilisateur, avec une phrase de synthèse. Pas un avis médical."""
    with db.session(readonly=True) as conn:
        return analysis.day_form(conn, analysis.to_date(date_jour) if date_jour else None, db.get_settings(conn))


@mcp.tool(annotations=READ)
def semaine(date_jour: str | None = None) -> dict[str, Any]:
    """Semaine (lundi → dimanche) contenant ce jour : postes de travail, séances, totaux face aux 4 semaines d'avant."""
    with db.session(readonly=True) as conn:
        return analysis.week_summary(conn, analysis.to_date(date_jour) if date_jour else None, db.get_settings(conn))


@mcp.tool(name="calendrier", annotations=READ)
def calendrier_entrainement(debut: str | None = None, fin: str | None = None) -> dict[str, Any]:
    """Calendrier d'entraînement (lien iCal relié dans les Réglages : calendrier Garmin Connect ou autre agenda) :
    séances prévues et courses de la période, chacune avec son état (fait + seance_id, manque, aujourdhui,
    a_venir), le bilan (prévues, faites, manquées), la prochaine course. Sans dates : les 7 derniers jours et
    les 28 prochains."""
    today = date.today()
    a = analysis.to_date(debut) if debut else today - timedelta(days=7)
    b = analysis.to_date(fin) if fin else today + timedelta(days=28)
    if b < a:
        a, b = b, a
    if (b - a).days > 400:
        return {"erreur": "Période trop longue : 400 jours au plus."}
    with db.session(readonly=True) as conn:
        state = calendrier.status(conn)
        if not state["lie"] and not calendrier.plan(conn, a, b):
            return {"lie": False, "message": "Aucun calendrier d'entraînement relié : l'utilisateur peut coller le lien "
                                             "de son calendrier Garmin Connect publié dans Foulée (Réglages → "
                                             "Calendrier)."}
        items = calendrier.plan(conn, a, b)
    out = {"du": a.isoformat(), "au": b.isoformat(), "evenements": items, "bilan": calendrier.tally(items),
           "prochaine_course": state["prochaine_course"], "derniere_lecture": state["lu_le"],
           "nom_du_calendrier": state["nom"]}
    if _strava_state()["connecte"]:
        out["note"] = ("« fait » ne tient compte que des séances de la base Garmin : celles venues de Strava ne sont "
                       "jamais transmises à Claude (règles de Strava).")
    return out


@mcp.tool(annotations=READ)
def records(debut: str | None = None, fin: str | None = None, sport: str = "pied") -> dict[str, Any]:
    """Meilleurs temps sur 1 km, 1 mile, 5 km, 10 km, semi… (calculés par Garmin pour chaque sortie) dans la
    période, face au record de tout l'historique. Sans dates : tout l'historique."""
    with db.session(readonly=True) as conn:
        return analysis.records(conn, analysis.to_date(debut) if debut else None,
                                analysis.to_date(fin) if fin else None, sport)


@mcp.tool(annotations=READ)
def horaires(debut: str | None = None, fin: str | None = None) -> dict[str, Any]:
    """Horaires de travail : modèle, postes et heures, puis le planning jour par jour (poste, repos ou congés)."""
    a, b = _period(debut, fin, 14)
    with db.session(readonly=True) as conn:
        settings = db.get_settings(conn)
    plan = schedule.Schedule.of(settings)
    return {**schedule.describe(settings["horaires"]), "jours": [plan.day(d) for d in analysis.days_between(a, b)]}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
def journee_detail(donnee: str = "fc", date_jour: str | None = None) -> dict[str, Any]:
    """Courbe d'une journée : donnee = 'fc' (FC minute par minute), 'body_battery', 'sommeil' (phases de la
    nuit, FC, VFC, SpO2…) ou 'vfc' (relevés de la nuit). Demandée à Garmin si elle n'est pas encore gardée."""
    if donnee not in intraday.KINDS:
        return {"erreur": f"donnee : {', '.join(intraday.KINDS)}"}
    with db.session() as conn:
        data = intraday.day_detail(conn, donnee, analysis.to_date(date_jour) if date_jour else date.today())
    for key in ("points", "fc", "vfc", "spo2", "respiration", "stress", "body_battery"):
        if isinstance(data.get(key), list) and len(data[key]) > 300:
            step = len(data[key]) // 300 + 1
            data[key] = data[key][::step]
    return data


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
    "calendar_events": "Calendrier d'entraînement relié (séances prévues et courses) : date, start_local (vide : "
                       "journée entière), end_local, title, description, location, kind (seance, course, autre), "
                       "sport (famille devinée du titre). L'outil calendrier y ajoute l'état fait / manqué.",
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
    # Jamais d'autre base que celle de Foulée (le cache Strava n'est pas pour Claude : règles de Strava)
    conn.set_authorizer(lambda action, *args: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ATTACH
                        else sqlite3.SQLITE_OK)
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
@mcp.tool(name="reglages", annotations=READ)
def lire_reglages() -> dict[str, Any]:
    """Réglages actuels (VMA, FC, objectif, horaires de travail, zones FC et d'allure, club FFA…).

    club_resume (si le club est coché) : saison FFA en cours, liens vers le classement du club sur athle.fr
    (saison en cours et précédente), sa page, son site, et l'état de la licence (jours restants, à renouveler).
    Foulée ne lit pas athle.fr : ces liens s'ouvrent dans le navigateur.
    """
    with db.session(readonly=True) as conn:
        settings = db.get_settings(conn)
    summary = club.summary(settings.get("club"))
    if summary:
        settings["club_resume"] = {k: summary[k] for k in ("saison_label", "liens", "licence")}
    return settings


@mcp.tool(annotations=WRITE)
def modifier_reglages(changements: dict[str, Any]) -> dict[str, Any]:
    """Modifie des réglages (ex. {"vma_kmh": 16.5} ou {"objectif": {"temps_cible": "1:24:00"}}).

    Un réglage composé est complété, pas remplacé : {"horaires": {"conges": [...]}} ne touche qu'aux congés.
    Zones : {"zones_fc": {"methode": "pct_reserve", "pct": [50, 60, 70, 80, 90]}} (méthodes garmin, pct_max,
    pct_reserve, pct_seuil, bornes) ; {"zones_allure": {"methode": "pct_vma", "pct": [70, 80, 88, 95]}}.
    Club FFA : {"club": {"actif": true, "numero": "012345", "nom": "…"}} ajoute la vue « Mon club » (numéro de
    club de la licence, 6 chiffres) ; {"club": {"actif": false}} la retire en gardant les informations.
    Synchro automatique : {"synchro_auto": {"garmin": 180, "withings": 180}}, un délai par source en minutes, de 30 à
    720 (sources : garmin, withings, strava, calendrier) ; 3 heures est le bon compromis (plus rapproché, Foulée
    sollicite Garmin et Withings pour rien).
    Les calculs dépendants (zones, TRIMP, charge) sont refaits aussitôt.
    """
    with db.session() as conn:
        try:
            settings, recalcul = reglages.apply(conn, changements, merge=True)
        except reglages.SettingsError as exc:
            return {"erreur": str(exc), "reglages_possibles": sorted(db.DEFAULT_SETTINGS)}
        if recalcul:
            analysis.refresh_all_activities(conn, settings)
            conn.commit()
    return {"reglages": settings, "recalcul_effectue": recalcul}


def start_profile() -> dict | None:
    """Profil de départ : le principal s'il autorise Claude, sinon le premier profil qui l'autorise."""
    allowed = utilisateurs.claude_profiles()
    principal = utilisateurs.principal()
    return principal if principal in allowed else (allowed[0] if allowed else None)


def serve() -> None:
    first = start_profile()
    if first:
        config.set_process_profile(first)
        with db.session():
            pass  # crée la base si besoin
    config.set_access_check(utilisateurs.check_claude_access)
    mcp.run()


if __name__ == "__main__":
    serve()
