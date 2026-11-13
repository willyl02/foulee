#!/usr/bin/env bash
# Réglages système du relais Foulée (en root) : configuration, dossiers, commande « foulee » et services.
# Appelé par l'installation et par chaque mise à jour ; on peut le relancer sans risque.
#
# Services mis en place :
#   foulee-relais          le relais, sur 127.0.0.1:8770 (le tunnel Cloudflare l'amène sur Internet en HTTPS)
#   foulee-relais-maj      la mise à jour automatique depuis GitHub, chaque nuit vers 4 h 30
#                          (canal de FOULEE_CANAL : « beta » pendant les essais, puis « stable »)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA=/var/lib/foulee
PORT=8770
ENV_FILE=/etc/default/foulee

[[ $EUID -eq 0 ]] || { echo "À lancer en root (sudo)." >&2; exit 1; }
id -u foulee >/dev/null 2>&1 || { echo "L'utilisateur « foulee » n'existe pas : lance d'abord installer-relais.sh." >&2; exit 1; }

# --- Configuration : on n'ajoute que ce qui manque, tes valeurs sont gardées
[[ -f "$ENV_FILE" ]] || printf '# Configuration du relais Foulée, lue par ses services.\n' > "$ENV_FILE"
add_setting() {
    grep -q "^$1=" "$ENV_FILE" || printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"
}
add_setting FOULEE_DATA "$DATA"
add_setting FOULEE_SECRETS "$DATA/secrets"
add_setting FOULEE_MAJ "$DATA/maj"
add_setting FOULEE_CANAL beta                       # canal des mises à jour automatiques : beta ou stable
add_setting FOULEE_SERVICE foulee-relais.service    # service relancé après une mise à jour
add_setting FOULEE_CONFIGURER configurer-relais.sh  # réglages refaits après une mise à jour
add_setting TZ Europe/Paris
add_setting PYTHONUTF8 1

# --- Dossiers
install -d -o foulee -g foulee -m 0750 "$DATA" "$DATA/maj"
install -d -o foulee -g foulee -m 0700 "$DATA/secrets"

# --- Commande « foulee » : lance Foulée sous l'utilisateur foulee, avec cette configuration
cat > /usr/local/bin/foulee <<EOF
#!/bin/sh
# Lance une commande Foulée (foulee relais comptes, foulee relais coach…) avec la configuration du relais.
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
cat > /etc/systemd/system/foulee-relais.service <<EOF
[Unit]
Description=Foulée : relais du club (coach et élèves)
After=network-online.target
Wants=network-online.target

[Service]
User=foulee
Group=foulee
WorkingDirectory=$ROOT
EnvironmentFile=$ENV_FILE
Environment=HOME=$DATA
ExecStart=$ROOT/.venv/bin/foulee relais serveur --hote 127.0.0.1 --port $PORT
Restart=always
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$DATA

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/foulee-relais-maj.service <<EOF
[Unit]
Description=Foulée : mise à jour automatique du relais (GitHub)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$ROOT
EnvironmentFile=$ENV_FILE
Environment=HOME=/root GIT_TERMINAL_PROMPT=0 UV_PYTHON_INSTALL_DIR=/opt/uv/python UV_CACHE_DIR=/opt/uv/cache PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=$ROOT/.venv/bin/python $ROOT/scripts/maj_serveur.py installer --console
TimeoutStartSec=20min
EOF

cat > /etc/systemd/system/foulee-relais-maj.timer <<EOF
[Unit]
Description=Foulée : mise à jour du relais, chaque nuit

[Timer]
OnCalendar=*-*-* 04:30
RandomizedDelaySec=20min
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now foulee-relais.service foulee-relais-maj.timer >/dev/null 2>&1
