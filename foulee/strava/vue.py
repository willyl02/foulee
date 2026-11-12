"""Strava dans l'interface : état de la connexion (Réglages, pastille) et informations Strava d'une séance."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .. import config, db
from . import cache, client, sync

REFUSED = sync.REFUSED


def refused(conn: sqlite3.Connection) -> dict | None:
    raw = db.get_meta(conn, REFUSED)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def status(conn: sqlite3.Connection) -> dict[str, Any]:
    """Ce que l'interface affiche dans Réglages → Strava (jamais le Client Secret ni les jetons)."""
    demo = config.is_demo()
    app = {} if demo else client.load_app()
    tokens = {} if demo else client.load()
    readable, everything = client.granted(tokens.get("scope"))
    stored = sync.counts()
    return {
        "demo": demo,
        "appli": demo or bool(app.get("client_id") and app.get("client_secret")),
        "client_id": app.get("client_id") or "",
        "connecte": (demo and stored["seances"] > 0) or bool(tokens.get("refresh_token")),
        "connecte_le": db.get_meta(conn, "strava_connecte_le"),
        "athlete_id": tokens.get("athlete_id") or "",
        "seances_privees": everything or demo,
        "droits_ok": readable or demo or not tokens,
        "refus": refused(conn),
        "cache": stored,
        "quota": client.quota(),
        "garde_heures": cache.KEEP_HOURS,
        "page_appli": client.SETTINGS_PAGE,
        "page_applis": client.APPS_PAGE,
    }


def annotate(conn: sqlite3.Connection, detail: dict) -> None:
    """Ajoute à une séance ce qui vient de Strava : lien « View on Strava », appareil, titre et description Strava
    d'une séance Garmin que Strava a aussi (connexion branchée sur le cache seulement)."""
    extra = detail.get("extra") or {}
    if detail.get("source") == "strava" and extra.get("strava_id"):
        detail["strava"] = {"url": client.activity_link(extra["strava_id"]), "appareil": extra.get("appareil"),
                            "kudos": extra.get("kudos"), "seance_strava": True, "manuelle": bool(extra.get("manuelle"))}
        return
    if detail.get("source") != "garmin" or not cache.attached(conn):
        return
    row = cache.paired_with(conn, detail)
    if not row:
        return
    try:
        copy = json.loads(row["extra"] or "{}")
    except ValueError:
        copy = {}
    detail["strava"] = {
        "url": client.activity_link(row["strava_id"]), "nom": row["name"], "description": row["description"],
        "kudos": copy.get("kudos"), "appareil": row["device_name"], "seance_strava": False,
        "detail_lu": bool(row["detail_at"]),
    }
