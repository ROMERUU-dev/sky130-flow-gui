"""Tests for splash branding asset resolution."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.core.branding import RESOURCE_DIR, resolve_branding_logo


class SplashBrandingTest(unittest.TestCase):
    def test_branding_uses_packaged_squirrel_svg_when_png_is_missing(self) -> None:
        asset_kind, asset_path = resolve_branding_logo()

        self.assertEqual(asset_kind, "svg")
        self.assertEqual(asset_path, RESOURCE_DIR / "ardilla_silueta_blanca_suave.svg")
        self.assertTrue(Path(asset_path).is_file())


if __name__ == "__main__":
    unittest.main()
