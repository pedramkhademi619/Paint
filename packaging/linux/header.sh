#!/bin/sh
# __NAME__ __VERSION__ - self-extracting installer for Linux (x86_64).
# Contains the program and its AI models; nothing is downloaded.
# Paintram is open source (GPL-3.0-or-later): __SOURCE__   -   curious about the insides? just read the code there.
#
#   sh __FILE__                 install for the current user (no root needed)
#   sh __FILE__ --system        install for everybody into /opt/__SLUG__ (run as root)
#   sh __FILE__ --prefix DIR    choose the install folder
#   sh __FILE__ --yes           do not ask questions
#   sh __FILE__ --uninstall     remove a previous installation
#   sh __FILE__ --check         verify this installer is not corrupted
set -eu

NAME="__NAME__"; SLUG="__SLUG__"; VERSION="__VERSION__"; APP_ID="__APP_ID__"
COMMENT="__TAGLINE__"
PAYLOAD_LINE=__PAYLOAD_LINE__
UNPACKED_KB=__UNPACKED_KB__
EXE="__EXE__"

SELF=$(readlink -f "$0" 2>/dev/null || echo "$0")
SYSTEM=0; ASSUME_YES=0; ACTION=install; PREFIX=""; MENU=1

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --system) SYSTEM=1 ;;
    --prefix) [ $# -ge 2 ] || die "--prefix needs a folder"; PREFIX=$2; shift ;;
    --yes|-y) ASSUME_YES=1 ;;
    --no-menu) MENU=0 ;;
    --uninstall) ACTION=uninstall ;;
    --check) ACTION=check ;;
    -h|--help) sed -n '2,13p' "$SELF" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown option: $1 (try --help)" ;;
  esac
  shift
done

if [ "$SYSTEM" = 1 ]; then
  [ "$(id -u)" = 0 ] || die "--system needs root. Try: sudo sh $0 --system"
  PREFIX=${PREFIX:-/opt/$SLUG}
  BIN_DIR=/usr/local/bin
  APPS_DIR=/usr/local/share/applications
  ICON_DIR=/usr/local/share/icons/hicolor/256x256/apps
else
  DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
  PREFIX=${PREFIX:-$DATA/$SLUG}
  BIN_DIR="${PAINTRAM_BIN_DIR:-$HOME/.local/bin}"
  APPS_DIR="$DATA/applications"
  ICON_DIR="$DATA/icons/hicolor/256x256/apps"
fi
# refuse anything that could point at the root of a disk or a home folder
case "$PREFIX" in ""|/|/usr|/bin|/etc|/home|/root|"$HOME") die "Refusing to install into '$PREFIX'. Choose a dedicated folder with --prefix." ;; esac

payload() { tail -n +"$PAYLOAD_LINE" "$SELF"; }

# ---------------------------------------------------------------- check / uninstall
if [ "$ACTION" = check ]; then
  say "Checking the installer (this reads the whole file)…"
  payload | gzip -t && say "OK: the installer is intact." && exit 0
  die "The installer is corrupted. Download it again."
fi

if [ "$ACTION" = uninstall ]; then
  if [ -x "$PREFIX/uninstall.sh" ]; then exec "$PREFIX/uninstall.sh"; fi
  die "No installation found in $PREFIX (use --prefix if you installed elsewhere)."
fi

# ---------------------------------------------------------------- pre-flight
[ "$(uname -s)" = Linux ] || die "This installer is for Linux. Use the Windows installer instead."
case "$(uname -m)" in x86_64|amd64) ;; *) die "This installer is for 64-bit Intel/AMD processors (x86_64); you have $(uname -m)." ;; esac

PARENT=$(dirname "$PREFIX")
mkdir -p "$PARENT" 2>/dev/null || die "Cannot create $PARENT"
AVAIL_KB=$(df -Pk "$PARENT" | awk 'NR==2 {print $4}')
NEED_KB=$((UNPACKED_KB + UNPACKED_KB / 20))
if [ "${AVAIL_KB:-0}" -lt "$NEED_KB" ]; then
  die "Not enough disk space in $PARENT: need about $((NEED_KB / 1024)) MB, have $((AVAIL_KB / 1024)) MB."
fi

if [ -e "$PREFIX/$EXE" ]; then
  warn "$NAME is already installed in $PREFIX; it will be replaced."
fi
if [ "$ASSUME_YES" = 0 ] && [ -t 0 ]; then
  printf '%s %s will be installed to %s (about %s MB). Continue? [Y/n] ' "$NAME" "$VERSION" "$PREFIX" "$((UNPACKED_KB / 1024))"
  read -r answer || answer=n
  case "$answer" in n|N|no|NO) die "Cancelled." ;; esac
fi

# ---------------------------------------------------------------- extract
say "Installing $NAME $VERSION into $PREFIX"
STAGE="$PREFIX.installing.$$"
rm -rf "${STAGE:?}"
mkdir -p "$STAGE"
trap 'rm -rf "${STAGE:?}"' EXIT INT TERM
TARFLAGS=""
if tar --version 2>/dev/null | grep -q GNU; then TARFLAGS="--checkpoint=20000 --checkpoint-action=dot"; fi
# shellcheck disable=SC2086
payload | tar $TARFLAGS -xzf - -C "$STAGE" || die "Extraction failed (corrupted installer or disk full)."
echo
[ -x "$STAGE/$EXE" ] || die "The package does not contain $EXE."
rm -rf "${PREFIX:?}"
mv "$STAGE" "$PREFIX"
trap - EXIT INT TERM

# user installs keep settings, caches and models under the install folder, so removing it removes every trace
if [ "$SYSTEM" = 0 ]; then
  echo "Delete this folder (or run uninstall.sh) to remove $NAME completely." > "$PREFIX/portable.marker"
fi

# ---------------------------------------------------------------- menu entry, launcher, uninstaller
ICON_SRC=$(find "$PREFIX" -name paint.png -print -quit 2>/dev/null || true)
if [ "$MENU" = 1 ]; then
  mkdir -p "$BIN_DIR" "$APPS_DIR" "$ICON_DIR"
  if [ -n "$ICON_SRC" ]; then cp "$ICON_SRC" "$ICON_DIR/$SLUG.png"; fi
  printf '#!/bin/sh\nexec "%s/%s" "$@"\n' "$PREFIX" "$EXE" > "$BIN_DIR/$SLUG"
  chmod +x "$BIN_DIR/$SLUG"
  cat > "$APPS_DIR/$SLUG.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=$NAME
Comment=$COMMENT
Exec="$PREFIX/$EXE" %F
Icon=$SLUG
Terminal=false
Categories=Graphics;RasterGraphics;2DGraphics;
MimeType=image/png;image/jpeg;image/bmp;image/webp;
StartupWMClass=$NAME
DESK
  if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true; fi
fi

# the uninstaller is generated with the real paths filled in; every removal is guarded against empty variables
cat > "$PREFIX/uninstall.sh" <<UNINST
#!/bin/sh
# Removes $NAME completely (program, AI models, caches, settings, menu entry, launcher).
set -eu
echo "Removing $NAME from ${PREFIX:?} ..."
rm -f "${BIN_DIR:?}/${SLUG:?}" "${APPS_DIR:?}/${SLUG:?}.desktop" "${ICON_DIR:?}/${SLUG:?}.png"
if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database "${APPS_DIR:?}" >/dev/null 2>&1 || true; fi
cd /
rm -rf "${PREFIX:?}"
echo "Done. Nothing of $NAME is left on this computer (your own pictures were not touched)."
UNINST
chmod +x "$PREFIX/uninstall.sh"

# ---------------------------------------------------------------- verify
say "Checking the installation"
if QT_QPA_PLATFORM=offscreen "$PREFIX/$EXE" --selftest >/dev/null 2>&1; then
  echo "Self-test passed."
else
  warn "The self-test did not pass. If $NAME does not start, Qt may need system libraries:"
  warn "  Debian/Ubuntu: sudo apt install libgl1 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0 libxcb-shape0 libegl1"
fi
if [ "$MENU" = 1 ]; then
  case ":$PATH:" in *":$BIN_DIR:"*) ;; *) warn "$BIN_DIR is not on your PATH; start $NAME from the application menu." ;; esac
fi
say "$NAME is installed. Start it from the application menu or run: $SLUG"
echo "Uninstall:  $PREFIX/uninstall.sh"
exit 0
__PAYLOAD_BELOW__
