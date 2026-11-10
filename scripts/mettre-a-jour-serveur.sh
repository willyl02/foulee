#!/usr/bin/env bash
# Met Foulée à jour sur le serveur (en root), comme le bouton « Mettre à jour » des Réglages :
# récupère la dernière version sur GitHub, met à jour les bibliothèques et les services,
# puis relance l'interface. Tes données, ta clé et tes vues ne bougent pas.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ $EUID -eq 0 ]] || { echo "Lance ce script en root (sudo -i)."; exit 1; }

set -a
# shellcheck disable=SC1091
[[ -f /etc/default/foulee ]] && . /etc/default/foulee
set +a
export HOME="${HOME:-/root}" GIT_TERMINAL_PROMPT=0 PATH="/usr/local/bin:$PATH"
export UV_PYTHON_INSTALL_DIR=/opt/uv/python UV_CACHE_DIR=/opt/uv/cache
export FOULEE_MAJ="${FOULEE_MAJ:-/var/lib/foulee/maj}"

exec "$ROOT/.venv/bin/python" "$ROOT/scripts/maj_serveur.py" installer --console
