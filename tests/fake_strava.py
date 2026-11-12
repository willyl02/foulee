"""Faux Strava pour les tests : mêmes chemins, mêmes paramètres et mêmes réponses que l'API publique (v3).

- ``/oauth/token`` : échange du code et renouvellement des jetons ; ``/oauth/revoke`` : retrait de l'accès ;
- ``/api/v3/athlete/activities`` (après une date, par pages), ``/api/v3/activities/{id}`` (détail) et
  ``/api/v3/activities/{id}/streams`` (courbes), avec les en-têtes de quota de Strava.

Chaque requête est notée (méthode, chemin, paramètres) : les tests vérifient que les données ne sont lues
qu'en GET. Les valeurs sont inventées ; la structure suit les réponses réelles de Strava.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CLIENT_ID = "123456"                                       # inventé
CLIENT_SECRET = "0123456789abcdef0123456789abcdef01234567"  # inventé (40 caractères hexadécimaux)


def run(strava_id: int, start: dt.datetime, minutes: float, *, km: float = 0.0, sport: str = "Run",
        name: str = "Course", device: str | None = "COROS PACE 3", external_id: str | None = None,
        hr: float | None = 142.0, description: str | None = None, manual: bool = False) -> dict:
    """Une séance Strava (SummaryActivity), heure locale ``start`` (Paris, en hiver : UTC+1)."""
    seconds = int(minutes * 60)
    return {
        "id": strava_id, "name": name, "sport_type": sport, "type": sport, "distance": km * 1000,
        "moving_time": seconds, "elapsed_time": seconds, "total_elevation_gain": 42.0,
        "start_date": (start - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start_date_local": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "timezone": "(GMT+01:00) Europe/Paris",
        "average_speed": km * 1000 / seconds if km else 0.0, "max_speed": 4.2 if km else 0.0,
        "average_cadence": 88.0 if km else None, "has_heartrate": hr is not None, "average_heartrate": hr,
        "max_heartrate": hr + 20 if hr else None, "device_name": device, "external_id": external_id,
        "upload_id": strava_id * 3, "manual": manual, "private": False, "visibility": "everyone", "trainer": False,
        "kudos_count": 3, "map": {"id": f"a{strava_id}", "summary_polyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
        "start_latlng": [48.40, 2.70] if km else [],
        # détail (DetailedActivity), rendu seulement par /activities/{id}
        "_description": description, "_calories": 420.0,
    }


class FakeStrava:
    def __init__(self, activities: list[dict] | None = None, *, limit15: int = 100, limit_day: int = 1000):
        self.activities = list(activities or [])
        self.codes: dict[str, bool] = {}
        self.access: str | None = None
        self.refresh: str | None = None
        self.revoked = False
        self.scope = "read,activity:read_all"
        self.requests: list[tuple[str, str, dict]] = []
        self.limit15, self.limit_day = limit15, limit_day
        self.used15 = self.used_day = 0
        self.athlete = {"id": 987654, "firstname": "Test", "lastname": "Athlète"}

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def issue_code(self) -> str:
        code = secrets.token_hex(20)
        self.codes[code] = True
        return code

    def api_calls(self) -> list[tuple[str, str, dict]]:
        return [r for r in self.requests if r[1].startswith("/api/v3/")]

    def detail(self, item: dict) -> dict:
        out = {k: v for k, v in item.items() if not k.startswith("_")}
        out["description"] = item.get("_description")
        out["calories"] = item.get("_calories")
        seconds = item["elapsed_time"]
        out["laps"] = [{"lap_index": i + 1, "elapsed_time": seconds // 2, "moving_time": seconds // 2,
                        "distance": item["distance"] / 2, "average_speed": item["average_speed"],
                        "average_heartrate": item.get("average_heartrate"), "average_cadence": 88.0}
                       for i in range(2)] if item["distance"] else []
        return out

    def streams(self, item: dict) -> dict:
        n = max(2, item["elapsed_time"] // 10)
        return {
            "time": {"data": [i * 10 for i in range(n)], "series_type": "time", "original_size": n},
            "heartrate": {"data": [140 + (i % 7) for i in range(n)]},
            "velocity_smooth": {"data": [3.2 for _ in range(n)]},
            "distance": {"data": [i * 32.0 for i in range(n)]},
            "altitude": {"data": [80 + (i % 5) for i in range(n)]},
            "cadence": {"data": [88 for _ in range(n)]},
            "latlng": {"data": [[48.40 + i * 1e-4, 2.70 + i * 1e-4] for i in range(n)]},
        }

    def __enter__(self) -> "FakeStrava":
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, status: int, payload, *, quota: bool = False) -> None:
                body = b"" if payload is None else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                if quota:
                    for prefix in ("X-RateLimit", "X-ReadRateLimit"):
                        self.send_header(f"{prefix}-Limit", f"{fake.limit15},{fake.limit_day}")
                        self.send_header(f"{prefix}-Usage", f"{fake.used15},{fake.used_day}")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
                path = urlparse(self.path).path
                fake.requests.append(("POST", path, form))
                if path == "/oauth/token":
                    if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
                        return self._reply(401, {"message": "Bad Request", "errors": [
                            {"resource": "Application", "field": "client_id", "code": "invalid"}]})
                    if form.get("grant_type") == "authorization_code":
                        if not fake.codes.pop(form.get("code", ""), None):
                            return self._reply(400, {"message": "Bad Request", "errors": [
                                {"resource": "AuthorizationCode", "field": "code", "code": "invalid"}]})
                        fake.revoked = False
                        fake.refresh = secrets.token_hex(20)
                    elif form.get("grant_type") == "refresh_token":
                        if fake.revoked or form.get("refresh_token") != fake.refresh:
                            return self._reply(400, {"message": "Bad Request", "errors": [
                                {"resource": "RefreshToken", "field": "refresh_token", "code": "invalid"}]})
                    else:
                        return self._reply(400, {"message": "Bad Request"})
                    fake.access = secrets.token_hex(20)
                    now = int(dt.datetime.now().timestamp())
                    body = {"token_type": "Bearer", "access_token": fake.access, "refresh_token": fake.refresh,
                            "expires_at": now + 21600, "expires_in": 21600, "scope": fake.scope}
                    if form.get("grant_type") == "authorization_code":
                        body["athlete"] = fake.athlete
                    return self._reply(200, body)
                if path == "/oauth/revoke":
                    auth = self.headers.get("Authorization", "")
                    expected = "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
                    if auth != expected:
                        return self._reply(401, {"message": "Authorization Error"})
                    fake.revoked = True
                    return self._reply(200, None)
                self._reply(404, {"message": "Record Not Found"})

            def do_GET(self):
                parts = urlparse(self.path)
                params = {k: v[0] for k, v in parse_qs(parts.query).items()}
                fake.requests.append(("GET", parts.path, params))
                if self.headers.get("Authorization") != f"Bearer {fake.access}" or fake.revoked or not fake.access:
                    return self._reply(401, {"message": "Authorization Error", "errors": [
                        {"resource": "Athlete", "field": "access_token", "code": "invalid"}]})
                if fake.used15 >= fake.limit15 or fake.used_day >= fake.limit_day:
                    return self._reply(429, {"message": "Rate Limit Exceeded"}, quota=True)
                fake.used15 += 1
                fake.used_day += 1
                path = parts.path.removeprefix("/api/v3")
                if path == "/athlete/activities":
                    after = int(params.get("after", 0))
                    page, per_page = int(params.get("page", 1)), int(params.get("per_page", 30))
                    items = sorted((a for a in fake.activities if dt.datetime.strptime(
                        a["start_date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp() > after),
                        key=lambda a: a["start_date"], reverse=True)
                    chunk = items[(page - 1) * per_page: page * per_page]
                    return self._reply(200, [{k: v for k, v in a.items() if not k.startswith("_")} for a in chunk],
                                       quota=True)
                bits = path.strip("/").split("/")
                if len(bits) >= 2 and bits[0] == "activities":
                    item = next((a for a in fake.activities if str(a["id"]) == bits[1]), None)
                    if item is None:
                        return self._reply(404, {"message": "Record Not Found"}, quota=True)
                    if len(bits) == 2:
                        return self._reply(200, fake.detail(item), quota=True)
                    if bits[2:] == ["streams"]:
                        return self._reply(200, fake.streams(item), quota=True)
                self._reply(404, {"message": "Record Not Found"}, quota=True)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()
