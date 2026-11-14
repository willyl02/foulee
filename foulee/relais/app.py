"""API du relais (``/api/v1/…``), que les Foulée des coachs et des élèves appellent.

Exposé sur Internet (par un tunnel Cloudflare, en HTTPS) : tout est refusé par défaut, sauf ces quelques
routes. Pas de page d'administration en ligne : les comptes coach se créent sur la machine du relais
(``foulee relais coach``). Après 5 mots de passe faux, un identifiant (ou une adresse) attend 15 minutes.
"""

from __future__ import annotations

import ipaddress
import logging
import time

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .. import __version__
from . import API_VERSION, club, store

log = logging.getLogger("foulee.relais")

MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60
MAX_BODY = 64 * 1024
MAX_SHARE = 4 * 1024 * 1024  # l'extrait de 4 semaines d'un élève, tracés GPS compris

HOME = """<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Relais Foulée</title><body style="font-family:system-ui;max-width:36em;margin:4em auto;padding:0 1em;color:#222">
<h1>Relais Foulée</h1><p>Ce relais relie les coachs et leurs élèves qui utilisent Foulée. Il ne s'ouvre pas dans un
navigateur : colle son adresse dans Foulée, Réglages → Coach et élèves.</p></body></html>"""


class Throttle:
    """Mots de passe faux : 5 essais par identifiant et par adresse, puis 15 minutes d'attente."""

    def __init__(self) -> None:
        self._state: dict[str, tuple[int, float]] = {}

    def blocked(self, *keys: str) -> bool:
        stamp = time.time()
        return any(self._state.get(key, (0, 0.0))[1] > stamp for key in keys)

    def failure(self, *keys: str) -> None:
        for key in keys:
            failures, until = self._state.get(key, (0, 0.0))
            failures += 1
            self._state[key] = (0, time.time() + LOCK_SECONDS) if failures >= MAX_FAILURES else (failures, until)
        if len(self._state) > 10000:  # garde-fou mémoire
            self._state.clear()

    def success(self, *keys: str) -> None:
        for key in keys:
            self._state.pop(key, None)


def client_ip(request: Request) -> str:
    """Adresse du visiteur : celle que donne Cloudflare quand la requête arrive par le tunnel (la machine
    elle-même), sinon l'adresse de la connexion. Un visiteur ne peut donc pas l'inventer."""
    host = request.client.host if request.client else ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host in ("testclient", "localhost")
    if loopback:
        return request.headers.get("cf-connecting-ip") or host
    return host


def create_relay_app() -> FastAPI:
    app = FastAPI(title="Relais Foulée", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    throttle = Throttle()
    with store.session():
        pass  # crée la base

    @app.middleware("http")
    async def guard(request: Request, call_next):
        length = request.headers.get("content-length")
        limit = MAX_SHARE if request.url.path == "/api/v1/partage" else MAX_BODY
        if length and length.isdigit() and int(length) > limit:
            return JSONResponse({"detail": "Requête trop volumineuse."}, status_code=413)
        response = await call_next(request)
        response.headers["X-Foulee-Api"] = str(API_VERSION)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def bearer(request: Request) -> str | None:
        value = request.headers.get("authorization") or ""
        return value[7:].strip() if value.lower().startswith("bearer ") else None

    def current(request: Request, conn, *, role: str | None = None):
        found = store.session_account(conn, bearer(request))
        if found is None:
            raise HTTPException(401, "Session expirée ou fermée : reconnecte-toi.")
        account, fingerprint = found
        if role and account["role"] != role:
            raise HTTPException(403, "Réservé aux coachs." if role == "coach" else "Réservé aux élèves.")
        return account, fingerprint

    def refuse(exc: store.RelayError) -> HTTPException:
        return HTTPException(400, str(exc))

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return HOME

    @app.get("/api/v1/sante")
    def health() -> dict:
        return {"service": "foulee-relais", "api": API_VERSION, "version": __version__}

    # ------------------------------------------------------------ connexion
    @app.post("/api/v1/connexion")
    def login(request: Request, payload: dict = Body(...)) -> dict:
        ident = str(payload.get("identifiant") or "").strip().lower()[:64]
        keys = (f"ip:{client_ip(request)}", f"id:{ident}")
        if throttle.blocked(*keys):
            raise HTTPException(429, "Trop d'essais : réessaie dans 15 minutes.")
        with store.session() as conn:
            account = store.authenticate(conn, ident, str(payload.get("mot_de_passe") or ""))
            if account is None:
                throttle.failure(*keys)
                raise HTTPException(401, "Identifiant ou mot de passe incorrect.")
            if not account["actif"]:
                raise HTTPException(403, "Ce compte est désactivé : vois avec ton coach ou l'administrateur.")
            throttle.success(*keys)
            token = store.open_session(conn, account["id"], payload.get("appareil"))
            fresh = conn.execute("SELECT * FROM comptes WHERE id = ?", (account["id"],)).fetchone()
            log.info("Connexion de %s (%s)", account["identifiant"], account["role"])
            return {"jeton": token, "compte": store.account_dict(fresh, conn)}

    @app.post("/api/v1/inscription")
    def register(request: Request, payload: dict = Body(...)) -> dict:
        keys = (f"ip:{client_ip(request)}",)
        if throttle.blocked(*keys):
            raise HTTPException(429, "Trop d'essais : réessaie dans 15 minutes.")
        with store.session() as conn:
            try:
                account = store.join(conn, code=str(payload.get("code") or ""),
                                     ident=str(payload.get("identifiant") or ""),
                                     name=str(payload.get("nom") or ""),
                                     password=str(payload.get("mot_de_passe") or ""))
            except store.RelayError as exc:
                if "invitation" in str(exc):
                    throttle.failure(*keys)  # deviner des codes coûte cher
                raise refuse(exc) from None
            token = store.open_session(conn, account["id"], payload.get("appareil"))
            log.info("Inscription de %s", account["identifiant"])
            return {"jeton": token, "compte": account}

    @app.post("/api/v1/deconnexion")
    def logout(request: Request) -> dict:
        with store.session() as conn:
            found = store.session_account(conn, bearer(request))
            if found:
                store.close_session(conn, found[1])
        return {"ok": True}

    # ---------------------------------------------------------------- moi
    @app.get("/api/v1/moi")
    def me(request: Request) -> dict:
        with store.session() as conn:
            account, _ = current(request, conn)
            return {"compte": store.account_dict(account, conn)}

    @app.post("/api/v1/moi/mot-de-passe")
    def change_password(request: Request, payload: dict = Body(...)) -> dict:
        with store.session() as conn:
            account, fingerprint = current(request, conn)
            if not store.check_password(str(payload.get("actuel") or ""), account["mot_de_passe"]):
                raise HTTPException(400, "Mot de passe actuel incorrect.")
            try:
                store.set_password(conn, account["id"], str(payload.get("nouveau") or ""), keep=fingerprint)
            except store.RelayError as exc:
                raise refuse(exc) from None
        return {"ok": True}

    @app.post("/api/v1/moi/quitter")
    def leave(request: Request, payload: dict = Body(...)) -> dict:
        """Un élève quitte son coach : son compte et tout ce qu'il a partagé sont effacés du relais."""
        with store.session() as conn:
            account, _ = current(request, conn, role="eleve")
            if not store.check_password(str(payload.get("mot_de_passe") or ""), account["mot_de_passe"]):
                raise HTTPException(400, "Mot de passe incorrect.")
            store.delete_account(conn, account["id"])
            log.info("%s a quitté le relais", account["identifiant"])
        return {"ok": True}

    # -------------------------------------------------------------- coach
    @app.get("/api/v1/eleves")
    def list_students(request: Request) -> dict:
        with store.session() as conn:
            account, _ = current(request, conn, role="coach")
            return {"eleves": store.students(conn, account["id"])}

    @app.delete("/api/v1/eleves/{student_id}")
    def remove_student(student_id: int, request: Request) -> dict:
        with store.session() as conn:
            account, _ = current(request, conn, role="coach")
            row = conn.execute("SELECT id FROM comptes WHERE id = ? AND role = 'eleve' AND coach_id = ?",
                               (student_id, account["id"])).fetchone()
            if row is None:
                raise HTTPException(404, "Élève introuvable dans ton groupe.")
            store.delete_account(conn, student_id)
            return {"eleves": store.students(conn, account["id"])}

    @app.get("/api/v1/invitations")
    def list_invitations(request: Request) -> dict:
        with store.session() as conn:
            account, _ = current(request, conn, role="coach")
            return {"invitations": store.invitations(conn, account["id"])}

    @app.post("/api/v1/invitations")
    def new_invitation(request: Request) -> dict:
        with store.session() as conn:
            account, _ = current(request, conn, role="coach")
            try:
                created = store.create_invitation(conn, account["id"])
            except store.RelayError as exc:
                raise refuse(exc) from None
            return {"invitation": created, "invitations": store.invitations(conn, account["id"])}

    @app.delete("/api/v1/invitations/{code}")
    def cancel_invitation(code: str, request: Request) -> dict:
        with store.session() as conn:
            account, _ = current(request, conn, role="coach")
            store.cancel_invitation(conn, account["id"], code)
            return {"invitations": store.invitations(conn, account["id"])}

    # ------------------------------------------------- partage, messages, séances
    def run(request: Request, action, *, role: str | None = None):
        """Ouvre la base, vérifie la session (et le rôle), traduit les refus en réponses claires."""
        with store.session() as conn:
            account, _ = current(request, conn, role=role)
            try:
                return action(conn, account)
            except store.RelayError as exc:
                raise refuse(exc) from None
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from None

    @app.get("/api/v1/partage/accord")
    def get_accord(request: Request) -> dict:
        return run(request, lambda conn, me: {"accord": club.get_accord(conn, me["id"]),
                                              "defaut": club.ACCORD_DEFAULT}, role="eleve")

    @app.put("/api/v1/partage/accord")
    def put_accord(request: Request, payload: dict = Body(...)) -> dict:
        return run(request, lambda conn, me: {"accord": club.set_accord(conn, me["id"], payload)}, role="eleve")

    @app.put("/api/v1/partage")
    def put_share(request: Request, payload: dict = Body(...)) -> dict:
        return run(request, lambda conn, me: club.receive_share(conn, me["id"], payload), role="eleve")

    @app.get("/api/v1/moi/coach")
    def my_coach(request: Request) -> dict:
        return run(request, lambda conn, me: club.my_page(conn, me), role="eleve")

    @app.get("/api/v1/moi/seances/{key}")
    def my_session(key: str, request: Request) -> dict:
        return run(request, lambda conn, me: club.student_session(conn, me, me["id"], key), role="eleve")

    @app.get("/api/v1/groupe")
    def group_overview(request: Request) -> dict:
        return run(request, lambda conn, me: {"eleves": club.overview(conn, me),
                                              "invitations": store.invitations(conn, me["id"])}, role="coach")

    @app.get("/api/v1/eleves/{student_id}/fiche")
    def student_page(student_id: int, request: Request, semaine: str | None = None) -> dict:
        return run(request, lambda conn, me: club.student_page(conn, me, student_id, club.parse_monday(semaine)),
                   role="coach")

    @app.get("/api/v1/eleves/{student_id}/seances/{key}")
    def student_session(student_id: int, key: str, request: Request) -> dict:
        return run(request, lambda conn, me: club.student_session(conn, me, student_id, key), role="coach")

    @app.post("/api/v1/propositions")
    def new_proposals(request: Request, payload: dict = Body(...)) -> dict:
        return run(request, lambda conn, me: {"propositions": club.create_proposals(conn, me["id"], payload)},
                   role="coach")

    @app.put("/api/v1/propositions/{proposal_id}")
    def edit_proposal(proposal_id: int, request: Request, payload: dict = Body(...)) -> dict:
        return run(request, lambda conn, me: {"proposition": club.update_proposal(conn, me["id"], proposal_id,
                                                                                   payload)}, role="coach")

    @app.delete("/api/v1/propositions/{proposal_id}")
    def drop_proposal(proposal_id: int, request: Request) -> dict:
        return run(request, lambda conn, me: {"ok": club.delete_proposal(conn, me["id"], proposal_id)}, role="coach")

    @app.get("/api/v1/modeles")
    def list_templates(request: Request) -> dict:
        return run(request, lambda conn, me: {"modeles": club.templates(conn, me["id"])}, role="coach")

    @app.post("/api/v1/modeles")
    def new_template(request: Request, payload: dict = Body(...)) -> dict:
        return run(request, lambda conn, me: {"modeles": club.save_template(conn, me["id"], payload)}, role="coach")

    @app.delete("/api/v1/modeles/{template_id}")
    def drop_template(template_id: int, request: Request) -> dict:
        return run(request, lambda conn, me: {"modeles": club.delete_template(conn, me["id"], template_id)},
                   role="coach")

    @app.get("/api/v1/fils")
    def list_threads(request: Request) -> dict:
        return run(request, lambda conn, me: {"fils": club.threads(conn, me)})

    @app.get("/api/v1/fils/{thread}")
    def read_thread(thread: str, request: Request, apres: int = 0) -> dict:
        return run(request, lambda conn, me: club.read_thread(conn, me, thread, apres))

    @app.post("/api/v1/fils/{thread}")
    def write(thread: str, request: Request, payload: dict = Body(...)) -> dict:
        return run(request, lambda conn, me: {"message": club.post(conn, me, thread, payload.get("texte"))})

    @app.post("/api/v1/messages/{message_id}/epingle")
    def pin(message_id: int, request: Request, payload: dict = Body(...)) -> dict:
        def action(conn, me):
            club.pin(conn, me, message_id, bool(payload.get("epingle", True)))
            return {"ok": True}
        return run(request, action)

    @app.delete("/api/v1/messages/{message_id}")
    def erase(message_id: int, request: Request) -> dict:
        def action(conn, me):
            club.delete_message(conn, me, message_id)
            return {"ok": True}
        return run(request, action)

    @app.get("/api/v1/nouveautes")
    def news(request: Request) -> dict:
        """Relevé léger, toutes les minutes : non lus et repère des changements."""
        return run(request, lambda conn, me: {"non_lus": club.unread_total(conn, me),
                                              "repere": club.last_activity(conn, me)})

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False)
    def not_found(path: str) -> JSONResponse:
        return JSONResponse({"detail": "Introuvable."}, status_code=404)

    return app
