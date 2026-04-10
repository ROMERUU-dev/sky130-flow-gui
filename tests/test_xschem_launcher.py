"""Tests for xschem launch context construction."""

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

from app.core.settings_manager import AppSettings
from app.core.xschem_launcher import XschemLaunchBuilder


class XschemLaunchBuilderTest(unittest.TestCase):
    def test_build_injects_sky130_context_and_rcfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sky130a = Path(tmpdir) / "pdk" / "sky130A"
            xschem_dir = sky130a / "libs.tech" / "xschem"
            xschem_dir.mkdir(parents=True)
            (xschem_dir / "xschemrc").write_text("# rc\n", encoding="utf-8")
            (sky130a / "libs.tech" / "combined").mkdir(parents=True)
            (sky130a / "libs.ref" / "sky130_fd_sc_hd" / "spice").mkdir(parents=True)

            project = Path(tmpdir) / "work" / "demo.sch"
            project.parent.mkdir(parents=True)
            project.write_text("v {}", encoding="utf-8")

            settings = AppSettings()
            settings.tool_paths.xschem = "/usr/bin/xschem"
            settings.pdk_paths.sky130a = str(sky130a)

            with mock.patch.dict(os.environ, {}, clear=True):
                spec = XschemLaunchBuilder(settings).build(str(project))

        self.assertEqual(spec.command[0], "/usr/bin/xschem")
        self.assertEqual(spec.command[1:3], ["--rcfile", str(xschem_dir / "xschemrc")])
        self.assertEqual(spec.command[-1], str(project.resolve()))
        self.assertEqual(spec.cwd, str(project.parent.resolve()))
        self.assertEqual(spec.env["PDK_ROOT"], str(sky130a.parent))
        self.assertEqual(spec.env["SKY130A"], str(sky130a))
        self.assertEqual(spec.env["SKYWATER_MODELS"], str(sky130a / "libs.tech" / "combined"))
        self.assertEqual(
            spec.env["SKYWATER_STDCELLS"],
            str(sky130a / "libs.ref" / "sky130_fd_sc_hd" / "spice"),
        )

    def test_build_falls_back_to_detected_pdk_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdk_root = Path(tmpdir) / "pdk"
            sky130a = pdk_root / "sky130A"
            xschem_dir = sky130a / "libs.tech" / "xschem"
            xschem_dir.mkdir(parents=True)
            (xschem_dir / "xschemrc").write_text("# rc\n", encoding="utf-8")

            settings = AppSettings()
            settings.tool_paths.xschem = "xschem"

            with mock.patch.dict(os.environ, {"PDK_ROOT": str(pdk_root)}, clear=True):
                spec = XschemLaunchBuilder(settings).build()

        self.assertEqual(spec.cwd, str(xschem_dir))
        self.assertEqual(spec.env["PDK_ROOT"], str(pdk_root))
        self.assertEqual(spec.env["SKY130A"], str(sky130a))
        self.assertEqual(spec.command[:3], ["xschem", "--rcfile", str(xschem_dir / "xschemrc")])

    def test_build_uses_project_directory_as_cwd_without_passing_it_as_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sky130a = Path(tmpdir) / "pdk" / "sky130A"
            xschem_dir = sky130a / "libs.tech" / "xschem"
            xschem_dir.mkdir(parents=True)
            (xschem_dir / "xschemrc").write_text("# rc\n", encoding="utf-8")

            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()

            settings = AppSettings()
            settings.tool_paths.xschem = "xschem"
            settings.pdk_paths.sky130a = str(sky130a)

            with mock.patch.dict(os.environ, {}, clear=True):
                spec = XschemLaunchBuilder(settings).build(str(project_dir))

        self.assertEqual(spec.cwd, str(project_dir.resolve()))
        self.assertEqual(spec.command, ["xschem", "--rcfile", str(xschem_dir / "xschemrc")])


if __name__ == "__main__":
    unittest.main()
