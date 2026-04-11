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
        self.assertEqual(channel.pdk_bundle_name, "tt-pdk-sky130a")
        self.assertTrue(channel.pdk_bundle_enabled)
        self.assertEqual(channel.pdk_bundle_version, "0.2.0-beta.9")
        self.assertEqual(
            channel.pdk_bundle_asset_url,
            "https://github.com/ROMERUU-dev/sky130-flow-gui/releases/download/v0.2.0-beta.9/tt-pdk-sky130a_0.2.0-beta.9.tar.gz",
        )
        self.assertEqual(channel.pdk_bundle_asset_filename, "tt-pdk-sky130a_0.2.0-beta.9.tar.gz")
        self.assertEqual(
            channel.pdk_bundle_asset_sha256,
            "25acfcdaace6e6b8ca0ca828407ecf1a896a1c0e04560465d2259cda8b9b4c24",
        )

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
