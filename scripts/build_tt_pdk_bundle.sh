#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
VERSION_FILE="$REPO_ROOT/VERSION"

DEFAULT_VERSION="0.1.0"
if [ -f "$VERSION_FILE" ]; then
  DEFAULT_VERSION="$(<"$VERSION_FILE")"
fi

SOURCE_SKY130A="${1:-$HOME/pdk/sky130A}"
VERSION="${2:-$DEFAULT_VERSION}"
BUNDLE_NAME="tt-pdk-sky130a"
OUTPUT_DIR="$DIST_DIR/${BUNDLE_NAME}_${VERSION}"
OUTPUT_TARBALL="$DIST_DIR/${BUNDLE_NAME}_${VERSION}.tar.gz"

if [ ! -d "$SOURCE_SKY130A" ]; then
  echo "Source SKY130A directory not found: $SOURCE_SKY130A" >&2
  exit 1
fi

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"
cp -a "$SOURCE_SKY130A" "$OUTPUT_DIR/sky130A"

mkdir -p "$DIST_DIR"
rm -f "$OUTPUT_TARBALL"
tar -C "$OUTPUT_DIR" -czf "$OUTPUT_TARBALL" sky130A

echo
echo "TT PDK bundle created:"
echo "  $OUTPUT_TARBALL"
echo "SHA256:"
sha256sum "$OUTPUT_TARBALL"
