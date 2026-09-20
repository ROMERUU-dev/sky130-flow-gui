#!/usr/bin/env bash
# Install a container runtime for the OpenLane/LibreLane digital flow.
#
# Ubuntu 26.04 ships docker.io 29.x, which is current enough for this, so no
# third-party apt repository or GPG key is added: the packages keep coming
# through Ubuntu's own security updates.
set -euo pipefail

TARGET_USER="${SUDO_USER:-${USER:-$(id -un)}}"

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer supports Ubuntu/Debian systems with apt-get." >&2
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "This step installs system packages and must run with privileges." >&2
  exit 1
fi

if [ "$TARGET_USER" = "root" ]; then
  echo "Refusing to run without a desktop user to grant access to." >&2
  echo "Run this through the app, or with sudo from your normal account." >&2
  exit 1
fi

echo "== Container runtime install =="
echo "Desktop user: $TARGET_USER"
echo

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2

echo
echo "Enabling the Docker service..."
systemctl enable --now docker || echo "systemd is unavailable; start the daemon yourself."

echo
echo "Granting $TARGET_USER access to the Docker socket..."
groupadd -f docker
usermod -aG docker "$TARGET_USER"

echo
docker --version || true
echo
echo "Done."
echo
echo "IMPORTANT: group membership only applies to new sessions. Log out and back"
echo "in (or reboot) before the app can talk to Docker without sudo."
echo "To check afterwards:  docker run --rm hello-world"
