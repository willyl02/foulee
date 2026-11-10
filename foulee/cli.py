"""Ligne de commande : « foulee <commande> ».

    foulee setup           enregistrer ta clé API Garmin et la tester
    foulee sync            synchroniser (incrémental)
    foulee web             ouvrir l'interface (http://127.0.0.1:8770)
    foulee mcp             serveur pour Claude Desktop (lancé par Claude Desktop lui-même)
    foulee demo            créer la base de démonstration
    foulee status          état général
    foulee diagnostic      tester chaque flux Garmin (rapport sans tes valeurs)
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import __version__, config, db, vault


def _setup_logging(command: str, quiet: bool = False, to_console: bool = True) -> None:
    # Un journal par type de processus (web, mcp, sync…) : sous Windows, deux processus
    # ne peuvent pas faire tourner le même fichier journal en même temps.
    handlers: list[logging.Handler] = [
        RotatingFileHandler(config.log_dir() / f"{command}.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    ]
    if to_console and not quiet:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.WARNING)
        handlers.append(console)
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    logging.getLogger("garmin_personal_api").setLevel(logging.WARNING)


def _say(text: str = "") -> None:
    print(text, flush=True)


def _ask(question: str, default: str = "") -> str:
    try:
        answer = input(f"{question} ").strip()
    except EOFError:
        return default
    return answer or default


def _progress_printer(quiet: bool):
    state = {"last": ""}

    def report(message: str, fraction: float | None = None) -> None:
        if quiet or message == state["last"]:
            return
        state["last"] = message
        pct = f"{round(fraction * 100):3d} %  " if fraction is not None else "       "
        _say(f"  {pct}{message}")

    return report


# ---------------------------------------------------------------- commandes
_STOP_WORDS = ("q", "n", "non", "stop", "quitter")


def _key_instructions(clipboard: bool) -> None:
    from .garmin.client import KEY_PAGE

    _say("1. Dans Garmin Connect sur le web, ouvre la page « API personnelle » :")
    _say(f"   {KEY_PAGE}")
    _say("   Créer une clé → accepte les conditions → choisis la durée (1 an conseillé) → Créer.")
    if clipboard:
        _say("2. Copie la clé avec le bouton « Copier » de Garmin (sinon : clique dans la clé, Ctrl+A puis Ctrl+C).")
        _say("   Garde la fenêtre Garmin ouverte jusqu'à la confirmation : la clé ne s'affiche qu'une fois.")
        _say("3. Reviens ici et appuie simplement sur Entrée : Foulée lit la clé dans le presse-papiers.")
        _say("   Inutile de la coller. Elle ne s'affichera jamais à l'écran.\n")
    else:
        _say("2. Copie la clé, colle-la ici UNE seule fois, puis Entrée (rien ne s'affiche, c'est normal).\n")


def _read_key(first: bool, clipboard: bool) -> tuple[str, str] | None:
    """(texte brut, d'où il vient) ; None si la personne veut arrêter."""
    from . import keyinput

    if clipboard:
        prompt = ("Clé copiée ? Appuie sur Entrée : " if first
                  else "Entrée = relire le presse-papiers, q = arrêter : ")
    else:
        prompt = "Colle ta clé puis Entrée : " if first else "Colle ta clé puis Entrée (q = arrêter) : "
    typed = getpass.getpass(prompt)
    keyinput.drain_console_input()
    if typed.strip().lower() in _STOP_WORDS:
        return None
    if typed.strip() or not clipboard:
        return typed, "collée"
    text = keyinput.read_clipboard()
    if text is None:
        _say("Presse-papiers illisible : colle la clé à la place.")
        return getpass.getpass("Colle ta clé puis Entrée : "), "collée"
    return text, "lue dans le presse-papiers"


def _explain_refusal(exc: Exception) -> None:
    if not getattr(exc, "key_rejected", False):
        _say(f"✗ {exc}")
        return
    _say(f"✗ Garmin a refusé cette clé (HTTP {exc.status}).")  # type: ignore[attr-defined]
    if getattr(exc, "detail", ""):
        _say(f"  Réponse de Garmin : « {exc.detail} »")  # type: ignore[attr-defined]
    _say("  À essayer, dans l'ordre :")
    _say("  1. Reclique sur « Copier » dans la fenêtre Garmin, puis réessaie ici.")
    _say("  2. Clique sur « Terminé » chez Garmin (la clé reste dans le presse-papiers),")
    _say("     attends une minute, puis réessaie ici.")
    _say("  3. Vérifie sur la page « API personnelle » que la clé y figure, active.")
    _say("  Si ça bloque encore, transmets ces lignes à Claude (jamais la clé elle-même).\n")


def _enter_key() -> int:
    """Demande la clé, la nettoie, la fait vérifier par Garmin puis la range. 0 si c'est fait."""
    from . import keyinput
    from .garmin.client import GarminError, check_key

    clipboard = keyinput.clipboard_available()
    _key_instructions(clipboard)
    for attempt in range(6):
        got = _read_key(attempt == 0, clipboard)
        if got is None:
            _say("Arrêt : aucune clé enregistrée.")
            return 1
        raw, origin = got
        key, notes = keyinput.normalize_key(raw)
        if not key:
            _say("✗ Rien n'a été collé." if origin == "collée" else
                 "✗ Rien à lire : le presse-papiers est vide ou ne contient pas de texte. "
                 "Copie la clé chez Garmin, puis réessaie.")
            continue
        corrections = f" ({', '.join(notes)})" if notes else ""
        _say(f"Clé {origin} : {keyinput.describe_key(key)}{corrections}.")
        problem = keyinput.key_problem(key)
        if problem:
            _say(f"✗ Ce texte ne peut pas être une clé Garmin : {problem}. Recopie-la chez Garmin, puis réessaie.")
            continue
        if not keyinput.looks_like_garmin_key(key) and _ask(
                "Ce texte ne ressemble pas à une clé Garmin. L'envoyer quand même à Garmin pour vérification ? [o/N]",
                "n").lower() not in ("o", "oui", "y"):
            continue
        _say("Vérification auprès de Garmin…")
        try:
            info = check_key(key)
        except GarminError as exc:
            _explain_refusal(exc)
            continue
        where = vault.set_key(key)
        _say(f"✓ Garmin accepte la clé (jeton valable jusqu'au {info['jeton_expire']}).")
        if info.get("profil_erreur"):
            _say(f"  ! Lecture du profil impossible pour l'instant : {info['profil_erreur']}")
        _say(f"✓ Clé rangée dans : {where}")
        if origin != "collée" and keyinput.clear_clipboard():
            _say("✓ Presse-papiers vidé. Si l'historique du presse-papiers est activé (Win+V),")
            _say("  supprimes-y aussi la clé (icône corbeille ou « … » → Supprimer).")
        _say("  Tu peux cliquer sur « Terminé » dans Garmin Connect.")
        return 0
    _say("Trop d'essais pour cette fois : relance Configurer-cle-Garmin.cmd quand tu veux.")
    return 2


def cmd_setup(args: argparse.Namespace) -> int:
    _say("\n=== Foulée : configuration de ta clé API Garmin ===\n")
    if vault.has_key() and _ask("Une clé est déjà enregistrée. La remplacer ? [o/N]", "n").lower() not in ("o", "oui", "y"):
        _say("Clé conservée.")
    else:
        code = _enter_key()
        if code:
            return code
    with db.session() as conn:
        settings = db.get_settings(conn)
    if args.sans_import:
        return 0
    default_since = (date.today() - timedelta(days=730)).isoformat()
    if settings.get("historique_depuis"):
        _say(f"\nHistorique déjà importé depuis le {settings['historique_depuis']}.")
        if _ask("Lancer une synchro maintenant ? [O/n]", "o").lower() in ("n", "non"):
            return 0
        return cmd_sync(argparse.Namespace(depuis=None, sans_fit=False, fit_jours=None, quiet=False))
    _say("\nPremier import : jusqu'où remonter ? (2 ans par défaut ; plus c'est loin, plus c'est long)")
    since = _ask(f"Date de début AAAA-MM-JJ [{default_since}] :", default_since)
    try:
        date.fromisoformat(since)
    except ValueError:
        _say("Date illisible : j'utilise la valeur par défaut.")
        since = default_since
    return cmd_sync(argparse.Namespace(depuis=since, sans_fit=False, fit_jours=None, quiet=False))


def cmd_sync(args: argparse.Namespace) -> int:
    from . import sync

    since = date.fromisoformat(args.depuis) if getattr(args, "depuis", None) else None
    started = time.monotonic()
    if not args.quiet:
        _say("Synchro en cours (tu peux laisser tourner)…")
    try:
        result = sync.run(since=since, fit_days=args.fit_jours, with_fit=not args.sans_fit,
                          progress=_progress_printer(args.quiet))
    except sync.SyncBusy as exc:
        _say(str(exc))
        return 3
    except Exception as exc:
        logging.getLogger("foulee").exception("Synchro impossible")
        _say(f"✗ Synchro impossible : {exc}")
        return 2
    if args.quiet:
        return 0 if result.get("statut") in ("ok", "partiel", "demo") else 2
    if result.get("statut") == "demo":
        _say(result["message"])
        return 0
    garmin = result["sources"].get("garmin", {})
    if "erreur" in garmin:
        _say(f"✗ {garmin['erreur']}")
        return 2
    _say(f"\n✓ Synchro {result['statut']} en {round(time.monotonic() - started)} s ({garmin.get('appels', 0)} appels à Garmin)")
    for label, count in garmin.get("flux", {}).items():
        _say(f"   {label:<20} {count} jour(s)")
    _say(f"   séances              {garmin.get('seances_nouvelles', 0)} nouvelle(s), {garmin.get('seances_maj', 0)} mise(s) à jour")
    _say(f"   fichiers FIT         {garmin.get('fit', 0)} téléchargé(s)")
    for error in garmin.get("erreurs", []):
        _say(f"   ! {error}")
    return 0


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def cmd_web(args: argparse.Namespace) -> int:
    import uvicorn

    from .web import create_app

    if args.demo:
        config.set_demo(True)
        if not config.db_path().exists():
            _say("Création de la base de démonstration…")
            from . import demo

            demo.build()
    url = f"http://127.0.0.1:{args.port}/"
    if _port_in_use(args.port):
        _say(f"L'interface tourne déjà : {url}")
        if not args.sans_navigateur:
            webbrowser.open(url)
        return 0
    _say(f"\nFoulée {'(démo) ' if args.demo else ''}→ {url}")
    _say("Garde cette fenêtre ouverte tant que tu utilises l'interface (Ctrl+C pour arrêter).\n")
    if not args.sans_navigateur:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    if args.demo:
        config.set_demo(True)
    from .mcp_server import serve

    serve()
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from . import demo

    _say("Génération des données fictives (une vingtaine de secondes)…")
    counts = demo.build()
    _say(f"✓ Base démo prête : {counts['activities']} séances, {counts['daily']} valeurs quotidiennes.")
    _say("  Ouvre-la avec : foulee web --demo")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from . import sync

    _say(f"Foulée {__version__}")
    _say(f"  Dossier de données : {config.data_dir()}")
    _say(f"  Clé API Garmin     : {'enregistrée' if vault.has_key() else 'absente (foulee setup)'}")
    token = config.token_cache_file()
    if token.exists():
        try:
            expires = json.loads(token.read_text(encoding="utf-8")).get("expires_at")
            _say(f"  Jeton temporaire   : valable jusqu'au {datetime.fromtimestamp(expires):%d/%m/%Y %H:%M}")
        except (ValueError, OSError, TypeError):
            pass
    if not config.db_path().exists():
        _say("  Base               : pas encore créée")
        return 0
    with db.session() as conn:
        counts = db.table_counts(conn)
        info = sync.last_sync_info(conn)
        first = conn.execute("SELECT MIN(date) AS d FROM daily").fetchone()["d"]
    _say(f"  Base               : {counts['activities']} séances, {counts['daily']} valeurs, {counts['streams']} séances avec courbes")
    _say(f"  Données depuis     : {first or '–'}")
    _say(f"  Dernière synchro   : {info.get('derniere_reussie') or 'jamais'}")
    return 0


def cmd_diagnostic(args: argparse.Namespace) -> int:
    from .garmin.diagnostic import run as run_diagnostic

    _say("Diagnostic : un appel par flux Garmin, rapport sans tes valeurs…")
    path = run_diagnostic()
    _say(f"\n✓ Rapport écrit : {path}")
    _say("  Il ne contient que des noms de champs et des statuts : tu peux me le transmettre.")
    return 0


def cmd_reparse(args: argparse.Namespace) -> int:
    from .garmin.sync import reparse_all

    with db.session() as conn:
        counts = reparse_all(conn)
    _say(f"✓ Tables reconstruites depuis le brut : {counts}")
    return 0


def cmd_fit(args: argparse.Namespace) -> int:
    from . import analysis
    from .garmin.client import GarminSession
    from .garmin.sync import fetch_fit

    cutoff = (date.today() - timedelta(days=args.jours)).isoformat()
    with db.session() as conn:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM activities WHERE has_streams = 0 AND source = 'garmin' AND date >= ? ORDER BY date DESC",
            (cutoff,))]
        if not ids:
            _say("Aucun fichier FIT manquant sur cette période.")
            return 0
        settings = db.get_settings(conn)
        hrp = analysis.hr_profile(conn, settings)
        with GarminSession() as session:
            for index, activity_id in enumerate(ids, 1):
                status = fetch_fit(session, conn, activity_id, settings, hrp)
                conn.commit()
                _say(f"  {index}/{len(ids)}  {activity_id}  {status}")
        analysis.recompute_daily_calc(conn)
    return 0


CLAUDE_DATA = "Claude-Data"


def claude_config_paths() -> list[Path]:
    """Emplacements possibles du fichier de configuration de Claude Desktop, le plus probable d'abord.

    Sous Windows, la version « paquet » (Microsoft Store / MSIX) lit
    %LOCALAPPDATA%\\Claude-Data\\claude_<paquet>\\claude_desktop_config.json ; les anciennes
    versions lisaient %APPDATA%\\Claude ou le dossier LocalCache du paquet.
    """
    paths: list[Path] = []
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        appdata = os.environ.get("APPDATA")
        if local:
            paths += [folder / "claude_desktop_config.json"
                      for folder in sorted((Path(local) / CLAUDE_DATA).glob("claude_*")) if folder.is_dir()]
        if appdata:
            paths.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
        if local:
            paths += [package / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
                      for package in sorted((Path(local) / "Packages").glob("Claude_*"))]
    elif sys.platform == "darwin":
        paths.append(Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
    else:
        paths.append(Path.home() / ".config" / "Claude" / "claude_desktop_config.json")
    return paths


def claude_config_targets() -> list[Path]:
    """Fichiers à modifier : ceux qui existent, plus celui de la version « paquet » s'il n'existe pas encore."""
    candidates = claude_config_paths()
    targets = [p for p in candidates if p.exists() or p.parent.parent.name == CLAUDE_DATA]
    return targets or candidates[:1]


def mcp_entry() -> dict:
    return {
        "command": sys.executable,
        "args": ["-m", "foulee", "mcp"],
        "env": {"PYTHONUTF8": "1", "FOULEE_DATA": str(config.data_dir())},
    }


def _run_quiet(command: list[str], timeout: float = 30) -> str:
    """Lance une commande Windows sans fenêtre et renvoie sa sortie ("" en cas d'échec)."""
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")


def claude_desktop_running() -> bool:
    if sys.platform != "win32":
        return False
    return "claude.exe" in _run_quiet(["tasklist", "/FI", "IMAGENAME eq claude.exe", "/NH"]).lower()


def _make_sure_claude_is_closed() -> None:
    """Claude Desktop réécrit son fichier de configuration : il doit être fermé pendant qu'on le modifie."""
    if not claude_desktop_running():
        return
    _say("Claude Desktop est ouvert. Il garde ses réglages dans ce fichier et pourrait effacer la modification.")
    _ask("Quitte-le (clic droit sur son icône près de l'horloge → Quitter), puis appuie sur Entrée.")
    for _ in range(10):
        if not claude_desktop_running():
            return
        time.sleep(1)
    if _ask("Claude tourne encore. Le fermer de force ? (ferme aussi Claude Code s'il est ouvert) [o/N]",
            "n").lower() in ("o", "oui", "y"):
        _run_quiet(["taskkill", "/IM", "claude.exe", "/F"])
        time.sleep(2)
    else:
        _say("  J'écris quand même. Si Foulée n'apparaît pas après redémarrage, relance cette commande Claude fermé.")


def _read_claude_config(path: Path) -> tuple[dict, str] | None:
    """(contenu, texte d'origine) ; None si le fichier n'est pas un objet JSON valide."""
    raw = path.read_text(encoding="utf-8-sig").strip() if path.exists() else ""  # tolère un BOM
    if not raw:
        return {}, ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return (data, raw) if isinstance(data, dict) else None


def cmd_claude_config(args: argparse.Namespace) -> int:
    entry = mcp_entry()
    if not (args.ecrire or args.retirer):
        _say("Bloc à placer dans « mcpServers » du fichier de configuration de Claude Desktop :\n")
        _say(json.dumps({"mcpServers": {"foulee": entry}}, indent=2, ensure_ascii=False))
        _say("\nFichiers de configuration de Claude Desktop sur ce PC :")
        found = False
        for path in claude_config_paths():
            if path.exists():
                found = True
                loaded = _read_claude_config(path)
                servers = (loaded[0].get("mcpServers") or {}) if loaded else {}
                state = "JSON invalide" if loaded is None else (
                    "Foulée présent" if isinstance(servers, dict) and "foulee" in servers else "sans Foulée")
                _say(f"  {path}  ({state})")
        if not found:
            _say("  aucun pour l'instant")
        _say("\nPour l'y ajouter : foulee claude-config --ecrire")
        return 0
    _make_sure_claude_is_closed()
    code = 0
    for path in claude_config_targets():
        loaded = _read_claude_config(path)
        if loaded is None:
            _say(f"✗ {path} n'est pas un JSON valide : je n'y touche pas.")
            code = 2
            continue
        data, raw = loaded
        servers = data.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            _say(f"✗ {path} : la rubrique « mcpServers » a une forme inattendue, je n'y touche pas.")
            code = 2
            continue
        if args.retirer:
            if "foulee" not in servers:
                continue
            del servers["foulee"]
        else:
            servers["foulee"] = entry
        path.parent.mkdir(parents=True, exist_ok=True)
        if raw:
            backup = path.with_name(f"{path.name}.sauvegarde-{datetime.now():%Y%m%d-%H%M%S}")
            backup.write_text(raw, encoding="utf-8")
            _say(f"  Sauvegarde : {backup}")
        # UTF-8 sans BOM : Claude Desktop ne lit pas un JSON précédé d'un BOM
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        _say(f"✓ Foulée {'retiré de' if args.retirer else 'ajouté à'} : {path}")
    if not args.retirer:
        _say("  Relance Claude Desktop. Au tout premier démarrage, Foulée peut mettre une vingtaine")
        _say("  de secondes à apparaître (Paramètres → Développeur, ou bouton + → Connecteurs).")
    return code


def cmd_forget_key(args: argparse.Namespace) -> int:
    removed = vault.delete_key()
    _say("✓ Clé supprimée de cet ordinateur." if removed else "Aucune clé enregistrée.")
    return 0


def cmd_reset_views(args: argparse.Namespace) -> int:
    from . import views

    with db.session() as conn:
        views.reset_default_views(conn)
    _say("✓ Vues par défaut restaurées (tes vues personnelles sont conservées).")
    return 0


# ---------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="foulee", description="Foulée — ton hub local de données sport et santé.")
    parser.add_argument("--version", action="version", version=f"Foulée {__version__}")
    sub = parser.add_subparsers(dest="cmd", metavar="commande")

    p = sub.add_parser("setup", help="enregistrer ta clé API Garmin, la tester et lancer le premier import")
    p.add_argument("--sans-import", action="store_true", help="ne pas proposer l'import")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("sync", help="synchroniser tes données Garmin")
    p.add_argument("--depuis", help="date de début AAAA-MM-JJ (par défaut : reprise là où on s'était arrêté)")
    p.add_argument("--sans-fit", action="store_true", help="ne pas télécharger les fichiers FIT")
    p.add_argument("--fit-jours", type=int, help="télécharger les FIT des N derniers jours")
    p.add_argument("--quiet", action="store_true", help="aucun affichage (tâche planifiée)")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("web", help="ouvrir l'interface dans le navigateur")
    p.add_argument("--demo", action="store_true", help="utiliser les données de démonstration")
    p.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    p.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur")
    p.set_defaults(func=cmd_web)

    p = sub.add_parser("mcp", help="serveur MCP pour Claude Desktop")
    p.add_argument("--demo", action="store_true")
    p.set_defaults(func=cmd_mcp)

    p = sub.add_parser("demo", help="(re)créer la base de démonstration")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("status", help="état de Foulée")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("diagnostic", help="tester chaque flux Garmin et écrire un rapport anonyme")
    p.set_defaults(func=cmd_diagnostic)

    p = sub.add_parser("reparse", help="reconstruire les tables depuis les réponses brutes")
    p.set_defaults(func=cmd_reparse)

    p = sub.add_parser("fit", help="télécharger les fichiers FIT manquants")
    p.add_argument("--jours", type=int, default=365, help="sur les N derniers jours (défaut 365)")
    p.set_defaults(func=cmd_fit)

    p = sub.add_parser("claude-config", help="afficher ou écrire la configuration de Claude Desktop")
    action = p.add_mutually_exclusive_group()
    action.add_argument("--ecrire", action="store_true", help="ajouter Foulée à Claude Desktop (avec sauvegarde)")
    action.add_argument("--retirer", action="store_true", help="retirer Foulée de Claude Desktop (avec sauvegarde)")
    p.set_defaults(func=cmd_claude_config)

    p = sub.add_parser("forget-key", help="supprimer la clé API enregistrée sur cet ordinateur")
    p.set_defaults(func=cmd_forget_key)

    p = sub.add_parser("reset-views", help="restaurer les vues par défaut")
    p.set_defaults(func=cmd_reset_views)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    _setup_logging(args.cmd, quiet=getattr(args, "quiet", False), to_console=args.cmd != "mcp")
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        _say("\nInterrompu.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
