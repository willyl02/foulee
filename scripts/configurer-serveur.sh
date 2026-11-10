#!/usr/bin/env bash
# Réglages système de Foulée sur le serveur (en root) : configuration, dossiers, commande
# « foulee » et services. Appelé par l'installation et par chaque mise à jour ; on peut le
# relancer sans risque, il garde tes réglages.
#
# Services mis en place :
#   foulee-web          l'interface (127.0.0.1 pour Tailscale, et le réseau local si activé)
#   foulee-sync.timer   la synchro avec Garmin toutes les 3 heures
#   foulee-maj.path     attend les demandes de mise à jour déposées par l'interface,
#   foulee-maj.service  et les traite en root (vérifier, ou installer depuis GitHub)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA=/var/lib/foulee
PORT=8770
ENV_FILE=/etc/default/foulee

[[ $EUID -eq 0 ]] || { echo "À lancer en root." >&2; exit 1; }
id -u foulee >/dev/null 2>&1 || { echo "L'utilisateur « foulee » n'existe pas : lance d'abord installer-serveur.sh." >&2; exit 1; }

# --- Configuration : on n'ajoute que ce qui manque, tes valeurs sont gardées
[[ -f "$ENV_FILE" ]] || printf '# Configuration de Foulée, lue par ses services.\n' > "$ENV_FILE"
add_setting() {
    grep -q "^$1=" "$ENV_FILE" || printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"
}
add_setting FOULEE_DATA "$DATA"
add_setting FOULEE_SECRETS "$DATA/secrets"
add_setting FOULEE_HOTES ""            # nom Tailscale du serveur, rempli par l'installation
add_setting FOULEE_ECOUTE 0.0.0.0      # le réseau local reste fermé tant qu'aucun mot de passe n'est choisi
add_setting FOULEE_MAJ "$DATA/maj"     # échange avec le service de mise à jour
add_setting TZ Europe/Paris
add_setting PYTHONUTF8 1

# --- Dossiers
install -d -o foulee -g foulee -m 0750 "$DATA" "$DATA/maj"
install -d -o foulee -g foulee -m 0700 "$DATA/secrets"

# --- Commande « foulee » pour root : lance Foulée sous l'utilisateur foulee, avec cette configuration
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

# --- Services
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

cat > /etc/systemd/system/foulee-maj.service <<EOF
[Unit]
Description=Foulée : mise à jour demandée depuis l'interface
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$ROOT
EnvironmentFile=$ENV_FILE
Environment=HOME=/root GIT_TERMINAL_PROMPT=0 UV_PYTHON_INSTALL_DIR=/opt/uv/python UV_CACHE_DIR=/opt/uv/cache
ExecStart=$ROOT/.venv/bin/python $ROOT/scripts/maj_serveur.py --depuis-interface
TimeoutStartSec=20min
EOF

cat > /etc/systemd/system/foulee-maj.path <<EOF
[Unit]
Description=Foulée : attend les demandes de mise à jour de l'interface

[Path]
PathExists=$DATA/maj/demande
Unit=foulee-maj.service

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now foulee-web.service foulee-sync.timer foulee-maj.path >/dev/null 2>&1
