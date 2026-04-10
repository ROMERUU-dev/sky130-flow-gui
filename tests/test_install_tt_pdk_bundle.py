"""Regression tests for the bundled PDK installer script."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


class InstallTTPdkBundleScriptTest(unittest.TestCase):
    def test_script_bootstraps_repo_root_for_app_imports(self) -> None:
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "install_tt_pdk_bundle.py"
        repo_root = str(script_path.resolve().parents[1])
        original_sys_path = list(sys.path)
        original_cwd = os.getcwd()

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.chdir(tmpdir)
                sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != Path(repo_root).resolve()]
                spec = importlib.util.spec_from_file_location("tt_pdk_bundle_installer_test", script_path)
                self.assertIsNotNone(spec)
                module = importlib.util.module_from_spec(spec)
                assert spec.loader is not None
                spec.loader.exec_module(module)
                self.assertEqual(Path(module.REPO_ROOT).resolve(), Path(repo_root).resolve())
                self.assertEqual(Path(sys.path[0]).resolve(), Path(repo_root).resolve())
        finally:
            os.chdir(original_cwd)
            sys.path[:] = original_sys_path


if __name__ == "__main__":
    unittest.main()
