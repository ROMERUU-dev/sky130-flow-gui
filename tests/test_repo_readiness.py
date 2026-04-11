"""Tests for local GitHub/Tiny Tapeout readiness checks."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.repo_readiness import RepoReadinessChecker


class RepoReadinessCheckerTest(unittest.TestCase):
    def test_generated_template_shape_has_no_metadata_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs").mkdir()
            (root / "src").mkdir()
            (root / "test").mkdir()
            (root / "gds").mkdir()
            (root / "lef").mkdir()
            (root / "runs" / "extraction").mkdir(parents=True)
            (root / "runs" / "lvs").mkdir(parents=True)
            (root / "runs" / "antenna").mkdir(parents=True)
            (root / "README.md").write_text("# Demo\n")
            (root / "docs" / "info.md").write_text("# Demo\n")
            (root / "src" / "project.v").write_text("module tt_um_demo; endmodule\n")
            (root / ".gitignore").write_text("runs/\n")
            (root / "info.yaml").write_text(
                "\n".join(
                    [
                        "yaml_version: 6",
                        "project:",
                        '  title: "Demo"',
                        '  author: "Ada"',
                        '  discord: ""',
                        '  description: "Demo project"',
                        "  language: Verilog",
                        "  clock_hz: 0",
                        "  tiles: 1x2",
                        "  analog_pins: 2",
                        "  uses_3v3: false",
                        "  top_module: tt_um_demo",
                        "  source_files:",
                        "    - project.v",
                        "",
                    ]
                )
            )

            checks = RepoReadinessChecker().check(root)
            errors = [check for check in checks if check.status == "error"]
            self.assertEqual([], errors)

    def test_missing_source_file_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs").mkdir()
            (root / "src").mkdir()
            (root / "test").mkdir()
            (root / "README.md").write_text("# Demo\n")
            (root / "docs" / "info.md").write_text("# Demo\n")
            (root / "info.yaml").write_text(
                "\n".join(
                    [
                        "yaml_version: 6",
                        "project:",
                        '  title: "Demo"',
                        '  author: "Ada"',
                        '  description: "Demo project"',
                        "  tiles: 1x2",
                        "  analog_pins: 2",
                        "  uses_3v3: false",
                        "  top_module: tt_um_demo",
                        "  source_files:",
                        "    - missing.v",
                        "",
                    ]
                )
            )

            checks = RepoReadinessChecker().check(root)
            self.assertTrue(any(check.status == "error" and "missing.v" in check.detail for check in checks))


if __name__ == "__main__":
    unittest.main()
