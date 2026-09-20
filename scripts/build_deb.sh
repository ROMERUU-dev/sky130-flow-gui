#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
BUILD_ROOT="$DIST_DIR/deb-build"
VERSION_FILE="$REPO_ROOT/VERSION"

DEFAULT_VERSION="0.1.0"
if [ -f "$VERSION_FILE" ]; then
  DEFAULT_VERSION="$(<"$VERSION_FILE")"
fi

PKG_NAME="sky130-flow-gui"
VERSION="${1:-$DEFAULT_VERSION}"
ARCH="${2:-$(dpkg --print-architecture)}"
DEB_COMPRESSION_TYPE="${DEB_COMPRESSION_TYPE:-xz}"
DEB_COMPRESSION_LEVEL="${DEB_COMPRESSION_LEVEL:-1}"
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
  libwayland-client0
  libwayland-cursor0
  libwayland-egl1
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
cp "$REPO_ROOT/VERSION" "$PKG_DIR/opt/$PKG_NAME/VERSION"

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
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/sky130-flow-gui"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/sky130-flow-gui"
USER_VENV="$DATA_DIR/venv"
LOG_FILE="$STATE_DIR/launcher.log"

mkdir -p "$STATE_DIR"
exec >>"$LOG_FILE" 2>&1

echo
echo "[$(date -Is)] launching sky130-flow-gui"

cd "$APP_ROOT"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# The user-owned environment wins: it is the one the Setup Assistant creates
# and repairs, and it survives a Python upgrade that would strand the
# interpreter baked into the package at build time.
if [ -x "$USER_VENV/bin/python" ] && "$USER_VENV/bin/python" -c "import PySide6, pyqtgraph" >/dev/null 2>&1; then
  exec "$USER_VENV/bin/python" -m app.main "$@"
fi

if [ -x "$APP_ROOT/.venv/bin/python" ] && "$APP_ROOT/.venv/bin/python" -c "import PySide6, pyqtgraph" >/dev/null 2>&1; then
  exec "$APP_ROOT/.venv/bin/python" -m app.main "$@"
fi

if python3 -c "import PySide6, pyqtgraph" >/dev/null 2>&1; then
  exec python3 -m app.main "$@"
fi

echo "No usable Python environment was found for SKY130 Flow GUI."
echo "Creating the user environment at $USER_VENV ..."
if python3 "$APP_ROOT/app/core/python_env.py" repair --app-root "$APP_ROOT"; then
  exec "$USER_VENV/bin/python" -m app.main "$@"
fi

echo "Automatic repair failed. Install python3-venv and re-run, or see $LOG_FILE."
exit 1
EOF
chmod 755 "$PKG_DIR/usr/bin/$PKG_NAME"

cp "$REPO_ROOT/packaging/debian/sky130-flow-gui.desktop" \
  "$PKG_DIR/usr/share/applications/sky130-flow-gui.desktop"
cp "$REPO_ROOT/app/resources/sky130-flow-gui.svg" \
  "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/sky130-flow-gui.svg"

PYTHON_VERSION="$("$PACKAGE_VENV/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
INSTALLED_SIZE="$(du -sk "$PKG_DIR" | awk '{print $1}')"

REQUIRED_DEPENDS="python3, python3-venv"
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
 .
 Built and tested on Ubuntu 26.04 LTS with Python ${PYTHON_VERSION}.
EOF

cat > "$PKG_DIR/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/sky130-flow-gui"

cat <<MSG
SKY130 Flow GUI was installed under $APP_ROOT.

It ships a Python runtime at $APP_ROOT/.venv, but prefers a user-owned one at
  ~/.local/share/sky130-flow-gui/venv
which the Setup Assistant can create and repair without root.

The SKY130 PDK is not bundled. Install it from upstream with:
  bash $APP_ROOT/scripts/install_sky130_pdk_ciel.sh

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
dpkg-deb -Z"$DEB_COMPRESSION_TYPE" -z"$DEB_COMPRESSION_LEVEL" --build "$PKG_DIR" "$DIST_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo
echo "Package created:"
echo "  $DIST_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb"
