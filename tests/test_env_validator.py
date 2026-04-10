"""Tests for environment diagnostics."""

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

from app.core.env_validator import EnvValidator
from app.core.settings_manager import AppSettings


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

    def test_root_owned_venv_problem_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            venv_bin = repo_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            (venv_bin / "python").write_text("", encoding="utf-8")
            (repo_root / "requirements.txt").write_text("PySide6\npyqtgraph\n", encoding="utf-8")
            self.validator.repo_root = repo_root

            original_stat = Path.stat

            def fake_stat(path_obj: Path, *args, **kwargs):
                if path_obj == repo_root / ".venv":
                    base = original_stat(path_obj, *args, **kwargs)
                    return SimpleNamespace(
                        st_uid=0,
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
                return original_stat(path_obj, *args, **kwargs)

            with mock.patch("pathlib.Path.stat", new=fake_stat), mock.patch.object(
                self.validator,
                "_check_python_requirements",
                return_value=True,
            ):
                diagnosis = self.validator._detect_python_environment(lang="en")

        self.assertTrue(diagnosis.venv_exists)
        self.assertTrue(any("belongs to root" in problem for problem in diagnosis.problems))


if __name__ == "__main__":
    unittest.main()
