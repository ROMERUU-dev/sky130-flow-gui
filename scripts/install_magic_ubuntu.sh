#!/usr/bin/env bash
# Build and install Magic from the official upstream repository.
#
# Ubuntu ships Magic 8.3.105 (2021).  Current SKY130 techfiles declare a much
# newer minimum, so the distro package cannot open sky130A at all.  This script
# builds a pinned upstream release instead.
set -euo pipefail

MAGIC_VERSION="${MAGIC_VERSION:-8.3.684}"
MAGIC_REPO="${MAGIC_REPO:-https://github.com/RTimothyEdwards/magic.git}"
MAGIC_TARBALL_URL="${MAGIC_TARBALL_URL:-http://www.opencircuitdesign.com/magic/archive/magic-${MAGIC_VERSION}.tgz}"
PREFIX="${PREFIX:-/usr/local}"
BUILD_ROOT="${BUILD_ROOT:-$HOME/src/magic-build}"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi

echo "== Magic ${MAGIC_VERSION} source install =="
echo "Repository: $MAGIC_REPO"
echo "Prefix:     $PREFIX"
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
  git \
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
srcdir="$BUILD_ROOT/magic-${MAGIC_VERSION}"

fetch_with_git() {
  command -v git >/dev/null 2>&1 || return 1
  rm -rf "$srcdir"
  git clone --quiet --depth 1 --branch "$MAGIC_VERSION" "$MAGIC_REPO" "$srcdir"
}

fetch_with_tarball() {
  local tarball="$BUILD_ROOT/magic-${MAGIC_VERSION}.tgz"
  if [ ! -f "$tarball" ]; then
    if command -v curl >/dev/null 2>&1; then
      curl -L --fail --output "$tarball" "$MAGIC_TARBALL_URL"
    elif command -v wget >/dev/null 2>&1; then
      wget -O "$tarball" "$MAGIC_TARBALL_URL"
    else
      echo "curl or wget is required to download Magic." >&2
      return 1
    fi
  fi
  rm -rf "$srcdir"
  tar -C "$BUILD_ROOT" -xzf "$tarball"
}

echo "Fetching Magic ${MAGIC_VERSION}..."
if ! fetch_with_git; then
  echo "Git checkout failed, falling back to the release tarball..."
  fetch_with_tarball
fi

cd "$srcdir"

# GCC 15 defaults to C23, which rejects constructs this codebase still relies
# on (notably old-style function declarations).  Pin the dialect it was
# written against instead of patching upstream sources.
GCC_MAJOR="$(gcc -dumpversion 2>/dev/null | cut -d. -f1 || echo 0)"
CONFIGURE_ENV=()
if [ "${GCC_MAJOR:-0}" -ge 14 ]; then
  echo "Detected GCC ${GCC_MAJOR}: building with -std=gnu17 for compatibility."
  CONFIGURE_ENV=(CFLAGS="${CFLAGS:--O2} -std=gnu17")
fi

echo "Configuring Magic..."
env "${CONFIGURE_ENV[@]}" ./configure --prefix="$PREFIX"

echo "Building Magic..."
make -j"$(nproc 2>/dev/null || echo 2)"

echo "Installing Magic into $PREFIX..."
$SUDO make install

echo
echo "Installed Magic version:"
"$PREFIX/bin/magic" --version
echo
echo "If your shell still finds an older Magic first, put $PREFIX/bin before /usr/bin in PATH"
echo "or set the Magic path in the app Preferences to:"
echo "  $PREFIX/bin/magic"
