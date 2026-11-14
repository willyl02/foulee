"""Base du relais : comptes, invitations, sessions (SQLite, ``relais.db`` dans le dossier des données).

- Les mots de passe ne sont jamais gardés, seulement leur empreinte scrypt (lente et gourmande en mémoire,
  pour décourager les essais en masse), avec un sel propre à chaque compte.
- Les jetons de session non plus : seule leur empreinte SHA-256 est en base. Un jeton volé dans une sauvegarde
  de la base ne sert donc à rien.
- Rôles : « coach » (avec ou sans la casquette d'administrateur, qui crée les comptes coach) et « eleve »,
  rattaché à un coach. Un élève rejoint son coach avec un code d'invitation, à usage unique.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS comptes (
    id                  INTEGER PRIMARY KEY,
    identifiant         TEXT NOT NULL UNIQUE,
    nom                 TEXT NOT NULL,
    role                TEXT NOT NULL CHECK (role IN ('coach', 'eleve')),
    admin               INTEGER NOT NULL DEFAULT 0,
    coach_id            INTEGER REFERENCES comptes(id) ON DELETE CASCADE,
    mot_de_passe        TEXT NOT NULL,
    actif               INTEGER NOT NULL DEFAULT 1,
    cree_le             TEXT NOT NULL,
    derniere_connexion  TEXT
);

CREATE TABLE IF NOT EXISTS invitations (
    code         TEXT PRIMARY KEY,
    coach_id     INTEGER NOT NULL REFERENCES comptes(id) ON DELETE CASCADE,
    cree_le      TEXT NOT NULL,
    expire_le    TEXT NOT NULL,
    utilisee_par INTEGER REFERENCES comptes(id) ON DELETE SET NULL,
    utilisee_le  TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    empreinte  TEXT PRIMARY KEY,
    compte_id  INTEGER NOT NULL REFERENCES comptes(id) ON DELETE CASCADE,
    appareil   TEXT NOT NULL DEFAULT '',
    cree_le    TEXT NOT NULL,
    vu_le      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_compte ON sessions(compte_id);

-- Ce que chaque élève a accepté de partager, et le dernier extrait reçu (4 semaines, remplacé à chaque envoi)
CREATE TABLE IF NOT EXISTS accords (
    eleve_id    INTEGER PRIMARY KEY REFERENCES comptes(id) ON DELETE CASCADE,
    choix       TEXT NOT NULL,
    modifie_le  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS partages (
    eleve_id    INTEGER PRIMARY KEY REFERENCES comptes(id) ON DELETE CASCADE,
    contenu     TEXT NOT NULL,
    recu_le     TEXT NOT NULL
);

-- Messages : fil du groupe (« groupe »), conversation coach-élève (« eleve-ID »), fil d'une séance
-- (« seance-ID-CLE »). coach_id = le groupe auquel le fil appartient.
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY,
    coach_id   INTEGER NOT NULL REFERENCES comptes(id) ON DELETE CASCADE,
    fil        TEXT NOT NULL,
    auteur_id  INTEGER REFERENCES comptes(id) ON DELETE SET NULL,
    texte      TEXT NOT NULL,
    cree_le    TEXT NOT NULL,
    epingle    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS messages_fil ON messages(coach_id, fil, id);
CREATE TABLE IF NOT EXISTS lus (
    compte_id  INTEGER NOT NULL REFERENCES comptes(id) ON DELETE CASCADE,
    fil        TEXT NOT NULL,
    dernier_id INTEGER NOT NULL,
    PRIMARY KEY (compte_id, fil)
);

-- Séances proposées par le coach (une ligne par élève), et ses modèles
CREATE TABLE IF NOT EXISTS propositions (
    id          INTEGER PRIMARY KEY,
    coach_id    INTEGER NOT NULL REFERENCES comptes(id) ON DELETE CASCADE,
    eleve_id    INTEGER NOT NULL REFERENCES comptes(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    titre       TEXT NOT NULL,
    sport       TEXT NOT NULL,
    contenu     TEXT NOT NULL,
    cree_le     TEXT NOT NULL,
    modifie_le  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS propositions_eleve ON propositions(eleve_id, date);
CREATE TABLE IF NOT EXISTS modeles (
    id        INTEGER PRIMARY KEY,
    coach_id  INTEGER NOT NULL REFERENCES comptes(id) ON DELETE CASCADE,
    titre     TEXT NOT NULL,
    sport     TEXT NOT NULL,
    contenu   TEXT NOT NULL,
    cree_le   TEXT NOT NULL
);
"""

SCHEMA_VERSION = 1
INVITATION_DAYS = 7
SESSION_DAYS = 180          # une session non utilisée pendant 6 mois expire
MIN_PASSWORD = 10
IDENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans 0/O ni 1/I : se dicte sans erreur
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


class RelayError(ValueError):
    """Refus expliqué en français (montré tel quel à l'utilisateur)."""


def _zone():
    """L'heure du club (Paris par défaut, FOULEE_RELAIS_TZ sinon) : un serveur loué tourne souvent en UTC, et les
    élèves lisent l'heure de leurs messages comme sur leur montre."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(os.environ.get("FOULEE_RELAIS_TZ") or "Europe/Paris")
    except Exception:  # base des fuseaux absente : l'heure du serveur
        return None


def local_now() -> datetime:
    zone = _zone()
    return datetime.now(zone).replace(tzinfo=None) if zone else datetime.now()


def now() -> str:
    return local_now().replace(microsecond=0).isoformat(sep=" ")


def db_path() -> Path:
    base = Path(os.environ.get("FOULEE_DATA") or Path.home() / ".local" / "share" / "foulee")
    base.mkdir(parents=True, exist_ok=True)
    return base / "relais.db"


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
        yield conn
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------ mots de passe
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, maxmem=64 * 1024 * 1024, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, digest = stored.split("$")
        if kind != "scrypt":
            return False
        computed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                                  dklen=32, maxmem=64 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(computed.hex(), digest)


_DUMMY = None


def burn_time() -> None:
    """Identifiant inconnu : on calcule quand même une empreinte, pour ne pas révéler qu'il n'existe pas."""
    global _DUMMY
    _DUMMY = _DUMMY or hash_password("rien-du-tout-123")
    check_password("rien-du-tout-123x", _DUMMY)


def validate_password(password: str | None) -> str:
    password = password or ""
    if len(password) < MIN_PASSWORD:
        raise RelayError(f"Mot de passe trop court : {MIN_PASSWORD} caractères au moins.")
    if len(password) > 200:
        raise RelayError("Mot de passe trop long (200 caractères au plus).")
    return password


def clean_ident(ident: str | None) -> str:
    value = (ident or "").strip().lower()
    if not IDENT_RE.match(value):
        raise RelayError("Identifiant : 3 à 32 caractères, lettres minuscules sans accent, chiffres, point, tiret "
                         "ou soulignement (par exemple « marie.dupont »).")
    return value


def clean_name(name: str | None) -> str:
    value = " ".join((name or "").split())
    if not 1 <= len(value) <= 60:
        raise RelayError("Nom affiché : 1 à 60 caractères (par exemple « Marie D. »).")
    return value


# ------------------------------------------------------------------- comptes
def account_dict(row: sqlite3.Row, conn: sqlite3.Connection | None = None) -> dict:
    data = {"id": row["id"], "identifiant": row["identifiant"], "nom": row["nom"], "role": row["role"],
            "admin": bool(row["admin"]), "actif": bool(row["actif"]), "cree_le": row["cree_le"],
            "derniere_connexion": row["derniere_connexion"]}
    if conn is not None and row["role"] == "eleve" and row["coach_id"]:
        coach = conn.execute("SELECT nom, identifiant FROM comptes WHERE id = ?", (row["coach_id"],)).fetchone()
        data["coach"] = {"nom": coach["nom"], "identifiant": coach["identifiant"]} if coach else None
    return data


def create_account(conn: sqlite3.Connection, *, ident: str, name: str, password: str, role: str,
                   admin: bool = False, coach_id: int | None = None) -> dict:
    ident, name, password = clean_ident(ident), clean_name(name), validate_password(password)
    if role not in ("coach", "eleve"):
        raise RelayError("Rôle inconnu.")
    if conn.execute("SELECT 1 FROM comptes WHERE identifiant = ?", (ident,)).fetchone():
        raise RelayError(f"L'identifiant « {ident} » est déjà pris : choisis-en un autre.")
    cur = conn.execute(
        "INSERT INTO comptes(identifiant, nom, role, admin, coach_id, mot_de_passe, cree_le) VALUES (?,?,?,?,?,?,?)",
        (ident, name, role, int(admin), coach_id, hash_password(password), now()))
    return account_dict(conn.execute("SELECT * FROM comptes WHERE id = ?", (cur.lastrowid,)).fetchone(), conn)


def find(conn: sqlite3.Connection, ident: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM comptes WHERE identifiant = ?", ((ident or "").strip().lower(),)).fetchone()


def authenticate(conn: sqlite3.Connection, ident: str, password: str) -> sqlite3.Row | None:
    row = find(conn, ident)
    if row is None:
        burn_time()
        return None
    if not check_password(password or "", row["mot_de_passe"]):
        return None
    return row


def set_password(conn: sqlite3.Connection, account_id: int, password: str, *, keep: str | None = None) -> None:
    """Nouveau mot de passe ; toutes les sessions du compte sont fermées (sauf celle qui fait le changement)."""
    conn.execute("UPDATE comptes SET mot_de_passe = ? WHERE id = ?", (hash_password(validate_password(password)),
                                                                       account_id))
    conn.execute("DELETE FROM sessions WHERE compte_id = ? AND empreinte != ?", (account_id, keep or ""))


def set_active(conn: sqlite3.Connection, account_id: int, active: bool) -> None:
    conn.execute("UPDATE comptes SET actif = ? WHERE id = ?", (int(active), account_id))
    if not active:
        conn.execute("DELETE FROM sessions WHERE compte_id = ?", (account_id,))


def delete_account(conn: sqlite3.Connection, account_id: int) -> None:
    """Efface le compte et tout ce qui s'y rattache (sessions, invitations, ce qu'il a partagé, ses conversations ;
    pour un coach, ses élèves et tout son groupe)."""
    conn.execute("DELETE FROM messages WHERE fil = ? OR fil LIKE ?", (f"eleve-{account_id}", f"seance-{account_id}-%"))
    conn.execute("DELETE FROM comptes WHERE id = ?", (account_id,))


def accounts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM comptes ORDER BY role, identifiant").fetchall()
    return [account_dict(row, conn) for row in rows]


def students(conn: sqlite3.Connection, coach_id: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM comptes WHERE role = 'eleve' AND coach_id = ? ORDER BY nom COLLATE NOCASE",
                        (coach_id,)).fetchall()
    return [account_dict(row) for row in rows]


def has_admin(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM comptes WHERE admin = 1 AND actif = 1").fetchone() is not None


# ------------------------------------------------------------------ sessions
def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def open_session(conn: sqlite3.Connection, account_id: int, device: str | None) -> str:
    token = secrets.token_urlsafe(32)
    stamp = now()
    conn.execute("INSERT INTO sessions(empreinte, compte_id, appareil, cree_le, vu_le) VALUES (?,?,?,?,?)",
                 (_fingerprint(token), account_id, (device or "")[:80], stamp, stamp))
    conn.execute("UPDATE comptes SET derniere_connexion = ? WHERE id = ?", (stamp, account_id))
    return token


def session_account(conn: sqlite3.Connection, token: str | None) -> tuple[sqlite3.Row, str] | None:
    """(compte, empreinte) du jeton, s'il est valable ; met à jour « vu le »."""
    if not token:
        return None
    fingerprint = _fingerprint(token)
    row = conn.execute("""SELECT c.*, s.vu_le AS session_vu FROM sessions s JOIN comptes c ON c.id = s.compte_id
                          WHERE s.empreinte = ?""", (fingerprint,)).fetchone()
    if row is None:
        return None
    limit = (local_now() - timedelta(days=SESSION_DAYS)).isoformat(sep=" ")
    if not row["actif"] or row["session_vu"] < limit:
        conn.execute("DELETE FROM sessions WHERE empreinte = ?", (fingerprint,))
        return None
    stamp = now()
    if row["session_vu"][:13] != stamp[:13]:  # au plus une écriture par heure et par session
        conn.execute("UPDATE sessions SET vu_le = ? WHERE empreinte = ?", (stamp, fingerprint))
        conn.execute("UPDATE comptes SET derniere_connexion = ? WHERE id = ?", (stamp, row["id"]))
    return row, fingerprint


def close_session(conn: sqlite3.Connection, fingerprint: str) -> None:
    conn.execute("DELETE FROM sessions WHERE empreinte = ?", (fingerprint,))


# --------------------------------------------------------------- invitations
def new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def clean_code(code: str | None) -> str:
    value = re.sub(r"[^A-Z0-9]", "", (code or "").upper())
    return f"{value[:4]}-{value[4:]}" if len(value) == 8 else ""


def create_invitation(conn: sqlite3.Connection, coach_id: int) -> dict:
    conn.execute("DELETE FROM invitations WHERE utilisee_par IS NULL AND expire_le < ?", (now(),))
    pending = conn.execute("SELECT COUNT(*) FROM invitations WHERE coach_id = ? AND utilisee_par IS NULL",
                           (coach_id,)).fetchone()[0]
    if pending >= 30:
        raise RelayError("Déjà 30 codes en attente : annule ceux qui ne servent plus.")
    code = new_code()
    expiry = (local_now() + timedelta(days=INVITATION_DAYS)).replace(microsecond=0).isoformat(sep=" ")
    conn.execute("INSERT INTO invitations(code, coach_id, cree_le, expire_le) VALUES (?,?,?,?)",
                 (code, coach_id, now(), expiry))
    return {"code": code, "cree_le": now(), "expire_le": expiry}


def invitations(conn: sqlite3.Connection, coach_id: int) -> list[dict]:
    rows = conn.execute("""SELECT code, cree_le, expire_le FROM invitations
                           WHERE coach_id = ? AND utilisee_par IS NULL AND expire_le >= ? ORDER BY cree_le DESC""",
                        (coach_id, now())).fetchall()
    return [dict(row) for row in rows]


def cancel_invitation(conn: sqlite3.Connection, coach_id: int, code: str) -> bool:
    cur = conn.execute("DELETE FROM invitations WHERE code = ? AND coach_id = ? AND utilisee_par IS NULL",
                       (clean_code(code), coach_id))
    return cur.rowcount > 0


def join(conn: sqlite3.Connection, *, code: str, ident: str, name: str, password: str) -> dict:
    """Crée le compte élève avec un code d'invitation valable (à usage unique)."""
    row = conn.execute("""SELECT i.*, c.actif FROM invitations i JOIN comptes c ON c.id = i.coach_id
                          WHERE i.code = ?""", (clean_code(code),)).fetchone()
    if row is None or row["utilisee_par"] is not None or row["expire_le"] < now() or not row["actif"]:
        raise RelayError("Code d'invitation inconnu, déjà utilisé ou expiré : demande un nouveau code à ton coach.")
    account = create_account(conn, ident=ident, name=name, password=password, role="eleve",
                             coach_id=row["coach_id"])
    conn.execute("UPDATE invitations SET utilisee_par = ?, utilisee_le = ? WHERE code = ?",
                 (account["id"], now(), row["code"]))
    return account
