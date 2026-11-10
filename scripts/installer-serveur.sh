#!/usr/bin/env bash
# Installation de Foulée sur un serveur Debian (par exemple un conteneur LXC sous Proxmox).
#
# À lancer en root depuis le dossier cloné :   bash /opt/foulee/scripts/installer-serveur.sh
# On peut le relancer sans risque : il complète ce qui manque et garde tes données.
#
# Ce qu'il met en place :
#   1. les paquets nécessaires (curl, git) ;
#   2. l'utilisateur système « foulee » et ses données dans /var/lib/foulee ;
#   3. Python et les bibliothèques, avec uv (dans /opt/uv et /opt/foulee/.venv) ;
#   4. deux services : l'interface (foulee-web) et la synchro toutes les 3 heures (foulee-sync.timer) ;
#   5. Tailscale, qui relaie l'interface en HTTPS vers tes seuls appareils ;
#   6. ta clé Garmin et le premier import.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA=/var/lib/foulee
PORT=8770
ENV_FILE=/etc/default/foulee
TS_NAME="${FOULEE_NOM_TAILSCALE:-foulee}"
TTY="${FOULEE_TTY:-/dev/tty}"
export UV_PYTHON_INSTALL_DIR=/opt/uv/python UV_CACHE_DIR=/opt/uv/cache
export PATH="/usr/local/bin:$PATH"

step() { printf '\n\033[1;36m[%s] %s\033[0m\n' "$1" "$2"; }
say() { printf '%s\n' "$*"; }
fail() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Lance ce script en root (dans la console du conteneur)."
[[ -f "$ROOT/pyproject.toml" && -d "$ROOT/foulee" ]] || fail "Ce script doit rester dans le dossier de Foulée."

printf '\n\033[1m=== Installation de Foulée sur ce serveur ===\033[0m\n'
say "Programme : $ROOT"
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
install -d -o foulee -g foulee -m 0700 "$DATA/secrets"
if [[ ! -f "$ENV_FILE" ]]; then
    cat > "$ENV_FILE" <<EOF
# Configuration de Foulée, lue par les services foulee-web et foulee-sync.
FOULEE_DATA=$DATA
FOULEE_SECRETS=$DATA/secrets
# Noms d'hôte acceptés en plus de 127.0.0.1 (le nom Tailscale du serveur, rempli par l'installation)
FOULEE_HOTES=
TZ=Europe/Paris
PYTHONUTF8=1
EOF
fi
# Commande « foulee » pour root : lance Foulée sous l'utilisateur foulee, avec la configuration du serveur
cat > /usr/local/bin/foulee <<EOF
#!/bin/sh
# Lance une commande Foulée (foulee status, foulee sync, foulee setup…) avec la configuration du serveur.
set -a
. $ENV_FILE
set +a
if [ "\$(id -u)" = 0 ]; then
    exec runuser -u foulee -- env HOME=$DATA "$ROOT/.venv/bin/foulee" "\$@"
fi
exec "$ROOT/.venv/bin/foulee" "\$@"
EOF
chmod 0755 /usr/local/bin/foulee
say "Utilisateur, dossier et commande « foulee » prêts."

# ---------------------------------------------------------------------------
step 3/6 "Python et bibliothèques (une à deux minutes la première fois)"
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi
install -d -m 0755 /opt/uv
(cd "$ROOT" && uv sync --no-dev --compile-bytecode)
# Précompile Foulée lui-même : l'utilisateur foulee n'a pas le droit d'écrire dans /opt/foulee
"$ROOT/.venv/bin/python" -m compileall -q "$ROOT/foulee" >/dev/null || true
say "Foulée $("$ROOT/.venv/bin/foulee" --version | awk '{print $2}') est installé."

# ---------------------------------------------------------------------------
step 4/6 "Services : interface et synchro toutes les 3 heures"
cat > /etc/systemd/system/foulee-web.service <<EOF
[Unit]
Description=Foulée : interface web
After=network-online.target
Wants=network-online.target

[Service]
User=foulee
Group=foulee
WorkingDirectory=$ROOT
EnvironmentFile=$ENV_FILE
Environment=HOME=$DATA
ExecStart=$ROOT/.venv/bin/foulee web --sans-navigateur --port $PORT
Restart=always
RestartSec=5
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/foulee-sync.service <<EOF
[Unit]
Description=Foulée : synchronisation avec Garmin
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=foulee
Group=foulee
WorkingDirectory=$ROOT
EnvironmentFile=$ENV_FILE
Environment=HOME=$DATA
ExecStart=$ROOT/.venv/bin/foulee sync --quiet
NoNewPrivileges=yes
EOF
cat > /etc/systemd/system/foulee-sync.timer <<EOF
[Unit]
Description=Foulée : synchro toutes les 3 heures

[Timer]
OnCalendar=*-*-* 02/3:17:00
Persistent=true
RandomizedDelaySec=5min

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now foulee-web.service foulee-sync.timer >/dev/null 2>&1
systemctl restart foulee-web.service
say "Interface et synchro automatique en route."

# ---------------------------------------------------------------------------
step 5/6 "Tailscale : l'accès depuis ton téléphone"
if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi
if [[ ! -c /dev/net/tun ]]; then
    # Conteneur sans /dev/net/tun : mode « userspace », aucun réglage à faire côté Proxmox
    say "Ce conteneur n'a pas /dev/net/tun : Tailscale fonctionne en mode « userspace »."
    touch /etc/default/tailscaled
    if grep -q '^FLAGS=' /etc/default/tailscaled; then
        sed -i 's|^FLAGS=.*|FLAGS="--tun=userspace-networking"|' /etc/default/tailscaled
    else
        echo 'FLAGS="--tun=userspace-networking"' >> /etc/default/tailscaled
    fi
    systemctl restart tailscaled
    sleep 2
fi
if ! tailscale status >/dev/null 2>&1; then
    say "Un lien va s'afficher : ouvre-le sur ton téléphone ou ton PC, connecte-toi à Tailscale"
    say "et valide l'ajout de ce serveur. La suite démarre toute seule ensuite."
    tailscale up --hostname="$TS_NAME"
fi
say "Mise en ligne de l'interface sur ton réseau Tailscale, en HTTPS."
say "(Si un lien s'affiche pour activer HTTPS ou « Serve », ouvre-le et valide.)"
tailscale serve --bg "$PORT"
TS_HOST="$(tailscale status --json | "$ROOT/.venv/bin/python" -c \
    'import json, sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
[[ -n "$TS_HOST" ]] || fail "Nom Tailscale introuvable : relance le script."
sed -i "s|^FOULEE_HOTES=.*|FOULEE_HOTES=$TS_HOST|" "$ENV_FILE"
systemctl restart foulee-web.service
for _ in $(seq 1 30); do
    if curl -fs -o /dev/null "http://127.0.0.1:$PORT/"; then break; fi
    sleep 1
done
curl -fsS -o /dev/null "http://127.0.0.1:$PORT/" || fail "L'interface ne répond pas : journalctl -u foulee-web -n 50"
say "Adresse de Foulée : https://$TS_HOST"

# ---------------------------------------------------------------------------
step 6/6 "Ta clé API Garmin et le premier import"
say "Tu peux déjà ouvrir https://$TS_HOST sur ton téléphone : les données arrivent pendant l'import."
/usr/local/bin/foulee setup <"$TTY" || say "La clé n'est pas encore enregistrée : relance « foulee setup » quand tu veux."

chown -R foulee:foulee "$DATA"
printf '\n\033[1;32m=== Foulée est en ligne ===\033[0m\n'
say "Sur ton téléphone, Tailscale connecté :  https://$TS_HOST"
say "Puis, dans le menu du navigateur : « Ajouter à l'écran d'accueil » (ou « Installer l'appli »)."
say ""
say "Commandes utiles (en root) :"
say "  foulee status                          état de la clé, de la base et de la dernière synchro"
say "  foulee sync                            synchroniser maintenant"
say "  systemctl status foulee-web            état de l'interface"
say "  bash $ROOT/scripts/mettre-a-jour-serveur.sh   mettre Foulée à jour depuis GitHub"
