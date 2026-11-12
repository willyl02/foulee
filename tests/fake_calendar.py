"""Faux calendrier publié (iCal), comme celui de Garmin Connect : un lien secret, des séances prévues en journées
entières, une course avec son heure et son lieu. Le serveur peut aussi répondre « publication annulée » (404)."""

from __future__ import annotations

import datetime as dt
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Le jeton du lien, secret : les tests vérifient qu'il ne sort jamais (interface, Claude, journal, erreurs)
TOKEN = "f3c1a9e07b6d4e2a9c8b1d0e5f7a6b3c"


def ics_date(day: dt.date) -> str:
    return day.strftime("%Y%m%d")


def garmin_feed(today: dt.date, *, extra: list[str] | None = None) -> str:
    """Le calendrier tel que Garmin Connect le publie : l'avenir seulement, sans fuseau déclaré (VTIMEZONE)."""
    race = today + dt.timedelta(days=12)
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Garmin Connect//ICalProvider 1.0//EN", "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT", "UID:w1-garmin", f"DTSTAMP:{ics_date(today)}T060000Z",
        f"DTSTART;VALUE=DATE:{ics_date(today)}", f"DTEND;VALUE=DATE:{ics_date(today + dt.timedelta(days=1))}",
        "SUMMARY:Footing 45 min", "END:VEVENT",
        "BEGIN:VEVENT", "UID:w2-garmin", f"DTSTART;VALUE=DATE:{ics_date(today + dt.timedelta(days=1))}",
        "SUMMARY:Fractionné 10 × 400 m",
        "DESCRIPTION:Échauffement 20 min\\, puis 10 × 400 m à 100 % VMA\\nRécupération 1 min 30",
        "END:VEVENT",
        "BEGIN:VEVENT", "UID:w3-garmin", f"DTSTART;VALUE=DATE:{ics_date(today + dt.timedelta(days=3))}",
        "SUMMARY:Renforcement musculaire : gainage et PPG pour les coureurs qui veulent tenir la di",
        " stance", "END:VEVENT",
        "BEGIN:VEVENT", "UID:e1-garmin", f"DTSTART;TZID=Europe/Paris:{ics_date(race)}T093000",
        f"DTEND;TZID=Europe/Paris:{ics_date(race)}T113000", "SUMMARY:10 km de la Vallée",
        "LOCATION:Saint-Rémy\\, France", "END:VEVENT",
        *(extra or []),
        "END:VCALENDAR", "",
    ]
    return "\r\n".join(lines)


class FakeCalendar:
    """with FakeCalendar(feed) as cal: cal.link est le lien secret ; cal.status, cal.body se changent en cours."""

    def __init__(self, body: str, *, status: int = 200, content_type: str = "text/calendar; charset=utf-8"):
        self.body, self.status, self.content_type = body, status, content_type
        self.hits = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                outer.hits += 1
                if self.path != f"/modern/calendar/export/{TOKEN}":
                    self.send_response(404)
                    self.end_headers()
                    return
                payload = outer.body.encode("utf-8") if outer.status == 200 else b"Not Found"
                self.send_response(outer.status)
                self.send_header("Content-Type", outer.content_type if outer.status == 200 else "text/plain")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.link = f"{self.url}/modern/calendar/export/{TOKEN}"

    def __enter__(self) -> "FakeCalendar":
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()
