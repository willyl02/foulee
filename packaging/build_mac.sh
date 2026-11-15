#!/bin/bash
# Construit l'application Mac de Foulée : build/out/Foulee-<version>-mac-<arm64|intel>.dmg et ses empreintes.
#
#   bash packaging/build_mac.sh            (sur un Mac, avec uv : https://docs.astral.sh/uv/)
#
# Étapes, comme pour Windows (build.ps1) :
#  1. un Python autonome (python-build-standalone, celui qu'installe uv), rangé dans l'application ;
#  2. Foulée et ses bibliothèques, aux versions exactes du fichier uv.lock (empreintes vérifiées) ;
#  3. Foulee.app : le lanceur (python -m foulee app), l'icône, Info.plist, signature « ad hoc »
#     (sans compte développeur Apple : macOS demande une autorisation au premier lancement) ;
#  4. le .dmg (Foulee.app et un raccourci vers Applications) et son empreinte SHA-256.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=${1:-$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/foulee/__init__.py")}
case "$(uname -m)" in
  arm64) LABEL=arm64; PBS=aarch64 ;;
  x86_64) LABEL=intel; PBS=x86_64 ;;
  *) echo "Processeur inconnu : $(uname -m)"; exit 1 ;;
esac
if ! [[ "$VERSION" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)((a|b|rc)([0-9]+))?$ ]]; then echo "Version illisible : $VERSION"; exit 1; fi
NUMERIC="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}.${BASH_REMATCH[3]}"
BUILD="$ROOT/build"
STAGE="$BUILD/stage"
APP="$STAGE/Foulee.app"
OUT="$BUILD/out"
NAME="Foulee-$VERSION-mac-$LABEL"
step() { printf '\n=== %s\n' "$1"; }

echo "Foulée $VERSION pour Mac ($LABEL)"
rm -rf "$BUILD"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$OUT"

step "1. Python autonome"
uv python install "$(cat "$ROOT/.python-version")" --install-dir "$BUILD/py"
PYHOME=$(find "$BUILD/py" -mindepth 1 -maxdepth 1 -type d -name "cpython-*-macos-$PBS-none" | head -1)
[ -n "$PYHOME" ] || { echo "Python autonome introuvable dans $BUILD/py"; ls -la "$BUILD/py"; exit 1; }
cp -R "$PYHOME" "$APP/Contents/Resources/python"
PYTHON="$APP/Contents/Resources/python/bin/python3"
rm -f "$APP"/Contents/Resources/python/lib/python3.*/EXTERNALLY-MANAGED
"$PYTHON" --version

step "2. Foulée et ses bibliothèques (uv.lock)"
(cd "$ROOT" && uv export --frozen --no-dev --no-emit-project --format requirements.txt -o "$BUILD/requirements.txt" \
  && uv build --wheel --out-dir "$BUILD/dist")
uv pip install --python "$PYTHON" --break-system-packages --no-cache --require-hashes -r "$BUILD/requirements.txt"
uv pip install --python "$PYTHON" --break-system-packages --no-cache --no-deps "$BUILD"/dist/foulee-*.whl
LIB=$(echo "$APP"/Contents/Resources/python/lib/python3.*)
# Ce qui ne sert pas à Foulée : tests, IDLE, Tk (le Finder choisit les dossiers), lanceurs de pip…
rm -rf "$LIB/test" "$LIB/idlelib" "$LIB/tkinter" "$LIB/turtledemo" "$LIB/ensurepip" "$LIB/lib2to3/tests"
# Bytecode compilé d'avance et jamais revérifié : l'application n'écrit rien dans son propre dossier
# (sa signature resterait intacte), et démarre vite
"$PYTHON" -m compileall -q -j 0 --invalidation-mode unchecked-hash "$LIB" >/dev/null || \
  echo "compileall : certains fichiers n'ont pas été précompilés"
INSTALLED=$("$PYTHON" -P -c "import foulee, foulee.config as c; print(foulee.__version__, c.is_packaged())")
[ "$INSTALLED" = "$VERSION True" ] || { echo "Contrôle de l'installation raté : « $INSTALLED »"; exit 1; }
"$PYTHON" -P -c "import pystray, keyring, AppKit; print('icône de la barre des menus et Trousseau : OK')"

step "3. Foulee.app"
cat > "$APP/Contents/MacOS/Foulee" <<'LAUNCHER'
#!/bin/bash
# Lance Foulée (python -m foulee app) avec le Python rangé dans l'application.
here="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONUTF8=1
args=()
for arg in "$@"; do
  case "$arg" in -psn_*) ;; *) args+=("$arg") ;; esac  # argument ajouté par d'anciens macOS au lancement
done
exec "$here/Resources/python/bin/python3" -P -m foulee app ${args[@]+"${args[@]}"}
LAUNCHER
chmod 755 "$APP/Contents/MacOS/Foulee"
"$PYTHON" -P -m foulee.icon --iconset "$BUILD/Foulee.iconset"
iconutil -c icns "$BUILD/Foulee.iconset" -o "$APP/Contents/Resources/Foulee.icns"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Foulée</string>
  <key>CFBundleDisplayName</key><string>Foulée</string>
  <key>CFBundleIdentifier</key><string>fr.foulee.app</string>
  <key>CFBundleExecutable</key><string>Foulee</string>
  <key>CFBundleIconFile</key><string>Foulee</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$NUMERIC</string>
  <key>CFBundleDevelopmentRegion</key><string>fr</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSHumanReadableCopyright</key><string>Foulée — tes données Garmin, chez toi</string>
</dict>
</plist>
PLIST
# Signature « ad hoc » (sans compte développeur) : l'application reste entière et cohérente ; macOS demande
# tout de même, une fois, l'autorisation de l'ouvrir (Réglages Système → Confidentialité et sécurité)
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo "Signature ad hoc vérifiée"

step "4. Image disque"
DMGDIR="$BUILD/dmg"
mkdir -p "$DMGDIR"
ditto "$APP" "$DMGDIR/Foulee.app"
ln -s /Applications "$DMGDIR/Applications"
hdiutil create -volname "Foulée" -srcfolder "$DMGDIR" -ov -format UDZO -fs HFS+ "$OUT/$NAME.dmg" >/dev/null
(cd "$OUT" && shasum -a 256 "$NAME.dmg" > "SHA256SUMS-mac-$LABEL.txt")
SIZE=$(du -m "$OUT/$NAME.dmg" | cut -f1)
echo
echo "Prêt : $OUT/$NAME.dmg ($SIZE Mo)"
cat "$OUT/SHA256SUMS-mac-$LABEL.txt"
