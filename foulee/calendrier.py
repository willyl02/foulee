"""Calendrier d'entraînement : les séances prévues et les courses d'un agenda iCal, lu par son lien de
publication (calendrier Garmin Connect publié, adresse secrète d'un agenda Google, calendrier du club…).

Le lien donne le calendrier à quiconque le connaît : il va dans le coffre, comme la clé Garmin, et ne sort
jamais vers l'interface (seulement une version masquée), ni vers Claude, ni dans les exports des réglages,
ni dans les messages d'erreur ou le journal.

Le calendrier publié par Garmin Connect ne contient que ce qui vient : les séances prévues (journée entière,
au nom de l'entraînement) et les événements (courses : heure, lieu). Foulée garde donc les jours passés tels
qu'il les a lus, pour dire ensuite « fait » ou « manqué », et remplace le reste à chaque lecture. Un agenda
qui publie aussi son passé (Google…) est remplacé sur toute la période qu'il couvre.
"""

from __future__ import annotations

import contextvars
import html
import json
import logging
import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit

import requests

from . import __version__, config, db, metrics, vault

LOG = logging.getLogger("foulee.calendrier")

SECRET = "calendrier"
REFUSED = "calendrier_refus"  # le lien ne répond plus (publication annulée) : il faut en coller un nouveau
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = 30
WINDOW_BACK = 400      # récurrences dépliées : jusqu'à 400 jours en arrière…
WINDOW_AHEAD = 400     # …et 400 jours en avant
HISTORY_DAYS = 800     # séances prévues passées gardées (pour « fait » ou « manqué »)
MAX_OCCURRENCES = 500  # au plus par événement récurrent


class CalendarError(Exception):
    """Erreur de lecture du calendrier, expliquée en français (jamais le lien dedans : il est secret)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status
        self.detail = ""
        # 404 / 410 : la publication a été annulée, réessayer ne sert à rien tant qu'on n'a pas un nouveau lien
        self.access_refused = status in (404, 410)


# ------------------------------------------------------------------ le lien
def clean_url(text: Any) -> str:
    value = str(text or "").strip().strip("\"'«»<> ")
    if not value:
        raise ValueError("Colle le lien du calendrier : il commence par https:// ou webcal://.")
    if not re.match(r"(?i)(https?|webcals?)://", value):
        raise ValueError("Ce texte n'est pas un lien de calendrier : il doit commencer par https:// (ou webcal://).")
    if re.search(r"\s", value):
        raise ValueError("Le lien ne doit pas contenir d'espace : recopie-le d'un seul bloc.")
    if value.lower().startswith("webcals://"):
        value = "https://" + value[len("webcals://"):]
    if value.lower().startswith("webcal://"):
        value = "https://" + value[len("webcal://"):]
    scheme, host = "", None
    try:
        parts = urlsplit(value)
        scheme, host = parts.scheme.lower(), parts.hostname
    except ValueError:
        pass
    if scheme not in ("http", "https") or not host:
        raise ValueError("Ce texte n'est pas un lien de calendrier : il doit commencer par https:// (ou webcal://).")
    if len(value) > 2000:
        raise ValueError("Ce lien est trop long pour un lien de calendrier.")
    return value


def masked(url: str | None) -> str:
    """« connect.garmin.com/…052b » : de quoi reconnaître le lien sans le révéler."""
    if not url:
        return ""
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        host = ""
    tail = re.sub(r"[^0-9A-Za-z]", "", url)[-4:]
    return f"{host}/…{tail}"


def load_url() -> str | None:
    return vault.get_secret(SECRET)


def linked() -> bool:
    return bool(load_url())


def save_url(url: str) -> str:
    return vault.set_secret(SECRET, url)


def forget_url() -> None:
    vault.delete_secret(SECRET)


# ---------------------------------------------------------------- lecture
_READING = contextvars.ContextVar("calendrier_lecture", default=False)


class _HideLink(logging.Filter):
    """Pendant la lecture du calendrier, urllib3 ne note rien : ses messages de débogage recopient l'adresse
    demandée, c'est-à-dire le lien secret."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not _READING.get()


for _name in ("urllib3.connectionpool", "urllib3.connection", "urllib3.util.retry", "urllib3.response", "requests"):
    logging.getLogger(_name).addFilter(_HideLink())


def fetch(url: str) -> str:
    """Télécharge le calendrier (texte iCal). Les messages d'erreur ne contiennent jamais le lien."""
    token = _READING.set(True)
    try:
        return _fetch(url)
    finally:
        _READING.reset(token)


def _fetch(url: str) -> str:
    headers = {"User-Agent": f"Foulee/{__version__} (calendrier iCal)",
               "Accept": "text/calendar, text/plain;q=0.8, */*;q=0.5"}
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True)
    except Exception as exc:  # le message d'origine (requests, urllib3) recopie l'adresse : jamais affiché
        raise CalendarError(f"Calendrier injoignable ({type(exc).__name__}) : vérifie la connexion à Internet, "
                            "puis réessaie.") from None
    with response:
        code = response.status_code
        if code in (404, 410):
            raise CalendarError(f"Le lien du calendrier ne répond plus (HTTP {code}) : la publication a peut-être été "
                                "annulée. Publie de nouveau le calendrier, puis colle le nouveau lien.", code)
        if code in (401, 403):
            raise CalendarError(f"Accès refusé au calendrier (HTTP {code}) : ce lien n'est pas public. Il faut le lien "
                                "de publication (ou l'adresse secrète au format iCal).", code)
        if code >= 400:
            raise CalendarError(f"Le serveur du calendrier répond une erreur (HTTP {code}) : réessaie plus tard.", code)
        chunks, size = [], 0
        deadline = time.monotonic() + 2 * TIMEOUT  # un serveur qui envoie au compte-gouttes ne bloque pas la synchro
        try:
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise CalendarError("Calendrier trop volumineux (plus de 5 Mo) : est-ce bien un agenda "
                                        "d'entraînement ?")
                if time.monotonic() > deadline:
                    raise CalendarError("Le serveur du calendrier répond trop lentement : réessaie plus tard.")
                chunks.append(chunk)
        except CalendarError:
            raise
        except Exception as exc:
            raise CalendarError(f"Lecture du calendrier interrompue ({type(exc).__name__}) : réessaie plus tard.") \
                from None
        charset = re.search(r"charset=\"?([\w-]+)", response.headers.get("Content-Type", ""), re.I)
    raw = b"".join(chunks)
    try:
        text = raw.decode(charset.group(1) if charset else "utf-8")
    except (LookupError, UnicodeDecodeError):
        text = raw.decode("latin-1")
    if "BEGIN:VCALENDAR" not in text.lstrip("﻿")[:4096].upper():
        raise CalendarError("Ce lien ne donne pas un calendrier iCal : vérifie que tu as copié le lien de publication "
                            "(il commence souvent par webcal://, ou finit par .ics).")
    return text


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw.strip():
            lines.append(raw)
    return lines


def _split(line: str) -> tuple[str, dict[str, str], str]:
    """« DTSTART;TZID=Europe/Paris:20261205T100000 » → (« DTSTART », {« TZID »: …}, « 20261205T100000 »)."""
    quoted = False
    for index, char in enumerate(line):
        if char == '"':
            quoted = not quoted
        elif char == ":" and not quoted:
            head, value = line[:index], line[index + 1:]
            break
    else:
        return line.strip().upper(), {}, ""
    parts = re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', head)
    params = {}
    for part in parts[1:]:
        if "=" in part:
            key, val = part.split("=", 1)
            params[key.strip().upper()] = val.strip().strip('"')
    return parts[0].strip().upper(), params, value


def _text(value: str) -> str:
    return re.sub(r"\\([\\;,nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value).strip()


def _plain(value: str) -> str:
    """Description d'agenda parfois en HTML (Google) : du texte simple, avec ses retours à la ligne."""
    text = re.sub(r"<\s*(br|/p|/div|/li)\s*/?>", "\n", value, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _zone(name: str | None):
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name.strip())
    except Exception:  # fuseau inconnu (nom Microsoft…) : l'heure est gardée telle quelle
        return None


def _when(value: str, params: dict[str, str], home) -> tuple[datetime | date, bool]:
    """Date (journée entière) ou heure locale. Une heure UTC (« Z ») passe à l'heure du calendrier ; une heure
    avec fuseau (TZID) reste l'heure affichée par l'agenda (une course à 10:00 reste à 10:00)."""
    text = value.strip()
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", text):
        return date(int(text[:4]), int(text[4:6]), int(text[6:8])), True
    match = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})?(Z?)", text)
    if not match:
        raise ValueError(text)
    moment = datetime(*(int(match.group(i)) for i in range(1, 6)), int(match.group(6) or 0))
    if match.group(7):
        utc = moment.replace(tzinfo=timezone.utc)
        moment = (utc.astimezone(home) if home else utc.astimezone()).replace(tzinfo=None)
    return moment, False


def _duration(text: str) -> timedelta | None:
    match = re.fullmatch(r"([+-]?)P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", text.strip())
    if not match:
        return None
    sign = -1 if match.group(1) == "-" else 1
    w, d, h, m, s = (int(match.group(i) or 0) for i in range(2, 7))
    return sign * timedelta(weeks=w, days=d, hours=h, minutes=m, seconds=s)


def _day(moment: datetime | date) -> date:
    return moment.date() if isinstance(moment, datetime) else moment


DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _add_months(day: date, months: int) -> date | None:
    year, month = divmod(day.month - 1 + months, 12)
    try:
        return day.replace(year=day.year + year, month=month + 1)
    except ValueError:  # 31 d'un mois de 30 jours : pas d'occurrence ce mois-là
        return None


def _weekdays_of_month(year: int, month: int, weekday: int, nth: int | None) -> list[date]:
    first = date(year, month, 1)
    days = [first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * k) for k in range(5)]
    days = [d for d in days if d.month == month]
    if nth is None:
        return days  # « tous les lundis du mois »
    if 0 < nth <= len(days):
        return [days[nth - 1]]
    if 0 < -nth <= len(days):
        return [days[nth]]
    return []


def _recur(start: datetime | date, rule: str, stop: date) -> Iterable[datetime | date]:
    """Occurrences d'une règle RRULE courante (DAILY, WEEKLY, MONTHLY, YEARLY ; INTERVAL, COUNT, UNTIL, BYDAY,
    BYMONTHDAY), dans l'ordre, jusqu'à ``stop``. Les règles plus rares donnent au moins la première date."""
    parts = dict(p.split("=", 1) for p in rule.upper().split(";") if "=" in p)
    freq = parts.get("FREQ", "")
    interval = int(parts["INTERVAL"]) if parts.get("INTERVAL", "").isdigit() and int(parts["INTERVAL"]) > 0 else 1
    count = int(parts["COUNT"]) if parts.get("COUNT", "").isdigit() else None
    until = None
    if parts.get("UNTIL"):
        try:
            until = _day(_when(parts["UNTIL"], {}, None)[0])
        except ValueError:
            until = None
    byday = [d.strip() for d in parts.get("BYDAY", "").split(",") if d.strip()]
    bymonthday = [int(d) for d in parts.get("BYMONTHDAY", "").split(",") if re.fullmatch(r"-?\d{1,2}", d.strip())]
    clock = start.time() if isinstance(start, datetime) else None
    first = _day(start)
    produced = 0

    def at(day: date):
        return datetime.combine(day, clock) if clock else day

    def over(day: date) -> bool:
        return (count is not None and produced >= count) or (until is not None and day > until) or day > stop

    if freq == "DAILY":
        day = first
        while not over(day):
            produced += 1
            yield at(day)
            day += timedelta(days=interval)
    elif freq == "WEEKLY":
        weekdays = sorted({DAYS.index(d[-2:]) for d in byday if d[-2:] in DAYS} or {first.weekday()})
        week = first - timedelta(days=first.weekday())
        while week <= stop:
            for weekday in weekdays:
                day = week + timedelta(days=weekday)
                if day < first:
                    continue
                if over(day):
                    return
                produced += 1
                yield at(day)
            week += timedelta(weeks=interval)
    elif freq == "MONTHLY":
        step = 0
        while True:
            anchor = _add_months(first.replace(day=1), step)
            if anchor is None or anchor > stop:
                return
            days: set[date] = set()
            for spec in byday:
                match = re.fullmatch(r"([+-]?\d)?(MO|TU|WE|TH|FR|SA|SU)", spec)
                if match:
                    nth = int(match.group(1)) if match.group(1) else None
                    days.update(_weekdays_of_month(anchor.year, anchor.month, DAYS.index(match.group(2)), nth))
            for number in bymonthday:
                try:
                    days.add(anchor.replace(day=number) if number > 0 else
                             _add_months(anchor, 1) - timedelta(days=-number))
                except (ValueError, TypeError):
                    pass
            if not byday and not bymonthday:
                same = _add_months(first, step)
                if same:
                    days.add(same)
            for day in sorted(days):
                if day < first:
                    continue
                if over(day):
                    return
                produced += 1
                yield at(day)
            step += interval
    elif freq == "YEARLY":
        step = 0
        while first.year + step <= stop.year:
            try:
                day = first.replace(year=first.year + step)
            except ValueError:  # 29 février
                step += interval
                continue
            if over(day):
                return
            produced += 1
            yield at(day)
            step += interval
    else:
        yield start


def _order(event: dict) -> tuple:
    """Journées entières d'abord, puis les heures fixes dans l'ordre."""
    start = event["start"]
    timed = isinstance(start, datetime)
    return _day(start), timed, start.time() if timed else datetime.min.time()


def parse_feed(text: str, today: date | None = None) -> tuple[list[dict], dict]:
    """Événements d'un calendrier iCal (titre, début, fin, lieu, description) et ce qu'on sait du calendrier
    (nom, publié par Garmin Connect ou non)."""
    today = today or date.today()
    lines = _unfold(text)
    info: dict[str, Any] = {"nom": None, "garmin": False}
    home = None
    for line in lines[:60]:
        name, _, value = _split(line)
        if name == "BEGIN" and value.upper() == "VEVENT":
            break
        if name == "PRODID":
            info["garmin"] = "garmin" in value.lower()
        elif name == "X-WR-TIMEZONE":
            home = _zone(value)
        elif name == "X-WR-CALNAME":
            info["nom"] = _text(value)[:80] or None
    blocks: list[dict] = []
    current: dict | None = None
    depth = 0
    for line in lines:
        name, params, value = _split(line)
        if name == "BEGIN":
            if value.upper() == "VEVENT" and current is None:
                current = {"props": {}, "exdates": [], "params": {}}
                depth = 0
            elif current is not None:
                depth += 1  # VALARM… dans l'événement : ignoré
            continue
        if name == "END":
            if current is not None and depth:
                depth -= 1
            elif current is not None and value.upper() == "VEVENT":
                blocks.append(current)
                current = None
            continue
        if current is None or depth:
            continue
        if name == "EXDATE":
            for part in value.split(","):
                try:
                    current["exdates"].append(_day(_when(part, params, home)[0]))
                except ValueError:
                    pass
            continue
        current["props"][name] = value
        current["params"][name] = params
    moved: dict[str, set[date]] = {}  # occurrences d'une série modifiées à part (RECURRENCE-ID)
    for block in blocks:
        props = block["props"]
        if "RECURRENCE-ID" in props and props.get("UID"):
            try:
                moved.setdefault(props["UID"], set()).add(
                    _day(_when(props["RECURRENCE-ID"], block["params"]["RECURRENCE-ID"], home)[0]))
            except ValueError:
                pass
    events: list[dict] = []
    window = (today - timedelta(days=WINDOW_BACK), today + timedelta(days=WINDOW_AHEAD))
    for block in blocks:
        props, params = block["props"], block["params"]
        if props.get("STATUS", "").upper() == "CANCELLED" or "DTSTART" not in props:
            continue
        try:
            start, all_day = _when(props["DTSTART"], params["DTSTART"], home)
        except ValueError:
            continue
        end = None
        if "DTEND" in props:
            try:
                end = _when(props["DTEND"], params["DTEND"], home)[0]
            except ValueError:
                end = None
        elif "DURATION" in props:
            span = _duration(props["DURATION"])
            end = start + span if span else None
        length = end - start if end is not None and type(end) is type(start) and end > start else None
        base = {
            "uid": props.get("UID", ""), "title": " ".join(_text(props.get("SUMMARY", "")).split()) or "Sans titre",
            "description": _plain(_text(props.get("DESCRIPTION", ""))) or None,
            "location": _text(props.get("LOCATION", "")) or None, "all_day": all_day, "garmin": info["garmin"],
        }
        if props.get("RRULE") and "RECURRENCE-ID" not in props:
            skip = set(block["exdates"]) | moved.get(props.get("UID", ""), set())
            kept = 0
            for occurrence in _recur(start, props["RRULE"], window[1]):
                day = _day(occurrence)
                if day in skip or day < window[0]:
                    continue
                events.append({**base, "start": occurrence, "end": occurrence + length if length else None})
                kept += 1
                if kept >= MAX_OCCURRENCES:
                    break
        else:
            events.append({**base, "start": start, "end": start + length if length else None})
    events.sort(key=_order)
    return events, info


def parse(text: str, today: date | None = None) -> list[dict]:
    return parse_feed(text, today)[0]


# ------------------------------------------------------------- classement
RACE_WORDS = re.compile(
    r"\b(trail|marathon|semi|ultra|cross\b|corrida|triathlon|duathlon|aquathlon|ekiden|relais|race|foulées|"
    r"swimrun|raid|grand prix|championnats?|compétition|competition|dossard|course (?:de|des|du|nature|sur route)|"
    r"\d+\s?km\b|\d+k\b|saint[- ]?sylvestre|granfondo|gran fondo|cyclosportive)", re.I)
# Une course sans heure ni lieu dans le calendrier Garmin : son titre seul la trahit (jamais celui d'une séance du
# plan, « Course de base », « Allure marathon 3 × 5 km »…)
STRONG_RACE_WORDS = re.compile(
    r"\b(marathon|semi[- ]marathon|ultra[- ]?trail|trail (?:de|des|du|d')|corrida|triathlon|duathlon|aquathlon|ekiden|"
    r"swimrun|cross (?:de|des|du|d')|\d+\s?km (?:de|des|du|d')|foulées|saint[- ]?sylvestre|championnats?|grand prix)",
    re.I)
WORKOUT_WORDS = re.compile(
    r"(footing|fractionn|endurance|seuil|vma|sortie|\bsl\b|\bef\b|renfo|renforcement|muscu|gainage|\bppg\b|"
    r"côtes|\bcotes\b|tempo|récup|recup|séance|seance|entraînement|entrainement|workout|interval|fartlek|"
    r"pyramide|allure|\bas\d+|\bvélo\b|\bvelo\b|natation|piscine|yoga|étirement|etirement|mobilit|\bhiit\b|"
    r"cardio|home ?trainer|\brun\b|jogging|échauffement|echauffement)", re.I)
SPORT_WORDS = [
    (None, r"triathlon|duathlon|aquathlon|swimrun|\braid\b|multisport"),  # plusieurs sports : toute séance compte
    ("renfo", r"renfo|renforcement|muscu|musculation|gainage|\bppg\b|strength|abdos|\bcore\b|circuit|crossfit"),
    ("velo", r"\bv[ée]lo\b|\bbike\b|cyclisme|\bcycling\b|spinning|\bvtt\b|home ?trainer|zwift|\bride\b|gravel|"
             r"granfondo|gran fondo|cyclosportive"),
    ("natation", r"natation|\bnage\b|\bswim|piscine"),
    ("rando", r"rando|\bhike\b|hiking"),
    ("marche", r"\bmarche\b|\bwalk"),
    ("souplesse", r"yoga|pilates|étirement|etirement|stretching|mobilité|mobilite|mobility"),
    ("cardio", r"\bhiit\b|cardio|elliptique|elliptical|rameur|rowing"),
    ("trail", r"trail"),
]


def classify(event: dict) -> tuple[str, str | None]:
    """(type, sport) : « course » pour une compétition, « seance » pour un entraînement prévu, « autre » sinon.

    Calendrier Garmin Connect : une séance prévue y est une journée entière ; un événement (course) a une heure
    ou un lieu, ou à défaut un nom de course. Ailleurs : les mots du titre (« Footing », « Renfo »… ; « Trail
    de… », « 10 km de… »)."""
    title = event["title"]
    if event.get("garmin"):
        planned = event["all_day"] and not event.get("location") and not (
            STRONG_RACE_WORDS.search(title) and not WORKOUT_WORDS.search(title))
        kind = "seance" if planned else "course"
    elif WORKOUT_WORDS.search(title):
        kind = "seance"
    elif RACE_WORDS.search(title):
        kind = "course"
    elif WORKOUT_WORDS.search(event.get("description") or ""):
        kind = "seance"
    else:
        return "autre", None
    for sport, pattern in SPORT_WORDS:
        if re.search(pattern, title, re.I):
            return kind, sport
    return kind, "course"


# ------------------------------------------------------------------ base
def ready(conn: sqlite3.Connection) -> bool:
    """La table existe-t-elle ? (base d'un autre profil ouverte en lecture seule, pas encore mise à niveau)"""
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'calendar_events'").fetchone() \
        is not None


def _iso(moment: datetime | date | None) -> str | None:
    if moment is None:
        return None
    return moment.isoformat(sep=" ") if isinstance(moment, datetime) else moment.isoformat()


def _end(event: dict) -> str | None:
    """Fin d'un événement : l'heure de fin, ou le dernier jour d'un événement de plusieurs jours (une journée
    entière se termine, en iCal, le lendemain à 0 h : rien à noter pour une seule journée)."""
    start, end = event["start"], event["end"]
    if end is None:
        return None
    if event["all_day"]:
        last = _day(end) - timedelta(days=1)
        return last.isoformat() if last > _day(start) else None
    return _iso(end)


INSERT = ("INSERT INTO calendar_events(date, start_local, end_local, all_day, title, description, location, kind, "
          "sport, uid, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")


def store(conn: sqlite3.Connection, events: list[dict], today: date | None = None) -> dict:
    """Remplace les événements à partir du premier jour couvert par le calendrier (aujourd'hui pour Garmin) ;
    les jours d'avant restent tels que Foulée les a lus. Renvoie {"evenements", "a_venir", "courses"}."""
    today = today or date.today()
    oldest = today - timedelta(days=HISTORY_DAYS)
    rows = [(event, _day(event["start"])) for event in events]
    rows = [(event, day) for event, day in rows if day >= oldest]
    since = min([today, *(day for _, day in rows)])
    kept: list[sqlite3.Row] = []
    if since == today:
        # Calendrier qui ne publie que l'avenir (Garmin) : une séance d'aujourd'hui qui en sort en cours de journée
        # (faite, ou son heure passée) reste là, pour dire ce soir « fait » ou « manqué ».
        fresh = {(event["title"][:200], None if event["all_day"] else _iso(event["start"]))
                 for event, day in rows if day == today}
        kept = [r for r in conn.execute("SELECT * FROM calendar_events WHERE date = ?", (today.isoformat(),))
                if (r["title"], r["start_local"]) not in fresh]
    now = db.now_iso()
    conn.execute("DELETE FROM calendar_events WHERE date >= ? OR date < ?", (since.isoformat(), oldest.isoformat()))
    upcoming = races = 0
    for event, day in rows:
        kind, sport = classify(event)
        conn.execute(INSERT, (
            day.isoformat(), None if event["all_day"] else _iso(event["start"]), _end(event), int(event["all_day"]),
            event["title"][:200], (event["description"] or "")[:2000] or None, (event["location"] or "")[:300] or None,
            kind, sport, (event["uid"] or "")[:200], now))
        if day >= today and kind != "autre":
            upcoming += 1
            races += kind == "course"
    for row in kept:
        conn.execute(INSERT, (row["date"], row["start_local"], row["end_local"], row["all_day"], row["title"],
                              row["description"], row["location"], row["kind"], row["sport"], row["uid"],
                              row["fetched_at"]))
    return {"evenements": len(rows), "a_venir": upcoming, "courses": races}


def apply(conn: sqlite3.Connection, events: list[dict], info: dict) -> dict[str, Any]:
    """Range un calendrier lu : ses événements, l'heure de lecture et ce qu'on sait de lui (nom, Garmin)."""
    summary = store(conn, events)
    db.set_meta(conn, "calendrier_lu_le", db.now_iso())
    db.set_meta(conn, "calendrier_info", json.dumps(info, ensure_ascii=False))
    conn.commit()
    return {**summary, "appels": 1, "erreurs": []}


def run(conn: sqlite3.Connection, *, since: date | None = None, fit_days: int | None = None, with_fit: bool = True,
        progress=None) -> dict[str, Any]:
    """Source de la synchro : relit le calendrier et met à jour ses événements (un seul appel)."""
    url = load_url()
    if not url:
        raise CalendarError("Aucun lien de calendrier : Réglages → Calendrier.")
    if progress:
        progress("Calendrier : lecture…", None)
    return apply(conn, *parse_feed(fetch(url)))


def forget(conn: sqlite3.Connection) -> None:
    """Retire le calendrier du profil : le lien et les séances prévues (les séances faites restent)."""
    forget_url()
    if ready(conn):
        conn.execute("DELETE FROM calendar_events")
    for key in ("calendrier_lu_le", "calendrier_info", "calendrier_lie_le", REFUSED):
        db.delete_meta(conn, key)


def refused(conn: sqlite3.Connection) -> dict | None:
    """Depuis quand le lien ne répond plus (publication annulée) ; None si tout va bien."""
    raw = db.get_meta(conn, REFUSED)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def feed_info(conn: sqlite3.Connection) -> dict:
    try:
        info = json.loads(db.get_meta(conn, "calendrier_info") or "{}")
    except ValueError:
        return {}
    return info if isinstance(info, dict) else {}


def source(conn: sqlite3.Connection) -> dict:
    """Mention de la source, à côté du titre des tuiles."""
    return {"cle": "calendrier", "nom": "Calendrier Garmin" if feed_info(conn).get("garmin") else "Agenda",
            "appareils": []}


# --------------------------------------------------------- prévu et fait
COMPATIBLE = {"course": metrics.RUNNING_SPORTS, "trail": metrics.RUNNING_SPORTS, "renfo": ("renfo", "cardio"),
              "cardio": ("cardio", "renfo"), "marche": ("marche", "rando"), "rando": ("rando", "marche")}


def _fits(planned: str | None, done: str | None) -> bool:
    if not planned:
        return True
    return done in COMPATIBLE.get(planned, (planned,))


def plan(conn: sqlite3.Connection, start: date, end: date, today: date | None = None,
         activities: list | None = None) -> list[dict]:
    """Événements de la période, chacun avec son état : « fait » (une séance du même sport ce jour-là),
    « manque » (jour passé, rien de tel), « aujourdhui », « a_venir ». Les événements « autre » restent neutres."""
    if not ready(conn):
        return []
    today = today or date.today()
    events = conn.execute("SELECT * FROM calendar_events WHERE date BETWEEN ? AND ? ORDER BY date, "
                          "COALESCE(start_local, date), id", (start.isoformat(), end.isoformat())).fetchall()
    if not events:
        return []
    if activities is None:
        activities = conn.execute("SELECT id, date, sport, name FROM activities WHERE date BETWEEN ? AND ? "
                                  "ORDER BY start_local", (start.isoformat(), end.isoformat())).fetchall()
    used: set[str] = set()
    matched: dict[int, Any] = {}
    # Les courses d'abord : la séance d'un jour de course, c'est la course
    for row in sorted(events, key=lambda r: (r["date"], r["kind"] != "course", r["start_local"] or "", r["id"])):
        if row["kind"] == "autre":
            continue
        found = next((a for a in activities if a["date"] == row["date"] and a["id"] not in used
                      and _fits(row["sport"], a["sport"])), None)
        if found is not None:
            used.add(found["id"])
            matched[row["id"]] = found
    out = []
    for row in events:
        day = date.fromisoformat(row["date"])
        done = matched.get(row["id"])
        if row["kind"] == "autre":
            state = "passe" if day < today else "aujourdhui" if day == today else "a_venir"
        else:
            state = "fait" if done is not None else "manque" if day < today else \
                "aujourdhui" if day == today else "a_venir"
        out.append({
            "id": row["id"], "date": row["date"], "heure": (row["start_local"] or "")[11:16] or None,
            "fin": row["end_local"], "titre": row["title"], "description": row["description"],
            "lieu": row["location"], "type": row["kind"], "sport": row["sport"],
            "sport_label": metrics.SPORTS.get(row["sport"]) if row["sport"] else None,
            "statut": state, "seance_id": done["id"] if done is not None else None,
            "seance_nom": done["name"] if done is not None else None, "journee": bool(row["all_day"]),
        })
    return out


def tally(items: list[dict]) -> dict:
    """Bilan d'une liste d'événements : prévus (séances et courses), faits, manqués, à venir."""
    counted = [i for i in items if i["type"] != "autre"]
    return {"prevues": len(counted), "faites": sum(i["statut"] == "fait" for i in counted),
            "manquees": sum(i["statut"] == "manque" for i in counted),
            "a_venir": sum(i["statut"] in ("a_venir", "aujourdhui") for i in counted),
            "courses": sum(i["type"] == "course" for i in counted)}


def next_race(conn: sqlite3.Connection, today: date | None = None) -> dict | None:
    if not ready(conn):
        return None
    today = today or date.today()
    row = conn.execute("SELECT * FROM calendar_events WHERE kind = 'course' AND date >= ? ORDER BY date, "
                       "COALESCE(start_local, date) LIMIT 1", (today.isoformat(),)).fetchone()
    if not row:
        return None
    return {"date": row["date"], "heure": (row["start_local"] or "")[11:16] or None, "titre": row["title"],
            "lieu": row["location"], "dans_jours": (date.fromisoformat(row["date"]) - today).days}


def status(conn: sqlite3.Connection, *, with_link: bool = False) -> dict[str, Any]:
    """Pour les Réglages, l'en-tête et Claude : relié ou non, dernière lecture, ce qui vient. Jamais le lien :
    au plus (with_link, Réglages seulement) sa version masquée."""
    demo = config.is_demo()
    url = None if demo else load_url()
    today = date.today()
    upcoming = {"n": 0, "c": 0}
    has_events = False
    if ready(conn):
        row = conn.execute("SELECT COUNT(*) AS n, SUM(kind = 'course') AS c FROM calendar_events WHERE date >= ? "
                           "AND kind <> 'autre'", (today.isoformat(),)).fetchone()
        upcoming = {"n": row["n"] or 0, "c": row["c"] or 0}
        has_events = conn.execute("SELECT 1 FROM calendar_events LIMIT 1").fetchone() is not None
    info = feed_info(conn)
    out = {"lie": bool(url) or (demo and has_events), "demo": demo, "nom": info.get("nom"),
           "garmin": bool(info.get("garmin")), "lu_le": db.get_meta(conn, "calendrier_lu_le"),
           "a_venir": upcoming["n"], "courses_a_venir": upcoming["c"], "prochaine_course": next_race(conn, today),
           "refus": refused(conn)}
    if with_link:
        out["masque"] = masked(url) if url else ""
    return out
