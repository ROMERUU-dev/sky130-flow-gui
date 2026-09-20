"""Tests for the netlist editor's undo, revert and save behaviour."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.output_manager import OutputManager
from app.core.settings_manager import AppSettings
from app.ui.simulation_tab import SimulationTab

ORIGINAL = "* original\nV1 in 0 1\nR1 in 0 1k\n.tran 1n 1u\n.end\n"


class NetlistEditorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.netlist = self.root / "design.spice"
        self.netlist.write_text(ORIGINAL, encoding="utf-8")
        outputs = OutputManager().resolve(str(self.root))
        self.tab = SimulationTab(AppSettings(), lambda: outputs)
        self.tab.load_netlist_path(str(self.netlist))

    def test_a_freshly_loaded_buffer_is_unmodified(self) -> None:
        self.assertFalse(self.tab.editor_is_modified())
        self.assertFalse(self.tab.undo_btn.isEnabled())
        self.assertFalse(self.tab.revert_btn.isEnabled())
        self.assertEqual(self.tab.editor_state.text(), "")

    def test_editing_is_announced_and_enables_undo(self) -> None:
        self.tab.file_view.insertPlainText("* extra\n")

        self.assertTrue(self.tab.editor_is_modified())
        self.assertTrue(self.tab.undo_btn.isEnabled())
        self.assertTrue(self.tab.revert_btn.isEnabled())
        self.assertIn("Editado", self.tab.editor_state.text())

    def test_undo_returns_to_the_loaded_text(self) -> None:
        self.tab.file_view.insertPlainText("* extra\n")

        self.tab.file_view.undo()

        self.assertEqual(self.tab.file_view.toPlainText(), ORIGINAL)
        self.assertFalse(self.tab.editor_is_modified())
        self.assertTrue(self.tab.redo_btn.isEnabled())

    def test_redo_reapplies_the_edit(self) -> None:
        self.tab.file_view.insertPlainText("* extra\n")
        self.tab.file_view.undo()

        self.tab.file_view.redo()

        self.assertTrue(self.tab.editor_is_modified())
        self.assertFalse(self.tab.redo_btn.isEnabled())

    def test_loading_a_file_does_not_leave_undo_reaching_into_it(self) -> None:
        """Undoing past a load would restore a different file's contents."""
        other = self.root / "other.spice"
        other.write_text("* other\n.end\n", encoding="utf-8")

        self.tab.load_netlist_path(str(other))

        self.assertFalse(self.tab.file_view.document().isUndoAvailable())
        self.assertFalse(self.tab.editor_is_modified())

    def test_revert_reloads_from_disk_when_confirmed(self) -> None:
        self.tab.file_view.insertPlainText("* mangled\n")

        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.tab.revert_netlist_editor()

        self.assertEqual(self.tab.file_view.toPlainText(), ORIGINAL)
        self.assertFalse(self.tab.editor_is_modified())

    def test_revert_keeps_the_edits_when_declined(self) -> None:
        self.tab.file_view.insertPlainText("* mangled\n")
        edited = self.tab.file_view.toPlainText()

        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            self.tab.revert_netlist_editor()

        self.assertEqual(self.tab.file_view.toPlainText(), edited)

    def test_editing_never_touches_the_file_on_disk(self) -> None:
        self.tab.file_view.insertPlainText("* mangled\n")

        self.assertEqual(self.netlist.read_text(encoding="utf-8"), ORIGINAL)

    def test_save_as_writes_the_buffer_and_clears_the_modified_mark(self) -> None:
        self.tab.file_view.insertPlainText("* extra\n")
        target = self.root / "copy.spice"

        with mock.patch("app.ui.simulation_tab.QFileDialog.getSaveFileName",
                        return_value=(str(target), "")):
            self.tab.save_netlist_as()

        self.assertIn("* extra", target.read_text(encoding="utf-8"))
        self.assertFalse(self.tab.editor_is_modified())
        # The source file is still untouched.
        self.assertEqual(self.netlist.read_text(encoding="utf-8"), ORIGINAL)

    def test_save_as_does_nothing_when_cancelled(self) -> None:
        self.tab.file_view.insertPlainText("* extra\n")

        with mock.patch("app.ui.simulation_tab.QFileDialog.getSaveFileName", return_value=("", "")):
            self.tab.save_netlist_as()

        self.assertTrue(self.tab.editor_is_modified())

    def test_save_as_refuses_an_empty_buffer(self) -> None:
        self.tab.file_view.setPlainText("   ")

        with mock.patch("app.ui.simulation_tab.QFileDialog.getSaveFileName") as dialog:
            self.tab.save_netlist_as()

        dialog.assert_not_called()

    def test_an_unreadable_file_does_not_wipe_the_buffer(self) -> None:
        self.tab.file_view.insertPlainText("* edits worth keeping\n")
        edited = self.tab.file_view.toPlainText()
        self.tab.netlist_edit.setText(str(self.root / "gone.spice"))

        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.tab.revert_netlist_editor()

        self.assertEqual(self.tab.file_view.toPlainText(), edited)


if __name__ == "__main__":
    unittest.main()
