#!/usr/bin/env python3
"""Download and install a prepared SKY130A PDK bundle into ~/pdk."""

from __future__ import annotations

import hashlib
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.dependency_manifest import DependencyManifest
from app.core.env_validator import REQUIRED_PDK_SUBDIRS


def _find_sky130a(root: Path) -> Path | None:
    direct = root / "sky130A"
    if direct.is_dir():
        return direct
    for match in sorted(root.rglob("sky130A")):
        if match.is_dir():
            return match
    return None


def _validate_sky130a(path: Path) -> list[str]:
    return [relative for relative in REQUIRED_PDK_SUBDIRS.values() if not path.joinpath(relative).exists()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    print(f"Downloading {url}", flush=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
        total = int(response.headers.get("Content-Length", "0") or "0")
        downloaded = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                print(f"Downloaded {downloaded // (1024 * 1024)} / {total // (1024 * 1024)} MiB", flush=True)
            else:
                print(f"Downloaded {downloaded // (1024 * 1024)} MiB", flush=True)


def main() -> int:
    channel_name = sys.argv[1] if len(sys.argv) > 1 else None
    manifest = DependencyManifest()
    policy = manifest.channel(channel_name)

    if not policy.pdk_bundle_enabled:
        print("PDK bundle installation is disabled in the manifest.", flush=True)
        return 2
    if not policy.pdk_bundle_asset_url or not policy.pdk_bundle_asset_filename:
        print("PDK bundle asset metadata is incomplete in the manifest.", flush=True)
        return 2

    install_root = Path(policy.pdk_bundle_install_root).expanduser()
    target_sky130a = install_root / "sky130A"
    cache_root = Path(policy.pdk_bundle_cache_root).expanduser()
    cache_root.mkdir(parents=True, exist_ok=True)

    if target_sky130a.exists():
        missing = _validate_sky130a(target_sky130a)
        if not missing:
            print(f"PDK already installed at {target_sky130a}", flush=True)
            return 0
        print(f"Target exists but is incomplete: {target_sky130a}", flush=True)
        return 3

    archive_path = cache_root / policy.pdk_bundle_asset_filename
    if archive_path.exists():
        print(f"Reusing cached archive {archive_path}", flush=True)
    else:
        _download(policy.pdk_bundle_asset_url, archive_path)

    if policy.pdk_bundle_asset_sha256:
        print("Verifying SHA256 checksum", flush=True)
        actual = _sha256(archive_path)
        if actual.lower() != policy.pdk_bundle_asset_sha256.lower():
            print(f"Checksum mismatch: expected {policy.pdk_bundle_asset_sha256}, got {actual}", flush=True)
            return 4

    with tempfile.TemporaryDirectory(prefix="tt-pdk-bundle-") as tmpdir:
        extract_root = Path(tmpdir)
        print(f"Extracting archive into {extract_root}", flush=True)
        with tarfile.open(archive_path, "r:*") as archive:
            archive.extractall(extract_root)

        extracted_sky130a = _find_sky130a(extract_root)
        if extracted_sky130a is None:
            print("Bundle archive does not contain a sky130A directory.", flush=True)
            return 5

        missing = _validate_sky130a(extracted_sky130a)
        if missing:
            print(f"Extracted sky130A is incomplete: {', '.join(missing)}", flush=True)
            return 6

        install_root.mkdir(parents=True, exist_ok=True)
        print(f"Installing sky130A into {target_sky130a}", flush=True)
        shutil.move(str(extracted_sky130a), str(target_sky130a))

    print(f"PDK bundle installed successfully at {target_sky130a}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
