#!/bin/bash
# Essai de l'application Mac construite par build_mac.sh, dans des dossiers à part (rien de l'utilisateur) :
# installation depuis le .dmg, démarrage, interface, lancement à l'ouverture de session, serveur MCP, arrêt.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DMG=$(ls "$ROOT"/build/out/Foulee-*-mac-*.dmg | head -1)
WORK=$(mktemp -d)
export HOME="$WORK/home" FOULEE_DATA="$WORK/donnees" FOULEE_CONFIG="$WORK/config" FOULEE_SECRETS="$WORK/secrets"
export FOULEE_COFFRE=fichier FOULEE_LAUNCH_AGENTS="$WORK/LaunchAgents" FOULEE_NAVIGATEUR_APP=""
mkdir -p "$HOME"
step() { printf '\n[%s] %s\n' "$((++N))" "$1"; }
fail() { echo "::error title=Essai de l'application Mac::$1"; tail -60 "$WORK"/app.out 2>/dev/null || true
         find "$FOULEE_DATA" -name '*.log' -exec tail -40 {} \; 2>/dev/null || true; exit 1; }
N=0

step "Installation depuis $(basename "$DMG")"
MNT="$WORK/mnt"
mkdir -p "$MNT" "$WORK/Applications"
hdiutil attach -nobrowse -readonly -mountpoint "$MNT" "$DMG" >/dev/null
[ -L "$MNT/Applications" ] || fail "le raccourci Applications manque dans le .dmg"
ditto "$MNT/Foulee.app" "$WORK/Applications/Foulee.app"
hdiutil detach "$MNT" -quiet
APP="$WORK/Applications/Foulee.app"
codesign --verify --deep --strict "$APP" || fail "signature ad hoc invalide après copie"
echo "  OK  Foulee.app copiée, signature intacte"

step "Démarrage (sans navigateur), interface"
"$APP/Contents/MacOS/Foulee" --sans-navigateur > "$WORK/app.out" 2>&1 &
PID=$!
for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8770/api/bootstrap -o "$WORK/boot.json" 2>/dev/null; then break; fi
  kill -0 $PID 2>/dev/null || fail "l'application s'est arrêtée au démarrage"
  sleep 1
done
[ -s "$WORK/boot.json" ] || fail "l'interface ne répond pas"
VERSION=$("$APP/Contents/Resources/python/bin/python3" -P -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$WORK/boot.json")
echo "  OK  interface en ligne, version $VERSION"
curl -fsS http://127.0.0.1:8770/ | grep -q "Foulée" || fail "page d'accueil illisible"
"$APP/Contents/MacOS/Foulee" --sans-navigateur && echo "  OK  deuxième lancement : la copie qui tourne répond"

step "Lancement à l'ouverture de session (LaunchAgent)"
curl -fsS -X PUT -H "X-Foulee: 1" -H "Content-Type: application/json" -d '{"demarrage_windows": true}' \
  http://127.0.0.1:8770/api/app > /dev/null || fail "réglage du lancement à l'ouverture de session refusé"
PLIST="$FOULEE_LAUNCH_AGENTS/fr.foulee.app.plist"
plutil -lint "$PLIST" >/dev/null || fail "LaunchAgent illisible"
grep -q "Foulee.app/Contents/MacOS/Foulee" "$PLIST" || fail "le LaunchAgent ne lance pas Foulee.app"
echo "  OK  $(basename "$PLIST")"

step "Claude Desktop : serveur MCP"
"$APP/Contents/Resources/python/bin/python3" -P "$ROOT/packaging/mcp_check.py" "$APP/Contents/Resources/python/bin/python3" \
  || fail "le serveur MCP ne répond pas"

step "Arrêt"
curl -fsS -X POST -H "X-Foulee: 1" http://127.0.0.1:8770/api/app/quitter > /dev/null || true
for _ in $(seq 1 30); do kill -0 $PID 2>/dev/null || break; sleep 1; done
kill -0 $PID 2>/dev/null && fail "l'application ne s'arrête pas"
echo "  OK  arrêtée"
echo "::notice title=Application Mac::$(basename "$DMG") ($(du -m "$DMG" | cut -f1) Mo) : installation, démarrage, LaunchAgent, MCP et arrêt OK"
