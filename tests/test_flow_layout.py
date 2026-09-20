"""Tests for the wrapping control-row layout."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from app.ui.flow_layout import FlowLayout


class FlowLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _row(self, count: int, width: int = 120) -> tuple[QWidget, FlowLayout, list[QPushButton]]:
        host = QWidget()
        layout = FlowLayout(host, spacing=8)
        buttons = []
        for index in range(count):
            button = QPushButton(f"b{index}")
            button.setFixedSize(width, 30)
            layout.addWidget(button)
            buttons.append(button)
        return host, layout, buttons

    def test_minimum_width_is_one_item_not_the_sum(self) -> None:
        """A QHBoxLayout would report 10 * 120; that is what forced page scroll."""
        host, layout, _buttons = self._row(10)

        self.assertLess(layout.minimumSize().width(), 200)

    def test_items_wrap_onto_a_second_line_when_narrow(self) -> None:
        host, layout, buttons = self._row(6)
        host.resize(400, 200)
        layout.setGeometry(QRect(0, 0, 400, 200))

        tops = {button.geometry().top() for button in buttons}

        self.assertGreater(len(tops), 1)

    def test_items_stay_on_one_line_when_wide(self) -> None:
        host, layout, buttons = self._row(4)
        host.resize(1200, 200)
        layout.setGeometry(QRect(0, 0, 1200, 200))

        tops = {button.geometry().top() for button in buttons}

        self.assertEqual(len(tops), 1)

    def test_height_for_width_grows_as_the_row_narrows(self) -> None:
        _host, layout, _buttons = self._row(6)

        self.assertGreater(layout.heightForWidth(300), layout.heightForWidth(1200))

    def test_items_can_be_taken_back_out(self) -> None:
        _host, layout, _buttons = self._row(3)

        self.assertEqual(layout.count(), 3)
        self.assertIsNotNone(layout.takeAt(0))
        self.assertEqual(layout.count(), 2)
        self.assertIsNone(layout.takeAt(99))


class WaveformViewerWidthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_viewer_does_not_impose_a_page_wide_minimum(self) -> None:
        """Thirteen controls in a fixed row needed 1174px on a 1536px desktop."""
        from app.ui.waveform_viewer import WaveformViewer

        viewer = WaveformViewer("es")

        self.assertLess(viewer.minimumSizeHint().width(), 600)


if __name__ == "__main__":
    unittest.main()
