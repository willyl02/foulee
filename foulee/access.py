"""Accès à l'interface depuis le réseau local, protégé par un mot de passe.

Sur le serveur, Foulée écoute aussi l'adresse du réseau local (http://192.168.x.y:8770).
Deux cas :
- la connexion vient de la machine elle-même : Tailscale passe par là, comme les
  commandes lancées sur le serveur. Aucun mot de passe n'est demandé ;
- elle vient d'un autre appareil du réseau : refusée tant que l'accès n'est pas
  activé, puis soumise au mot de passe.

Le mot de passe n'est jamais stocké, seulement son empreinte (PBKDF2), dans le dossier
des secrets et non dans la base, que Claude peut interroger. Une connexion réussie
dépose un cookie signé valable 90 jours. Changer le mot de passe déconnecte tout le monde.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import time
from pathlib import Path

from . import config

FILE_NAME = "acces-reseau.json"
COOKIE = "foulee_acces"
SESSION_DAYS = 90
ITERATIONS = 600_000
MIN_LENGTH = 8
MAX_FAILURES = 5
LOCK_SECONDS = 60


def path() -> Path:
    return config.secrets_dir() / FILE_NAME


def is_local_client(host: str | None) -> bool:
    """La requête vient-elle de la machine elle-même (Tailscale, console du serveur) ?"""
    if host == "testclient":  # client des tests automatiques
        return True
    try:
        return bool(host) and ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _digest(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def load() -> dict | None:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("empreinte") and data.get("secret") else None


def is_enabled() -> bool:
    return load() is not None


def set_password(password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise ValueError(f"Mot de passe trop court : {MIN_LENGTH} caractères au moins.")
    salt = secrets.token_bytes(16)
    data = {
        "algo": "pbkdf2_sha256",
        "iterations": ITERATIONS,
        "sel": salt.hex(),
        "empreinte": _digest(password, salt, ITERATIONS).hex(),
        "secret": secrets.token_hex(32),  # signe les cookies ; nouveau à chaque changement
        "modifie_le": time.strftime("%Y-%m-%d %H:%M"),
    }
    target = path()
    temporary = target.with_name(target.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(temporary, target)


def disable() -> bool:
    try:
        path().unlink()
        return True
    except FileNotFoundError:
        return False


def check_password(password: str) -> bool:
    data = load()
    if not data or not password:
        return False
    actual = _digest(password, bytes.fromhex(data["sel"]), int(data["iterations"]))
    return hmac.compare_digest(bytes.fromhex(data["empreinte"]), actual)


def _signature(secret: str, expiry: str) -> str:
    return hmac.new(bytes.fromhex(secret), expiry.encode("ascii"), hashlib.sha256).hexdigest()


def make_cookie(now: float | None = None) -> str:
    data = load()
    if not data:
        raise RuntimeError("Accès réseau désactivé")
    expiry = str(int((now or time.time()) + SESSION_DAYS * 86400))
    return f"{expiry}.{_signature(data['secret'], expiry)}"


def cookie_valid(value: str | None, now: float | None = None) -> bool:
    data = load()
    if not data or not value or "." not in value:
        return False
    expiry, signature = value.split(".", 1)
    if not expiry.isdigit() or int(expiry) < (now or time.time()):
        return False
    return hmac.compare_digest(_signature(data["secret"], expiry), signature)


class Throttle:
    """Après 5 mots de passe faux, une adresse doit attendre une minute."""

    def __init__(self) -> None:
        self._state: dict[str, tuple[int, float]] = {}

    def blocked(self, ip: str) -> bool:
        return self._state.get(ip, (0, 0.0))[1] > time.time()

    def failure(self, ip: str) -> None:
        failures, until = self._state.get(ip, (0, 0.0))
        failures += 1
        self._state[ip] = (0, time.time() + LOCK_SECONDS) if failures >= MAX_FAILURES else (failures, until)

    def success(self, ip: str) -> None:
        self._state.pop(ip, None)


def listening_on_network() -> bool:
    """Le serveur web écoute-t-il au-delà de la machine elle-même ?"""
    return os.environ.get("FOULEE_ECOUTE", "127.0.0.1") not in ("127.0.0.1", "localhost", "::1")


def lan_addresses(port: int) -> list[str]:
    """Adresse de cette machine sur le réseau local, celle par laquelle elle sort vers Internet."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))  # adresse réservée à la documentation : rien n'est envoyé
            ip = probe.getsockname()[0]
    except OSError:
        return []
    return [] if ip.startswith("127.") else [f"http://{ip}:{port}"]
