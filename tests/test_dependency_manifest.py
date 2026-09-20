"""Tests for the dependency policy manifest."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.dependency_manifest import DependencyManifest


class DependencyManifestTest(unittest.TestCase):
    def test_loads_default_channel_and_packages(self) -> None:
        manifest = DependencyManifest()

        channel = manifest.channel()

        self.assertEqual(channel.name, "stable")
        self.assertIn("xschem", channel.apt_packages)
        self.assertIn("netgen-lvs", channel.apt_packages)
        self.assertIn("~/tt-pdk/ciel", channel.pdk_search_roots)
        self.assertIn("autoconf", channel.pdk_source_build_required_commands)
        self.assertEqual(channel.pdk_managed_root, "~/pdk")
        self.assertEqual(channel.pdk_bundle_install_root, "~/pdk")

    def test_maintainer_built_pdk_bundle_is_not_distributed(self) -> None:
        """The shipped manifest must not point users at a hand-built PDK tarball."""
        channel = DependencyManifest().channel()

        self.assertFalse(channel.pdk_bundle_enabled)
        self.assertEqual(channel.pdk_bundle_asset_url, "")
        self.assertEqual(channel.pdk_bundle_asset_sha256, "")
        self.assertIn("reproducible", channel.pdk_bundle_disabled_reason)

    def test_prebuilt_pdk_route_points_at_upstream_releases(self) -> None:
        channel = DependencyManifest().channel()

        self.assertTrue(channel.pdk_prebuilt_enabled)
        self.assertEqual(channel.pdk_prebuilt_provider, "ciel")
        self.assertEqual(channel.pdk_prebuilt_family, "sky130")
        self.assertIn("fossi-foundation", channel.pdk_prebuilt_releases_url)
        self.assertIn("ciel", channel.pdk_prebuilt_install_command)
        self.assertIn(channel.pdk_prebuilt_version, channel.pdk_prebuilt_enable_command)

    def test_tool_minimum_versions_flag_stale_distro_packages(self) -> None:
        """Ubuntu ships Magic 8.3.105, which current SKY130 techfiles reject."""
        minimums = dict(DependencyManifest().channel().tool_minimum_versions)

        self.assertEqual(minimums["magic"], "8.3.411")
        self.assertIn("netgen", minimums)

    def test_open_pdks_source_build_is_pinned_to_a_current_release(self) -> None:
        channel = DependencyManifest().channel()

        self.assertEqual(channel.pdk_source_build_open_pdks_ref, "1.0.608")
        self.assertIn("RTimothyEdwards/open_pdks", channel.pdk_source_build_open_pdks_repo)

    def test_unknown_channel_raises(self) -> None:
        manifest = DependencyManifest()

        with self.assertRaises(KeyError):
            manifest.channel("does-not-exist")

    def test_can_load_custom_manifest_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "dependency_manifest.json"
            manifest_path.write_text(
                """
{
  "default_channel": "stable",
  "channels": {
    "stable": {
      "description": "test",
      "bootstrap": {"apt_packages": ["git"]},
      "pdk": {
        "strategy": "external-managed",
        "bundle": {
          "enabled": true,
          "name": "tt-pdk-sky130a",
          "version": "0.1.0",
          "install_root": "~/pdk",
          "cache_root": "~/.cache/tt-pdk",
          "minimum_free_gb": 12,
          "asset_url": "https://example.invalid/tt-pdk-sky130a.tar.gz",
          "asset_filename": "tt-pdk-sky130a.tar.gz",
          "asset_sha256": "abc123"
        },
        "preferred_sources": ["settings"],
        "search_roots": ["~/pdk"]
      }
    }
  }
}
""".strip(),
                encoding="utf-8",
            )

            manifest = DependencyManifest(manifest_path)

        channel = manifest.channel()
        self.assertEqual(channel.apt_packages, ("git",))
        self.assertTrue(channel.pdk_bundle_enabled)
        self.assertEqual(channel.pdk_bundle_version, "0.1.0")
        self.assertEqual(channel.pdk_bundle_asset_filename, "tt-pdk-sky130a.tar.gz")


if __name__ == "__main__":
    unittest.main()
