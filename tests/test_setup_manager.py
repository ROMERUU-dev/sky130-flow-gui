"""Tests for setup manager helpers."""

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
from app.core.setup_manager import SetupManager


class SetupManagerTest(unittest.TestCase):
    def test_detect_reusable_pdk_candidates_prefers_complete_installations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            complete = root / "volare" / "sky130A"
            incomplete = root / "staging" / "sky130A"
            for relative in (
                "libs.tech/magic",
                "libs.tech/netgen",
                "libs.tech/klayout",
                "libs.tech/ngspice",
                "libs.tech/xschem",
            ):
                (complete / relative).mkdir(parents=True, exist_ok=True)
            (incomplete / "libs.tech" / "magic").mkdir(parents=True, exist_ok=True)

            manager = SetupManager()
            with mock.patch.object(
                manager.manifest,
                "channel",
                return_value=SimpleNamespace(pdk_search_roots=(str(root),)),
            ), mock.patch.dict(os.environ, {}, clear=True):
                candidates = manager.detect_reusable_pdk_candidates()

        self.assertEqual(candidates[0].status, "present")
        self.assertEqual(candidates[0].sky130a_path, str(complete.resolve()))
        self.assertEqual(candidates[1].status, "incomplete")

    def test_apply_pdk_candidate_updates_settings_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sky130a = Path(tmpdir) / "pdk" / "sky130A"
            (sky130a / "libs.tech" / "magic").mkdir(parents=True)
            (sky130a / "libs.tech" / "netgen").mkdir(parents=True)
            (sky130a / "libs.tech" / "klayout" / "drc").mkdir(parents=True)
            (sky130a / "libs.tech" / "magic" / "sky130A.magicrc").write_text("", encoding="utf-8")
            (sky130a / "libs.tech" / "netgen" / "sky130A_setup.tcl").write_text("", encoding="utf-8")
            (sky130a / "libs.tech" / "klayout" / "drc" / "sky130A_ant.rb").write_text("", encoding="utf-8")

            settings = AppSettings()
            manager = SetupManager()

            changed = manager.apply_pdk_candidate(settings, str(sky130a))

        self.assertTrue(changed)
        self.assertEqual(settings.pdk_paths.sky130a, str(sky130a.resolve()))
        self.assertEqual(settings.pdk_paths.pdk_root, str(sky130a.resolve().parent))
        self.assertTrue(settings.pdk_paths.magic_rc.endswith("sky130A.magicrc"))

    def test_pdk_install_preflight_reports_target_and_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate = root / "cache" / "sky130A"
            for relative in (
                "libs.tech/magic",
                "libs.tech/netgen",
                "libs.tech/klayout",
                "libs.tech/ngspice",
                "libs.tech/xschem",
            ):
                (candidate / relative).mkdir(parents=True, exist_ok=True)

            manager = SetupManager()
            with mock.patch.object(
                manager.manifest,
                "channel",
                return_value=SimpleNamespace(
                    pdk_search_roots=(str(root / "cache"),),
                    pdk_managed_root=str(root / "managed"),
                    pdk_managed_install_mode="symlink",
                    pdk_minimum_free_gb=1,
                ),
            ), mock.patch("shutil.disk_usage", return_value=SimpleNamespace(free=20 * 1024**3)), mock.patch.dict(os.environ, {}, clear=True):
                preflight = manager.pdk_install_preflight(AppSettings())

        self.assertTrue(preflight.enough_space)
        self.assertEqual(preflight.existing_status, "missing")
        self.assertEqual(preflight.selected_candidate, str(candidate.resolve()))

    def test_install_managed_pdk_creates_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate = root / "cache" / "sky130A"
            for relative in (
                "libs.tech/magic",
                "libs.tech/netgen",
                "libs.tech/klayout/drc",
                "libs.tech/ngspice",
                "libs.tech/xschem",
            ):
                (candidate / relative).mkdir(parents=True, exist_ok=True)
            (candidate / "libs.tech" / "magic" / "sky130A.magicrc").write_text("", encoding="utf-8")
            (candidate / "libs.tech" / "netgen" / "sky130A_setup.tcl").write_text("", encoding="utf-8")
            (candidate / "libs.tech" / "klayout" / "drc" / "sky130A_ant.rb").write_text("", encoding="utf-8")

            manager = SetupManager()
            settings = AppSettings()
            with mock.patch.object(
                manager.manifest,
                "channel",
                return_value=SimpleNamespace(
                    pdk_search_roots=(str(root / "cache"),),
                    pdk_managed_root=str(root / "managed"),
                    pdk_managed_install_mode="symlink",
                    pdk_minimum_free_gb=1,
                ),
            ), mock.patch("shutil.disk_usage", return_value=SimpleNamespace(free=20 * 1024**3)), mock.patch.dict(os.environ, {}, clear=True):
                result = manager.install_managed_pdk(settings)
                managed_target = root / "managed" / "sky130A"
                self.assertTrue(result.ok)
                self.assertTrue(result.changed)
                self.assertTrue(managed_target.is_symlink())
                self.assertEqual(managed_target.resolve(), candidate.resolve())
                self.assertEqual(settings.pdk_paths.sky130a, str(managed_target.resolve()))

    def test_source_build_preflight_reports_missing_commands_and_candidate_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate = root / "cache" / "sky130A"
            for relative in (
                "libs.tech/magic",
                "libs.tech/netgen",
                "libs.tech/klayout",
                "libs.tech/ngspice",
                "libs.tech/xschem",
            ):
                (candidate / relative).mkdir(parents=True, exist_ok=True)

            manager = SetupManager()
            with mock.patch.object(
                manager.manifest,
                "channel",
                return_value=SimpleNamespace(
                    pdk_search_roots=(str(root / "cache"),),
                    pdk_managed_root=str(root / "managed"),
                    pdk_managed_install_mode="symlink",
                    pdk_minimum_free_gb=1,
                    pdk_source_build_root=str(root / "srcbuild"),
                    pdk_source_build_minimum_free_gb=20,
                    pdk_source_build_required_commands=("git", "autoconf", "tcsh"),
                    pdk_source_build_open_pdks_repo="https://example.com/open_pdks.git",
                    pdk_source_build_open_pdks_ref="1.0.321",
                ),
            ), mock.patch("shutil.disk_usage", return_value=SimpleNamespace(free=40 * 1024**3)), mock.patch(
                "shutil.which",
                side_effect=lambda command: "/usr/bin/" + command if command == "git" else None,
            ), mock.patch.dict(os.environ, {}, clear=True):
                summary = manager.pdk_source_build_preflight(AppSettings())

        self.assertFalse(summary.ready)
        self.assertTrue(summary.has_pinned_source)
        self.assertEqual(summary.missing_commands, ("autoconf", "tcsh"))
        self.assertTrue(summary.reusable_candidate_available)

    def test_pdk_bundle_preflight_reports_disabled_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager = SetupManager()
            with mock.patch.object(
                manager.manifest,
                "channel",
                return_value=SimpleNamespace(
                    pdk_bundle_enabled=False,
                    pdk_bundle_name="tt-pdk-sky130a",
                    pdk_bundle_version="",
                    pdk_bundle_install_root=str(root / "pdk"),
                    pdk_bundle_cache_root=str(root / ".cache" / "pdk"),
                    pdk_bundle_minimum_free_gb=10,
                    pdk_bundle_asset_url="",
                    pdk_bundle_asset_filename="",
                    pdk_bundle_asset_sha256="",
                ),
            ), mock.patch("shutil.disk_usage", return_value=SimpleNamespace(free=40 * 1024**3)):
                summary = manager.pdk_bundle_preflight(AppSettings())

        self.assertFalse(summary.ready)
        self.assertFalse(summary.enabled)
        self.assertEqual(summary.target_status, "missing")

    def test_pdk_bundle_preflight_is_ready_when_asset_and_space_are_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager = SetupManager()
            with mock.patch.object(
                manager.manifest,
                "channel",
                return_value=SimpleNamespace(
                    pdk_bundle_enabled=True,
                    pdk_bundle_name="tt-pdk-sky130a",
                    pdk_bundle_version="0.1.0",
                    pdk_bundle_install_root=str(root / "pdk"),
                    pdk_bundle_cache_root=str(root / ".cache" / "pdk"),
                    pdk_bundle_minimum_free_gb=10,
                    pdk_bundle_asset_url="https://example.invalid/tt-pdk-sky130a.tar.gz",
                    pdk_bundle_asset_filename="tt-pdk-sky130a.tar.gz",
                    pdk_bundle_asset_sha256="deadbeef",
                ),
            ), mock.patch("shutil.disk_usage", return_value=SimpleNamespace(free=40 * 1024**3)):
                summary = manager.pdk_bundle_preflight(AppSettings())

        self.assertTrue(summary.ready)
        self.assertEqual(summary.target_sky130a, str((root / "pdk" / "sky130A")))
        self.assertEqual(summary.bundle_name, "tt-pdk-sky130a")

    def test_pdk_bundle_install_command_uses_current_python(self) -> None:
        manager = SetupManager()

        command = manager.pdk_bundle_install_command()

        self.assertEqual(command[0], sys.executable)
        self.assertTrue(command[1].endswith("scripts/install_tt_pdk_bundle.py"))


if __name__ == "__main__":
    unittest.main()
