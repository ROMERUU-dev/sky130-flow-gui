"""Tests for environment diagnostics."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.qt_stubs import install_qtcore_stub

install_qtcore_stub()

from app.core.env_validator import EnvValidator
from app.core.python_env import PythonEnvironmentManager
from app.core.settings_manager import AppSettings


def _stat_owned_by(target: Path, uid: int):
    """Return a ``Path.stat`` replacement that reports ``target`` as owned by ``uid``."""
    original_stat = Path.stat

    def fake_stat(path_obj: Path, *args, **kwargs):
        base = original_stat(path_obj, *args, **kwargs)
        if path_obj == target:
            return SimpleNamespace(
                st_uid=uid,
                st_mode=base.st_mode,
                st_ino=base.st_ino,
                st_dev=base.st_dev,
                st_nlink=base.st_nlink,
                st_gid=base.st_gid,
                st_size=base.st_size,
                st_atime=base.st_atime,
                st_mtime=base.st_mtime,
                st_ctime=base.st_ctime,
            )
        return base

    return fake_stat


class EnvValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = EnvValidator()
        self.settings = AppSettings()

    def test_netgen_alias_is_reported_as_valid(self) -> None:
        with mock.patch.object(
            self.validator,
            "_resolve_command",
            side_effect=lambda candidate: None if candidate == "netgen" else ("netgen-lvs", "/usr/bin/netgen-lvs"),
        ), mock.patch.object(
            self.validator,
            "_query_version",
            return_value="netgen-lvs 1.5.270",
        ), mock.patch.object(
            self.validator,
            "_find_sky130a",
            return_value=None,
        ), mock.patch.object(
            self.validator,
            "_detect_python_environment",
            return_value=mock.Mock(problems=[], requirements_ok=True, venv_exists=True, message="ok"),
        ), mock.patch.object(
            self.validator,
            "_detect_gui_dependencies",
            return_value=mock.Mock(missing_required=[], missing_recommended=[], checked=True, message="ok"),
        ):
            diagnosis = self.validator.diagnose(self.settings, lang="en")

        self.assertEqual(diagnosis.tools["netgen"].status, "alias")
        self.assertEqual(diagnosis.tools["netgen"].found_binary, "netgen-lvs")
        self.assertIn("not missing", diagnosis.tools["netgen"].message)

    def test_pdk_incomplete_is_not_reported_as_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sky130a = Path(tmpdir) / "pdk" / "sky130A"
            (sky130a / "libs.tech" / "magic").mkdir(parents=True)
            self.settings.pdk_paths.pdk_root = str(Path(tmpdir) / "pdk")

            with mock.patch.dict(os.environ, {}, clear=True):
                pdk = self.validator._detect_pdk(self.settings, lang="en")

        self.assertTrue(pdk.found)
        self.assertEqual(pdk.status, "incomplete")
        self.assertIn("libs.tech/netgen", pdk.missing_subdirs)

    def test_pdk_reports_magic_techfile_version_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sky130a = Path(tmpdir) / "pdk" / "sky130A"
            for relative in (
                "libs.tech/magic",
                "libs.tech/netgen",
                "libs.tech/klayout",
                "libs.tech/ngspice",
                "libs.tech/xschem",
            ):
                (sky130a / relative).mkdir(parents=True)
            (sky130a / "libs.tech" / "magic" / "sky130A.tech").write_text(
                "tech\nversion 8.3.411\n",
                encoding="utf-8",
            )
            self.settings.pdk_paths.pdk_root = str(Path(tmpdir) / "pdk")

            with mock.patch.dict(os.environ, {}, clear=True):
                pdk = self.validator._detect_pdk(
                    self.settings,
                    lang="en",
                    magic_version="Magic 8.3 revision 105 - Compiled on Mon, 06 Dec 2021 22:32:27 +0200.",
                )

        self.assertTrue(pdk.found)
        self.assertEqual(pdk.status, "incompatible")
        self.assertIn("requires Magic 8.3.411", pdk.message)
        self.assertIn("Magic 8.3.105 was detected", pdk.message)

    def test_foreign_owned_user_venv_is_reported_as_permission_error(self) -> None:
        """A venv the desktop user cannot write to must not be reported as ready."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_home = Path(tmpdir) / "data"
            venv_dir = data_home / "sky130-flow-gui" / "venv"
            (venv_dir / "bin").mkdir(parents=True)
            (venv_dir / "bin" / "python").write_text("", encoding="utf-8")
            repo_root = Path(tmpdir) / "app-root"
            repo_root.mkdir()
            (repo_root / "requirements.txt").write_text("PySide6\npyqtgraph\n", encoding="utf-8")
            self.validator.repo_root = repo_root

            manager = PythonEnvironmentManager(
                repo_root,
                environ={"XDG_DATA_HOME": str(data_home), "PATH": os.environ.get("PATH", "")},
                system_python=sys.executable,
            )
            with mock.patch.object(Path, "stat", _stat_owned_by(venv_dir, uid=0)), mock.patch(
                "os.access", return_value=False
            ):
                status = manager.diagnose()

        self.assertTrue(status.venv_exists)
        self.assertEqual(status.status, "permission_error")
        self.assertFalse(status.ready)

    def test_magic_usage_text_is_not_stored_as_a_version(self) -> None:
        """Magic 8.3.6xx answers `-version` with usage text and exit code 0."""
        usage = (
            "Unknown option: '-version'\n"
            "Usage:  magic [-g gPort] [-d devType] [-m monType]\n"
        )
        self.assertEqual(EnvValidator._clean_version_output(usage), "")

    def test_ngspice_banner_separator_is_skipped(self) -> None:
        banner = "******\n** ngspice-45.2 : Circuit level simulation program\n"
        self.assertEqual(
            EnvValidator._clean_version_output(banner),
            "** ngspice-45.2 : Circuit level simulation program",
        )

    def test_magic_long_option_is_probed_before_the_rejected_short_one(self) -> None:
        from app.core.env_validator import TOOL_VERSION_ARGS

        self.assertEqual(TOOL_VERSION_ARGS["magic"][0], ("--version",))

    def test_distro_netgen_is_flagged_against_the_manifest_floor(self) -> None:
        detected = "Netgen 1.5.133 compiled on Thu Dec  1 22:32:11 UTC 2022"
        self.assertTrue(EnvValidator._is_outdated(detected, "1.5.200"))
        self.assertFalse(EnvValidator._is_outdated("Netgen 1.5.323", "1.5.200"))

    def test_outdated_check_is_silent_without_a_usable_version(self) -> None:
        self.assertFalse(EnvValidator._is_outdated("", "1.5.200"))
        self.assertFalse(EnvValidator._is_outdated("Netgen 1.5.323", ""))

    def test_netgen_version_probe_uses_batch_quit(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return SimpleNamespace(returncode=0, stdout="Netgen 1.5.133\n", stderr="")

        with mock.patch("subprocess.run", side_effect=fake_run):
            version = self.validator._query_version("netgen", "/usr/bin/netgen-lvs")

        self.assertEqual(version, "Netgen 1.5.133")
        self.assertEqual(calls, [["/usr/bin/netgen-lvs", "-batch", "quit"]])

    def test_magic_version_probe_prefers_the_long_option(self) -> None:
        """`magic --version` prints the version and exits without opening a window."""
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return SimpleNamespace(returncode=0, stdout="8.3.684\n", stderr="")

        with mock.patch("subprocess.run", side_effect=fake_run):
            version = self.validator._query_version("magic", "/usr/bin/magic")

        self.assertEqual(version, "8.3.684")
        self.assertEqual(calls, [["/usr/bin/magic", "--version"]])

    def test_magic_falls_back_to_noninteractive_flags_on_older_builds(self) -> None:
        """Older Magic builds reject `--version`, so the probe keeps trying."""
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[1:] == ["--version"]:
                return SimpleNamespace(returncode=0, stdout="Unknown option: '--version'\nUsage:  magic\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="Magic 8.3 revision 452\n", stderr="")

        with mock.patch("subprocess.run", side_effect=fake_run):
            version = self.validator._query_version("magic", "/usr/bin/magic")

        self.assertEqual(version, "Magic 8.3 revision 452")
        self.assertEqual(calls[0], ["/usr/bin/magic", "--version"])
        self.assertIn("-noconsole", calls[1])


if __name__ == "__main__":
    unittest.main()
