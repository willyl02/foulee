#!/usr/bin/env bash
# Met Foulée à jour sur le serveur (en root) : récupère le code sur GitHub,
# met à jour les bibliothèques et relance l'interface. Tes données ne bougent pas.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_PYTHON_INSTALL_DIR=/opt/uv/python UV_CACHE_DIR=/opt/uv/cache
export PATH="/usr/local/bin:$PATH"

[[ $EUID -eq 0 ]] || { echo "Lance ce script en root."; exit 1; }
cd "$ROOT"
before="$(git rev-parse --short HEAD)"
git pull --ff-only
after="$(git rev-parse --short HEAD)"
if [[ "$before" == "$after" ]]; then
    echo "Foulée est déjà à jour ($("$ROOT/.venv/bin/foulee" --version))."
    exit 0
fi
uv sync --no-dev --compile-bytecode
"$ROOT/.venv/bin/python" -m compileall -q "$ROOT/foulee" >/dev/null || true
systemctl restart foulee-web.service
echo "✓ $("$ROOT/.venv/bin/foulee" --version) installé ($before → $after), interface relancée."
echo "  Sur le téléphone, rouvre Foulée pour charger la nouvelle version."
