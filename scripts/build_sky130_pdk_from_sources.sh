#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST_PATH="$REPO_ROOT/app/data/dependency_manifest.json"
CHANNEL="${1:-stable}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to read the dependency manifest."
  exit 1
fi

if [ ! -f "$MANIFEST_PATH" ]; then
  echo "Dependency manifest not found at $MANIFEST_PATH"
  exit 1
fi

eval "$(python3 - "$MANIFEST_PATH" "$CHANNEL" <<'PY'
import json
import os
import shlex
import sys

manifest_path, channel = sys.argv[1:3]
with open(manifest_path, "r", encoding="utf-8") as handle:
    data = json.load(handle)
channels = data.get("channels", {})
if channel not in channels:
    available = ", ".join(sorted(channels))
    raise SystemExit(f"Unknown dependency channel: {channel}. Available: {available}")
pdk = channels[channel].get("pdk", {})
build_root = os.path.expanduser(pdk.get("source_build_root", "~/src/pdk-build"))
managed_root = os.path.expanduser(pdk.get("managed_root", "~/pdk"))
repo = pdk.get("source_build_open_pdks_repo", "")
ref = pdk.get("source_build_open_pdks_ref", "")
configure_args = pdk.get("source_build_configure_args", [])
required_commands = pdk.get("source_build_required_commands", [])
minimum_gb = int(pdk.get("source_build_minimum_free_gb", 20))

def emit(name: str, value: str) -> None:
    print(f"{name}={shlex.quote(value)}")

emit("BUILD_ROOT", build_root)
emit("MANAGED_ROOT", managed_root)
emit("OPEN_PDKS_REPO", repo)
emit("OPEN_PDKS_REF", ref)
emit("CONFIGURE_ARGS", "\n".join(configure_args))
emit("REQUIRED_COMMANDS", "\n".join(required_commands))
emit("MINIMUM_GB", str(minimum_gb))
PY
)"

TARGET_SKY130A="$MANAGED_ROOT/sky130A"
OPEN_PDKS_DIR="$BUILD_ROOT/open_pdks"
INSTALL_PREFIX="$BUILD_ROOT/install"
LOG_DIR="$BUILD_ROOT/logs"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/build_sky130_pdk_${TIMESTAMP}.log"
mkdir -p "$LOG_DIR"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "== SKY130 PDK source build =="
echo "Channel: $CHANNEL"
echo "Build root: $BUILD_ROOT"
echo "Managed root: $MANAGED_ROOT"
echo "Target sky130A: $TARGET_SKY130A"
echo "Log file: $LOG_FILE"
echo

if [ -e "$TARGET_SKY130A" ]; then
  echo "Refusing to build because target already exists: $TARGET_SKY130A"
  exit 1
fi

FREE_GB="$(python3 - "$BUILD_ROOT" <<'PY'
import os
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1]).expanduser()
usage_root = root if root.exists() else root.parent if root.parent.exists() else Path.home()
free = shutil.disk_usage(usage_root).free
print(free // (1024 ** 3))
PY
)"

if [ "$FREE_GB" -lt "$MINIMUM_GB" ]; then
  echo "Not enough free space. Need at least ${MINIMUM_GB} GB, found ${FREE_GB} GB."
  exit 1
fi

while IFS= read -r cmd; do
  [ -z "$cmd" ] && continue
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd"
    exit 1
  fi
done <<< "$REQUIRED_COMMANDS"

if [ -z "$OPEN_PDKS_REPO" ] || [ -z "$OPEN_PDKS_REF" ]; then
  echo "Manifest is missing pinned open_pdks source information."
  exit 1
fi

mkdir -p "$BUILD_ROOT"

if [ ! -d "$OPEN_PDKS_DIR/.git" ]; then
  echo "Cloning open_pdks from pinned source..."
  git clone "$OPEN_PDKS_REPO" "$OPEN_PDKS_DIR"
fi

echo "Fetching pinned source revision..."
git -C "$OPEN_PDKS_DIR" fetch --tags --prune origin
git -C "$OPEN_PDKS_DIR" checkout --detach "$OPEN_PDKS_REF"

mkdir -p "$INSTALL_PREFIX"

CONFIG_ARGS_ARRAY=()
if [ -n "$CONFIGURE_ARGS" ]; then
  mapfile -t CONFIG_ARGS_ARRAY <<< "$CONFIGURE_ARGS"
fi

echo "Running configure..."
cd "$OPEN_PDKS_DIR"
./configure --prefix="$INSTALL_PREFIX" "${CONFIG_ARGS_ARRAY[@]}"

JOBS="${JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"
echo "Running make -j$JOBS ..."
make -j"$JOBS"

echo "Running make install ..."
make install

BUILT_SKY130A=""
for candidate in \
  "$INSTALL_PREFIX/share/pdk/sky130A" \
  "$INSTALL_PREFIX/share/pdks/sky130A" \
  "$INSTALL_PREFIX/sky130A"
do
  if [ -d "$candidate" ]; then
    BUILT_SKY130A="$candidate"
    break
  fi
done

if [ -z "$BUILT_SKY130A" ]; then
  echo "Build finished but no installed sky130A directory was found under $INSTALL_PREFIX."
  exit 1
fi

mkdir -p "$MANAGED_ROOT"
ln -s "$BUILT_SKY130A" "$TARGET_SKY130A"

echo
echo "Build completed."
echo "Installed candidate: $BUILT_SKY130A"
echo "Managed target: $TARGET_SKY130A"
