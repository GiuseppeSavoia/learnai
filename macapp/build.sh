#!/usr/bin/env bash
# Costruisce LearnAI.app (app nativa per Mac) e la installa in /Applications.
#
#   macapp/build.sh                 build completa + installazione in /Applications
#   macapp/build.sh --no-install    solo build in dist/LearnAI.app
#
# Passi: build del frontend (npm), backend congelato con PyInstaller (onedir), wrapper Swift
# (swiftc), icona, assemblaggio del bundle, firma ad-hoc, rimozione della quarantena, installazione.
set -euo pipefail

INSTALL=1
for arg in "$@"; do
  case "$arg" in
    --no-install) INSTALL=0 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Opzione sconosciuta: $arg" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MACAPP="$ROOT/macapp"
BUILD="$ROOT/build/macapp"
DIST="$ROOT/dist"
APP_NAME="LearnAI"
BUNDLE_ID="com.local.chessai"
APP="$BUILD/$APP_NAME.app"
FINAL="$DIST/$APP_NAME.app"
INSTALLED="/Applications/$APP_NAME.app"
VENV_PY="$ROOT/backend/.venv/bin/python"
PUZZLES_DB="${CHESSAI_PUZZLES_DB:-$ROOT/backend/data/puzzles.db}"
STOCKFISH_SRC="${STOCKFISH_PATH:-$(command -v stockfish || echo /opt/homebrew/bin/stockfish)}"
ARCH="$(uname -m)"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31mErrore:\033[0m %s\n' "$*" >&2; exit 1; }

# --- prerequisiti -------------------------------------------------------------------------
step "Controllo dei prerequisiti"
[ "$(uname -s)" = Darwin ] || die "serve macOS"
command -v swiftc >/dev/null || die "swiftc non trovato (installa Xcode o i Command Line Tools)"
command -v iconutil >/dev/null || die "iconutil non trovato"
[ -x "$VENV_PY" ] || die "manca backend/.venv: cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt"
if ! command -v node >/dev/null 2>&1 && [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
  # shellcheck disable=SC1091
  . "${NVM_DIR:-$HOME/.nvm}/nvm.sh" >/dev/null
fi
command -v npm >/dev/null || die "Node.js/npm non trovato (brew install node)"
STOCKFISH_SRC="$(cd "$(dirname "$STOCKFISH_SRC")" && pwd -P)/$(basename "$STOCKFISH_SRC")"
STOCKFISH_SRC="$(readlink -f "$STOCKFISH_SRC" 2>/dev/null || echo "$STOCKFISH_SRC")"
[ -x "$STOCKFISH_SRC" ] || die "Stockfish non trovato (brew install stockfish o STOCKFISH_PATH=...)"
if otool -L "$STOCKFISH_SRC" | tail -n +2 | grep -v -E '/usr/lib/|/System/' | grep -q .; then
  die "Stockfish ($STOCKFISH_SRC) dipende da librerie esterne: non è copiabile nel bundle"
fi
if [ ! -f "$PUZZLES_DB" ]; then
  echo "Attenzione: $PUZZLES_DB non trovato: l'app userà solo il piccolo set di puzzle di riserva."
  echo "            (cd backend && .venv/bin/python scripts/import_puzzles.py per importarli)"
fi
if ! "$VENV_PY" -c 'import PyInstaller' 2>/dev/null; then
  step "Installo PyInstaller (backend/requirements-dev.txt)"
  "$VENV_PY" -m pip install -q -r "$ROOT/backend/requirements-dev.txt"
fi
echo "Python: $("$VENV_PY" --version)  PyInstaller: $("$VENV_PY" -m PyInstaller --version)"
echo "Node: $(node --version)  Stockfish: $STOCKFISH_SRC  Arch: $ARCH"

mkdir -p "$BUILD" "$DIST"

# --- 1. frontend ----------------------------------------------------------------------------
step "1/7 Build del frontend (Vite)"
( cd "$ROOT/frontend"
  [ -d node_modules ] || npm ci
  npm run build --silent )
[ -f "$ROOT/frontend/dist/index.html" ] || die "build del frontend non riuscita"

# --- 2. backend congelato ---------------------------------------------------------------------
step "2/7 Backend congelato con PyInstaller (onedir)"
rm -rf "$BUILD/pyinstaller"
"$VENV_PY" -m PyInstaller --noconfirm --clean --log-level WARN \
  --name chessai-server --onedir --console \
  --distpath "$BUILD/pyinstaller/dist" --workpath "$BUILD/pyinstaller/work" --specpath "$BUILD/pyinstaller" \
  --paths "$ROOT/backend" \
  --add-data "$ROOT/backend/app/resources:app/resources" \
  --collect-submodules uvicorn \
  --hidden-import anthropic \
  --exclude-module tkinter --exclude-module _tkinter \
  --exclude-module pytest --exclude-module _pytest \
  --exclude-module watchfiles --exclude-module zstandard \
  --exclude-module IPython --exclude-module _decimal \
  "$ROOT/backend/server.py"
SERVER_DIR="$BUILD/pyinstaller/dist/chessai-server"
[ -x "$SERVER_DIR/chessai-server" ] || die "PyInstaller non ha prodotto chessai-server"

# --- 3. wrapper Swift -------------------------------------------------------------------------
step "3/7 Compilazione del wrapper Swift"
swiftc -O -swift-version 5 -target "$ARCH-apple-macos13.0" \
  -framework AppKit -framework WebKit \
  "$MACAPP"/Sources/*.swift -o "$BUILD/$APP_NAME"

# --- 4. icona ----------------------------------------------------------------------------------
step "4/7 Icona"
swiftc -O "$MACAPP/make_icon.swift" -o "$BUILD/make_icon"
rm -rf "$BUILD/AppIcon.iconset"
"$BUILD/make_icon" "$BUILD/AppIcon.iconset"
iconutil -c icns "$BUILD/AppIcon.iconset" -o "$BUILD/AppIcon.icns"

# --- 5. assemblaggio --------------------------------------------------------------------------
step "5/7 Assemblaggio del bundle"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/it.lproj" "$APP/Contents/Resources/licenses"
cp "$MACAPP/Info.plist" "$APP/Contents/Info.plist"
plutil -replace CFBundleVersion -string "$(date +%Y%m%d.%H%M)" "$APP/Contents/Info.plist"
printf 'APPL????' > "$APP/Contents/PkgInfo"
cp "$BUILD/$APP_NAME" "$APP/Contents/MacOS/$APP_NAME"
cp "$BUILD/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
ditto "$SERVER_DIR" "$APP/Contents/Resources/server"
cp "$STOCKFISH_SRC" "$APP/Contents/Resources/stockfish"
chmod 755 "$APP/Contents/Resources/stockfish"
SF_PREFIX="$(dirname "$(dirname "$STOCKFISH_SRC")")"
for lic in Copying.txt COPYING LICENSE; do
  [ -f "$SF_PREFIX/$lic" ] && cp "$SF_PREFIX/$lic" "$APP/Contents/Resources/licenses/stockfish-COPYING.txt" && break
done
if [ -f "$PUZZLES_DB" ]; then
  # il server lo apre in sola lettura (mode=ro, journal "delete": nessun file -wal/-shm nel bundle)
  cp "$PUZZLES_DB" "$APP/Contents/Resources/puzzles.db"
  chmod 644 "$APP/Contents/Resources/puzzles.db"
fi
ditto "$ROOT/frontend/dist" "$APP/Contents/Resources/web"
find "$APP" -name .DS_Store -delete

# --- 6. firma ad-hoc ---------------------------------------------------------------------------
step "6/7 Firma ad-hoc"
# prima tutto il codice annidato (dylib/.so/eseguibili del server e Stockfish), poi il bundle
while IFS= read -r -d '' f; do
  if file -b "$f" | grep -q 'Mach-O'; then
    codesign --force --sign - --timestamp=none "$f" >/dev/null 2>&1 || die "firma fallita: $f"
  fi
done < <(find "$APP/Contents/Resources" -type f -print0)
codesign --force --deep --sign - --timestamp=none "$APP"
codesign --verify --deep --strict "$APP" || die "verifica della firma fallita"
xattr -cr "$APP"

rm -rf "$FINAL"
ditto "$APP" "$FINAL"
codesign --verify --deep --strict "$FINAL"
echo "Creato: $FINAL ($(du -sh "$FINAL" | cut -f1))"

# --- 7. installazione ------------------------------------------------------------------------
if [ "$INSTALL" = 1 ]; then
  step "7/7 Installazione in $INSTALLED"
  if [ -e "$INSTALLED" ]; then
    existing_id="$(defaults read "$INSTALLED/Contents/Info.plist" CFBundleIdentifier 2>/dev/null || true)"
    [ "$existing_id" = "$BUNDLE_ID" ] || die "$INSTALLED esiste ma non è LearnAI creata da questo script (id: '$existing_id'): non la sovrascrivo"
    if pgrep -f "$INSTALLED/Contents/MacOS/$APP_NAME" >/dev/null; then
      echo "LearnAI è in esecuzione: la chiudo..."
      osascript -e "tell application id \"$BUNDLE_ID\" to quit" >/dev/null 2>&1 || true
      for _ in $(seq 1 50); do pgrep -f "$INSTALLED/Contents/MacOS/$APP_NAME" >/dev/null || break; sleep 0.2; done
    fi
    rm -rf "$INSTALLED"
  fi
  ditto "$FINAL" "$INSTALLED"
  xattr -cr "$INSTALLED"
  codesign --verify --deep --strict "$INSTALLED"
  # aggiorna la cache di Launch Services (icona e nome nel Finder/Dock)
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$INSTALLED" >/dev/null 2>&1 || true
  echo "Installata: $INSTALLED"
  if [ -e "/Applications/ChessAI.app" ]; then
    echo "Nota: c'è ancora la vecchia /Applications/ChessAI.app (stesso bundle id). I dati sono condivisi;"
    echo "      puoi rimuoverla con: rm -rf /Applications/ChessAI.app"
  fi
else
  echo "Installazione saltata (--no-install)."
fi

step "Fatto"
echo "Avvia con: open \"$([ "$INSTALL" = 1 ] && echo "$INSTALLED" || echo "$FINAL")\""
