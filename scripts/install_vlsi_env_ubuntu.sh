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
  python3-venv \
  libxcb-cursor0 \
  libxcb-xinerama0 \
  libxkbcommon-x11-0 \
  libxcb-xkb1 \
  libxcb-icccm4 \
  libxcb-image0 \
  libxcb-keysyms1 \
  libxcb-render-util0 \
  libxcb-randr0 \
  libxcb-shape0 \
  libxcb-xfixes0 \
  libgl1

echo
echo "Package installation finished."
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
