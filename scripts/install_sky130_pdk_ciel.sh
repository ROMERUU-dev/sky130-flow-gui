#!/usr/bin/env bash
# Install sky130A from the upstream prebuilt PDK releases.
#
# Builds come from fossi-foundation/ciel-releases and are keyed by the
# open_pdks commit they were produced from, so an install is reproducible and
# carries no local modifications.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST_PATH="${MANIFEST_PATH:-$REPO_ROOT/app/data/dependency_manifest.json}"
CHANNEL="${1:-stable}"

# Ubuntu marks its system Python as externally managed (PEP 668), so
# `pip install --user` is refused outright. The manager gets its own
# virtualenv under the user's XDG data directory instead.
TOOLS_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/sky130-flow-gui/tools"
CIEL_VENV="$TOOLS_HOME/ciel"
CIEL="$CIEL_VENV/bin/ciel"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to read the dependency manifest." >&2
  exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
  echo "Refusing to install a user PDK as root. Run this as your desktop user." >&2
  exit 1
fi

read -r PDK_FAMILY PDK_VERSION DEFAULT_ROOT < <(
  python3 - "$MANIFEST_PATH" "$CHANNEL" <<'PY'
import json
import sys

manifest_path, channel = sys.argv[1:3]
with open(manifest_path, "r", encoding="utf-8") as handle:
    data = json.load(handle)
channels = data.get("channels", {})
if channel not in channels:
    raise SystemExit(f"Unknown dependency channel: {channel}. Available: {', '.join(sorted(channels))}")
prebuilt = channels[channel].get("pdk", {}).get("prebuilt", {})
if not prebuilt.get("enabled"):
    raise SystemExit("The prebuilt PDK route is disabled in this manifest channel.")
print(prebuilt.get("pdk_family", "sky130"), prebuilt.get("version", ""), prebuilt.get("pdk_root", "~/.ciel"))
PY
)

if [ -z "$PDK_VERSION" ]; then
  echo "The manifest does not pin a prebuilt PDK version." >&2
  exit 1
fi

PDK_ROOT="${PDK_ROOT:-${DEFAULT_ROOT/#\~/$HOME}}"

echo "== SKY130 prebuilt PDK install =="
echo "Family:    $PDK_FAMILY"
echo "Version:   $PDK_VERSION"
echo "PDK_ROOT:  $PDK_ROOT"
echo "Manager:   $CIEL_VENV"
echo

if [ ! -x "$CIEL" ]; then
  echo "Creating the PDK manager environment..."
  mkdir -p "$TOOLS_HOME"
  if ! python3 -m venv "$CIEL_VENV"; then
    echo "Could not create a virtual environment. Install the Ubuntu package python3-venv." >&2
    exit 1
  fi
fi

echo "Installing the ciel PDK manager..."
"$CIEL_VENV/bin/python" -m pip install --quiet --upgrade pip
"$CIEL_VENV/bin/python" -m pip install --quiet --upgrade ciel

if [ ! -x "$CIEL" ]; then
  echo "ciel was installed but $CIEL is missing." >&2
  exit 1
fi

echo "Manager version: $("$CIEL" --version 2>&1 | head -1)"
echo
echo "Enabling $PDK_FAMILY build $PDK_VERSION..."
mkdir -p "$PDK_ROOT"
PDK_ROOT="$PDK_ROOT" "$CIEL" enable --pdk-family "$PDK_FAMILY" "$PDK_VERSION"

echo
echo "Done. Point the app at:"
echo "  PDK_ROOT = $PDK_ROOT"
echo "  SKY130A  = $PDK_ROOT/sky130A"
echo
echo "Available builds: https://github.com/fossi-foundation/ciel-releases/releases"
