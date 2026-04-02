#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
BUILD_ROOT="$DIST_DIR/deb-build"

PKG_NAME="sky130-flow-gui"
VERSION="${1:-0.1.0}"
ARCH="${2:-all}"
PKG_DIR="$BUILD_ROOT/${PKG_NAME}_${VERSION}_${ARCH}"

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

mkdir -p "$PKG_DIR/opt/$PKG_NAME/scripts"
cp "$REPO_ROOT/scripts/install_vlsi_env_ubuntu.sh" \
  "$PKG_DIR/opt/$PKG_NAME/scripts/install_vlsi_env_ubuntu.sh"

find "$PKG_DIR/opt/$PKG_NAME" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$PKG_DIR/opt/$PKG_NAME" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

cat > "$PKG_DIR/usr/bin/$PKG_NAME" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/sky130-flow-gui"
cd "$APP_ROOT"

if [ -x "$APP_ROOT/.venv/bin/python" ]; then
  exec "$APP_ROOT/.venv/bin/python" -m app.main "$@"
fi

exec python3 -m app.main "$@"
EOF
chmod 755 "$PKG_DIR/usr/bin/$PKG_NAME"

cp "$REPO_ROOT/packaging/debian/sky130-flow-gui.desktop" \
  "$PKG_DIR/usr/share/applications/sky130-flow-gui.desktop"
cp "$REPO_ROOT/app/resources/sky130-flow-gui.svg" \
  "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/sky130-flow-gui.svg"

INSTALLED_SIZE="$(du -sk "$PKG_DIR" | awk '{print $1}')"

cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $VERSION
Section: electronics
Priority: optional
Architecture: $ARCH
Maintainer: ROMERUU-dev
Depends: python3, python3-venv, python3-pip
Installed-Size: $INSTALLED_SIZE
Description: SKY130 workflow manager with setup assistant
 A desktop app for coordinating simulation, extraction, LVS,
 antenna checks, and setup tasks for SKY130 projects.
EOF

cat > "$PKG_DIR/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/sky130-flow-gui"
TARGET_USER="${SUDO_USER:-}"
if [ -z "$TARGET_USER" ] && [ -n "${PKEXEC_UID:-}" ]; then
  TARGET_USER="$(id -nu "$PKEXEC_UID")"
fi

if [ -n "$TARGET_USER" ] && [ "$TARGET_USER" != "root" ]; then
  runuser -u "$TARGET_USER" -- bash -lc "
    set -euo pipefail
    cd '$APP_ROOT'
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
  " || true
else
  python3 -m venv "$APP_ROOT/.venv" || true
  "$APP_ROOT/.venv/bin/python" -m pip install --upgrade pip || true
  "$APP_ROOT/.venv/bin/python" -m pip install -r "$APP_ROOT/requirements.txt" || true
fi

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
