"""E-mails du relais : le service d'envoi (SMTP) posé par l'administrateur, et l'envoi d'un message.

Le relais ne fait pas serveur de courrier lui-même : un e-mail envoyé depuis une machine à la maison finit dans les
indésirables, quand le port 25 n'est pas tout simplement bloqué par la box. Il passe par un service d'envoi qui
signe les e-mails pour le domaine du club (DKIM). Par défaut Brevo (smtp-relay.brevo.com, offre gratuite : 300
e-mails par jour), mais n'importe quel SMTP avec identifiant et mot de passe convient.

« sudo foulee relais email » pose ces réglages sur la machine du relais : la clé SMTP se tape dans le terminal,
sans s'afficher, et va dans le dossier des secrets du relais (vault), jamais dans la base ni dans un journal.
"""

from __future__ import annotations

import json
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import escape
from typing import Callable

from .. import vault

SECRET = "relais-email"
DEFAULT_HOST = "smtp-relay.brevo.com"
DEFAULT_PORT = 587
DEFAULT_NAME = "Foulée Coach"
TIMEOUT = 20
EMAIL = re.compile(r"[^@\s<>\"',;]{1,64}@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")


class MailError(Exception):
    """Un réglage refusé ou un envoi qui échoue, avec un message à montrer tel quel (jamais la clé)."""


def valid_address(value: str | None) -> str | None:
    text = (value or "").strip()
    return text if len(text) <= 254 and EMAIL.fullmatch(text) else None


def settings() -> dict | None:
    """Les réglages d'envoi enregistrés, ou None tant que l'administrateur n'en a pas posé."""
    raw = vault.get_secret(SECRET)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    needed = ("hote", "port", "identifiant", "mot_de_passe", "expediteur")
    return data if isinstance(data, dict) and all(data.get(k) for k in needed) else None


def ready() -> bool:
    return settings() is not None


def public(data: dict | None = None) -> dict | None:
    """Ce qu'on peut afficher : tout sauf la clé, dont on ne donne que la longueur."""
    data = data or settings()
    if not data:
        return None
    return {"hote": data["hote"], "port": data["port"], "identifiant": data["identifiant"],
            "expediteur": data["expediteur"], "nom": data.get("nom") or DEFAULT_NAME,
            "cle": len(data["mot_de_passe"])}


def save(host: str, port: int | str, login: str, password: str, sender: str, name: str = DEFAULT_NAME) -> dict:
    host, login, password, name = (host or "").strip(), (login or "").strip(), (password or "").strip(), \
        (name or "").strip() or DEFAULT_NAME
    if not re.fullmatch(r"[A-Za-z0-9.-]{3,253}", host):
        raise MailError("Serveur SMTP : un nom comme smtp-relay.brevo.com.")
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise MailError("Port : 587 (ou 465, ou 2525).") from None
    if not 1 <= port <= 65535:
        raise MailError("Port : 587 (ou 465, ou 2525).")
    if not login or len(login) > 254:
        raise MailError("Identifiant SMTP : celui que donne le service d'envoi (chez Brevo, une adresse e-mail).")
    if not password or len(password) > 500:
        raise MailError("Clé SMTP vide.")
    if not valid_address(sender):
        raise MailError("Adresse d'expédition : une adresse du domaine du club, par exemple notifications@mon-club.com.")
    if len(name) > 80 or any(c in name for c in "<>\"\r\n"):
        raise MailError("Nom d'expéditeur : quelques mots, sans guillemets ni chevrons.")
    data = {"hote": host, "port": port, "identifiant": login, "mot_de_passe": password,
            "expediteur": sender.strip(), "nom": name}
    vault.set_secret(SECRET, json.dumps(data))
    return public(data)


def remove() -> None:
    vault.delete_secret(SECRET)


# ------------------------------------------------------------------ le message
FOOTER = ("Tu reçois cet e-mail parce que tu as activé les e-mails dans Foulée (Réglages › Club et coach › "
          "Notifications). Pour ne plus en recevoir, décoche-les au même endroit.")


def build(data: dict, to: str, subject: str, text: str, *, footer: str = FOOTER) -> EmailMessage:
    """Un e-mail texte et HTML, simple et sobre, au nom du club."""
    message = EmailMessage()
    message["From"] = formataddr((data.get("nom") or DEFAULT_NAME, data["expediteur"]))
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=data["expediteur"].rsplit("@", 1)[1])
    message["Auto-Submitted"] = "auto-generated"  # pas de répondeur automatique en retour
    message.set_content(f"{text}\n\n--\n{footer}\n")
    paragraphs = "".join(f'<p style="margin:0 0 12px">{escape(p).replace(chr(10), "<br>")}</p>'
                         for p in text.split("\n\n") if p.strip())
    message.add_alternative(f"""<!doctype html><html lang="fr"><body style="margin:0;padding:0;background:#f3f5f4">
<div style="max-width:560px;margin:0 auto;padding:24px 16px;font:16px/1.5 -apple-system,'Segoe UI',Roboto,Arial,sans-serif;color:#15201b">
<div style="font-weight:700;font-size:18px;margin-bottom:16px"><span style="display:inline-block;width:14px;height:10px;background:#fff;border:1px solid #d3d9d6;border-bottom:5px solid #d3263a;margin-right:8px;vertical-align:1px"></span>{escape(data.get("nom") or DEFAULT_NAME)}</div>
<div style="background:#fff;border:1px solid #dce3df;border-radius:12px;padding:20px">{paragraphs}</div>
<p style="font-size:12px;color:#66736d;margin:16px 4px 0">{escape(footer)}</p>
</div></body></html>""", subtype="html")
    return message


def _smtp_send(data: dict, message: EmailMessage) -> None:
    context = ssl.create_default_context()
    if int(data["port"]) == 465:
        server = smtplib.SMTP_SSL(data["hote"], 465, timeout=TIMEOUT, context=context)
    else:
        server = smtplib.SMTP(data["hote"], int(data["port"]), timeout=TIMEOUT)
    with server:
        if int(data["port"]) != 465:
            server.starttls(context=context)
        server.login(data["identifiant"], data["mot_de_passe"])
        server.send_message(message)


SENDER: Callable[[dict, EmailMessage], None] = _smtp_send  # remplacé par les tests


def send(to: str, subject: str, text: str, *, footer: str = FOOTER) -> None:
    """Envoie un e-mail ; MailError avec un motif lisible si ça coince (jamais la clé)."""
    data = settings()
    if data is None:
        raise MailError("Le relais n'a pas de service d'envoi d'e-mails : « sudo foulee relais email ».")
    address = valid_address(to)
    if not address:
        raise MailError("Adresse e-mail invalide.")
    message = build(data, address, subject, text, footer=footer)
    try:
        SENDER(data, message)
    except smtplib.SMTPAuthenticationError:
        raise MailError("Le service d'envoi refuse l'identifiant ou la clé SMTP (une clé d'API ne marche pas : il "
                        "faut une clé SMTP).") from None
    except smtplib.SMTPSenderRefused:
        raise MailError(f"Le service d'envoi refuse l'expéditeur {data['expediteur']} : son domaine est-il "
                        "authentifié chez lui ?") from None
    except smtplib.SMTPRecipientsRefused:
        raise MailError("Le service d'envoi refuse cette adresse de destination.") from None
    except smtplib.SMTPException as exc:
        raise MailError(f"Le service d'envoi a refusé l'e-mail ({type(exc).__name__}).") from None
    except (socket.timeout, TimeoutError):
        raise MailError(f"{data['hote']} ne répond pas (port {data['port']} bloqué par le réseau ?).") from None
    except (OSError, ssl.SSLError) as exc:
        raise MailError(f"Connexion impossible à {data['hote']}:{data['port']} ({type(exc).__name__}).") from None
