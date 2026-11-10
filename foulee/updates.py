"""Mises à jour de Foulée, sur le canal stable ou bêta.

Trois façons d'être installé, trois façons de se mettre à jour :
- « exe » (PC, installé par Foulee-Setup.exe) : Foulée cherche sur GitHub la dernière
  version publiée (les versions stables, ou aussi les pré-versions bêta), télécharge
  son installateur, vérifie son empreinte SHA-256 puis le lance en mode silencieux ;
  l'installateur remplace le programme et relance Foulée ;
- « serveur » : l'interface dépose une demande que le service système foulee-maj
  traite (scripts/maj_serveur.py suit la branche main ou beta du dépôt) ;
- « dev » (dossier décompressé, installation à la main) : Mettre-a-jour-Foulee.cmd.

Le dépôt est public : ses versions se lisent sans jeton. S'il redevenait privé, GitHub exigerait un
jeton (Réglages → Mises à jour) ; un jeton expiré ou révoqué n'empêche pas de lire un dépôt public.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

import requests

from . import __version__, config, vault

LOG = logging.getLogger("foulee.maj")

REPO_DEFAULT = "willyl02/foulee"
API = "https://api.github.com"
CHANNELS = ("stable", "beta")
ASSET_PATTERN = re.compile(r"^Foulee-Setup-[\w.\-]+\.exe$")
SUMS_NAME = "SHA256SUMS.txt"
_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-.]?(a|alpha|b|beta|rc)[-.]?(\d+)?)?$", re.IGNORECASE)
_PRE_RANK = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "rc": 2}


class UpdateError(Exception):
    """Mise à jour impossible, expliquée en français."""


def repo() -> str:
    return os.environ.get("FOULEE_DEPOT") or REPO_DEFAULT


def parse_version(text: str) -> tuple[int, int, int, int, int]:
    """« 0.4.0b1 » → (0, 4, 0, 1, 1). Une version finale passe après ses pré-versions."""
    match = _VERSION.match(text.strip())
    if not match:
        raise ValueError(f"Version illisible : {text}")
    major, minor, patch = int(match[1]), int(match[2]), int(match[3] or 0)
    if match[4]:
        return major, minor, patch, _PRE_RANK[match[4].lower()], int(match[5] or 0)
    return major, minor, patch, 9, 0


def is_prerelease(text: str) -> bool:
    return parse_version(text)[3] < 9


def mode() -> str:
    """« exe », « serveur » ou « dev » : la façon dont cette copie de Foulée se met à jour."""
    if config.is_packaged() and sys.platform == "win32":
        return "exe"
    folder = os.environ.get("FOULEE_MAJ")
    if folder and Path(folder).is_dir():
        return "serveur"
    return "dev"


# ---------------------------------------------------------------- GitHub
def _headers(token: str | None, *, binary: bool = False) -> dict:
    headers = {
        "Accept": "application/octet-stream" if binary else "application/vnd.github+json",
        "User-Agent": f"Foulee/{__version__}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(url: str, token: str | None, *, binary: bool = False, fallback: bool = True, **kwargs) -> requests.Response:
    """GET vers GitHub. Un jeton refusé (expiré, révoqué) ne bloque pas un dépôt public : on réessaie sans."""
    response = requests.get(url, headers=_headers(token, binary=binary), **kwargs)
    if response.status_code == 401 and token and fallback:
        retry = requests.get(url, headers=_headers(None, binary=binary), **kwargs)
        if retry.status_code == 200:
            LOG.info("Jeton GitHub refusé, mais le dépôt se lit sans : le jeton ne sert plus")
            response.close()
            return retry
        retry.close()
    return response


def _explain(response: requests.Response, token: str | None) -> UpdateError:
    if response.status_code == 404:
        return UpdateError("GitHub ne trouve pas le dépôt de Foulée : tant qu'il est privé, ajoute un jeton "
                           "GitHub dans les Réglages." if not token else
                           "GitHub ne trouve pas le dépôt avec ce jeton : vérifie qu'il donne accès au dépôt foulee.")
    if response.status_code == 401:
        return UpdateError("GitHub refuse le jeton : il a peut-être expiré. Crée-en un nouveau.")
    if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        return UpdateError("Trop de demandes à GitHub pour l'instant : réessaie dans une heure.")
    return UpdateError(f"GitHub a répondu {response.status_code}.")


def list_releases(token: str | None = None, *, fallback: bool = True) -> list[dict]:
    """Les versions publiées. fallback=False : sans repli sans jeton (pour vérifier un jeton)."""
    try:
        response = _get(f"{API}/repos/{repo()}/releases", token, fallback=fallback, params={"per_page": 30}, timeout=20)
    except requests.RequestException as exc:
        raise UpdateError(f"GitHub injoignable ({exc.__class__.__name__}) : vérifie la connexion Internet.") from exc
    if response.status_code != 200:
        raise _explain(response, token)
    data = response.json()
    return data if isinstance(data, list) else []


def _notes(body: str | None) -> list[str]:
    """Les nouveautés d'une version, une par ligne, sans la mise en forme Markdown.

    Ce qui suit une ligne « --- » (mode d'emploi de l'installateur) n'en fait pas partie.
    """
    lines = []
    for line in (body or "").splitlines():
        text = line.strip()
        if text.startswith("---"):
            break
        if not text or text.startswith("#") or text.startswith("<!--"):
            continue
        lines.append(re.sub(r"^[-*+]\s+|\*\*|`", "", text))
    return lines[:20]


def pick(releases: list[dict], channel: str) -> dict | None:
    """La version la plus récente du canal qui a bien son installateur et ses empreintes."""
    best = None
    for release in releases:
        if release.get("draft") or (release.get("prerelease") and channel != "beta"):
            continue
        try:
            version = parse_version(release.get("tag_name", ""))
        except ValueError:
            continue
        assets = release.get("assets") or []
        installer = next((a for a in assets if ASSET_PATTERN.match(a.get("name", ""))), None)
        sums = next((a for a in assets if a.get("name") == SUMS_NAME), None)
        if installer and sums and (best is None or version > best["cle"]):
            best = {"cle": version, "version": release["tag_name"].lstrip("vV"), "release": release,
                    "installateur": installer, "empreintes": sums}
    return best


def check(channel: str, token: str | None = None) -> dict:
    """Compare la version installée à la dernière version publiée sur le canal."""
    best = pick(list_releases(token), channel)
    current = __version__
    if best is None:
        return {"installee": current, "disponible": None, "retard": 0, "canal": channel, "nouveautes": [],
                "message": "Aucune version publiée sur ce canal pour l'instant."}
    newer = best["cle"] > parse_version(current)
    if newer:
        kind = " (bêta)" if best["release"].get("prerelease") else ""
        message = f"Version {best['version']}{kind} disponible."
    elif best["cle"] < parse_version(current) and channel == "stable":
        message = (f"Tu utilises une bêta ({current}) : tu repasseras sur le canal stable dès qu'une version "
                   f"stable plus récente sortira (dernière : {best['version']}).")
    else:
        message = f"Foulée est à jour (version {current})."
    return {"installee": current, "disponible": best["version"], "retard": 1 if newer else 0, "canal": channel,
            "nouveautes": _notes(best["release"].get("body")) if newer else [],
            "publiee_le": (best["release"].get("published_at") or "")[:10], "message": message, "_meilleure": best}


def _expected_digest(sums_asset: dict, filename: str, token: str | None) -> str:
    response = _get(sums_asset["url"], token, binary=True, timeout=30)
    if response.status_code != 200:
        raise _explain(response, token)
    for line in response.text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            return parts[0].lower()
    raise UpdateError("Empreinte de l'installateur introuvable : mise à jour annulée par prudence.")


def download(best: dict, token: str | None, folder: Path,
             progress: Callable[[float], None] | None = None) -> Path:
    """Télécharge l'installateur et vérifie son empreinte SHA-256 avant de le garder."""
    asset = best["installateur"]
    expected = _expected_digest(best["empreintes"], asset["name"], token)
    target = folder / asset["name"]
    digest = hashlib.sha256()
    try:
        with _get(asset["url"], token, binary=True, stream=True, timeout=60) as response:
            if response.status_code != 200:
                raise _explain(response, token)
            total = int(response.headers.get("Content-Length") or asset.get("size") or 0)
            done = 0
            with open(target, "wb") as handle:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    handle.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress and total:
                        progress(min(done / total, 1.0))
    except requests.RequestException as exc:
        target.unlink(missing_ok=True)
        raise UpdateError(f"Téléchargement interrompu ({exc.__class__.__name__}) : réessaie.") from exc
    if digest.hexdigest() != expected:
        target.unlink(missing_ok=True)
        raise UpdateError("Le fichier téléchargé ne correspond pas à son empreinte : mise à jour annulée.")
    return target


def launch_installer(path: Path) -> None:
    """Lance l'installateur en mode silencieux ; il remplace le programme puis relance Foulée."""
    log = config.log_dir() / "installation.log"
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={log}"],
                     creationflags=flags, close_fds=True)


# ------------------------------------------------- sortie de l'application
_exit_hook: Callable[[], None] | None = None


def set_exit_hook(hook: Callable[[], None]) -> None:
    """L'application de bureau indique comment se fermer proprement avant une mise à jour."""
    global _exit_hook
    _exit_hook = hook


def _exit_soon(delay: float = 2.0) -> None:
    def leave() -> None:
        if _exit_hook:
            _exit_hook()
            time.sleep(3)
        os._exit(0)  # libère les fichiers que l'installateur doit remplacer

    threading.Timer(delay, leave).start()


# ------------------------------------------------------- travail en cours
class LocalJob:
    """Vérification ou installation lancée depuis l'interface du PC, suivie par sondage."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict | None = None
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict | None:
        with self._lock:
            return dict(self._state) if self._state else None

    def _set(self, status: str, message: str, **extra: object) -> None:
        with self._lock:
            self._state = {"statut": status, "message": message, "horodatage": time.time(), **extra}

    def start(self, action: str, channel: str) -> float:
        if self._thread and self._thread.is_alive():
            raise UpdateError("Une vérification ou une installation est déjà en cours.")
        stamp = time.time()
        self._set("en_cours", "C'est parti…")
        self._thread = threading.Thread(target=self._run, args=(action, channel), daemon=True)
        self._thread.start()
        return stamp

    def _run(self, action: str, channel: str) -> None:
        try:
            token = vault.get_secret("github")
            self._set("en_cours", "Recherche d'une nouvelle version sur GitHub…", canal=channel)
            info = check(channel, token)
            best = info.pop("_meilleure", None)
            message = info.pop("message")
            if action == "verifier" or not info["retard"] or best is None:
                self._set("verifie", message, **info)
                return
            folder = Path(tempfile.mkdtemp(prefix="foulee-maj-"))
            self._set("en_cours", f"Téléchargement de Foulée {info['disponible']}…", **info)
            path = download(best, token, folder, progress=lambda f: self._set(
                "en_cours", f"Téléchargement de Foulée {info['disponible']} : {int(f * 100)} %", **info))
            self._set("termine", f"Installation de Foulée {info['disponible']}. L'application redémarre toute seule…",
                      **info)
            launch_installer(path)
            _exit_soon()
        except UpdateError as exc:
            self._set("erreur", str(exc), canal=channel)
        except Exception as exc:  # toute erreur doit apparaître dans les Réglages
            LOG.exception("Mise à jour impossible")
            self._set("erreur", f"Erreur inattendue : {exc}")
