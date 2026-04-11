#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHANNEL="${1:-stable}"
MANIFEST_PATH="$REPO_ROOT/app/data/dependency_manifest.json"

echo "== SKY130 Flow Ubuntu bootstrap =="
echo
echo "Dependency channel: $CHANNEL"
echo

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer currently supports Ubuntu/Debian systems with apt-get."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to read the dependency manifest at $MANIFEST_PATH."
  exit 1
fi

if [ ! -f "$MANIFEST_PATH" ]; then
  echo "Dependency manifest not found at $MANIFEST_PATH."
  exit 1
fi

mapfile -t APT_PACKAGES < <(
  python3 - "$MANIFEST_PATH" "$CHANNEL" <<'PY'
import json
import sys

manifest_path, channel = sys.argv[1:3]
with open(manifest_path, "r", encoding="utf-8") as handle:
    data = json.load(handle)
channels = data.get("channels", {})
if channel not in channels:
    available = ", ".join(sorted(channels))
    raise SystemExit(f"Unknown dependency channel: {channel}. Available: {available}")
packages = channels[channel].get("bootstrap", {}).get("apt_packages", [])
for package in packages:
    print(package)
PY
)

if [ "${#APT_PACKAGES[@]}" -eq 0 ]; then
  echo "No apt packages were defined for channel '$CHANNEL'."
  exit 1
fi

echo "Updating package index..."
apt-get update

echo "Installing core VLSI toolchain packages..."
apt-get install -y "${APT_PACKAGES[@]}"

echo
echo "Package installation finished."
echo
echo "Installing official Magic 8.3.634 source release for current SKY130 techfiles..."
MAGIC_INSTALLER="$REPO_ROOT/scripts/install_magic_8_3_634_ubuntu.sh"
if [ ! -f "$MAGIC_INSTALLER" ]; then
  echo "Magic source installer not found at $MAGIC_INSTALLER."
  exit 1
fi
/bin/bash "$MAGIC_INSTALLER"

echo
echo "Magic source installation finished."
echo
echo "System bootstrap completed."
echo "This script intentionally does NOT create or modify $REPO_ROOT/.venv."
echo "Create the Python environment later as the normal user, for example:"
echo "  cd '$REPO_ROOT'"
echo "  python3 -m venv .venv"
echo "  .venv/bin/python -m pip install --upgrade pip"
echo "  .venv/bin/python -m pip install -r requirements.txt"
echo
echo "Do not mix pkexec/sudo with user-owned .venv creation inside the repository."

echo
echo "Checking for common SKY130A locations..."

found_pdk=""
for candidate in \
  /usr/share/pdk/sky130A \
  /usr/local/share/pdk/sky130A \
  "$HOME/pdk/sky130A"
do
  if [ -d "$candidate" ]; then
    found_pdk="$candidate"
    break
  fi
done

if [ -n "$found_pdk" ]; then
  echo "Detected SKY130A at: $found_pdk"
else
  echo "SKY130A was not found in common locations."
  echo "Installing apt packages is not the same as having the SKY130 PDK."
  echo "Point Preferences/Setup to an existing SKY130A tree or install one separately and re-run detection."
fi

echo
echo "Bootstrap completed."
