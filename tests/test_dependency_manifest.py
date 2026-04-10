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

        self.assertEqual(manifest.channel().apt_packages, ("git",))


if __name__ == "__main__":
    unittest.main()
