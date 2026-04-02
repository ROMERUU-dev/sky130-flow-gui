#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "== SKY130 Flow Ubuntu bootstrap =="
echo

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer currently supports Ubuntu/Debian systems with apt-get."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "Updating package index..."
apt-get update

echo "Installing core VLSI toolchain packages..."
apt-get install -y \
  git \
  xschem \
  ngspice \
  magic \
  netgen-lvs \
  klayout \
  python3 \
  python3-pip \
  python3-venv

echo
echo "Package installation finished."
echo
echo "Preparing Python environment for this project..."

ORIG_USER="${SUDO_USER:-}"
if [ -z "$ORIG_USER" ] && [ -n "${PKEXEC_UID:-}" ]; then
  ORIG_USER="$(id -nu "$PKEXEC_UID")"
fi

if [ -n "$ORIG_USER" ] && [ "$ORIG_USER" != "root" ]; then
  runuser -u "$ORIG_USER" -- bash -lc "
    set -euo pipefail
    cd '$REPO_ROOT'
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
  "
  echo "Python environment ready at: $REPO_ROOT/.venv"
else
  echo "Could not determine the original desktop user."
  echo "Create the project venv manually with:"
  echo "  cd '$REPO_ROOT' && python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
fi

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
  echo "You can still use the app now, then point Preferences/Setup to an existing PDK,"
  echo "or install a SKY130A distribution separately and re-run detection."
fi

echo
echo "Bootstrap completed."
