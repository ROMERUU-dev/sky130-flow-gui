#!/usr/bin/env bash
# Install a container runtime for the OpenLane/LibreLane digital flow.
#
# Ubuntu 26.04 ships docker.io 29.x, which is current enough for this, so no
# third-party apt repository or GPG key is added: the packages keep coming
# through Ubuntu's own security updates.
set -euo pipefail

# Work out which account should get Docker access. pkexec does not set
# SUDO_USER and resets USER to root, so PKEXEC_UID is the only reliable
# pointer back to the desktop user when the app launches this.
resolve_target_user() {
  if [ -n "${PKEXEC_UID:-}" ]; then
    getent passwd "$PKEXEC_UID" | cut -d: -f1
    return
  fi
  if [ -n "${SUDO_USER:-}" ]; then
    printf '%s\n' "$SUDO_USER"
    return
  fi
  if [ -n "${SKY130_TARGET_USER:-}" ]; then
    printf '%s\n' "$SKY130_TARGET_USER"
    return
  fi
  # Last resort: the owner of the session that invoked us.
  logname 2>/dev/null || id -un
}

TARGET_USER="$(resolve_target_user)"

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer supports Ubuntu/Debian systems with apt-get." >&2
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "This step installs system packages and must run with privileges." >&2
  exit 1
fi

if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
  echo "Could not determine which desktop user should get Docker access." >&2
  echo "Re-run with SKY130_TARGET_USER=<your-user>, or with sudo from that account." >&2
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
