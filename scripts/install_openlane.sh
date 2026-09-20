#!/usr/bin/env bash
# Pull the pinned LibreLane image, which carries the whole digital flow.
#
# LibreLane is the maintained successor to OpenLane 2. The image bundles
# OpenROAD, Yosys, Magic, KLayout and netgen, so nothing else is installed on
# the host. This runs as the desktop user; no privileges are required once the
# docker group is in effect.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST_PATH="${MANIFEST_PATH:-$REPO_ROOT/app/data/dependency_manifest.json}"
CHANNEL="${1:-stable}"

if [ "$(id -u)" -eq 0 ]; then
  echo "Refusing to pull images as root; run this as your desktop user." >&2
  exit 1
fi

read -r IMAGE MIN_GB < <(
  python3 - "$MANIFEST_PATH" "$CHANNEL" <<'PY'
import json
import sys

manifest_path, channel = sys.argv[1:3]
with open(manifest_path, "r", encoding="utf-8") as handle:
    data = json.load(handle)
channels = data.get("channels", {})
if channel not in channels:
    raise SystemExit(f"Unknown dependency channel: {channel}. Available: {', '.join(sorted(channels))}")
flow = channels[channel].get("digital_flow", {})
if not flow.get("enabled"):
    raise SystemExit("The digital flow is disabled in this manifest channel.")
print(flow.get("image", ""), flow.get("minimum_free_gb", 12))
PY
)

if [ -z "$IMAGE" ]; then
  echo "The manifest does not pin a digital-flow image." >&2
  exit 1
fi

ENGINE="$(command -v docker || command -v podman || true)"
if [ -z "$ENGINE" ]; then
  echo "No container runtime was found. Install Docker first." >&2
  exit 1
fi

if ! "$ENGINE" info >/dev/null 2>&1; then
  echo "The container daemon is not reachable." >&2
  echo "If Docker was just installed, log out and back in so the 'docker' group applies." >&2
  exit 1
fi

FREE_GB="$(df -BG --output=avail /var/lib 2>/dev/null | tail -1 | tr -dc '0-9')"
if [ -n "$FREE_GB" ] && [ "$FREE_GB" -lt "$MIN_GB" ]; then
  echo "Not enough free space for the image: ${FREE_GB}GB available, ${MIN_GB}GB needed." >&2
  exit 1
fi

echo "== Digital flow image =="
echo "Engine: $ENGINE"
echo "Image:  $IMAGE"
echo

"$ENGINE" pull "$IMAGE"

echo
echo "Verifying the toolchain inside the image..."
"$ENGINE" run --rm "$IMAGE" openroad -version || echo "  (openroad -version was not answered)"

echo
echo "Done. The image bundles OpenROAD, Yosys, Magic, KLayout and netgen."
echo "Run the flow with, for example:"
echo "  $ENGINE run --rm -v \"\$PWD:/work\" -w /work $IMAGE librelane --help"
