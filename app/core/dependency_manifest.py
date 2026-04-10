"""Versioned dependency policy manifest loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChannelPolicy:
    """Resolved policy for one dependency channel."""

    name: str
    description: str
    apt_packages: tuple[str, ...]
    pdk_strategy: str
    pdk_managed_root: str
    pdk_managed_install_mode: str
    pdk_minimum_free_gb: int
    pdk_source_build_root: str
    pdk_source_build_minimum_free_gb: int
    pdk_source_build_required_commands: tuple[str, ...]
    pdk_source_build_open_pdks_repo: str
    pdk_source_build_open_pdks_ref: str
    pdk_source_build_configure_args: tuple[str, ...]
    pdk_bundle_enabled: bool
    pdk_bundle_name: str
    pdk_bundle_version: str
    pdk_bundle_install_root: str
    pdk_bundle_cache_root: str
    pdk_bundle_minimum_free_gb: int
    pdk_bundle_asset_url: str
    pdk_bundle_asset_filename: str
    pdk_bundle_asset_sha256: str
    pdk_preferred_sources: tuple[str, ...]
    pdk_search_roots: tuple[str, ...]


class DependencyManifest:
    """Load the checked-in dependency policy used by setup and validation."""

    def __init__(self, manifest_path: Path | None = None) -> None:
        self.manifest_path = manifest_path or Path(__file__).resolve().parents[1] / "data" / "dependency_manifest.json"
        self._raw = self._load_json()

    def default_channel(self) -> str:
        return str(self._raw.get("default_channel", "stable"))

    def channel_names(self) -> tuple[str, ...]:
        channels = self._raw.get("channels", {})
        return tuple(channels.keys())

    def channel(self, name: str | None = None) -> ChannelPolicy:
        channel_name = name or self.default_channel()
        channels = self._raw.get("channels", {})
        if channel_name not in channels:
            raise KeyError(f"Unknown dependency channel: {channel_name}")
        raw_channel = channels[channel_name]
        bootstrap = raw_channel.get("bootstrap", {})
        pdk = raw_channel.get("pdk", {})
        return ChannelPolicy(
            name=channel_name,
            description=str(raw_channel.get("description", "")),
            apt_packages=tuple(str(item) for item in bootstrap.get("apt_packages", [])),
            pdk_strategy=str(pdk.get("strategy", "external-managed")),
            pdk_managed_root=str(pdk.get("managed_root", "~/pdk")),
            pdk_managed_install_mode=str(pdk.get("managed_install_mode", "symlink")),
            pdk_minimum_free_gb=int(pdk.get("minimum_free_gb", 8)),
            pdk_source_build_root=str(pdk.get("source_build_root", "~/src/pdk-build")),
            pdk_source_build_minimum_free_gb=int(pdk.get("source_build_minimum_free_gb", 20)),
            pdk_source_build_required_commands=tuple(str(item) for item in pdk.get("source_build_required_commands", [])),
            pdk_source_build_open_pdks_repo=str(pdk.get("source_build_open_pdks_repo", "")),
            pdk_source_build_open_pdks_ref=str(pdk.get("source_build_open_pdks_ref", "")),
            pdk_source_build_configure_args=tuple(str(item) for item in pdk.get("source_build_configure_args", [])),
            pdk_bundle_enabled=bool(pdk.get("bundle", {}).get("enabled", False)),
            pdk_bundle_name=str(pdk.get("bundle", {}).get("name", "tt-pdk-sky130a")),
            pdk_bundle_version=str(pdk.get("bundle", {}).get("version", "")),
            pdk_bundle_install_root=str(pdk.get("bundle", {}).get("install_root", "~/tt-pdk")),
            pdk_bundle_cache_root=str(pdk.get("bundle", {}).get("cache_root", "~/.cache/sky130-flow-gui/pdk")),
            pdk_bundle_minimum_free_gb=int(pdk.get("bundle", {}).get("minimum_free_gb", 10)),
            pdk_bundle_asset_url=str(pdk.get("bundle", {}).get("asset_url", "")),
            pdk_bundle_asset_filename=str(pdk.get("bundle", {}).get("asset_filename", "")),
            pdk_bundle_asset_sha256=str(pdk.get("bundle", {}).get("asset_sha256", "")),
            pdk_preferred_sources=tuple(str(item) for item in pdk.get("preferred_sources", [])),
            pdk_search_roots=tuple(str(item) for item in pdk.get("search_roots", [])),
        )

    def _load_json(self) -> dict:
        with self.manifest_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
