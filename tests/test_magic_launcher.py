"""Tests for interactive magic launch context construction."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

qtcore_stub = SimpleNamespace(QSettings=object)
sys.modules.setdefault("PySide6", SimpleNamespace(QtCore=qtcore_stub))
sys.modules.setdefault("PySide6.QtCore", qtcore_stub)

from app.core.magic_launcher import MagicLaunchBuilder
from app.core.settings_manager import AppSettings


class MagicLaunchBuilderTest(unittest.TestCase):
    def test_build_injects_pdk_context_and_magicrc(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sky130a = Path(tmpdir) / "pdk" / "sky130A"
            magic_rc = sky130a / "libs.tech" / "magic" / "sky130A.magicrc"
            magic_rc.parent.mkdir(parents=True)
            magic_rc.write_text("# magicrc\n", encoding="utf-8")

            layout_dir = Path(tmpdir) / "work" / "mag"
            layout_dir.mkdir(parents=True)

            settings = AppSettings()
            settings.tool_paths.magic = "/usr/bin/magic"
            settings.pdk_paths.sky130a = str(sky130a)
            settings.pdk_paths.magic_rc = str(magic_rc)

            with mock.patch.dict(os.environ, {}, clear=True):
                spec = MagicLaunchBuilder(settings).build(str(layout_dir))

        self.assertEqual(spec.command, ["/usr/bin/magic", "-rcfile", str(magic_rc.resolve())])
        self.assertEqual(spec.cwd, str(layout_dir.resolve()))
        self.assertEqual(spec.env["PDK_ROOT"], str(sky130a.parent))
        self.assertEqual(spec.env["SKY130A"], str(sky130a))

    def test_build_opens_mag_file_by_cell_name_in_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mag_path = Path(tmpdir) / "layout" / "tt_um_demo.mag"
            mag_path.parent.mkdir(parents=True)
            mag_path.write_text("magic\n", encoding="utf-8")

            settings = AppSettings()
            settings.tool_paths.magic = "magic"

            with mock.patch.dict(os.environ, {}, clear=True):
                spec = MagicLaunchBuilder(settings).build(str(mag_path))

        self.assertEqual(spec.command, ["magic", "tt_um_demo"])
        self.assertEqual(spec.cwd, str(mag_path.parent.resolve()))


if __name__ == "__main__":
    unittest.main()
