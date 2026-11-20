"""Application partenaire : un site web (l'appli du club, par défaut Club en ligne) ouvert dans Foulée.

Réglage du profil : {"actif": bool, "nom": "…", "adresse": "https://…"}. Coché, une entrée s'ajoute dans la
colonne de gauche, sous « Nouvelle vue » ; la page affiche le site dans un cadre, avec précédent, suivant,
recharger et « ouvrir dans le navigateur ». L'adresse peut aller jusqu'à une page précise du site.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

DEFAULT = {"actif": False, "nom": "Club en ligne", "adresse": "https://app.clubenligne.fr/"}
MAX_NAME = 30
MAX_URL = 500


class PartnerError(ValueError):
    pass


def clean(value: Any) -> dict | None:
    """Contrôle le réglage ; None le remet par défaut."""
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        raise PartnerError("Application partenaire : réglage illisible.")
    name = " ".join(str(value.get("nom") or "").split())[:MAX_NAME] or DEFAULT["nom"]
    url = str(value.get("adresse") or "").strip() or DEFAULT["adresse"]
    if "://" not in url:
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:(?!\d)", url):  # « javascript:… », « mailto:… »
            raise PartnerError("Application partenaire : l'adresse doit être celle d'un site web "
                               "(https://…), par exemple https://app.clubenligne.fr/.")
        url = "https://" + url
    parts = urlsplit(url)
    if (parts.scheme not in ("http", "https") or not re.fullmatch(r"[A-Za-z0-9.-]+(:\d{1,5})?", parts.netloc or "")
            or any(c.isspace() for c in url) or len(url) > MAX_URL):
        raise PartnerError("Application partenaire : l'adresse doit être celle d'un site web "
                           "(https://…), par exemple https://app.clubenligne.fr/.")
    return {"actif": bool(value.get("actif")), "nom": name, "adresse": url}


def resolve(value: Any) -> dict:
    """Le réglage tel que l'interface l'utilise (les valeurs par défaut si rien n'est enregistré)."""
    try:
        return clean(value) or dict(DEFAULT)
    except PartnerError:
        return dict(DEFAULT)
