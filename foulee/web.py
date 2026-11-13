"""Serveur web : l'API JSON de l'interface + les pages elles-mêmes.

Sur le PC, il n'écoute que sur 127.0.0.1 : aucun autre appareil ne peut s'y
connecter. Sur un serveur, Tailscale (« tailscale serve ») relaie l'interface en
HTTPS vers tes seuls appareils ; le serveur peut aussi écouter le réseau local
(FOULEE_ECOUTE=0.0.0.0), et les appareils de la maison passent alors par un mot de
passe (voir access.py). Ce qui arrive de la machine elle-même, dont Tailscale,
n'en demande jamais.

Deux protections en plus contre les sites web malveillants :
- l'en-tête Host doit être une adresse IP, localhost ou un nom de FOULEE_HOTES
  (le nom Tailscale du serveur) : c'est la parade au « DNS rebinding » ;
- toute requête qui modifie quelque chose doit porter l'en-tête X-Foulee,
  ce qu'un autre site ne peut pas ajouter sans autorisation du navigateur.

Profils : chaque requête vise le profil retenu par ce navigateur (cookie signé, voir
utilisateurs.py). Tant qu'aucun profil n'est choisi sur un appareil alors qu'il en faut un,
seules la liste des profils et la page de choix répondent.
"""

from __future__ import annotations

import contextvars
import ipaddress
import json
import mimetypes
import os
import secrets
import sqlite3
import sys
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import (
    __version__,
    access,
    analysis,
    calendrier,
    club,
    claude_desktop,
    coach,
    config,
    datadir,
    db,
    keyinput,
    metrics,
    profile,
    reglages,
    renfo,
    retours,
    schedule,
    updates,
    utilisateurs,
    vault,
    views,
)
from . import sync as sync_module
from .garmin import intraday
from .garmin.client import KEY_PAGE, GarminError, check_key
from .strava import cache as strava_cache
from .strava import client as strava_client
from .strava import sync as strava_sync
from .strava import vue as strava_vue
from .strava.client import StravaError
from .withings import client as withings_client
from .withings import vue as withings_vue
from .withings.client import WithingsError

DERIVED_KEYS = reglages.DERIVED


class SyncJob:
    """Une synchro lancée depuis l'interface, suivie par sondage."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state: dict[str, Any] = {"en_cours": False, "message": "", "progression": None, "resultat": None,
                                      "erreur": None}

    def start(self, since: date | None = None, sources: list[str] | None = None) -> bool:
        with self.lock:
            if self.state["en_cours"] or sync_module.is_running():
                return False
            self.state = {"en_cours": True, "message": "Démarrage…", "progression": 0.0, "resultat": None,
                          "erreur": None, "debut": time.time(), "sources": sources}
        # La synchro vise le profil de celui qui la lance (requête, synchro automatique…)
        context = contextvars.copy_context()
        threading.Thread(target=context.run, args=(self._run, since, sources), name="foulee-synchro",
                         daemon=True).start()
        return True

    def _progress(self, message: str, fraction: float | None = None) -> None:
        with self.lock:
            self.state["message"] = message
            if fraction is not None:
                self.state["progression"] = round(fraction, 3)

    def _run(self, since: date | None, sources: list[str] | None = None) -> None:
        try:
            extra = {"sources": sources} if sources else {}  # par défaut : toutes les sources actives
            result = sync_module.run(since=since, progress=self._progress, **extra)
            with self.lock:
                self.state.update({"en_cours": False, "resultat": result, "message": "Synchro terminée",
                                   "progression": 1.0})
        except Exception as exc:  # affiché tel quel dans l'interface
            with self.lock:
                self.state.update({"en_cours": False, "erreur": str(exc), "message": "Échec de la synchro"})

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.state)


class SyncJobs:
    """Une synchro suivie par profil : deux personnes peuvent synchroniser en même temps."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, SyncJob] = {}

    def get(self, profile_id: str | None = None) -> SyncJob:
        key = profile_id or utilisateurs.current()["id"]
        with self._lock:
            return self._jobs.setdefault(key, SyncJob())


def _period(start: str | None, end: str | None, days: int | None = None) -> tuple[date, date]:
    try:
        return analysis.resolve_period(start, end, days)
    except ValueError as exc:
        raise HTTPException(400, f"Date illisible : {exc}") from exc


def _metric(key: str) -> str:
    if not metrics.exists(key):
        raise HTTPException(400, f"Métrique inconnue : {key}")
    return key


def _day(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return analysis.to_date(text)
    except ValueError as exc:
        raise HTTPException(400, f"Date illisible : {text}") from exc


def _refresh_in_background() -> None:
    """Recalcule zones, TRIMP et charge de toutes les séances après un changement de réglage."""
    def work() -> None:
        with db.session() as conn:
            analysis.refresh_all_activities(conn, db.get_settings(conn))
            conn.commit()
    context = contextvars.copy_context()  # le profil qui a changé ses réglages
    threading.Thread(target=context.run, args=(work,), name="foulee-recalcul", daemon=True).start()


STARTED_AT = time.time()  # permet à l'interface de voir que le serveur a redémarré
LOCAL_HOSTS = ("127.0.0.1", "localhost", "testserver")
PUBLIC_PATHS = {"/connexion", "/api/connexion"}  # seules pages ouvertes avant le mot de passe
# Ce qui répond tant que ce navigateur n'a pas choisi son profil (page « Qui es-tu ? »)
BEFORE_PROFILE = ("/api/bootstrap", "/api/utilisateurs", "/api/connexion", "/api/deconnexion", "/api/retours")

mimetypes.add_type("application/manifest+json", ".webmanifest")


def host_name(header: str | None) -> str:
    """Nom d'hôte d'un en-tête Host, sans le port (« 192.168.0.19:8770 » → « 192.168.0.19 »)."""
    host = (header or "").strip().lower()
    if host.startswith("["):  # IPv6 : [::1]:8770
        return host[1:].split("]", 1)[0]
    if host.count(":") == 1:
        host = host.rsplit(":", 1)[0]
    return host.rstrip(".")


def allowed_hosts() -> set[str]:
    """Noms d'hôte acceptés : la machine elle-même, plus ceux de FOULEE_HOTES (séparés par des virgules)."""
    names = {host_name(name) for name in os.environ.get("FOULEE_HOTES", "").split(",")}
    return set(LOCAL_HOSTS) | {name for name in names if name}


def host_allowed(host: str, names: set[str]) -> bool:
    if host in names:
        return True
    try:
        ipaddress.ip_address(host)  # une adresse IP ne peut pas servir au « DNS rebinding »
        return True
    except ValueError:
        return False


def update_dir() -> Path | None:
    """Dossier d'échange avec le service de mise à jour du serveur (FOULEE_MAJ), s'il existe."""
    value = os.environ.get("FOULEE_MAJ")
    return Path(value) if value and Path(value).is_dir() else None


def create_app() -> FastAPI:
    app = FastAPI(title="Foulée", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    jobs = SyncJobs()
    app.state.sync_jobs = jobs  # l'application de bureau s'en sert pour la synchro automatique
    app.state.quit = None     # fourni par l'application de bureau : arrêt propre
    demo_build = {"en_cours": False, "erreur": None}
    with db.session():
        pass  # crée la base et les vues par défaut si besoin

    hosts = allowed_hosts()
    throttle = access.Throttle()
    code_throttle = access.Throttle()  # codes de profil : 5 essais, puis une minute d'attente

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if not host_allowed(host_name(request.headers.get("host")), hosts):
            return JSONResponse({"detail": "Hôte refusé"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-foulee") != "1":
            return JSONResponse({"detail": "En-tête X-Foulee manquant"}, status_code=403)
        # Tailscale et la console du serveur arrivent par la machine elle-même : pas de mot de passe
        request.state.local = access.is_local_client(request.client.host if request.client else None)
        path = request.url.path
        if not request.state.local and path not in PUBLIC_PATHS:
            if not access.is_enabled():
                if path.startswith("/api/"):
                    return JSONResponse({"detail": "Accès depuis le réseau local désactivé"}, status_code=403)
                return FileResponse(config.STATIC_DIR / "reseau-desactive.html", status_code=403,
                                    headers={"Cache-Control": "no-store"})
            if not access.cookie_valid(request.cookies.get(access.COOKIE)):
                if path.startswith("/api/"):
                    return JSONResponse({"detail": "Connexion requise"}, status_code=401)
                return RedirectResponse("/connexion", status_code=303)
        # Profil de ce navigateur : tout ce que fait la requête vise ses données
        profile, required = utilisateurs.resolve(request.cookies.get(utilisateurs.cookie_name()))
        request.state.profil = profile
        request.state.profil_requis = required
        if required and path.startswith("/api/") and not path.startswith(BEFORE_PROFILE):
            return JSONResponse({"detail": "Choisis d'abord ton profil.", "profil_requis": True}, status_code=409)
        expected = request.headers.get("x-foulee-profil")
        if expected and profile and expected != profile["id"] and path.startswith("/api/"):
            # La page a été ouverte pour un autre profil (changé depuis un autre onglet) : elle se recharge
            return JSONResponse({"detail": "Le profil a changé dans un autre onglet : la page se recharge.",
                                 "profil_requis": True}, status_code=409)
        token = config.set_profile(profile)
        try:
            response = await call_next(request)
        finally:
            config.reset_profile(token)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/static/"):
            # Le navigateur revérifie chaque fichier (réponse 304 s'il n'a pas changé) :
            # après une mise à jour, le téléphone charge tout de suite la nouvelle version.
            response.headers["Cache-Control"] = "no-cache"
        return response

    # ------------------------------------------------------------- démarrage
    @app.get("/api/bootstrap")
    def bootstrap(request: Request) -> dict:
        if request.state.profil_requis:  # « Qui es-tu ? » : rien des données de personne
            return {"app": "Foulée", "version": __version__, "demo": config.is_demo(), "profil_requis": True,
                    "utilisateurs": utilisateurs.cards(), "acces": "local" if request.state.local else "reseau",
                    "machine": "pc" if sys.platform == "win32" else "serveur", "retours": retours.info(),
                    "demarre_le": STARTED_AT}
        me = request.state.profil
        with db.session() as conn:
            settings = db.get_settings(conn)
            return {
                "app": "Foulée", "version": __version__, "demo": config.is_demo(),
                "aujourdhui": date.today().isoformat(),
                "metriques": metrics.catalog_json() + views.raw_metrics_in_use(conn), "sports": metrics.SPORTS,
                "tuiles": views.TILE_TYPES, "icones": views.ICONS, "periodes": views.PERIODES,
                "vues": views.list_views(conn), "reglages": settings,
                "categories_tuiles": views.TILE_CATEGORIES, "categories_metriques": metrics.CATEGORIES,
                "objectif": analysis.objective(settings), "profil_fc": analysis.hr_profile(conn, settings),
                "club": club.summary(settings.get("club")), "club_licences": club.LICENCE_TYPES,
                "garmin_profil": analysis.garmin_profile(conn),
                "planning": schedule.describe(settings["horaires"]),
                "modeles_horaires": schedule.MODELES,
                "profil": {**(settings.get("profil") or {}), "prenom_affiche": profile.first_name(conn, settings),
                           **profile.info(), "garmin": profile.garmin_identity(conn)["photo_url"] is not None},
                "synchro": sync_module.last_sync_info(conn), "cle": vault.has_key() or config.is_demo(),
                "connexions": sync_module.connections(conn),
                "dossier_donnees": str(config.data_dir()),
                "machine": "pc" if sys.platform == "win32" else "serveur",
                "acces": "local" if request.state.local else "reseau",
                "installation": updates.mode(),
                "application": app.state.quit is not None,
                "cle_refusee": sync_module.key_refused(conn),
                "withings": {"connecte": withings_client.connected(), "refus": withings_vue.refused(conn)},
                "strava": {"connecte": strava_client.connected() or (config.is_demo() and strava_cache.path().exists()),
                           "appli": strava_client.has_app(), "refus": strava_vue.refused(conn),
                           "seances": strava_sync.counts()["seules"] if strava_cache.path().exists() else 0},
                "calendrier": calendrier.status(conn),  # jamais le lien (secret), même masqué
                "coach": coach.light(conn),  # relais du club : rôle et nom, jamais le jeton
                "demarre_le": STARTED_AT,
                "maj": update_dir() is not None,
                "volumes": db.table_counts(conn),
                "premiere_date": conn.execute("SELECT MIN(date) AS d FROM daily").fetchone()["d"],
                "retours": retours.info(),
                "utilisateur": {"id": me["id"], "principal": bool(me.get("principal")), "code": bool(me.get("code")),
                                "claude": utilisateurs.claude_allowed(me)},
                "utilisateurs": utilisateurs.cards(me["id"]),
                "claude_possible": sys.platform in ("win32", "darwin"),
            }

    # ------------------------------------------------------------ séries & co
    @app.get("/api/series")
    def get_series(metric: str, start: str | None = None, end: str | None = None, agg: str = "jour",
                   fn: str | None = None, sport: str | None = None, smooth: int = 0) -> dict:
        a, b = _period(start, end)
        sport = None if sport in (None, "", "tous") else sport
        with db.session(readonly=True, strava=True) as conn:
            data = analysis.series(conn, _metric(metric), a, b, agg, None if fn in (None, "", "auto") else fn,
                                   sport, smooth)
            data["sources"] = analysis.sources_for(conn, [metric], a, b, sport)
            return data

    @app.get("/api/kpi")
    def get_kpi(metric: str, as_of: str | None = None, baseline: int = 30, window: str | None = None) -> dict:
        day = analysis.to_date(as_of) if as_of else None
        with db.session(readonly=True, strava=True) as conn:
            data = analysis.kpi(conn, _metric(metric), day, baseline, None if window in (None, "", "auto") else window)
            end = day or date.today()
            data["sources"] = analysis.sources_for(conn, [metric], end - timedelta(days=max(7, baseline)), end)
            return data

    @app.get("/api/load")
    def get_load(start: str | None = None, end: str | None = None) -> dict:
        a, b = _period(start, end)
        with db.session(readonly=True, strava=True) as conn:
            data: dict[str, Any] = {key: analysis.series(conn, key, a, b)["points"]
                                    for key in ("ctl", "atl", "tsb", "acwr", "load_day")}
            data["sources"] = analysis.sources_for(conn, ["ctl"], a, b)
            return data

    @app.get("/api/zones")
    def get_zones(kind: str = "fc", start: str | None = None, end: str | None = None, group: str = "semaine",
                  sport: str | None = None) -> dict:
        a, b = _period(start, end)
        sport = None if sport in (None, "", "tous") else sport
        with db.session(readonly=True, strava=True) as conn:
            settings = db.get_settings(conn)
            data = analysis.zones(conn, kind, a, b, group, sport, settings)
            data["sources"] = analysis.sources_for(conn, [], a, b, sport, activities=True)
            return data

    @app.get("/api/calendar")
    def get_calendar(metric: str, start: str | None = None, end: str | None = None) -> dict:
        a, b = _period(start, end, 180)
        with db.session(readonly=True, strava=True) as conn:
            values = analysis.daily_values(conn, _metric(metric), a, b)
            sources = analysis.sources_for(conn, [metric], a, b)
        meta = metrics.get(metric)
        return {"metric": metric, "label": meta.label, "fmt": meta.fmt, "unit": meta.unit, "better": meta.better,
                "start": a.isoformat(), "end": b.isoformat(), "points": sorted(values.items()), "sources": sources}

    @app.get("/api/scatter")
    def get_scatter(x: str, y: str, start: str | None = None, end: str | None = None, lag: int = 0) -> dict:
        a, b = _period(start, end)
        with db.session(readonly=True, strava=True) as conn:
            data = analysis.scatter(conn, _metric(x), _metric(y), a, b, db.get_settings(conn), lag)
            data["sources"] = analysis.sources_for(conn, [x, y], a, b)
            return data

    @app.get("/api/shifts")
    def get_shifts(metrics_list: str = "", start: str | None = None, end: str | None = None,
                   weekdays: int = 1) -> dict:
        keys = [_metric(k) for k in metrics_list.split(",") if k]
        a, b = _period(start, end, 180)
        with db.session(readonly=True, strava=True) as conn:
            data = analysis.shift_compare(conn, keys, a, b, db.get_settings(conn), bool(weekdays))
            data["sources"] = analysis.sources_for(conn, keys, a, b)
            return data

    @app.get("/api/fast-laps")
    def get_fast_laps(start: str | None = None, end: str | None = None) -> dict:
        a, b = _period(start, end, 120)
        with db.session(readonly=True, strava=True) as conn:
            settings = db.get_settings(conn)
            data = analysis.fast_laps(conn, a, b, settings)
            data["sources"] = analysis.sources_for(conn, [], a, b, "pied", activities=True)
        data["objectif"] = analysis.objective(settings)
        return data

    @app.get("/api/objective")
    def get_objective() -> dict:
        with db.session(readonly=True) as conn:
            return analysis.objective(db.get_settings(conn))

    # -------------------------------------------------------------- accueil
    @app.get("/api/forme")
    def get_form(day: str | None = None) -> dict:
        when = _day(day) or date.today()
        with db.session(readonly=True, strava=True) as conn:
            data = analysis.day_form(conn, when, db.get_settings(conn))
            keys = [i.get("metric") for i in data.get("items") or data.get("signaux") or [] if isinstance(i, dict)]
            data["sources"] = analysis.sources_for(conn, [k for k in keys if k], when - timedelta(days=30), when)
            return data

    @app.get("/api/semaine")
    def get_week(day: str | None = None) -> dict:
        when = _day(day) or date.today()
        with db.session(readonly=True, strava=True) as conn:
            data = analysis.week_summary(conn, when, db.get_settings(conn))
            monday = when - timedelta(days=when.weekday())
            data["sources"] = analysis.sources_for(conn, [], monday - timedelta(days=7), monday + timedelta(days=6),
                                                   activities=True)
            if data.get("plan"):
                data["sources"].append(calendrier.source(conn))
            return data

    @app.get("/api/calendrier")
    def get_planned(start: str | None = None, end: str | None = None) -> dict:
        """Calendrier d'entraînement sur une période : séances prévues et courses (avec leur état : fait, manqué,
        à venir), séances faites, bilan et prochaine course."""
        a, b = _period(start, end, 42)
        if (b - a).days > 400:
            raise HTTPException(400, "Période trop longue pour le calendrier (400 jours au plus).")
        with db.session(readonly=True, strava=True) as conn:
            rows = analysis.fetch_activities(conn, a, b)
            planned = calendrier.plan(conn, a, b, activities=rows)
            data = {
                **calendrier.status(conn), "debut": analysis.iso(a), "fin": analysis.iso(b),
                "evenements": planned, "bilan": calendrier.tally(planned),
                "seances": [{"id": r["id"], "date": r["date"], "heure": (r["start_local"] or "")[11:16] or None,
                             "sport": r["sport"], "sport_label": metrics.SPORTS.get(r["sport"], r["sport"]),
                             "nom": r["name"], "distance_km": round((r["distance_m"] or 0) / 1000, 1),
                             "duree": metrics.fmt_duration(r["duration_s"]), "d_plus": round(r["elev_gain_m"] or 0),
                             "source": r["source"]} for r in rows],
                "sources": analysis.sources_for(conn, [], a, b, activities=True),
            }
            if planned or data["lie"]:
                data["sources"].append(calendrier.source(conn))
            return data

    @app.get("/api/allures")
    def get_paces(comparer: float | None = None, test: str | None = None) -> dict:
        with db.session(readonly=True) as conn:
            settings = db.get_settings(conn)
        data = analysis.paces_table(settings, comparer, test or None)
        if test and not data["test"]:
            raise HTTPException(400, "Temps du test illisible : de 2:00 à 59:59 (minutes:secondes).")
        return data

    @app.get("/api/records")
    def get_records(start: str | None = None, end: str | None = None, sport: str | None = "pied") -> dict:
        with db.session(readonly=True) as conn:  # records : ceux que Garmin a mesurés
            data = analysis.records(conn, _day(start), _day(end), None if sport in (None, "", "tous") else sport)
        data["sources"] = [{"cle": "garmin", "nom": "Garmin", "appareils": []}]
        return data

    @app.get("/api/renfo")
    def get_renfo(start: str | None = None, end: str | None = None, semaines: int = 12) -> dict:
        """Bilan du renfo sur la période : séances, muscles travaillés, exercices et leur progression."""
        a, b = _period(start, end, 30)
        with db.session(readonly=True, strava=True) as conn:
            data = renfo.period(conn, a, b, max(4, min(int(semaines), 52)))
            data["sources"] = analysis.sources_for(conn, [], a, b, ",".join(renfo.SPORTS), activities=True)
            return data

    @app.get("/api/journee")
    def get_day_detail(donnee: str = "body_battery", day: str | None = None) -> dict:
        if donnee not in intraday.KINDS:
            raise HTTPException(400, f"Donnée inconnue : {donnee}")
        with db.session() as conn:  # écriture : la réponse de Garmin est gardée pour la prochaine fois
            data = intraday.day_detail(conn, donnee, _day(day) or date.today())
        data["sources"] = [{"cle": "garmin", "nom": "Garmin", "appareils": []}]
        return data

    # ------------------------------------------------------------- profils
    def remember(response: Response, entry: dict) -> Response:
        """Ce navigateur reste sur ce profil (à redonner après chaque changement de son code)."""
        response.set_cookie(utilisateurs.cookie_name(), utilisateurs.make_cookie(entry), path="/", httponly=True,
                            samesite="strict", max_age=utilisateurs.COOKIE_DAYS * 86400)
        return response

    def myself(request: Request) -> dict:
        if not request.state.profil:
            raise HTTPException(409, "Choisis d'abord ton profil.")
        return utilisateurs.get(request.state.profil["id"]) or request.state.profil

    def check_profile_code(request: Request, entry: dict, code: object) -> None:
        key = f"{request.client.host if request.client else '?'}|{entry['id']}"
        if code_throttle.blocked(key):
            raise HTTPException(429, "Trop d'essais : attends une minute avant de recommencer.")
        if not utilisateurs.check_code(entry, str(code or "")):
            code_throttle.failure(key)
            raise HTTPException(401, "Code incorrect.")
        code_throttle.success(key)

    def users_state(request: Request) -> dict:
        me = request.state.profil
        manager = utilisateurs.is_principal(me) if me else False
        return {"utilisateurs": utilisateurs.cards(me["id"] if me else None, details=manager),
                "courant": me["id"] if me else None, "gestion": manager, "max": utilisateurs.MAX_PROFILES}

    @app.get("/api/utilisateurs")
    def users_list(request: Request) -> dict:
        return users_state(request)

    @app.get("/api/utilisateurs/{profile_id}/photo")
    def user_photo(profile_id: str):
        entry = utilisateurs.get(profile_id)
        if not entry:
            raise HTTPException(404, "Profil introuvable.")
        with config.using_profile(entry):
            path = profile.photo_path()
        if not path.exists():
            raise HTTPException(404, "Pas de photo de profil")
        return FileResponse(path, media_type="image/jpeg",
                            headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})

    @app.post("/api/utilisateurs/choisir")
    def users_choose(request: Request, payload: dict = Body(...)) -> Response:
        """Passer sur un profil (son code s'il en a un) ; ce navigateur le retient."""
        entry = utilisateurs.get(str(payload.get("id") or ""))
        if not entry:
            raise HTTPException(404, "Profil introuvable.")
        if not (request.state.profil and request.state.profil["id"] == entry["id"]):
            check_profile_code(request, entry, payload.get("code"))
        return remember(JSONResponse({"ok": True, "id": entry["id"]}), entry)

    @app.put("/api/utilisateurs/moi")
    def users_me(request: Request, payload: dict = Body(...)) -> Response:
        """Son propre profil : code (le code actuel est demandé pour le changer) et accès de Claude Desktop."""
        me = myself(request)
        if "code" in payload:
            if me.get("code"):
                check_profile_code(request, me, payload.get("ancien"))
            try:
                me = utilisateurs.set_code(me["id"], payload.get("code") or None)
            except utilisateurs.ProfileError as exc:
                raise HTTPException(400, str(exc)) from exc
        if "claude" in payload:
            me = utilisateurs.set_claude(me["id"], bool(payload["claude"]))
        state = {**users_state(request), "utilisateur": {"id": me["id"], "principal": bool(me.get("principal")),
                                                         "code": bool(me.get("code")),
                                                         "claude": utilisateurs.claude_allowed(me)}}
        return remember(JSONResponse(state), me)

    @app.post("/api/utilisateurs")
    def users_create(request: Request, payload: dict = Body(...)) -> Response:
        require_principal(request)
        try:
            entry = utilisateurs.create(payload.get("prenom"), payload.get("code") or None)
        except utilisateurs.ProfileError as exc:
            raise HTTPException(400, str(exc)) from exc
        # Il faut désormais choisir son profil : le principal reste sur le sien dans ce navigateur
        me = utilisateurs.get(request.state.profil["id"])
        return remember(JSONResponse({**users_state(request), "cree": utilisateurs.card(entry)}), me)

    @app.put("/api/utilisateurs/{profile_id}")
    def users_rename(profile_id: str, request: Request, payload: dict = Body(...)) -> dict:
        require_principal(request)
        try:
            utilisateurs.rename(profile_id, payload.get("prenom"))
        except utilisateurs.ProfileError as exc:
            raise HTTPException(400, str(exc)) from exc
        return users_state(request)

    @app.delete("/api/utilisateurs/{profile_id}/code")
    def users_clear_code(profile_id: str, request: Request) -> Response:
        """Code oublié : le principal l'efface (sans le connaître)."""
        require_principal(request)
        try:
            entry = utilisateurs.set_code(profile_id, None)
        except utilisateurs.ProfileError as exc:
            raise HTTPException(404, str(exc)) from exc
        response = JSONResponse(users_state(request))
        return remember(response, entry) if entry["id"] == request.state.profil["id"] else response

    @app.delete("/api/utilisateurs/{profile_id}")
    def users_delete(profile_id: str, request: Request) -> dict:
        require_principal(request)
        try:
            report = utilisateurs.delete(profile_id)
        except utilisateurs.ProfileError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {**users_state(request), "supprime": report}

    @app.post("/api/club/fiche")
    def club_sheet(payload: dict = Body(...)) -> dict:
        """Lit la fiche « Coordonnées et contacts » copiée depuis la page du club sur athle.fr."""
        text = str(payload.get("texte") or "")
        if len(text) > 20000:
            raise HTTPException(400, "Texte trop long : copie seulement le cadre « Coordonnées et contacts ».")
        found = club.parse_sheet(text)
        return {"champs": found, "trouves": len(found)}

    @app.get("/api/retours")
    def get_feedback_info() -> dict:
        """Où envoyer un retour, et si la page des sujets GitHub s'ouvre pour tout le monde."""
        return {**retours.info(), "visibilite": retours.visibility()}

    @app.get("/api/garmin/champs")
    def get_raw_fields() -> dict:
        with db.session(readonly=True) as conn:
            return {"champs": analysis.raw_fields(conn), "flux": metrics.RAW_KINDS}

    @app.get("/api/horaires")
    def get_schedule(start: str | None = None, end: str | None = None) -> dict:
        a, b = _period(start, end, 28)
        with db.session(readonly=True) as conn:
            settings = db.get_settings(conn)
        plan = schedule.Schedule.of(settings)
        return {"horaires": settings["horaires"], "jours": [plan.day(d) for d in analysis.days_between(a, b)]}

    # ---------------------------------------------------------------- profil
    def _profile_state(conn) -> dict:
        settings = db.get_settings(conn)
        return {**(settings.get("profil") or {}), "prenom_affiche": profile.first_name(conn, settings),
                **profile.info(), "garmin": profile.garmin_identity(conn)["photo_url"] is not None}

    @app.get("/api/profil")
    def get_profile() -> dict:
        with db.session(readonly=True) as conn:
            return _profile_state(conn)

    @app.put("/api/profil")
    def put_profile(payload: dict = Body(...)) -> dict:
        with db.session() as conn:
            current = db.get_settings(conn).get("profil") or {}
            reglages.apply(conn, {"profil": {**current, **payload}})
            return _profile_state(conn)

    @app.get("/api/profil/photo")
    def get_photo():
        path = profile.photo_path()
        if not path.exists():
            raise HTTPException(404, "Pas de photo de profil")
        return FileResponse(path, media_type="image/jpeg",
                            headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})

    @app.put("/api/profil/photo")
    async def put_photo(request: Request) -> dict:
        if int(request.headers.get("content-length") or 0) > profile.MAX_UPLOAD:
            raise HTTPException(413, "Image trop lourde : 8 Mo au plus.")
        data = await request.body()
        try:
            profile.save_photo(data)
        except profile.PhotoError as exc:
            raise HTTPException(400, str(exc)) from exc
        with db.session() as conn:
            return _profile_state(conn)

    @app.delete("/api/profil/photo")
    def delete_photo() -> dict:
        profile.delete_photo()
        with db.session() as conn:
            current = db.get_settings(conn).get("profil") or {}
            if current.get("logo") == "photo":
                reglages.apply(conn, {"profil": {**current, "logo": "foulee"}})
            return _profile_state(conn)

    @app.post("/api/profil/photo/garmin")
    def garmin_photo() -> dict:
        if config.is_demo():
            raise HTTPException(400, "Pas de photo Garmin en mode démo.")
        with db.session() as conn:
            try:
                profile.fetch_garmin_photo(conn)
            except profile.PhotoError as exc:
                raise HTTPException(400, str(exc)) from exc
            return _profile_state(conn)

    # ------------------------------------------------------- export / import
    @app.get("/api/reglages/export")
    def export_settings(vues: int = 1, photo: int = 1) -> JSONResponse:
        with db.session(readonly=True) as conn:
            data = reglages.export(conn, with_views=bool(vues), with_photo=bool(photo))
        machine = "pc" if sys.platform == "win32" else "serveur"
        name = f"foulee-reglages-{machine}-{date.today().isoformat()}.json"
        return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/api/reglages/import")
    def import_settings(payload: dict = Body(...)) -> dict:
        parts = {p for p in payload.get("parties") or ["reglages", "vues", "photo"] if p in ("reglages", "vues", "photo")}
        with db.session() as conn:
            try:
                report = reglages.import_(conn, payload.get("donnees"), parts=parts)
            except reglages.SettingsError as exc:
                raise HTTPException(400, str(exc)) from exc
        if report["recalcul"]:
            _refresh_in_background()
        return report

    # ---------------------------------------------------------------- séances
    @app.get("/api/activities")
    def get_activities(start: str | None = None, end: str | None = None, sport: str | None = None,
                       search: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        a = analysis.to_date(start) if start else None
        b = analysis.to_date(end) if end else None
        with db.session(readonly=True, strava=True) as conn:
            return analysis.activities_list(conn, a, b, None if sport in (None, "", "tous") else sport, search,
                                            min(limit, 500), offset)

    @app.get("/api/activities/{activity_id}")
    def get_activity(activity_id: str, fetch: int = 1) -> dict:
        status = strava_status = None
        if activity_id.startswith("strava:"):
            # Séance Strava : son détail et ses courbes, demandés à Strava s'ils manquent (gardés 48 heures)
            strava_status = strava_sync.ensure_detail(activity_id) if fetch else None
        else:
            with db.session() as conn:
                row = conn.execute("SELECT has_streams FROM activities WHERE id = ?", (activity_id,)).fetchone()
                if not row:
                    raise HTTPException(404, "Séance introuvable")
                if fetch and row["has_streams"] == 0 and vault.has_key() and not config.is_demo():
                    from .garmin.sync import ensure_streams

                    try:
                        status = ensure_streams(conn, activity_id)
                    except GarminError as exc:
                        status = f"téléchargement impossible : {exc}"
        with db.session(readonly=True, strava=True) as conn:
            detail = analysis.activity_detail(conn, activity_id, db.get_settings(conn))
            if detail is None:
                raise HTTPException(404, "Séance introuvable (une séance Strava n'est gardée que 48 heures après "
                                         "sa dernière synchro)." if activity_id.startswith("strava:") else
                                    "Séance introuvable")
            strava_vue.annotate(conn, detail)
            detail["sources"] = [{"cle": detail["source"], "nom": analysis.SOURCE_NAMES.get(detail["source"], ""),
                                  "appareils": [detail["appareil"]] if detail.get("appareil") else []}]
        detail["telechargement"] = status
        detail["strava_message"] = strava_status
        return detail

    @app.get("/api/activities/{activity_id}/streams")
    def get_streams(activity_id: str, max_points: int = 1500) -> dict:
        with db.session(readonly=True, strava=True) as conn:
            data = analysis.activity_streams(conn, activity_id, max(100, min(max_points, 6000)))
        if data is None and activity_id.startswith("strava:"):
            data = strava_sync.polyline_streams(activity_id)  # le tracé résumé de Strava, sans aucun appel
        if data is None:
            raise HTTPException(404, "Pas de courbes pour cette séance")
        return data

    # ------------------------------------------------------------------ vues
    @app.get("/api/views")
    def get_views() -> list[dict]:
        with db.session(readonly=True) as conn:
            return views.list_views(conn)

    @app.post("/api/views")
    def create_view(payload: dict = Body(...)) -> dict:
        with db.session() as conn:
            view_id = payload.get("id") or views.slugify(payload.get("name", "vue"))
            base, n = view_id, 2
            while conn.execute("SELECT 1 FROM views WHERE id = ?", (view_id,)).fetchone():
                view_id, n = f"{base}-{n}", n + 1
            return views.save_view(conn, view_id, payload.get("name", "Nouvelle vue"), payload.get("spec") or {},
                                   payload.get("icon"))

    @app.put("/api/views/{view_id}")
    def update_view(view_id: str, payload: dict = Body(...)) -> dict:
        with db.session() as conn:
            return views.save_view(conn, view_id, payload.get("name", "Vue"), payload.get("spec") or {},
                                   payload.get("icon"))

    @app.delete("/api/views/{view_id}")
    def remove_view(view_id: str) -> dict:
        with db.session() as conn:
            return {"supprimee": views.delete_view(conn, view_id)}

    @app.post("/api/views/reorder")
    def reorder(payload: dict = Body(...)) -> dict:
        with db.session() as conn:
            views.reorder_views(conn, [str(i) for i in payload.get("ids", [])])
            return {"ok": True}

    @app.post("/api/views/reset")
    def reset_views() -> list[dict]:
        with db.session() as conn:
            views.reset_default_views(conn)
            return views.list_views(conn)

    # --------------------------------------------------------------- réglages
    @app.get("/api/settings")
    def get_settings() -> dict:
        with db.session(readonly=True) as conn:
            return db.get_settings(conn)

    @app.put("/api/settings")
    def put_settings(request: Request, payload: dict = Body(...)) -> dict:
        allowed = set(db.DEFAULT_SETTINGS)
        if not utilisateurs.is_principal(request.state.profil):
            allowed.discard("canal_maj")  # réglage de l'installation : seul le principal le change
        changes = {k: v for k, v in payload.items() if k in allowed}
        with db.session() as conn:
            try:
                settings, recalcul = reglages.apply(conn, changes)
            except reglages.SettingsError as exc:
                raise HTTPException(400, str(exc)) from exc
            hrp = analysis.hr_profile(conn, settings)
            planning = schedule.describe(settings["horaires"])
        if recalcul:
            _refresh_in_background()
        return {"reglages": settings, "recalcul": recalcul, "objectif": analysis.objective(settings),
                "profil_fc": hrp, "planning": planning}

    # ------------------------------------------------------------------ synchro
    @app.post("/api/sync")
    def start_sync(payload: dict = Body(default={})) -> dict:
        if config.is_demo():
            return {"lance": False, "message": "Mode démo : les données sont fictives, pas de synchro."}
        if not sync_module.can_sync():
            return {"lance": False, "message": "Aucune clé API : ajoute-la dans les Réglages (Clé API Garmin), ou "
                                               "connecte Strava (Réglages → Strava)."}
        since = None
        if payload.get("depuis"):
            try:
                since = date.fromisoformat(str(payload["depuis"]))
            except ValueError as exc:
                raise HTTPException(400, "Date de début illisible (AAAA-MM-JJ).") from exc
            if since > date.today():
                raise HTTPException(400, "La date de début est dans le futur.")
        sources = None
        if payload.get("sources") is not None:  # une seule source (pastille du calendrier : « Actualiser »)
            wanted = payload["sources"] if isinstance(payload["sources"], list) else [payload["sources"]]
            sources = [s for s in sync_module.active_sources() if s in wanted]
            if not sources:
                return {"lance": False, "message": "Cette source n'est pas branchée sur ton profil."}
        started = jobs.get().start(since, sources)
        return {"lance": started, "message": "Synchro lancée" if started else "Une synchro est déjà en cours"}

    @app.get("/api/sync")
    def sync_status() -> dict:
        with db.session(readonly=True) as conn:
            info = sync_module.last_sync_info(conn)
            info["connexions"] = sync_module.connections(conn)
        return {"job": jobs.get().snapshot(), **info}

    # ------------------------------------------------------------------ pages
    app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(config.STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    # ------------------------------------------------ accès par le réseau local
    @app.get("/connexion")
    def login_page(request: Request):
        if request.state.local:
            return RedirectResponse("/", status_code=303)
        page = "connexion.html" if access.is_enabled() else "reseau-desactive.html"
        return FileResponse(config.STATIC_DIR / page, headers={"Cache-Control": "no-store"})

    @app.post("/api/connexion")
    def login(request: Request, payload: dict = Body(...)) -> JSONResponse:
        if request.state.local:
            return JSONResponse({"ok": True})
        if not access.is_enabled():
            raise HTTPException(403, "Accès depuis le réseau local désactivé.")
        ip = request.client.host if request.client else "?"
        if throttle.blocked(ip):
            raise HTTPException(429, "Trop d'essais : attends une minute avant de recommencer.")
        if not access.check_password(str(payload.get("mot_de_passe") or "")):
            throttle.failure(ip)
            raise HTTPException(401, "Mot de passe incorrect.")
        throttle.success(ip)
        response = JSONResponse({"ok": True})
        response.set_cookie(access.COOKIE, access.make_cookie(), max_age=access.SESSION_DAYS * 86400,
                            httponly=True, samesite="strict", path="/")
        return response

    @app.post("/api/deconnexion")
    def logout() -> JSONResponse:
        response = JSONResponse({"ok": True})
        response.delete_cookie(access.COOKIE, path="/")
        return response

    @app.get("/api/acces-reseau")
    def lan_status(request: Request) -> dict:
        data = access.load()
        listening = access.listening_on_network()
        port = int(os.environ.get("FOULEE_PORT") or config.DEFAULT_PORT)
        return {
            "ecoute": listening, "actif": data is not None,
            "modifie_le": data.get("modifie_le") if data else None,
            "adresses": access.lan_addresses(port) if listening else [],
            "depuis": "local" if request.state.local else "reseau",
            "longueur_min": access.MIN_LENGTH,
        }

    def require_local(request: Request) -> None:
        if not request.state.local:
            raise HTTPException(403, "Ce réglage se change par Tailscale ou sur le serveur lui-même.")

    def require_principal(request: Request) -> None:
        if not utilisateurs.is_principal(request.state.profil):
            raise HTTPException(403, "Réservé à l'utilisateur principal : ce réglage concerne toute l'installation.")

    @app.put("/api/acces-reseau")
    def lan_enable(request: Request, payload: dict = Body(...)) -> dict:
        require_local(request)
        require_principal(request)
        try:
            access.set_password(str(payload.get("mot_de_passe") or ""))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return lan_status(request)

    @app.delete("/api/acces-reseau")
    def lan_disable(request: Request) -> dict:
        require_local(request)
        require_principal(request)
        access.disable()
        return lan_status(request)

    # ------------------------------------------------------- mises à jour
    # Serveur : l'interface dépose une demande que le service foulee-maj (root) traite, et lit
    # où il en est dans etat.json. PC installé par le .exe : Foulée s'en charge elle-même.
    local_job = updates.LocalJob()

    def update_channel() -> str:
        with config.using_profile(utilisateurs.principal()), db.session(readonly=True) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'canal_maj'").fetchone()
        if row is None:
            # Jamais choisi : une bêta installée continue de suivre les bêtas, sinon canal stable
            try:
                return "beta" if updates.is_prerelease(__version__) else "stable"
            except ValueError:
                return "stable"
        try:
            channel = json.loads(row["value"])
        except ValueError:
            channel = "stable"
        return channel if channel in updates.CHANNELS else "stable"

    @app.get("/api/maj")
    def update_status() -> dict:
        how = updates.mode()
        folder = update_dir()
        state = None
        if how == "serveur" and folder:
            try:
                state = json.loads((folder / "etat.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                state = None
        elif how == "exe":
            state = local_job.snapshot()
        return {
            "mode": how, "disponible": how in ("exe", "serveur"), "version": __version__,
            "canal": update_channel(), "etat": state, "depot": updates.repo(),
            "en_attente": bool(how == "serveur" and folder and (folder / "demande").exists()),
            "jeton_github": bool(vault.get_secret("github")) if how == "exe" else None,
        }

    @app.get("/api/maj/alerte")
    def update_alert(request: Request) -> dict:
        """« Une nouvelle version est disponible ! » : GitHub revérifié toutes les 3 heures au plus."""
        how = updates.mode()
        channel = update_channel()
        info = updates.WATCH.state(channel, lambda: updates.check(channel, vault.get_secret("github")), wait=8)
        principal = utilisateurs.is_principal(request.state.profil)
        out = {"mode": how, "canal": channel, "installee": __version__, "nouvelle": False, "principal": principal,
               "peut_installer": how in ("exe", "serveur") and principal, "verifie_le": (info or {}).get("verifie_le")}
        if info and info.get("ok") and info.get("retard") and info.get("disponible"):
            version = str(info["disponible"])
            try:
                beta = updates.is_prerelease(version)
            except ValueError:
                beta = False
            out.update(nouvelle=True, version=version, beta=beta, nouveautes=list(info.get("nouveautes") or [])[:8],
                       publiee_le=info.get("publiee_le") or None)
        return out

    @app.post("/api/maj")
    def update_request(request: Request, payload: dict = Body(...)) -> dict:
        require_principal(request)
        action = payload.get("action")
        if action not in ("verifier", "installer"):
            raise HTTPException(400, "Action inconnue : « verifier » ou « installer ».")
        how = updates.mode()
        channel = update_channel()
        if how == "serveur":
            folder = update_dir()
            temporary = folder / "demande.tmp"
            temporary.write_text(f"{action}:{channel}", encoding="utf-8")
            os.replace(temporary, folder / "demande")
            return {"ok": True, "action": action, "canal": channel, "horodatage": time.time()}
        if how == "exe":
            try:
                stamp = local_job.start(action, channel)
            except updates.UpdateError as exc:
                raise HTTPException(409, str(exc)) from exc
            return {"ok": True, "action": action, "canal": channel, "horodatage": stamp}
        raise HTTPException(404, "Sur cette installation, la mise à jour se fait avec Mettre-a-jour-Foulee.cmd.")

    @app.put("/api/github-jeton")
    def github_token_set(request: Request, payload: dict = Body(...)) -> dict:
        require_local(request)
        require_principal(request)
        token = "".join(str(payload.get("jeton") or "").split())
        if not token:
            raise HTTPException(400, "Colle le jeton GitHub.")
        try:
            updates.list_releases(token, fallback=False)  # vérifie que GitHub accepte bien ce jeton
        except updates.UpdateError as exc:
            raise HTTPException(400, str(exc)) from exc
        vault.set_secret("github", token)
        return update_status()

    @app.delete("/api/github-jeton")
    def github_token_delete(request: Request) -> dict:
        require_local(request)
        require_principal(request)
        vault.delete_secret("github")
        return update_status()

    # -------------------------------------------------------------- clé Garmin
    def key_info() -> dict:
        with db.session(readonly=True) as conn:
            refused = sync_module.key_refused(conn)
            saved = db.get_meta(conn, "cle_enregistree_le")
        return {"enregistree": vault.has_key(), "enregistree_le": saved, "refus": refused,
                "demo": config.is_demo(), "page_garmin": KEY_PAGE}

    @app.get("/api/cle")
    def key_status() -> dict:
        return key_info()

    @app.put("/api/cle")
    def key_replace(request: Request, payload: dict = Body(...)) -> dict:
        # La clé ne transite que par la machine elle-même ou par Tailscale (chiffré)
        require_local(request)
        if config.is_demo():
            raise HTTPException(400, "Inutile en mode démo : les données sont fictives.")
        key, notes = keyinput.normalize_key(str(payload.get("cle") or ""))
        problem = keyinput.key_problem(key)
        if problem:
            raise HTTPException(400, f"Ce texte ne peut pas être une clé Garmin : {problem}.")
        try:
            info = check_key(key)
        except GarminError as exc:
            if exc.key_rejected:
                detail = f" Réponse de Garmin : « {exc.detail} »." if exc.detail else ""
                raise HTTPException(400, f"Garmin refuse cette clé (HTTP {exc.status}).{detail} Vérifie qu'elle est "
                                         "complète et toujours active sur la page « API personnelle ».") from exc
            raise HTTPException(502, str(exc)) from exc
        where = vault.set_key(key)
        with db.session() as conn:
            db.set_meta(conn, "cle_enregistree_le", db.now_iso())
            db.delete_meta(conn, sync_module.KEY_REFUSED)
            conn.commit()
        return {**key_info(), "emplacement": where, "jeton_expire": info["jeton_expire"],
                "lu": keyinput.describe_key(key), "corrections": notes, "profil_erreur": info.get("profil_erreur")}

    @app.delete("/api/cle")
    def key_forget(request: Request) -> dict:
        require_local(request)
        vault.delete_key()
        return key_info()

    # ---------------------------------------------------------------- Withings
    # Connexion en trois temps : appli Withings (ClientID, Secret), autorisation chez Withings, retour par la
    # page relais. Les demandes d'autorisation en cours (nonce → profil) vivent le temps d'un quart d'heure.
    withings_pending: dict[str, dict] = {}
    withings_notes: dict[str, dict] = {}  # profil → résultat de la dernière connexion, affiché une fois
    withings_lock = threading.Lock()
    pending_lifetime = 900
    unknown_profile = ""  # retour illisible ou expiré : le profil n'est pas connu, le message va au premier venu

    def withings_note(profile_id: str, statut: str, message: str) -> None:
        with withings_lock:
            withings_notes[profile_id] = {"statut": statut, "message": message, "le": time.time()}

    def withings_info(request: Request) -> dict:
        with db.session(readonly=True) as conn:
            info = withings_vue.status(conn)
        with withings_lock:
            note = withings_notes.pop((request.state.profil or {}).get("id"), None) or \
                withings_notes.pop(unknown_profile, None)
        if note and time.time() - note["le"] < pending_lifetime:
            info["note"] = note
        info["local"] = bool(request.state.local)
        info["synchro"] = jobs.get().snapshot()
        return info

    @app.get("/api/withings")
    def withings_status(request: Request) -> dict:
        return withings_info(request)

    @app.get("/api/withings/resume")
    def withings_summary() -> dict:
        with db.session(readonly=True) as conn:
            data = withings_vue.summary(conn)
        data["sources"] = [{"cle": "withings", "nom": "Withings", "appareils": []}]
        return data

    @app.put("/api/withings/appli")
    def withings_app(request: Request, payload: dict = Body(...)) -> dict:
        # Le Secret ne transite que par la machine elle-même ou par Tailscale (chiffré)
        require_local(request)
        if config.is_demo():
            raise HTTPException(400, "Inutile en mode démo : les données sont fictives.")
        try:
            client_id = withings_client.clean_credential(payload.get("client_id"), "ClientID")
            secret = withings_client.clean_credential(payload.get("client_secret"), "Secret")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if client_id == secret:
            raise HTTPException(400, "Le ClientID et le Secret sont identiques : recopie chacun depuis son propre "
                                     "champ du tableau de bord de Withings.")
        where = withings_client.set_app(client_id, secret)
        with db.session() as conn:
            db.set_meta(conn, "withings_appli_le", db.now_iso())
            conn.commit()
        return {**withings_info(request), "emplacement": where}

    @app.post("/api/withings/connexion")
    def withings_connect(request: Request, payload: dict = Body(default={})) -> dict:
        """Prépare l'autorisation chez Withings : renvoie l'adresse de sa page « Autoriser »."""
        require_local(request)
        if config.is_demo():
            raise HTTPException(400, "Inutile en mode démo : les données sont fictives.")
        app_data = withings_client.load()
        if not (app_data.get("client_id") and app_data.get("client_secret")):
            raise HTTPException(400, "Enregistre d'abord le ClientID et le Secret de ton appli Withings (étape 2).")
        origin = str(payload.get("origine") or "").rstrip("/")
        problem = withings_client.origin_problem(origin, request.headers.get("host"))
        if problem:
            raise HTTPException(400, f"Connexion impossible depuis cette adresse : {problem}.")
        nonce = secrets.token_urlsafe(18)
        now = time.time()
        with withings_lock:
            for key in [k for k, v in withings_pending.items() if now - v["le"] > pending_lifetime]:
                del withings_pending[key]
            withings_pending[nonce] = {"profil": request.state.profil["id"], "le": now}
        state = withings_client.make_state(nonce, origin)
        return {"url": withings_client.authorize_url(app_data["client_id"], state), "relais": withings_client.relay_url()}

    @app.get("/withings/retour")
    def withings_return(code: str = "", state: str = "", error: str = "") -> RedirectResponse:
        """Retour de Withings (par la page relais) : échange du code, puis retour aux Réglages.

        Le navigateur arrive d'un autre site, la page relais : il n'envoie donc pas le cookie du profil, réservé
        aux requêtes venues de Foulée lui-même (SameSite=Strict). Le profil est celui qui a lancé la connexion,
        retrouvé grâce au « state » : un jeton à usage unique que seul ce navigateur a reçu.
        """

        def back(statut: str, message: str, profile_id: str = unknown_profile) -> RedirectResponse:
            withings_note(profile_id, statut, message)  # affiché par le panneau Withings des Réglages
            return RedirectResponse(f"/#/reglages?section=withings&withings={statut}", status_code=303)

        try:
            nonce = withings_client.read_state(state)["n"]
        except ValueError:
            return back("erreur", "Withings n'a pas renvoyé les informations attendues : relance la connexion "
                                  "depuis cette page.")
        with withings_lock:
            pending = withings_pending.pop(nonce, None)
        if not pending or time.time() - pending["le"] > pending_lifetime:
            return back("erreur", "Cette demande de connexion a expiré ou a déjà servi : relance la connexion.")
        profile = utilisateurs.get(pending["profil"])
        if not profile:
            return back("erreur", "Le profil qui a lancé la connexion n'existe plus.")
        mine = profile["id"]
        if error:
            return back("refus", "Withings n'a pas donné l'accès (bouton « Allow » non cliqué, ou demande annulée) : "
                                 "rien n'a changé. Tu peux relancer la connexion quand tu veux.", mine)
        if not code:
            return back("erreur", "Withings n'a pas renvoyé de code d'autorisation : relance la connexion.", mine)
        with config.using_profile(profile):  # jetons, base, vue et synchro de ce profil
            try:
                withings_client.exchange_code(code)
            except WithingsError as exc:
                return back("erreur", str(exc), mine)
            with db.session() as conn:
                db.set_meta(conn, "withings_connecte_le", db.now_iso())
                db.delete_meta(conn, withings_vue.REFUSED)
                views.sync_withings_view(conn, True, withings_vue.families(conn))
                conn.commit()
            started = jobs.get(mine).start(sources=["withings"])
        return back("connecte", "Compte Withings connecté. " + (
            "Premier import en cours : la vue « Withings » se remplit dans un instant." if started else
            "Une synchro est déjà en cours : tes mesures Withings arriveront avec la suivante."), mine)

    @app.delete("/api/withings")
    def withings_disconnect(request: Request, tout: int = 0) -> dict:
        """Déconnecte Withings (et oublie l'appli si « tout ») : la vue s'en va, les mesures importées restent."""
        require_local(request)
        withings_client.disconnect(forget_app=bool(tout))
        with db.session() as conn:
            views.sync_withings_view(conn, False)
            for key in ("withings_connecte_le", withings_vue.REFUSED, *(("withings_appli_le",) if tout else ())):
                db.delete_meta(conn, key)
            conn.commit()
        return withings_info(request)

    # ------------------------------------------------------------------ Strava
    try:  # au démarrage : rien de Strava au-delà de 48 heures (voir strava/cache.py)
        strava_cache.purge_all()
    except Exception:  # jamais de quoi empêcher l'interface de démarrer
        pass
    # L'appli Strava (Client ID, Client Secret) sert à toute l'installation : le profil principal l'enregistre
    # depuis la machine elle-même ou Tailscale. Chaque profil y connecte ensuite son propre compte Strava.
    strava_pending: dict[str, dict] = {}
    strava_notes: dict[str, dict] = {}  # profil → résultat de la dernière connexion, affiché une fois
    strava_lock = threading.Lock()

    def strava_note(profile_id: str, statut: str, message: str) -> None:
        with strava_lock:
            strava_notes[profile_id] = {"statut": statut, "message": message, "le": time.time()}

    def strava_info(request: Request) -> dict:
        with db.session(readonly=True) as conn:
            info = strava_vue.status(conn)
        with strava_lock:
            note = strava_notes.pop((request.state.profil or {}).get("id"), None) or \
                strava_notes.pop(unknown_profile, None)
        if note and time.time() - note["le"] < pending_lifetime:
            info["note"] = note
        host = str(request.headers.get("host") or "").lower()
        info["domaine_rappel"] = host.split("]")[0] + "]" if host.startswith("[") else host.rsplit(":", 1)[0]
        info["local"] = bool(request.state.local)
        info["principal"] = utilisateurs.is_principal(request.state.profil)
        head = utilisateurs.principal()
        info["prenom_principal"] = utilisateurs.card(head)["prenom"] if head else ""
        info["synchro"] = jobs.get().snapshot()
        return info

    @app.get("/api/strava")
    def strava_status(request: Request) -> dict:
        return strava_info(request)

    @app.put("/api/strava/appli")
    def strava_app(request: Request, payload: dict = Body(...)) -> dict:
        # Le Client Secret ne transite que par la machine elle-même ou par Tailscale (chiffré)
        require_local(request)
        require_principal(request)
        if config.is_demo():
            raise HTTPException(400, "Inutile en mode démo : les données sont fictives.")
        try:
            client_id = strava_client.clean_client_id(payload.get("client_id"))
            secret = strava_client.clean_client_secret(payload.get("client_secret"))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        where = strava_client.set_app(client_id, secret)
        return {**strava_info(request), "emplacement": where}

    @app.delete("/api/strava/appli")
    def strava_forget_app(request: Request) -> dict:
        """Oublie l'appli Strava de l'installation (la connexion du profil courant est retirée chez Strava)."""
        require_local(request)
        require_principal(request)
        strava_client.revoke()
        strava_client.forget_tokens()
        strava_cache.forget()
        strava_client.forget_app()
        with db.session() as conn:
            for key in ("strava_connecte_le", strava_vue.REFUSED):
                db.delete_meta(conn, key)
            conn.commit()
        return strava_info(request)

    @app.post("/api/strava/connexion")
    def strava_connect(request: Request, payload: dict = Body(default={})) -> dict:
        """Prépare l'autorisation chez Strava : renvoie l'adresse de sa page « Autoriser »."""
        require_local(request)
        if config.is_demo():
            raise HTTPException(400, "Inutile en mode démo : les données sont fictives.")
        app_data = strava_client.load_app()
        if not (app_data.get("client_id") and app_data.get("client_secret")):
            raise HTTPException(400, "L'appli Strava n'est pas encore enregistrée : c'est l'étape 2, depuis le profil "
                                     "principal.")
        origin = str(payload.get("origine") or "").rstrip("/")
        problem = strava_client.origin_problem(origin, request.headers.get("host"))
        if problem:
            raise HTTPException(400, f"Connexion impossible depuis cette adresse : {problem}.")
        nonce = secrets.token_urlsafe(18)
        now = time.time()
        with strava_lock:
            for key in [k for k, v in strava_pending.items() if now - v["le"] > pending_lifetime]:
                del strava_pending[key]
            strava_pending[nonce] = {"profil": request.state.profil["id"], "le": now}
        return {"url": strava_client.authorize_url(app_data["client_id"], origin, nonce),
                "domaine": strava_client.callback_domain(origin), "libre": strava_client.callback_free(origin)}

    @app.get("/strava/retour")
    def strava_return(code: str = "", state: str = "", scope: str = "", error: str = "") -> RedirectResponse:
        """Retour de Strava après « Autoriser » : échange du code, puis retour aux Réglages.

        Le navigateur arrive de strava.com : il n'envoie pas le cookie du profil (SameSite=Strict). Le profil est
        celui qui a lancé la connexion, retrouvé grâce au « state » : un jeton à usage unique."""

        def back(statut: str, message: str, profile_id: str = unknown_profile) -> RedirectResponse:
            strava_note(profile_id, statut, message)  # affiché par le panneau Strava des Réglages
            return RedirectResponse(f"/#/reglages?section=strava&strava={statut}", status_code=303)

        with strava_lock:
            pending = strava_pending.pop(state, None)
        if not pending or time.time() - pending["le"] > pending_lifetime:
            return back("erreur", "Cette demande de connexion a expiré ou a déjà servi : relance la connexion.")
        profile = utilisateurs.get(pending["profil"])
        if not profile:
            return back("erreur", "Le profil qui a lancé la connexion n'existe plus.")
        mine = profile["id"]
        if error:
            return back("refus", "Strava n'a pas donné l'accès (« Autoriser » non cliqué, ou demande annulée) : rien "
                                 "n'a changé. Tu peux relancer la connexion quand tu veux.", mine)
        if not code:
            return back("erreur", "Strava n'a pas renvoyé de code d'autorisation : relance la connexion.", mine)
        with config.using_profile(profile):  # jetons, base, cache et synchro de ce profil
            try:
                tokens = strava_client.exchange_code(code)
            except StravaError as exc:
                return back("erreur", str(exc), mine)
            readable, everything = strava_client.granted(tokens.get("scope") or scope)
            if not readable:
                strava_client.revoke()
                strava_client.forget_tokens()
                return back("erreur", "Sur la page de Strava, la case « Voir les données de tes activités » doit rester "
                                      "cochée : sans elle, Foulée ne voit aucune séance. Relance la connexion.", mine)
            with db.session() as conn:
                db.set_meta(conn, "strava_connecte_le", db.now_iso())
                db.delete_meta(conn, strava_vue.REFUSED)
                conn.commit()
            started = jobs.get(mine).start(sources=["strava"])
        message = "Compte Strava connecté. " + (
            "Premier import en cours : tes séances Strava arrivent dans un instant." if started else
            "Une synchro est déjà en cours : tes séances Strava arriveront avec la suivante.")
        if not everything:
            message += " Tes séances « Moi uniquement » restent invisibles (case décochée chez Strava)."
        return back("connecte", message, mine)

    @app.delete("/api/strava")
    def strava_disconnect(request: Request) -> dict:
        """Déconnecte Strava pour ce profil : accès retiré chez Strava, jetons et cache effacés."""
        require_local(request)
        revoked = strava_client.revoke()
        strava_client.forget_tokens()
        strava_cache.forget()
        with db.session() as conn:
            for key in ("strava_connecte_le", strava_vue.REFUSED):
                db.delete_meta(conn, key)
            conn.commit()
        return {**strava_info(request), "revoque": revoked}

    # -------------------------------------------------------------- calendrier
    # Le lien de publication du calendrier donne celui-ci à quiconque le connaît : il arrive par la machine
    # elle-même ou par Tailscale (chiffré), va dans le coffre, et ne repart jamais (au plus sa version masquée).
    busy_db = "La base est occupée par une synchro en cours : réessaie dans un instant."

    def calendar_info(request: Request) -> dict:
        with db.session(readonly=True) as conn:
            info = calendrier.status(conn, with_link=True)
            mine = db.get_meta(conn, "calendrier_vue")
            info["vue"] = mine if mine and conn.execute("SELECT 1 FROM views WHERE id = ?", (mine,)).fetchone() \
                else None
            info["lie_le"] = db.get_meta(conn, "calendrier_lie_le")
        info["local"] = bool(request.state.local)
        return info

    @app.get("/api/calendrier/statut")
    def calendar_status(request: Request) -> dict:
        return calendar_info(request)

    @app.put("/api/calendrier")
    def calendar_link(request: Request, payload: dict = Body(...)) -> dict:
        """Lit le calendrier une première fois, puis range son lien et ajoute la vue « Calendrier »."""
        require_local(request)
        if config.is_demo():
            raise HTTPException(400, "Inutile en mode démo : les données sont fictives.")
        try:
            url = calendrier.clean_url(payload.get("lien"))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        try:
            feed = calendrier.parse_feed(calendrier.fetch(url))
        except calendrier.CalendarError as exc:
            raise HTTPException(400, str(exc)) from None
        where = calendrier.save_url(url)
        try:
            with db.session() as conn:
                db.set_meta(conn, "calendrier_lie_le", db.now_iso())
                views.sync_calendar_view(conn, True)
                conn.commit()
                result = sync_module.refresh_calendar(conn, feed)
        except sqlite3.OperationalError:
            raise HTTPException(503, f"Lien enregistré, mais {busy_db[0].lower()}{busy_db[1:]}") from None
        return {**calendar_info(request), "emplacement": where, "lu": result}

    @app.post("/api/calendrier/actualiser")
    def calendar_refresh(request: Request) -> dict:
        """Relit le calendrier tout de suite (sans attendre la synchro automatique)."""
        if config.is_demo():
            raise HTTPException(400, "Mode démo : le calendrier est fictif, rien à relire.")
        if not calendrier.linked():
            raise HTTPException(400, "Aucun calendrier relié : colle d'abord son lien (Réglages → Calendrier).")
        try:
            with db.session() as conn:
                result = sync_module.refresh_calendar(conn)
        except calendrier.CalendarError as exc:
            raise HTTPException(502, str(exc)) from None
        except sqlite3.OperationalError:
            raise HTTPException(503, busy_db) from None
        return {**calendar_info(request), "lu": result}

    @app.delete("/api/calendrier")
    def calendar_unlink(request: Request) -> dict:
        """Oublie le lien du calendrier : la vue « Calendrier » et les séances prévues s'en vont (les séances faites
        restent, bien sûr)."""
        require_local(request)
        if config.is_demo():
            raise HTTPException(400, "Inutile en mode démo : les données sont fictives.")
        try:
            with db.session() as conn:
                calendrier.forget(conn)
                views.sync_calendar_view(conn, False)
                conn.commit()
        except sqlite3.OperationalError:
            raise HTTPException(503, busy_db) from None
        return calendar_info(request)

    # ------------------------------------------------------- coach et élèves
    # Le relais du club : se connecter range un jeton dans le coffre, donc par la machine elle-même ou Tailscale,
    # comme les autres secrets. Une fois relié, la page « Mes élèves » / « Mon coach » s'ouvre de partout.
    def coach_call(action):
        if config.is_demo():
            raise HTTPException(400, "Mode démo : pas de relais, les données sont fictives.")
        try:
            with db.session() as conn:
                return action(conn)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        except coach.CoachError as exc:
            raise HTTPException(exc.status if exc.status in (400, 401, 403, 404, 409, 429) else 502, str(exc)) from None
        except sqlite3.OperationalError:
            raise HTTPException(503, busy_db) from None

    def coach_info(request: Request, conn) -> dict:
        return {**coach.status(conn), "local": bool(request.state.local)}

    @app.get("/api/coach")
    def coach_status(request: Request) -> dict:
        with db.session(readonly=True) as conn:
            return coach_info(request, conn)

    @app.post("/api/coach/connexion")
    def coach_login(request: Request, payload: dict = Body(...)) -> dict:
        require_local(request)
        return coach_call(lambda conn: {**coach.login(conn, str(payload.get("adresse") or ""),
                                                      str(payload.get("identifiant") or ""),
                                                      str(payload.get("mot_de_passe") or "")),
                                        "local": True})

    @app.post("/api/coach/inscription")
    def coach_join(request: Request, payload: dict = Body(...)) -> dict:
        require_local(request)
        return coach_call(lambda conn: {**coach.join(conn, str(payload.get("adresse") or ""),
                                                     code=str(payload.get("code") or ""),
                                                     ident=str(payload.get("identifiant") or ""),
                                                     name=str(payload.get("nom") or ""),
                                                     password=str(payload.get("mot_de_passe") or "")),
                                        "local": True})

    @app.post("/api/coach/actualiser")
    def coach_refresh(request: Request) -> dict:
        def run(conn):
            try:
                coach.refresh(conn)
            except coach.CoachError as exc:
                if exc.status != 401:
                    raise
            return coach_info(request, conn)
        return coach_call(run)

    @app.delete("/api/coach")
    def coach_logout(request: Request) -> dict:
        return coach_call(lambda conn: {**coach.logout(conn), "local": bool(request.state.local)})

    @app.post("/api/coach/mot-de-passe")
    def coach_password(request: Request, payload: dict = Body(...)) -> dict:
        require_local(request)
        coach_call(lambda conn: coach.change_password(conn, str(payload.get("actuel") or ""),
                                                      str(payload.get("nouveau") or "")))
        return {"ok": True}

    @app.post("/api/coach/quitter")
    def coach_leave(request: Request, payload: dict = Body(...)) -> dict:
        require_local(request)
        return coach_call(lambda conn: {**coach.leave(conn, str(payload.get("mot_de_passe") or "")),
                                        "local": True})

    @app.get("/api/coach/groupe")
    def coach_group(request: Request) -> dict:
        """Page « Mes élèves » : les élèves et les codes d'invitation en attente."""
        return coach_call(lambda conn: {"eleves": coach.students(conn), "invitations": coach.invitations(conn)})

    @app.post("/api/coach/invitations")
    def coach_invite(request: Request) -> dict:
        return coach_call(coach.create_invitation)

    @app.delete("/api/coach/invitations/{code}")
    def coach_cancel_invite(code: str, request: Request) -> dict:
        return coach_call(lambda conn: {"invitations": coach.cancel_invitation(conn, code)})

    @app.delete("/api/coach/eleves/{student_id}")
    def coach_remove_student(student_id: int, request: Request) -> dict:
        return coach_call(lambda conn: {"eleves": coach.remove_student(conn, student_id)})

    # -------------------------------------------------- dossier des données
    @app.get("/api/dossier")
    def folder_status(anciennes: int = 0) -> dict:
        info = {**datadir.describe(), "choix_fenetre": sys.platform == "win32"}
        if anciennes:
            info["anciennes"] = datadir.previous_installs()
        return info

    @app.post("/api/dossier/examiner")
    def folder_inspect(request: Request, payload: dict = Body(...)) -> dict:
        require_local(request)
        require_principal(request)
        return datadir.inspect(str(payload.get("chemin") or ""))

    @app.post("/api/dossier/parcourir")
    def folder_pick(request: Request, payload: dict = Body(default={})) -> dict:
        require_local(request)
        require_principal(request)
        if sys.platform != "win32":
            raise HTTPException(404, "La fenêtre de choix n'existe que sur le PC.")
        return {"chemin": datadir.pick_folder(payload.get("depart"))}

    @app.put("/api/dossier")
    def folder_change(request: Request, payload: dict = Body(...)) -> dict:
        require_local(request)
        require_principal(request)
        try:
            report = datadir.change(str(payload.get("chemin") or ""), str(payload.get("mode") or ""))
        except datadir.DataDirError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"rapport": report, "dossier": folder_status()}

    # ------------------------------------------------------------ Claude Desktop
    @app.get("/api/claude")
    def claude_status() -> dict:
        return {**claude_desktop.status(), "possible": sys.platform in ("win32", "darwin")}

    @app.post("/api/claude")
    def claude_connect(request: Request, payload: dict = Body(default={})) -> dict:
        require_local(request)
        require_principal(request)
        if sys.platform not in ("win32", "darwin"):
            raise HTTPException(404, "Claude Desktop se branche depuis le PC où il est installé.")
        if claude_desktop.is_running():
            if not payload.get("fermer"):
                raise HTTPException(409, "Claude Desktop est ouvert : il faut le fermer pendant la modification.")
            claude_desktop.close()
            time.sleep(2)
        report = claude_desktop.write(remove=payload.get("action") == "retirer")
        return {"rapport": report, **claude_status()}

    # ------------------------------------------------- application de bureau
    def app_info() -> dict:
        from . import desktop

        running = app.state.quit is not None
        return {
            "application": running,
            "demarrage_windows": desktop.startup_enabled() if running and desktop.startup_supported() else None,
            "synchro_auto_heures": desktop.SYNC_EVERY // 3600 if running else None,  # rythme par défaut
        }

    @app.get("/api/app")
    def app_status() -> dict:
        return app_info()

    @app.put("/api/app")
    def app_settings(request: Request, payload: dict = Body(...)) -> dict:
        from . import desktop

        require_local(request)
        require_principal(request)
        if "demarrage_windows" in payload:
            if app.state.quit is None or not desktop.startup_supported():
                raise HTTPException(404, "Réglage propre à l'application Windows.")
            try:
                desktop.set_startup(bool(payload["demarrage_windows"]))
            except OSError as exc:
                raise HTTPException(500, f"Réglage impossible : {exc}") from exc
        return app_info()

    @app.post("/api/app/quitter")
    def app_quit(request: Request) -> dict:
        require_local(request)
        if app.state.quit is None:
            raise HTTPException(404, "Foulée ne tourne pas en application ici.")
        threading.Timer(0.3, app.state.quit).start()  # le temps de répondre
        return {"ok": True}

    @app.get("/api/demo")
    def demo_status() -> dict:
        return {"actif": config.is_demo(), "preparation": demo_build["en_cours"], "erreur": demo_build["erreur"]}

    @app.post("/api/demo")
    def demo_switch(request: Request, payload: dict = Body(...)) -> dict:
        """Découvrir Foulée avec des données fictives, puis revenir à ses vraies données."""
        require_local(request)
        if not payload.get("actif"):  # quitter la démo : depuis n'importe lequel de ses profils
            config.set_demo(False)
            return demo_status()
        require_principal(request)
        if demo_build["en_cours"]:
            return demo_status()
        config.set_demo(True)  # base séparée (foulee-demo.db) : les vraies données ne sont pas touchées
        if config.db_path().exists():
            with db.session(readonly=True) as conn:
                if db.table_counts(conn).get("activities"):
                    return demo_status()  # déjà prête

        def build() -> None:
            from . import demo

            try:
                demo.build()
                demo_build["erreur"] = None
            except Exception as exc:  # affiché dans l'interface
                demo_build["erreur"] = str(exc)
                config.set_demo(False)
            finally:
                demo_build["en_cours"] = False

        demo_build["en_cours"] = True
        context = contextvars.copy_context()
        threading.Thread(target=context.run, args=(build,), name="foulee-demo", daemon=True).start()
        return demo_status()

    # Appli installable sur l'écran d'accueil du téléphone (servie à la racine pour couvrir tout le site)
    @app.get("/manifest.webmanifest")
    def manifest() -> FileResponse:
        return FileResponse(config.STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json",
                            headers={"Cache-Control": "no-cache"})

    @app.get("/sw.js")
    def service_worker() -> FileResponse:
        return FileResponse(config.STATIC_DIR / "sw.js", media_type="text/javascript",
                            headers={"Cache-Control": "no-cache"})

    return app
