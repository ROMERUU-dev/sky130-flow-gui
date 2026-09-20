from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.python_env import CommandResult, PythonEnvironmentManager, user_data_home, venv_path


class PythonPathTests(unittest.TestCase):
    def test_xdg_data_home(self):
        self.assertEqual(user_data_home({"XDG_DATA_HOME": "/tmp/data"}, Path("/home/anyone")), Path("/tmp/data"))

    def test_home_fallback(self):
        self.assertEqual(user_data_home({}, Path("/home/alice")), Path("/home/alice/.local/share"))

    def test_no_username_is_embedded(self):
        self.assertEqual(venv_path({}, Path("/srv/users/different")), Path("/srv/users/different/.local/share/sky130-flow-gui/venv"))

    def test_relative_xdg_is_rejected(self):
        with self.assertRaises(ValueError):
            user_data_home({"XDG_DATA_HOME": "relative"}, Path("/home/alice"))


class PythonDiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "requirements.txt").write_text("PySide6>=6.7\npyqtgraph>=0.13\n")
        self.home = self.root / "home"
        self.manager = PythonEnvironmentManager(self.root, environ={"PATH": "/usr/bin"}, home=self.home,
                                                system_python="/usr/bin/python3")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def ok(command, output=""):
        return CommandResult(list(command), 0, output, "")

    def system_probe(self):
        """The single probe run against the system interpreter."""
        return self.ok([], "Python 3.14.4\nx86_64\n")

    def venv_report(self, **overrides):
        """The single JSON probe run inside the virtual environment."""
        report = {"prefix": str(self.manager.path), "version": "3.14.4", "pip": "25.0",
                  "packages": {"PySide6": "6.9.0", "pyqtgraph": "0.13.7"}, "error": ""}
        report.update(overrides)
        return self.ok([], json.dumps(report))

    def create_venv(self):
        (self.manager.path / "bin").mkdir(parents=True)
        (self.manager.path / "bin/python").touch()

    def test_python_detection(self):
        with patch.object(self.manager, "_run", side_effect=[self.system_probe(), self.ok([])]):
            status = self.manager.diagnose()
        self.assertEqual(status.system_version, "Python 3.14.4")
        self.assertEqual(status.architecture, "x86_64")

    def test_missing_venv(self):
        with patch.object(self.manager, "_run", side_effect=[self.system_probe(), self.ok([])]):
            self.assertEqual(self.manager.diagnose().status, "venv_missing")

    def test_existing_venv_with_valid_imports(self):
        self.create_venv()
        results = [self.system_probe(), self.venv_report()]
        with patch.object(self.manager, "_run", side_effect=results):
            status = self.manager.diagnose()
        self.assertTrue(status.ready)
        self.assertEqual(status.packages["PySide6"], "6.9.0")

    def test_missing_package_is_distinguished(self):
        self.create_venv()
        results = [self.system_probe(),
                   self.venv_report(error="ModuleNotFoundError: No module named 'PySide6'")]
        with patch.object(self.manager, "_run", side_effect=results):
            status = self.manager.diagnose()
        self.assertEqual(status.status, "packages_missing")
        self.assertEqual(status.missing_packages, ["PySide6"])

    def test_native_import_error_is_distinguished(self):
        self.create_venv()
        results = [self.system_probe(),
                   self.venv_report(error="ImportError: libxcb-cursor.so.0: cannot open shared object file")]
        with patch.object(self.manager, "_run", side_effect=results):
            self.assertEqual(self.manager.diagnose().status, "import_error")

    def test_legacy_venv_is_reported_but_not_used(self):
        (self.root / ".venv").mkdir()
        with patch.object(self.manager, "_run", side_effect=[self.system_probe(), self.ok([])]):
            status = self.manager.diagnose()
        self.assertEqual(status.legacy_path, str(self.root / ".venv"))
        self.assertEqual(status.venv_path, str(self.manager.path))

    def test_missing_venv_module_is_distinguished(self):
        failure = CommandResult([], 1, "", "No module named venv")
        with patch.object(self.manager, "_run", side_effect=[self.system_probe(), failure]):
            self.assertEqual(self.manager.diagnose().status, "venv_module_missing")

    def test_permission_error(self):
        self.create_venv()
        real_access = os.access
        with patch("app.core.python_env.os.access", side_effect=lambda path, mode: False if Path(path) == self.manager.path else real_access(path, mode)), \
             patch.object(self.manager, "_run", side_effect=[self.system_probe()]):
            self.assertEqual(self.manager.diagnose().status, "permission_error")

    def test_foreign_prefix_is_reported_as_corrupt(self):
        """A venv whose interpreter reports another prefix must not be trusted."""
        self.create_venv()
        results = [self.system_probe(), self.venv_report(prefix="/usr")]
        with patch.object(self.manager, "_run", side_effect=results):
            self.assertEqual(self.manager.diagnose().status, "venv_corrupt")

    def test_unreadable_probe_output_is_reported_as_corrupt(self):
        self.create_venv()
        results = [self.system_probe(), self.ok([], "not json at all")]
        with patch.object(self.manager, "_run", side_effect=results):
            self.assertEqual(self.manager.diagnose().status, "venv_corrupt")

    def test_missing_pip_is_distinguished(self):
        self.create_venv()
        results = [self.system_probe(), self.venv_report(pip="")]
        with patch.object(self.manager, "_run", side_effect=results):
            self.assertEqual(self.manager.diagnose().status, "pip_missing")

    def test_root_repair_is_refused(self):
        with patch("app.core.python_env.os.geteuid", return_value=0):
            with self.assertRaises(PermissionError):
                self.manager.repair()


if __name__ == "__main__":
    unittest.main()
