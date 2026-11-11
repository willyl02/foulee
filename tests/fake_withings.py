"""Faux Withings pour les tests : mêmes chemins, mêmes paramètres et mêmes réponses que l'API publique.

- ``/oauth2_user/authorize2`` : la page « Autoriser » (le faux clique tout de suite sur « Allow »,
  ou sur « Deny » si ``deny`` est vrai) puis renvoie vers l'adresse de retour avec un code ;
- ``/v2/oauth2`` : échange du code et renouvellement des jetons (le jeton de renouvellement
  change à chaque fois, l'ancien ne vaut plus rien) ;
- ``/measure`` (getmeas), ``/v2/sleep`` (getsummary), ``/v2/measure`` (getactivity), par pages.

Les valeurs sont inventées ; la structure suit les réponses réelles de Withings.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
CLIENT_ID = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9"  # inventé
CLIENT_SECRET = "f9e8d7c6b5a40312f9e8d7c6b5a40312f9e8d7c6b5a40312f9e8d7c6b5a40312"  # inventé


def stamp(day: dt.date, hour: int, minute: int = 0) -> int:
    return int(dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=PARIS).timestamp())


def measure(value: float, kind: int, unit: int) -> dict:
    return {"value": int(round(value * 10 ** -unit)), "type": kind, "unit": unit, "algo": 0, "fm": 3}


class FakeWithings:
    def __init__(self, days: int = 40, *, relay: str = "https://relais.test/foulee/withings/", page: int = 7):
        self.today = dt.date.today()
        self.relay = relay
        self.page = page                      # groupes de mesures par page (pagination « more / offset »)
        self.codes: dict[str, float] = {}     # code d'autorisation → heure d'émission
        self.access: str | None = None
        self.refresh: str | None = None
        self.revoked = False                  # autorisation retirée dans le compte Withings
        self.deny = False                     # l'utilisateur clique sur « Deny »
        self.requests: list[tuple[str, dict]] = []
        self.groups: list[dict] = []
        self.sleeps: list[dict] = []
        self.activities: list[dict] = []
        self._build(days)

    # ------------------------------------------------------------ données
    def _build(self, days: int) -> None:
        grpid = 1000
        first = self.today - dt.timedelta(days=days)
        # La taille, saisie à la création du compte (sert à l'IMC)
        self.groups.append({"grpid": grpid, "attrib": 4, "date": stamp(first, 9), "created": stamp(first, 9),
                            "modified": stamp(first, 9), "category": 1, "deviceid": None, "hash_deviceid": None,
                            "measures": [measure(1.78, 4, -2)], "comment": None, "timezone": "Europe/Paris"})
        for i in range(days):
            day = first + dt.timedelta(days=i + 1)
            weight = 74.0 - 0.02 * i
            for hour, extra in ((7, 0.0), (21, 0.6)) if i % 5 == 0 else ((7, 0.0),):  # deux pesées certains jours
                grpid += 1
                w = weight + extra
                self.groups.append({
                    "grpid": grpid, "attrib": 0, "date": stamp(day, hour, 12), "created": stamp(day, hour, 13),
                    "modified": stamp(day, hour, 13), "category": 1, "deviceid": "bd1", "hash_deviceid": "bd1",
                    "measures": [measure(w, 1, -3), measure(16.0, 6, -1), measure(w * 0.16, 8, -2),
                                 measure(w * 0.84, 5, -2), measure(59.1, 76, -1), measure(w * 0.56, 77, -2),
                                 measure(3.1, 88, -1), measure(62, 11, 0)],
                    "comment": None, "timezone": "Europe/Paris"})
            if i % 3 == 0:  # tension : deux mesures le matin
                for minute, (sys_, dia) in ((0, (124, 80)), (3, (120, 78))):
                    grpid += 1
                    self.groups.append({
                        "grpid": grpid, "attrib": 0, "date": stamp(day, 8, minute), "created": stamp(day, 8, minute),
                        "modified": stamp(day, 8, minute), "category": 1, "deviceid": "bpm", "hash_deviceid": "bpm",
                        "measures": [measure(sys_, 10, 0), measure(dia, 9, 0), measure(58, 11, 0)],
                        "comment": None, "timezone": "Europe/Paris"})
            night_start = stamp(day - dt.timedelta(days=1), 23, 10)
            night_end = stamp(day, 6, 40)
            self.sleeps.append({
                "id": 9000 + i, "timezone": "Europe/Paris", "model": 32, "model_id": 63, "hash_deviceid": "sa1",
                "startdate": night_start, "enddate": night_end, "date": (day - dt.timedelta(days=1)).isoformat(),
                "created": night_end + 600, "modified": night_end + 600,
                "data": {"total_sleep_time": 25200, "total_timeinbed": 27000, "deepsleepduration": 5400,
                         "lightsleepduration": 14400, "remsleepduration": 5400, "wakeupduration": 1200,
                         "wakeupcount": 2, "sleep_latency": 600, "sleep_efficiency": 0.93, "sleep_score": 81,
                         "hr_average": 52, "hr_min": 47, "rr_average": 14, "snoring": 420, "out_of_bed_count": 1},
            })
            self.activities.append({
                "date": day.isoformat(), "timezone": "Europe/Paris", "deviceid": None, "hash_deviceid": None,
                "brand": 18, "is_tracker": False, "steps": 8000 + i * 10, "distance": 6100.5, "elevation": 12,
                "soft": 3600, "moderate": 1200, "intense": 300, "active": 1500, "calories": 410.5,
                "totalcalories": 2350.2, "hr_average": 0, "hr_min": 0, "hr_max": 0, "modified": stamp(day, 23),
            })
        # Un objectif de poids fixé par l'utilisateur (catégorie 2) : à ignorer
        self.groups.append({"grpid": 99999, "attrib": 2, "date": stamp(self.today, 10), "created": stamp(self.today, 10),
                            "modified": stamp(self.today, 10), "category": 2, "deviceid": None, "hash_deviceid": None,
                            "measures": [measure(70.0, 1, -3)], "comment": None, "timezone": "Europe/Paris"})

    def add_weight(self, day: dt.date, hour: int, kilos: float) -> int:
        grpid = max(g["grpid"] for g in self.groups) + 1
        now = int(time.time())
        self.groups.append({"grpid": grpid, "attrib": 0, "date": stamp(day, hour), "created": now, "modified": now,
                            "category": 1, "deviceid": "bd1", "hash_deviceid": "bd1",
                            "measures": [measure(kilos, 1, -3)], "comment": None, "timezone": "Europe/Paris"})
        return grpid

    def issue_code(self) -> str:
        code = secrets.token_hex(20)
        self.codes[code] = time.time()
        return code

    def expire_access(self) -> None:
        self.access = "jeton-perime"

    # ------------------------------------------------------------ serveur
    def __enter__(self) -> "FakeWithings":
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, payload: dict) -> None:
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                url = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                fake.requests.append((url.path, query))
                if url.path != "/oauth2_user/authorize2":
                    self.send_response(404)
                    self.end_headers()
                    return
                params = {"state": query.get("state", "")}
                if fake.deny:
                    params["error"] = "access_denied"
                else:
                    params["code"] = fake.issue_code()
                self.send_response(302)
                self.send_header("Location", f"{query['redirect_uri']}?{urlencode(params)}")
                self.end_headers()

            def do_POST(self):
                url = urlparse(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
                fake.requests.append((url.path, form))
                if url.path == "/v2/oauth2":
                    self._reply(fake.oauth(form))
                    return
                token = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
                if fake.revoked or not token or token != fake.access:
                    self._reply({"status": 401, "body": {},
                                 "error": "XRequestID: Not provided invalid_token: The access token provided is invalid"})
                    return
                action = form.get("action")
                if url.path == "/measure" and action == "getmeas":
                    self._reply({"status": 0, "body": fake.getmeas(form)})
                elif url.path == "/v2/sleep" and action == "getsummary":
                    self._reply({"status": 0, "body": fake.getsummary(form)})
                elif url.path == "/v2/measure" and action == "getactivity":
                    self._reply({"status": 0, "body": fake.getactivity(form)})
                else:
                    self._reply({"status": 2555, "body": {}, "error": "Unknown action"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()

    # ------------------------------------------------------------ réponses
    def oauth(self, form: dict) -> dict:
        if form.get("action") != "requesttoken":
            return {"status": 503, "body": {}, "error": "Invalid Params: invalid action"}
        if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
            return {"status": 503, "body": {}, "error": "Invalid Params: invalid client id or secret"}
        grant = form.get("grant_type")
        if grant == "authorization_code":
            issued = self.codes.pop(form.get("code", ""), None)
            if issued is None or time.time() - issued > 30:
                return {"status": 503, "body": {}, "error": "Invalid Params: invalid code"}
            if form.get("redirect_uri") != self.relay:
                return {"status": 503, "body": {}, "error": "Invalid Params: redirect_uri_mismatch"}
            self.revoked = False
        elif grant == "refresh_token":
            if self.revoked or form.get("refresh_token") != self.refresh:
                return {"status": 503, "body": {}, "error": "Invalid Params: invalid refresh_token"}
        else:
            return {"status": 503, "body": {}, "error": "Invalid Params: invalid grant_type"}
        self.access, self.refresh = secrets.token_hex(20), secrets.token_hex(20)
        return {"status": 0, "body": {"userid": "4242", "access_token": self.access, "refresh_token": self.refresh,
                                      "expires_in": 10800, "scope": "user.info,user.metrics,user.activity,user.sleepevents",
                                      "csrf_token": "x", "token_type": "Bearer"}}

    @staticmethod
    def _since(form: dict) -> int:
        return int(form.get("lastupdate") or 0)

    def getmeas(self, form: dict) -> dict:
        since = self._since(form)
        groups = [g for g in self.groups if g["modified"] >= since]
        if form.get("category"):
            groups = [g for g in groups if g["category"] == int(form["category"])]
        if form.get("meastype"):  # les groupes qui ont ce type de mesure, réduits à lui
            kind = int(form["meastype"])
            groups = [{**g, "measures": [m for m in g["measures"] if m["type"] == kind]}
                      for g in groups if any(m["type"] == kind for m in g["measures"])]
        offset = int(form.get("offset") or 0)
        chunk = groups[offset:offset + self.page]
        more = offset + self.page < len(groups)
        return {"updatetime": int(time.time()), "timezone": "Europe/Paris", "measuregrps": chunk,
                "more": 1 if more else 0, "offset": offset + self.page if more else 0}

    def getsummary(self, form: dict) -> dict:
        since = self._since(form)
        return {"series": [s for s in self.sleeps if s["modified"] >= since], "more": False, "offset": 0}

    def getactivity(self, form: dict) -> dict:
        since = self._since(form)
        return {"activities": [a for a in self.activities if a["modified"] >= since], "more": False, "offset": 0}
