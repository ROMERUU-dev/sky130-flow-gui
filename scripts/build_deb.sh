#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
BUILD_ROOT="$DIST_DIR/deb-build"

PKG_NAME="sky130-flow-gui"
VERSION="${1:-0.1.0}"
ARCH="${2:-$(dpkg --print-architecture)}"
PKG_DIR="$BUILD_ROOT/${PKG_NAME}_${VERSION}_${ARCH}"
PACKAGE_VENV="$PKG_DIR/opt/$PKG_NAME/.venv"
SOURCE_VENV="$REPO_ROOT/.venv"

REQUIRED_GUI_PACKAGES=(
  libxcb-cursor0
  libxkbcommon-x11-0
  libxcb-xkb1
  libxcb-xfixes0
  libgl1
)

RECOMMENDED_GUI_PACKAGES=(
  libxcb-xinerama0
  libxcb-icccm4
  libxcb-image0
  libxcb-keysyms1
  libxcb-render-util0
  libxcb-randr0
  libxcb-shape0
)

rm -rf "$PKG_DIR"
mkdir -p \
  "$PKG_DIR/DEBIAN" \
  "$PKG_DIR/opt/$PKG_NAME" \
  "$PKG_DIR/usr/bin" \
  "$PKG_DIR/usr/share/applications" \
  "$PKG_DIR/usr/share/icons/hicolor/scalable/apps"

cp -R \
  "$REPO_ROOT/app" \
  "$REPO_ROOT/requirements.txt" \
  "$REPO_ROOT/README.md" \
  "$PKG_DIR/opt/$PKG_NAME/"

cp -R "$REPO_ROOT/scripts" "$PKG_DIR/opt/$PKG_NAME/"

if [ -x "$SOURCE_VENV/bin/python" ]; then
  cp -a "$SOURCE_VENV" "$PACKAGE_VENV"
else
  python3 -m venv "$PACKAGE_VENV"
  "$PACKAGE_VENV/bin/python" -m pip install --upgrade pip
  "$PACKAGE_VENV/bin/python" -m pip install -r "$REPO_ROOT/requirements.txt"
fi

find "$PKG_DIR/opt/$PKG_NAME" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$PKG_DIR/opt/$PKG_NAME" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

cat > "$PKG_DIR/usr/bin/$PKG_NAME" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/sky130-flow-gui"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/sky130-flow-gui"
LOG_FILE="$LOG_DIR/launcher.log"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

echo
echo "[$(date -Is)] launching sky130-flow-gui"

cd "$APP_ROOT"

if [ -x "$APP_ROOT/.venv/bin/python" ]; then
  exec "$APP_ROOT/.venv/bin/python" -m app.main "$@"
fi

if python3 -c "import PySide6, pyqtgraph" >/dev/null 2>&1; then
  exec python3 -m app.main "$@"
fi

echo "Missing packaged or system Python dependencies for SKY130 Flow GUI."
exec python3 -m app.main "$@"
EOF
chmod 755 "$PKG_DIR/usr/bin/$PKG_NAME"

cp "$REPO_ROOT/packaging/debian/sky130-flow-gui.desktop" \
  "$PKG_DIR/usr/share/applications/sky130-flow-gui.desktop"
cp "$REPO_ROOT/app/resources/sky130-flow-gui.svg" \
  "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/sky130-flow-gui.svg"

INSTALLED_SIZE="$(du -sk "$PKG_DIR" | awk '{print $1}')"

REQUIRED_DEPENDS="python3"
for pkg in "${REQUIRED_GUI_PACKAGES[@]}"; do
  REQUIRED_DEPENDS+=", ${pkg}"
done

RECOMMENDS_FIELD=""
if [ "${#RECOMMENDED_GUI_PACKAGES[@]}" -gt 0 ]; then
  RECOMMENDS_JOINED="$(IFS=, ; echo "${RECOMMENDED_GUI_PACKAGES[*]}")"
  RECOMMENDS_FIELD="Recommends: ${RECOMMENDS_JOINED}"
fi

cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $VERSION
Section: electronics
Priority: optional
Architecture: $ARCH
Maintainer: ROMERUU-dev
Depends: $REQUIRED_DEPENDS
$RECOMMENDS_FIELD
Installed-Size: $INSTALLED_SIZE
Description: SKY130 workflow manager with setup assistant
 A desktop app for coordinating simulation, extraction, LVS,
 antenna checks, and setup tasks for SKY130 projects.
EOF

cat > "$PKG_DIR/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/sky130-flow-gui"

cat <<MSG
SKY130 Flow GUI was installed under $APP_ROOT.

This package includes its own Python runtime under:
  $APP_ROOT/.venv

If the desktop launcher fails, check:
  ~/.local/state/sky130-flow-gui/launcher.log
MSG

update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
gtk-update-icon-cache /usr/share/icons/hicolor >/dev/null 2>&1 || true
EOF
chmod 755 "$PKG_DIR/DEBIAN/postinst"

cat > "$PKG_DIR/DEBIAN/prerm" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
gtk-update-icon-cache /usr/share/icons/hicolor >/dev/null 2>&1 || true
EOF
chmod 755 "$PKG_DIR/DEBIAN/prerm"

mkdir -p "$DIST_DIR"
dpkg-deb --build "$PKG_DIR" "$DIST_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo
echo "Package created:"
echo "  $DIST_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb"
