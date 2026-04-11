#!/usr/bin/env bash
set -euo pipefail

MAGIC_VERSION="${MAGIC_VERSION:-8.3.634}"
MAGIC_TARBALL_URL="${MAGIC_TARBALL_URL:-http://www.opencircuitdesign.com/magic/archive/magic-${MAGIC_VERSION}.tgz}"
PREFIX="${PREFIX:-/usr/local}"
BUILD_ROOT="${BUILD_ROOT:-$HOME/src/magic-build}"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi

download() {
  local url="$1"
  local output="$2"

  if command -v curl >/dev/null 2>&1; then
    curl -L --fail --output "$output" "$url"
    return
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -O "$output" "$url"
    return
  fi

  echo "curl or wget is required to download Magic." >&2
  exit 1
}

echo "== Magic ${MAGIC_VERSION} source install =="
echo "Source: $MAGIC_TARBALL_URL"
echo "Prefix: $PREFIX"
echo "Build root: $BUILD_ROOT"
echo

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer currently supports Ubuntu/Debian systems with apt-get." >&2
  exit 1
fi

echo "Installing Magic build dependencies..."
$SUDO apt-get update
$SUDO apt-get install -y \
  build-essential \
  m4 \
  tcsh \
  tcl-dev \
  tk-dev \
  libcairo2-dev \
  libx11-dev \
  libxft-dev \
  libxrender-dev \
  libglu1-mesa-dev \
  curl \
  ca-certificates

mkdir -p "$BUILD_ROOT"
cd "$BUILD_ROOT"

tarball="magic-${MAGIC_VERSION}.tgz"
srcdir="magic-${MAGIC_VERSION}"

if [ ! -f "$tarball" ]; then
  echo "Downloading $tarball..."
  download "$MAGIC_TARBALL_URL" "$tarball"
else
  echo "Using existing $BUILD_ROOT/$tarball"
fi

rm -rf "$srcdir"
tar -xzf "$tarball"
cd "$srcdir"

echo "Configuring Magic..."
./configure --prefix="$PREFIX"

echo "Building Magic..."
make

echo "Installing Magic into $PREFIX..."
$SUDO make install

echo
echo "Installed Magic version:"
"$PREFIX/bin/magic" -dnull -noconsole -version
echo
echo "If your shell still finds an older Magic first, put $PREFIX/bin before /usr/bin in PATH"
echo "or set the Magic path in the app Preferences to:"
echo "  $PREFIX/bin/magic"
