"""Foulée sur ton téléphone : sur le PC, Tailscale relaie l'interface vers tes appareils.

Sur le PC, Foulée n'écoute que la machine elle-même (127.0.0.1). « tailscale serve » ouvre une adresse
HTTPS privée (https://mon-pc.tail1234.ts.net), joignable seulement par les appareils de ton réseau
Tailscale, et la relaie vers Foulée : la liaison est chiffrée de bout en bout, et Foulée voit la requête
arriver de la machine elle-même, comme sur le PC. Il reste à accepter ce nom (l'en-tête Host) : il est
gardé dans config.json, sous ``telephone_hote``, et web.py l'ajoute aux noms permis.

Avant, il fallait le faire à la main dans PowerShell (``tailscale serve --bg 8770`` et ``setx
FOULEE_HOTES …``) : Réglages › Foulée sur ton téléphone s'en charge. Si Tailscale exige des droits
d'administrateur, Windows le demande (fenêtre « Autoriser cette application… ? »).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import config

CONFIG_KEY = "telephone_hote"
DOWNLOAD = "https://tailscale.com/download"
ADMIN_DNS = "https://login.tailscale.com/admin/dns"
TIMEOUT = 20
DENIED = ("access denied", "accès refusé", "acces refuse", "permission denied", "must be root", "operator", "sudo")


class PhoneError(RuntimeError):
    """Refus expliqué en français (Tailscale absent, pas connecté, HTTPS pas activé…)."""


def cli() -> str | None:
    """Le programme « tailscale » : FOULEE_TAILSCALE (tests), le PATH, puis le dossier d'installation Windows."""
    custom = os.environ.get("FOULEE_TAILSCALE")
    if custom:
        return custom if Path(custom).exists() else None
    found = shutil.which("tailscale")
    if found:
        return found
    if sys.platform == "win32":  # pragma: no cover - Windows
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"), r"C:\Program Files"):
            path = Path(base or "") / "Tailscale" / "tailscale.exe"
            if base and path.exists():
                return str(path)
    if sys.platform == "darwin":  # pragma: no cover - Mac : l'appli Tailscale fait aussi office de commande
        for path in (Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale"), Path("/usr/local/bin/tailscale"),
                     Path("/opt/homebrew/bin/tailscale")):
            if path.exists():
                return str(path)
    return None


def _flags() -> dict:
    # Sous Windows, pas de fenêtre noire qui clignote à chaque appel
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if sys.platform == "win32" else {}


def run(*args: str, timeout: int = TIMEOUT) -> tuple[int, str]:
    exe = cli()
    if not exe:
        raise PhoneError("Tailscale n'est pas installé sur ce PC.")
    try:
        done = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, **_flags())
    except subprocess.TimeoutExpired as exc:
        raise PhoneError("Tailscale ne répond pas : vérifie qu'il est lancé (son icône près de l'horloge).") from exc
    except OSError as exc:
        raise PhoneError(f"Impossible de lancer Tailscale : {exc}") from exc
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def _json(*args: str) -> dict:
    code, out = run(*args)
    try:
        return json.loads(out[out.index("{"):]) if "{" in out else {}
    except ValueError:
        return {}


def port() -> int:
    return int(os.environ.get("FOULEE_PORT") or config.DEFAULT_PORT)


def allowed_host() -> str | None:
    """Le nom Tailscale accepté par Foulée (None tant que l'accès n'a pas été activé ici)."""
    value = config.load_user_config().get(CONFIG_KEY)
    return value if isinstance(value, str) and value else None


def _serving(serve: dict, name: str, wanted: int) -> bool:
    """La config de « tailscale serve » relaie-t-elle https://<nom>/ vers Foulée ?"""
    for host, site in (serve.get("Web") or {}).items():
        if host.split(":", 1)[0].rstrip(".") != name:
            continue
        for handler in (site.get("Handlers") or {}).values():
            target = str(handler.get("Proxy") or "").rstrip("/")
            if target.endswith(f":{wanted}") and any(h in target for h in ("127.0.0.1", "localhost")):
                return True
    return False


def status() -> dict:
    """Où on en est : Tailscale installé, connecté, HTTPS activé, relais en place, nom accepté par Foulée."""
    info = {"installe": False, "connecte": False, "https": False, "actif": False, "nom": None, "adresse": None,
            "autorise": False, "telechargement": DOWNLOAD, "console_dns": ADMIN_DNS, "port": port()}
    if not cli():
        return info
    info["installe"] = True
    state = _json("status", "--json")
    info["connecte"] = state.get("BackendState") == "Running"
    name = str((state.get("Self") or {}).get("DNSName") or "").rstrip(".")
    if not info["connecte"] or not name:
        return info
    info["nom"] = name
    info["adresse"] = f"https://{name}/"
    info["https"] = name in [str(d).rstrip(".") for d in state.get("CertDomains") or []]
    info["actif"] = _serving(_json("serve", "status", "--json"), name, port())
    info["autorise"] = allowed_host() == name
    return info


def _denied(out: str) -> bool:
    low = out.lower()
    return any(word in low for word in DENIED)


def _serve(*args: str) -> None:
    """« tailscale serve … » ; si Tailscale exige l'administrateur, Windows le demande (UAC)."""
    code, out = run("serve", *args)
    if code != 0 and "--yes" in args and "flag provided but not defined" in out:
        args = tuple(a for a in args if a != "--yes")  # Tailscale trop ancien pour --yes
        code, out = run("serve", *args)
    if code == 0:
        return
    if _denied(out) and sys.platform == "win32":  # pragma: no cover - Windows
        _elevated("serve", *args)
        return
    raise PhoneError(f"Tailscale a refusé : {out.strip()[:300] or f'code {code}'}")


def _elevated(*args: str) -> None:  # pragma: no cover - Windows
    exe = cli()
    arg_list = ",".join("'" + a.replace("'", "''") + "'" for a in args)
    script = (f"$p = Start-Process -FilePath '{exe}' -ArgumentList {arg_list} -Verb RunAs -WindowStyle Hidden "
              f"-Wait -PassThru; exit $p.ExitCode")
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, text=True, timeout=180, **_flags())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PhoneError("Windows n'a pas pu demander l'autorisation d'administrateur.") from exc
    if done.returncode != 0:
        raise PhoneError("Autorisation refusée : sans elle, Tailscale ne peut pas relayer Foulée. Réessaie et réponds « Oui ».")


def enable() -> dict:
    info = status()
    if not info["installe"]:
        raise PhoneError("Installe d'abord Tailscale sur ce PC (tailscale.com/download), puis connecte-toi.")
    if not info["connecte"]:
        raise PhoneError("Tailscale n'est pas connecté : ouvre-le (son icône près de l'horloge) et connecte-toi.")
    if not info["https"]:
        raise PhoneError("Active d'abord les certificats HTTPS de ton réseau Tailscale : console Tailscale › DNS › « Enable HTTPS ».")
    if not info["actif"]:
        _serve("--bg", "--yes", str(info["port"]))
    config.save_user_config({CONFIG_KEY: info["nom"]})
    info = status()
    if not info["actif"]:
        raise PhoneError("Tailscale n'a pas pris le relais : réessaie dans un instant.")
    return info


def disable() -> dict:
    info = status()
    if info["actif"]:
        _serve("--https=443", "off")
    config.save_user_config({CONFIG_KEY: None})
    return status()
