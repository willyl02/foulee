"""Notifications du relais : prévenir un élève (séance reçue, modifiée, annulée ; message du coach) ou un coach
(message d'un élève), sur son téléphone par ntfy, et par e-mail.

ntfy (https://ntfy.sh) : une appli gratuite (Android, iPhone), sans compte. Chaque compte a son « sujet », un nom
long et aléatoire que lui seul connaît : il s'y abonne dans l'appli (QR code dans Foulée), le relais y publie.
Le serveur est ntfy.sh par défaut ; un ntfy installé sur la VM du relais se règle à la place (sur iPhone, un ntfy
installé chez soi relaie quand même par ntfy.sh pour que la notification arrive tout de suite).

Les heures calmes (22 h – 7 h par défaut) retardent la notification à leur fin : ntfy la garde et la délivre à
l'heure dite. Le contenu reste court (« Nouvelle séance : Seuil 3 × 10 min, samedi 21 ») ; « Sans le détail » ne
dit que « Nouvelle séance de ton coach ».

L'e-mail passe par le service d'envoi posé sur le relais (courriel.py, « sudo foulee relais email »). L'adresse se
confirme par un code à six chiffres envoyé à cette adresse (30 minutes, cinq essais, cinq codes par heure au plus) :
personne ne reçoit les e-mails du club sans l'avoir demandé. Pendant les heures calmes, l'e-mail attend leur fin dans
la base du relais (courriels_attente) ; un tour toutes les minutes l'envoie.

Les envois partent en tâche de fond : ni la séance ni le message n'attendent ntfy ou le service d'envoi ; le résultat
du dernier envoi (réussi ou non) s'affiche dans les réglages.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any, Callable

import requests

from . import courriel, store

log = logging.getLogger("foulee.relais")

DEFAULT_SERVER = "https://ntfy.sh"
EVENTS = {  # clé : (pour qui, libellé dans les réglages)
    "seance": ("eleve", "Une séance de ton coach arrive"),
    "seance_modifiee": ("eleve", "Ton coach modifie une séance"),
    "seance_annulee": ("eleve", "Ton coach annule une séance"),
    "message": ("tous", "Un nouveau message"),
}
TIMEOUT = 10
CODE_MINUTES = 30
CODE_TRIES = 5
CODES_PER_HOUR = 5
HINTS = {"seance": "Elle t'attend dans Foulée, page « Mon coach », et dans ton calendrier.",
         "seance_modifiee": "La nouvelle version est dans Foulée, page « Mon coach ».",
         "seance_annulee": "Elle a disparu de « Mon coach » et de ton calendrier.",
         "message": "Pour répondre : Foulée, page Messages.",
         "essai": "Les e-mails de Foulée arriveront à cette adresse."}
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="notif")
SYNC = False  # les tests envoient sur-le-champ


def _transport(url: str, payload: dict) -> tuple[int, str]:
    response = requests.post(url, json=payload, timeout=TIMEOUT)
    return response.status_code, response.text[:300]


TRANSPORT: Callable[[str, dict], tuple[int, str]] = _transport  # remplacé par les tests


# ------------------------------------------------------------------ réglages d'un compte
def _defaults() -> dict:
    return {"ntfy": {"actif": False, "serveur": DEFAULT_SERVER, "sujet": f"foulee-{secrets.token_urlsafe(18)}"},
            "email": {"actif": False, "adresse": None, "verifiee_le": None},
            "evenements": {key: True for key in EVENTS},
            "detail": True,
            "calme": {"actif": True, "debut": "22:00", "fin": "07:00"},
            "verification": None}  # code e-mail en attente : jamais montré tel quel


def settings(conn: sqlite3.Connection, account_id: int) -> dict:
    row = conn.execute("SELECT reglages FROM notifications WHERE compte_id = ?", (account_id,)).fetchone()
    base = _defaults()
    if row is None:
        conn.execute("INSERT INTO notifications(compte_id, reglages, modifie_le) VALUES (?,?,?)",
                     (account_id, json.dumps(base), store.now()))
        return base
    try:
        saved = json.loads(row["reglages"])
    except ValueError:
        saved = {}
    for key, value in base.items():
        if isinstance(value, dict):
            base[key] = {**value, **(saved.get(key) or {})}
        elif key in saved:
            base[key] = saved[key]
    return base


def _hhmm(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", text) else fallback


def _server(value: Any) -> str:
    text = str(value or "").strip().rstrip("/") or DEFAULT_SERVER
    if not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?(/[A-Za-z0-9._~/-]*)?", text):
        raise store.RelayError("Serveur ntfy : une adresse https://…, par exemple https://ntfy.sh.")
    return text


def save_settings(conn: sqlite3.Connection, account: sqlite3.Row, payload: dict) -> dict:
    """Met à jour ce que l'interface envoie (le reste ne bouge pas) ; « nouveau_sujet » en tire un autre."""
    if not isinstance(payload, dict):
        raise store.RelayError("Réglages illisibles.")
    current = settings(conn, account["id"])
    ntfy = payload.get("ntfy") or {}
    if "actif" in ntfy:
        current["ntfy"]["actif"] = bool(ntfy["actif"])
    if "serveur" in ntfy:
        current["ntfy"]["serveur"] = _server(ntfy["serveur"])
    if payload.get("nouveau_sujet"):
        current["ntfy"]["sujet"] = f"foulee-{secrets.token_urlsafe(18)}"
    for key, value in (payload.get("evenements") or {}).items():
        if key in EVENTS:
            current["evenements"][key] = bool(value)
    email = payload.get("email") or {}
    if email.get("retirer"):
        current["email"] = {"actif": False, "adresse": None, "verifiee_le": None}
        current["verification"] = None
    elif "actif" in email:
        if email["actif"] and not current["email"]["verifiee_le"]:
            raise store.RelayError("Confirme d'abord ton adresse avec le code reçu par e-mail.")
        current["email"]["actif"] = bool(email["actif"])
    if "detail" in payload:
        current["detail"] = bool(payload["detail"])
    quiet = payload.get("calme") or {}
    if quiet:
        current["calme"] = {"actif": bool(quiet.get("actif", current["calme"]["actif"])),
                            "debut": _hhmm(quiet.get("debut"), current["calme"]["debut"]),
                            "fin": _hhmm(quiet.get("fin"), current["calme"]["fin"])}
    _write(conn, account["id"], current)
    return page(conn, account)


def _write(conn: sqlite3.Connection, account_id: int, current: dict) -> None:
    conn.execute("UPDATE notifications SET reglages = ?, modifie_le = ? WHERE compte_id = ?",
                 (json.dumps(current), store.now(), account_id))


def _pending(current: dict) -> dict | None:
    """Le code e-mail en attente, s'il vaut encore."""
    pending = current.get("verification")
    if not isinstance(pending, dict) or not pending.get("expire"):
        return None
    try:
        return pending if datetime.fromisoformat(pending["expire"]) > store.local_now() else None
    except ValueError:
        return None


def page(conn: sqlite3.Connection, account: sqlite3.Row) -> dict:
    """Ce que l'interface affiche : réglages, événements qui concernent ce rôle, dernier envoi."""
    current = settings(conn, account["id"])
    role = account["role"]
    last = conn.execute("SELECT * FROM notifications_envois WHERE compte_id = ? ORDER BY id DESC LIMIT 1",
                        (account["id"],)).fetchone()
    pending = _pending(current)
    shown = {key: value for key, value in current.items() if key != "verification"}
    return {"reglages": shown,
            "evenements": [{"cle": k, "libelle": label if role == "eleve" or k != "message" else "Un message d'un élève"}
                           for k, (who, label) in EVENTS.items() if who in ("tous", role)],
            "abonnement": f"{current['ntfy']['serveur']}/{current['ntfy']['sujet']}",
            "email_pret": courriel.ready(),
            "email_attente": pending["adresse"] if pending and pending.get("empreinte") else None,
            "dernier": dict(last) if last else None}


# ------------------------------------------------------------------ confirmer une adresse e-mail
def _digest(account_id: int, code: str) -> str:
    return hashlib.sha256(f"foulee-email:{account_id}:{code}".encode()).hexdigest()


def email_code(conn: sqlite3.Connection, account: sqlite3.Row, payload: dict) -> dict:
    """Envoie un code à six chiffres à l'adresse donnée ; elle ne sert qu'une fois confirmée."""
    if not courriel.ready():
        raise store.RelayError("Le relais du club n'envoie pas encore d'e-mails.")
    address = courriel.valid_address((payload or {}).get("adresse"))
    if not address:
        raise store.RelayError("Adresse e-mail invalide.")
    current = settings(conn, account["id"])
    moment = store.local_now()
    previous = current.get("verification") if isinstance(current.get("verification"), dict) else {}
    recent = []
    for stamp in previous.get("envois") or []:
        try:
            if datetime.fromisoformat(stamp) > moment - timedelta(hours=1):
                recent.append(stamp)
        except (TypeError, ValueError):
            pass
    if len(recent) >= CODES_PER_HOUR:
        raise store.RelayError("Trop de codes demandés : réessaie dans une heure.")
    code = f"{secrets.randbelow(10 ** 6):06d}"
    conn.commit()  # rien ne reste verrouillé pendant que le service d'envoi répond
    try:
        courriel.send(address, f"Foulée : ton code {code}",
                      f"Ton code de vérification : {code}\n\nTape-le dans Foulée (Réglages › Club et coach › "
                      f"Notifications) pour recevoir à cette adresse les e-mails du club. Il vaut {CODE_MINUTES} "
                      "minutes.\n\nTu n'as rien demandé ? Ignore cet e-mail : sans le code, rien ne change.",
                      footer="E-mail envoyé par le relais Foulée du club, à la demande d'un de ses membres.")
    except courriel.MailError as exc:
        _log(account["id"], "email", "code", "echec", str(exc))
        raise store.RelayError(f"E-mail non envoyé : {exc}") from None
    current["verification"] = {"adresse": address, "empreinte": _digest(account["id"], code), "essais": 0,
                               "expire": (moment + timedelta(minutes=CODE_MINUTES)).isoformat(timespec="seconds"),
                               "envois": recent + [moment.isoformat(timespec="seconds")]}
    _write(conn, account["id"], current)
    return page(conn, account)


def email_verify(conn: sqlite3.Connection, account: sqlite3.Row, payload: dict) -> dict:
    """Le code reçu : l'adresse est confirmée, et les e-mails activés. Un code faux compte un essai (renvoyé avec
    « erreur », pour que l'essai soit bien enregistré)."""
    current = settings(conn, account["id"])
    pending = _pending(current)
    if not pending or not pending.get("empreinte"):
        raise store.RelayError("Code expiré ou jamais demandé : demandes-en un nouveau.")
    if pending.get("essais", 0) >= CODE_TRIES:
        raise store.RelayError("Trop d'essais : demande un nouveau code.")
    code = re.sub(r"\D", "", str((payload or {}).get("code") or ""))
    if not hmac.compare_digest(_digest(account["id"], code), pending["empreinte"]):
        pending["essais"] = pending.get("essais", 0) + 1
        _write(conn, account["id"], current)
        left = CODE_TRIES - pending["essais"]
        return {**page(conn, account),
                "erreur": f"Code incorrect ({left} essai{'s' if left > 1 else ''} restant{'s' if left > 1 else ''})."
                if left else "Code incorrect. Demande un nouveau code."}
    current["email"] = {"actif": True, "adresse": pending["adresse"], "verifiee_le": store.now()}
    current["verification"] = {"envois": pending.get("envois") or []}
    _write(conn, account["id"], current)
    return page(conn, account)


# ------------------------------------------------------------------ envoi
def _quiet_until(quiet: dict, moment: datetime) -> datetime | None:
    """La fin des heures calmes si `moment` tombe dedans (22:00 → 07:00 enjambe minuit)."""
    if not quiet.get("actif"):
        return None
    start = datetime.strptime(quiet["debut"], "%H:%M").time()
    end = datetime.strptime(quiet["fin"], "%H:%M").time()
    now_t = moment.time()
    if start == end:
        return None
    inside = start <= now_t < end if start < end else (now_t >= start or now_t < end)
    if not inside:
        return None
    day = moment.date() if now_t < end else moment.date() + timedelta(days=1)
    return datetime.combine(day, end)


def _log(account_id: int, channel: str, event: str, status: str, detail: str = "") -> None:
    try:
        with store.session() as conn:
            conn.execute("INSERT INTO notifications_envois(compte_id, canal, evenement, statut, detail, cree_le) "
                         "VALUES (?,?,?,?,?,?)", (account_id, channel, event, status, detail[:300], store.now()))
            conn.execute("DELETE FROM notifications_envois WHERE compte_id = ? AND id NOT IN (SELECT id FROM "
                         "notifications_envois WHERE compte_id = ? ORDER BY id DESC LIMIT 20)", (account_id, account_id))
    except sqlite3.Error:
        log.exception("Journal des notifications illisible")


def _deliver(account_id: int, event: str, url: str, payload: dict) -> None:
    try:
        status, text = TRANSPORT(url, payload)
    except requests.RequestException as exc:
        log.warning("Notification ntfy impossible (%s) : %s", event, exc)
        _log(account_id, "ntfy", event, "echec", f"Serveur ntfy injoignable : {type(exc).__name__}")
        return
    if status >= 400:
        log.warning("Notification ntfy refusée (HTTP %s) : %s", status, text)
        _log(account_id, "ntfy", event, "echec", f"ntfy a répondu HTTP {status}")
    else:
        _log(account_id, "ntfy", event, "ok")


def _deliver_email(account_id: int, event: str, to: str, subject: str, text: str) -> None:
    try:
        courriel.send(to, subject, text)
    except courriel.MailError as exc:
        log.warning("E-mail impossible (%s) : %s", event, exc)
        _log(account_id, "email", event, "echec", str(exc))
    else:
        _log(account_id, "email", event, "ok")


def flush_due() -> int:
    """Les e-mails retenus par les heures calmes dont l'heure est venue ; renvoie le nombre d'envois tentés."""
    jobs = []
    with store.session() as conn:
        rows = conn.execute("SELECT * FROM courriels_attente WHERE a_envoyer_le <= ? ORDER BY id",
                            (store.now(),)).fetchall()
        for row in rows:
            conn.execute("DELETE FROM courriels_attente WHERE id = ?", (row["id"],))
            email = settings(conn, row["compte_id"])["email"]
            if email["actif"] and email["verifiee_le"] and email["adresse"]:  # pas décoché entre-temps
                jobs.append((row["compte_id"], row["evenement"], email["adresse"], row["sujet"], row["texte"]))
    for job in jobs:
        _deliver_email(*job)
    return len(jobs)


def start_ticker(every: int = 60) -> None:
    """Le tour des e-mails différés, en tâche de fond, pendant que le relais tourne."""
    def loop() -> None:
        while True:
            time.sleep(every)
            try:
                if courriel.ready():
                    flush_due()
            except Exception:  # le relais continue quoi qu'il arrive
                log.exception("Tour des e-mails différés")

    threading.Thread(target=loop, name="courriels", daemon=True).start()


def _queue(conn: sqlite3.Connection, job: Callable[[], None]) -> None:
    """Après l'enregistrement de la séance ou du message, en tâche de fond (sur-le-champ dans les tests)."""
    store.after_commit(conn, job if SYNC else lambda: _POOL.submit(job))


def notify(conn: sqlite3.Connection, account_ids: list[int], event: str, title: str, body: str,
           discreet: str, *, force: str | None = None) -> int:
    """Prévient ces comptes (ceux qui ont coché l'événement), sur ntfy et par e-mail selon leurs réglages ; renvoie
    le nombre d'envois. force="ntfy" ou "email" : l'essai, sur ce canal seul, tout de suite."""
    sent = 0
    moment = store.local_now()
    mail_ready = courriel.ready()
    for account_id in dict.fromkeys(account_ids):
        current = settings(conn, account_id)
        if not force and not current["evenements"].get(event, False):
            continue
        later = None if force else _quiet_until(current["calme"], moment)
        ntfy = current["ntfy"]
        if force == "ntfy" or (not force and ntfy["actif"]):
            payload = {"topic": ntfy["sujet"], "title": title if current["detail"] else "Foulée",
                       "message": body if current["detail"] else discreet, "tags": ["runner"], "priority": 3}
            if later:
                payload["delay"] = str(int(later.timestamp()))
            url = ntfy["serveur"].rstrip("/") + "/"
            _queue(conn, lambda a=account_id, u=url, p=payload: _deliver(a, event, u, p))
            sent += 1
        email = current["email"]
        if mail_ready and email["adresse"] and email["verifiee_le"] and (force == "email" or (not force and email["actif"])):
            subject = title if current["detail"] else "Foulée : du nouveau"
            text = (f"{title}\n\n{body}" if current["detail"] else discreet) + (f"\n\n{HINTS[event]}" if event in HINTS else "")
            if later:
                conn.execute("INSERT INTO courriels_attente(compte_id, evenement, sujet, texte, a_envoyer_le, cree_le) "
                             "VALUES (?,?,?,?,?,?)", (account_id, event, subject, text,
                                                     later.isoformat(sep=" ", timespec="seconds"), store.now()))
            else:
                _queue(conn, lambda a=account_id, to=email["adresse"], s=subject, t=text: _deliver_email(a, event, to, s, t))
            sent += 1
    return sent


def test(conn: sqlite3.Connection, account: sqlite3.Row, payload: dict | None = None) -> dict:
    """« Envoyer un essai » : tout de suite, même pendant les heures calmes, sur ntfy ou par e-mail."""
    channel = "email" if (payload or {}).get("canal") == "email" else "ntfy"
    if channel == "email":
        email = settings(conn, account["id"])["email"]
        if not courriel.ready():
            raise store.RelayError("Le relais du club n'envoie pas encore d'e-mails.")
        if not (email["adresse"] and email["verifiee_le"]):
            raise store.RelayError("Confirme d'abord ton adresse avec le code reçu par e-mail.")
    notify(conn, [account["id"]], "essai", "Foulée : ça marche !",
           "Tu recevras ici les séances et les messages du club.", "Notification d'essai.", force=channel)
    return {"ok": True}


# ------------------------------------------------------------------ les événements du club
def _day(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    months = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    return f"{days[d.weekday()]} {d.day} {months[d.month - 1]}"


def _name(conn: sqlite3.Connection, account_id: int | None) -> str:
    row = conn.execute("SELECT nom FROM comptes WHERE id = ?", (account_id,)).fetchone() if account_id else None
    return (row["nom"] if row else "").split(" ")[0] or "Ton coach"


def proposal_event(conn: sqlite3.Connection, event: str, item: dict) -> None:
    """Séance proposée, modifiée ou annulée : l'élève concerné."""
    coach = _name(conn, item.get("coach_id"))
    when = _day(item.get("date"))
    titles = {"seance": f"Nouvelle séance de {coach}", "seance_modifiee": f"{coach} a modifié une séance",
              "seance_annulee": f"{coach} a annulé une séance"}
    body = f"{item.get('titre') or 'Séance'}{f', {when}' if when else ''}"
    try:
        notify(conn, [item["eleve_id"]], event, titles[event], body, titles[event].replace(coach, "Ton coach"))
    except (sqlite3.Error, KeyError):
        log.exception("Notification de séance impossible")


def message_event(conn: sqlite3.Connection, author: sqlite3.Row, thread: str, group: int, text: str) -> None:
    """Un message : les autres membres du fil (tout le groupe pour « groupe »)."""
    if thread == "groupe":
        members = [group] + [row["id"] for row in conn.execute(
            "SELECT id FROM comptes WHERE role = 'eleve' AND coach_id = ?", (group,))]
        where = "dans le fil du groupe"
    else:
        members = [group, int(thread.split("-")[1])]
        where = "à propos d'une séance" if thread.startswith("seance-") else ""
    others = [m for m in members if m != author["id"]]
    who = (author["nom"] or "").split(" ")[0] or "Ton club"
    preview = " ".join(text.split())
    preview = preview if len(preview) <= 140 else preview[:137] + "…"
    try:
        notify(conn, others, "message", f"Message de {who}{f' {where}' if where else ''}", preview,
               "Nouveau message dans Foulée")
    except sqlite3.Error:
        log.exception("Notification de message impossible")
