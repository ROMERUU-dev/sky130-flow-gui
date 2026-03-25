"""Focused tests for Simulation tab EM debug behavior."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    from app.core.output_manager import OutputPaths
    from app.core.settings_manager import AppSettings
    from app.ui.simulation_tab import SimulationTab
    PYSIDE6_AVAILABLE = True
except ImportError:
    QApplication = None
    OutputPaths = None
    AppSettings = None
    SimulationTab = None
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this test environment")
class SimulationTabEmDebugTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _make_outputs(self, root: str) -> OutputPaths:
        base = Path(root) / "workspace"
        runs = base / "runs"
        logs = runs / "logs" / "run_001"
        results = runs / "results" / "run_001"
        logs.mkdir(parents=True, exist_ok=True)
        results.mkdir(parents=True, exist_ok=True)
        return OutputPaths(
            base=base.resolve(),
            runs=runs.resolve(),
            logs=logs.resolve(),
            results=results.resolve(),
            lvs=(runs / "lvs").resolve(),
            extraction=(runs / "extraction").resolve(),
            antenna=(runs / "antenna").resolve(),
        )

    def test_prepare_em_followup_creates_netlist_and_json_in_debug_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = self._make_outputs(temp_dir)
            tab = SimulationTab(AppSettings(), lambda: outputs)
            tab.debug_em_only_checkbox.setChecked(True)

            generated_netlist = os.path.join(outputs.results, "run.spice")
            with open(generated_netlist, "w", encoding="utf-8") as handle:
                handle.write("V1 vpwr 0 1.8\nR1 vpwr out 1k\n.tran 1n 5n\n.end\n")

            em_run = tab._prepare_em_followup(os.path.abspath(generated_netlist), outputs)

            self.assertIsNotNone(em_run)
            self.assertTrue(em_run["debug_only"])
            self.assertTrue(os.path.exists(em_run["netlist_path"]))
            self.assertTrue(os.path.exists(em_run["metadata_path"]))
            self.assertTrue(str(em_run["netlist_path"]).endswith("run_001__emprobe.spice"))
            self.assertTrue(str(em_run["metadata_path"]).endswith("run_001__emprobe_map.json"))

    def test_debug_mode_does_not_run_ngspice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = self._make_outputs(temp_dir)
            tab = SimulationTab(AppSettings(), lambda: outputs)
            tab.file_view.setPlainText("V1 vpwr 0 1.8\nR1 vpwr out 1k\n.tran 1n 5n\n.end\n")
            tab.debug_em_only_checkbox.setChecked(True)
            tab.runner.run = Mock()
            with patch("app.ui.simulation_tab.QMessageBox.information"):
                tab.run()

            tab.runner.run.assert_not_called()
            self.assertIsNotNone(tab._pending_em_run)
            self.assertTrue(tab._pending_em_run["debug_only"])

    def test_em_option_state_enables_controls_for_debug_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = self._make_outputs(temp_dir)
            tab = SimulationTab(AppSettings(), lambda: outputs)

            tab.generate_em_checkbox.setChecked(False)
            tab.debug_em_only_checkbox.setChecked(False)
            tab._sync_em_options_state()
            self.assertFalse(tab.em_project_mode.isEnabled())
            self.assertFalse(tab.keep_em_files_checkbox.isEnabled())

            tab.debug_em_only_checkbox.setChecked(True)
            tab._sync_em_options_state()
            self.assertTrue(tab.em_project_mode.isEnabled())
            self.assertTrue(tab.keep_em_files_checkbox.isEnabled())

    def test_internal_net_inspector_populates_connected_elements_for_selected_net(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = self._make_outputs(temp_dir)
            tab = SimulationTab(AppSettings(), lambda: outputs)
            tab.file_view.setPlainText(
                "\n".join(
                    [
                        "* Internal net connectivity test",
                        "X1 in1 p1 vgnd cell_a",
                        "XC_LOAD p1 0 cap_load",
                        "R1 p1 p2 10k",
                        ".subckt cell_a a y vgnd",
                        "RDRV a y 1k",
                        ".ends",
                        ".subckt cap_load a b",
                        "C1 a b 10p",
                        ".ends",
                        ".end",
                    ]
                )
            )

            tab._refresh_internal_net_inspector()
            index = tab.internal_net_combo.findData("p1")
            self.assertGreaterEqual(index, 0)
            tab.internal_net_combo.setCurrentIndex(index)
            tab._populate_internal_net_table()

            self.assertEqual(tab.internal_net_combo.currentText(), "p1")
            self.assertEqual(tab.internal_connections_table.rowCount(), 3)
            instance_names = {
                tab.internal_connections_table.item(row, 0).text()
                for row in range(tab.internal_connections_table.rowCount())
            }
            self.assertEqual(instance_names, {"X1", "XC_LOAD", "R1"})


if __name__ == "__main__":
    unittest.main()
