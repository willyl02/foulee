"""Serveur web local : l'API JSON de l'interface + les pages elles-mêmes.

Il n'écoute que sur 127.0.0.1 : aucun autre appareil ne peut s'y connecter
directement. Sur un serveur, c'est Tailscale (« tailscale serve ») qui relaie
l'interface en HTTPS, et seulement vers tes propres appareils.

Deux protections en plus contre les sites web malveillants qui tenteraient de
parler à ce serveur :
- seuls les noms d'hôte attendus sont acceptés dans l'en-tête Host (anti « DNS
  rebinding ») : 127.0.0.1, localhost, et ceux listés dans FOULEE_HOTES
  (par exemple le nom Tailscale du serveur) ;
- toute requête qui modifie quelque chose doit porter l'en-tête X-Foulee,
  ce qu'un autre site ne peut pas ajouter sans autorisation du navigateur.
"""

from __future__ import annotations

import mimetypes
import os
import sys
import threading
import time
from datetime import date
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, analysis, config, db, metrics, vault, views
from . import sync as sync_module

DERIVED_KEYS = {"vma_kmh", "fc_max", "fc_repos", "sexe", "zones_allure_pct_vma", "charge_source"}


class SyncJob:
    """Une synchro lancée depuis l'interface, suivie par sondage."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state: dict[str, Any] = {"en_cours": False, "message": "", "progression": None, "resultat": None,
                                      "erreur": None}

    def start(self) -> bool:
        with self.lock:
            if self.state["en_cours"] or sync_module.is_running():
                return False
            self.state = {"en_cours": True, "message": "Démarrage…", "progression": 0.0, "resultat": None,
                          "erreur": None, "debut": time.time()}
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _progress(self, message: str, fraction: float | None = None) -> None:
        with self.lock:
            self.state["message"] = message
            if fraction is not None:
                self.state["progression"] = round(fraction, 3)

    def _run(self) -> None:
        try:
            result = sync_module.run(progress=self._progress)
            with self.lock:
                self.state.update({"en_cours": False, "resultat": result, "message": "Synchro terminée",
                                   "progression": 1.0})
        except Exception as exc:  # affiché tel quel dans l'interface
            with self.lock:
                self.state.update({"en_cours": False, "erreur": str(exc), "message": "Échec de la synchro"})

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.state)


def _period(start: str | None, end: str | None, days: int | None = None) -> tuple[date, date]:
    try:
        return analysis.resolve_period(start, end, days)
    except ValueError as exc:
        raise HTTPException(400, f"Date illisible : {exc}") from exc


def _metric(key: str) -> str:
    if key not in metrics.CATALOG:
        raise HTTPException(400, f"Métrique inconnue : {key}")
    return key


LOCAL_HOSTS = ("127.0.0.1", "localhost", "testserver")

mimetypes.add_type("application/manifest+json", ".webmanifest")


def allowed_hosts() -> set[str]:
    """Noms d'hôte acceptés : la machine elle-même, plus ceux de FOULEE_HOTES (séparés par des virgules)."""
    extra = os.environ.get("FOULEE_HOTES", "")
    names = {name.strip().lower().rstrip(".").split(":")[0] for name in extra.split(",")}
    return set(LOCAL_HOSTS) | {name for name in names if name}


def create_app() -> FastAPI:
    app = FastAPI(title="Foulée", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    job = SyncJob()
    with db.session():
        pass  # crée la base et les vues par défaut si besoin

    hosts = allowed_hosts()

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0].lower().rstrip(".")
        if host not in hosts:
            return JSONResponse({"detail": "Hôte refusé"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-foulee") != "1":
            return JSONResponse({"detail": "En-tête X-Foulee manquant"}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # ------------------------------------------------------------- démarrage
    @app.get("/api/bootstrap")
    def bootstrap() -> dict:
        with db.session() as conn:
            settings = db.get_settings(conn)
            return {
                "app": "Foulée", "version": __version__, "demo": config.is_demo(),
                "aujourdhui": date.today().isoformat(),
                "metriques": metrics.catalog_json(), "sports": metrics.SPORTS,
                "tuiles": views.TILE_TYPES, "icones": views.ICONS, "periodes": views.PERIODES,
                "vues": views.list_views(conn), "reglages": settings,
                "objectif": analysis.objective(settings), "profil_fc": analysis.hr_profile(conn, settings),
                "synchro": sync_module.last_sync_info(conn), "cle": vault.has_key() or config.is_demo(),
                "dossier_donnees": str(config.data_dir()),
                "machine": "pc" if sys.platform == "win32" else "serveur",
                "volumes": db.table_counts(conn),
                "premiere_date": conn.execute("SELECT MIN(date) AS d FROM daily").fetchone()["d"],
            }

    # ------------------------------------------------------------ séries & co
    @app.get("/api/series")
    def get_series(metric: str, start: str | None = None, end: str | None = None, agg: str = "jour",
                   fn: str | None = None, sport: str | None = None, smooth: int = 0) -> dict:
        a, b = _period(start, end)
        with db.session(readonly=True) as conn:
            return analysis.series(conn, _metric(metric), a, b, agg, None if fn in (None, "", "auto") else fn,
                                   None if sport in (None, "", "tous") else sport, smooth)

    @app.get("/api/kpi")
    def get_kpi(metric: str, as_of: str | None = None, baseline: int = 30, window: str | None = None) -> dict:
        with db.session(readonly=True) as conn:
            return analysis.kpi(conn, _metric(metric), analysis.to_date(as_of) if as_of else None, baseline,
                                None if window in (None, "", "auto") else window)

    @app.get("/api/load")
    def get_load(start: str | None = None, end: str | None = None) -> dict:
        a, b = _period(start, end)
        with db.session(readonly=True) as conn:
            return {key: analysis.series(conn, key, a, b)["points"] for key in ("ctl", "atl", "tsb", "acwr", "load_day")}

    @app.get("/api/zones")
    def get_zones(kind: str = "fc", start: str | None = None, end: str | None = None, group: str = "semaine",
                  sport: str | None = None) -> dict:
        a, b = _period(start, end)
        with db.session(readonly=True) as conn:
            settings = db.get_settings(conn)
            return analysis.zones(conn, kind, a, b, group, None if sport in (None, "", "tous") else sport, settings)

    @app.get("/api/calendar")
    def get_calendar(metric: str, start: str | None = None, end: str | None = None) -> dict:
        a, b = _period(start, end, 180)
        with db.session(readonly=True) as conn:
            values = analysis.daily_values(conn, _metric(metric), a, b)
        meta = metrics.get(metric)
        return {"metric": metric, "label": meta.label, "fmt": meta.fmt, "unit": meta.unit, "better": meta.better,
                "start": a.isoformat(), "end": b.isoformat(), "points": sorted(values.items())}

    @app.get("/api/scatter")
    def get_scatter(x: str, y: str, start: str | None = None, end: str | None = None, lag: int = 0) -> dict:
        a, b = _period(start, end)
        with db.session(readonly=True) as conn:
            return analysis.scatter(conn, _metric(x), _metric(y), a, b, db.get_settings(conn), lag)

    @app.get("/api/shifts")
    def get_shifts(metrics_list: str = "", start: str | None = None, end: str | None = None,
                   weekdays: int = 1) -> dict:
        keys = [_metric(k) for k in metrics_list.split(",") if k]
        a, b = _period(start, end, 180)
        with db.session(readonly=True) as conn:
            return analysis.shift_compare(conn, keys, a, b, db.get_settings(conn), bool(weekdays))

    @app.get("/api/fast-laps")
    def get_fast_laps(start: str | None = None, end: str | None = None) -> dict:
        a, b = _period(start, end, 120)
        with db.session(readonly=True) as conn:
            settings = db.get_settings(conn)
            data = analysis.fast_laps(conn, a, b, settings)
        data["objectif"] = analysis.objective(settings)
        return data

    @app.get("/api/objective")
    def get_objective() -> dict:
        with db.session(readonly=True) as conn:
            return analysis.objective(db.get_settings(conn))

    # ---------------------------------------------------------------- séances
    @app.get("/api/activities")
    def get_activities(start: str | None = None, end: str | None = None, sport: str | None = None,
                       search: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        a = analysis.to_date(start) if start else None
        b = analysis.to_date(end) if end else None
        with db.session(readonly=True) as conn:
            return analysis.activities_list(conn, a, b, None if sport in (None, "", "tous") else sport, search,
                                            min(limit, 500), offset)

    @app.get("/api/activities/{activity_id}")
    def get_activity(activity_id: str, fetch: int = 1) -> dict:
        status = None
        with db.session() as conn:
            row = conn.execute("SELECT has_streams FROM activities WHERE id = ?", (activity_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Séance introuvable")
            if fetch and row["has_streams"] == 0 and vault.has_key() and not config.is_demo():
                from .garmin.client import GarminError
                from .garmin.sync import ensure_streams

                try:
                    status = ensure_streams(conn, activity_id)
                except GarminError as exc:
                    status = f"téléchargement impossible : {exc}"
            detail = analysis.activity_detail(conn, activity_id, db.get_settings(conn))
        detail["telechargement"] = status
        return detail

    @app.get("/api/activities/{activity_id}/streams")
    def get_streams(activity_id: str, max_points: int = 1500) -> dict:
        with db.session(readonly=True) as conn:
            data = analysis.activity_streams(conn, activity_id, max(100, min(max_points, 6000)))
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
    def put_settings(payload: dict = Body(...)) -> dict:
        allowed = set(db.DEFAULT_SETTINGS)
        changed = [k for k in payload if k in allowed]
        with db.session() as conn:
            for key in changed:
                db.set_setting(conn, key, payload[key])
            conn.commit()
            settings = db.get_settings(conn)
        if DERIVED_KEYS & set(changed):
            def refresh() -> None:
                with db.session() as conn2:
                    analysis.refresh_all_activities(conn2, db.get_settings(conn2))
            threading.Thread(target=refresh, daemon=True).start()
        return {"reglages": settings, "recalcul": bool(DERIVED_KEYS & set(changed)),
                "objectif": analysis.objective(settings)}

    # ------------------------------------------------------------------ synchro
    @app.post("/api/sync")
    def start_sync() -> dict:
        if config.is_demo():
            return {"lance": False, "message": "Mode démo : les données sont fictives, pas de synchro."}
        if not vault.has_key():
            return {"lance": False, "message": "Aucune clé API : lance « foulee setup » dans un terminal."}
        started = job.start()
        return {"lance": started, "message": "Synchro lancée" if started else "Une synchro est déjà en cours"}

    @app.get("/api/sync")
    def sync_status() -> dict:
        with db.session(readonly=True) as conn:
            info = sync_module.last_sync_info(conn)
        return {"job": job.snapshot(), **info}

    # ------------------------------------------------------------------ pages
    app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(config.STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

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
