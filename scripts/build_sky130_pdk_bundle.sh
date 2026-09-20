#!/usr/bin/env bash
# Build a redistributable sky130A bundle from a clean open_pdks checkout.
#
# The previous version of this script tarred up whatever happened to live in
# the maintainer's ~/pdk/sky130A.  That made the published asset unreproducible
# and let local edits leak into a public download, so this script refuses to
# package an in-use PDK root and records the exact inputs it built from.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST_PATH="${MANIFEST_PATH:-$REPO_ROOT/app/data/dependency_manifest.json}"
DIST_DIR="$REPO_ROOT/dist"
BUILD_ROOT="${BUILD_ROOT:-$DIST_DIR/pdk-bundle-build}"
CHANNEL="${1:-stable}"

read -r OPEN_PDKS_REPO OPEN_PDKS_REF < <(
  python3 - "$MANIFEST_PATH" "$CHANNEL" <<'PY'
import json
import sys

manifest_path, channel = sys.argv[1:3]
with open(manifest_path, "r", encoding="utf-8") as handle:
    data = json.load(handle)
pdk = data["channels"][channel]["pdk"]
print(pdk["source_build_open_pdks_repo"], pdk["source_build_open_pdks_ref"])
PY
)

BUNDLE_NAME="sky130a-prebuilt"
VERSION="${2:-$OPEN_PDKS_REF}"
STAGE_DIR="$BUILD_ROOT/stage"
INSTALL_DIR="$BUILD_ROOT/install"
OUTPUT_TARBALL="$DIST_DIR/${BUNDLE_NAME}_${VERSION}.tar.gz"

echo "== SKY130 PDK bundle build =="
echo "open_pdks: $OPEN_PDKS_REPO @ $OPEN_PDKS_REF"
echo "Build root: $BUILD_ROOT"
echo

# A bundle must never be produced from a PDK root that tools are using.
for forbidden in "$HOME/pdk" "$HOME/.ciel" "$HOME/.volare"; do
  case "$BUILD_ROOT/" in
    "$forbidden"/*)
      echo "Refusing to build a bundle inside an in-use PDK root: $forbidden" >&2
      exit 1
      ;;
  esac
done

for command in git make gcc python3 tclsh; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required build command: $command" >&2
    exit 1
  fi
done

rm -rf "$STAGE_DIR" "$INSTALL_DIR"
mkdir -p "$STAGE_DIR" "$INSTALL_DIR" "$DIST_DIR"

echo "Cloning open_pdks $OPEN_PDKS_REF..."
git clone --quiet --depth 1 --branch "$OPEN_PDKS_REF" "$OPEN_PDKS_REPO" "$STAGE_DIR/open_pdks"

cd "$STAGE_DIR/open_pdks"
echo "Configuring open_pdks..."
./configure --enable-sky130-pdk --prefix="$INSTALL_DIR"

echo "Building sky130A (this takes a while)..."
make
make install

SKY130A_DIR="$(find "$INSTALL_DIR" -maxdepth 4 -type d -name sky130A -print -quit)"
if [ -z "$SKY130A_DIR" ]; then
  echo "Build finished but no sky130A directory was produced." >&2
  exit 1
fi

cat > "$(dirname "$SKY130A_DIR")/BUNDLE_PROVENANCE.txt" <<PROV
sky130A bundle provenance
=========================
open_pdks repository : $OPEN_PDKS_REPO
open_pdks ref        : $OPEN_PDKS_REF
magic used for build : $(magic --version 2>/dev/null || echo "not detected")
built on             : $(date -u +%Y-%m-%dT%H:%M:%SZ)
built by             : clean-room build via scripts/build_sky130_pdk_bundle.sh
notes                : No maintainer workstation files are included in this archive.
PROV

echo "Packaging..."
rm -f "$OUTPUT_TARBALL"
tar -C "$(dirname "$SKY130A_DIR")" -czf "$OUTPUT_TARBALL" sky130A BUNDLE_PROVENANCE.txt

echo
echo "Bundle created:"
echo "  $OUTPUT_TARBALL"
echo "SHA256:"
sha256sum "$OUTPUT_TARBALL"
echo
echo "Update app/data/dependency_manifest.json with this checksum before publishing,"
echo "and re-enable the bundle route only once the asset is uploaded."
