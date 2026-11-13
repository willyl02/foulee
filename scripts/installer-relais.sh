#!/usr/bin/env bash
# Installation du relais Foulée (coach et élèves) sur une machine Ubuntu ou Debian, AMD ou ARM
# (par exemple une machine « Always Free » d'Oracle Cloud). En une commande, en root :
#
#   sudo apt update && sudo apt install -y git && sudo git clone -b beta https://github.com/willyl02/foulee /opt/foulee && sudo bash /opt/foulee/scripts/installer-relais.sh
#
# On peut le relancer sans risque : il complète ce qui manque et garde les comptes.
#
# Ce qu'il met en place :
#   1. les paquets nécessaires (curl, git) ;
#   2. l'utilisateur système « foulee » et ses données dans /var/lib/foulee ;
#   3. Python et les bibliothèques, avec uv ;
#   4. le service du relais (127.0.0.1:8770) et sa mise à jour automatique chaque nuit ;
#   5. la vérification du tunnel Cloudflare, qui amène le relais sur Internet en HTTPS ;
#   6. ton compte d'administrateur (et de coach).
#
# Le relais n'écoute que la machine elle-même : seul le tunnel Cloudflare le rend joignable, aucun port
# n'est à ouvrir.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA=/var/lib/foulee
PORT=8770
TTY="${FOULEE_TTY:-/dev/tty}"
export UV_PYTHON_INSTALL_DIR=/opt/uv/python UV_CACHE_DIR=/opt/uv/cache
export PATH="/usr/local/bin:$PATH"

step() { printf '\n\033[1;36m[%s] %s\033[0m\n' "$1" "$2"; }
say() { printf '%s\n' "$*"; }
fail() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Lance ce script en root : sudo bash $0"
[[ -f "$ROOT/pyproject.toml" && -d "$ROOT/foulee" ]] || fail "Ce script doit rester dans le dossier de Foulée."

printf '\n\033[1m=== Installation du relais Foulée ===\033[0m\n'
say "Programme : $ROOT ($(uname -m))"
say "Données   : $DATA"

# ---------------------------------------------------------------------------
step 1/6 "Paquets du système"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git tzdata >/dev/null
say "curl, git et les fuseaux horaires sont prêts."

# ---------------------------------------------------------------------------
step 2/6 "Utilisateur « foulee » et dossier des données"
if ! id -u foulee >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$DATA" --shell /usr/sbin/nologin foulee
fi
install -d -o foulee -g foulee -m 0750 "$DATA"
say "Utilisateur « foulee » prêt."

# ---------------------------------------------------------------------------
step 3/6 "Python et bibliothèques (une à deux minutes la première fois)"
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi
install -d -m 0755 /opt/uv
(cd "$ROOT" && uv sync --no-dev --compile-bytecode)
"$ROOT/.venv/bin/python" -m compileall -q "$ROOT/foulee" >/dev/null || true
say "Foulée $("$ROOT/.venv/bin/foulee" --version | awk '{print $2}') est installé."

# ---------------------------------------------------------------------------
step 4/6 "Service du relais et mises à jour automatiques"
bash "$ROOT/scripts/configurer-relais.sh"
systemctl restart foulee-relais.service
for _ in $(seq 1 30); do
    if curl -fs -o /dev/null "http://127.0.0.1:$PORT/api/v1/sante"; then break; fi
    sleep 1
done
curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/v1/sante" || fail "Le relais ne répond pas : journalctl -u foulee-relais -n 50"
say "Le relais répond sur la machine (port $PORT). Mise à jour automatique chaque nuit vers 4 h 30 (canal $(grep '^FOULEE_CANAL=' /etc/default/foulee | cut -d= -f2))."

# ---------------------------------------------------------------------------
step 5/6 "Tunnel Cloudflare"
if systemctl is-active --quiet cloudflared 2>/dev/null; then
    say "Le tunnel Cloudflare tourne. Dans Cloudflare (Zero Trust → Networks → Tunnels), son adresse publique"
    say "doit pointer vers le service HTTP « localhost:$PORT »."
else
    say "Le tunnel Cloudflare n'est pas encore installé sur cette machine. Dans Cloudflare : Zero Trust → Networks →"
    say "Tunnels → Create a tunnel → Cloudflared, choisis Debian et ton architecture ($(dpkg --print-architecture)),"
    say "puis colle ici la commande qu'il affiche. Adresse publique : service HTTP « localhost:$PORT »."
    say "(Tu peux le faire après : le relais n'en a pas besoin pour démarrer.)"
fi

# ---------------------------------------------------------------------------
step 6/6 "Ton compte d'administrateur"
ACCOUNTS="$(/usr/local/bin/foulee relais comptes 2>/dev/null || true)"
if grep -q "(admin)" <<<"$ACCOUNTS"; then
    say "Un administrateur existe déjà :"
    say "$ACCOUNTS"
else
    say "Tu es l'administrateur du relais, et aussi un coach : choisis ton identifiant, ton nom et ton mot de passe."
    /usr/local/bin/foulee relais admin <"$TTY" || say "Compte non créé : relance « sudo foulee relais admin » quand tu veux."
fi

chown -R foulee:foulee "$DATA"
printf '\n\033[1;32m=== Le relais Foulée est en place ===\033[0m\n'
say "Dans ton Foulée : Réglages → Coach et élèves → « J'ai déjà un compte », avec l'adresse publique du relais."
say ""
say "Commandes utiles :"
say "  sudo foulee relais comptes                      la liste des comptes"
say "  sudo foulee relais coach                        créer un compte coach"
say "  sudo foulee relais mot-de-passe IDENTIFIANT     changer le mot de passe d'un compte"
say "  sudo foulee relais desactiver IDENTIFIANT       bloquer un compte (reactiver pour le rouvrir)"
say "  systemctl status foulee-relais                  état du relais (journalctl -u foulee-relais -n 50)"
say "  sudo bash $ROOT/scripts/mettre-a-jour-serveur.sh   mettre à jour tout de suite"
