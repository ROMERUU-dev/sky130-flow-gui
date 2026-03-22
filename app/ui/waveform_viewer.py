"""Simple waveform viewer widget using pyqtgraph."""

from __future__ import annotations

import random

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget
import pyqtgraph as pg


class WaveformViewer(QWidget):
    """MVP waveform viewer with selectable fake traces + ready extension hook."""

    def __init__(self) -> None:
        super().__init__()
        self.plot = pg.PlotWidget(title="Waveform Viewer")
        self.plot.showGrid(x=True, y=True)
        self.signal_select = QComboBox()
        self.signal_select.currentTextChanged.connect(self._render_selected)

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Signal:"))
        row.addWidget(self.signal_select)
        layout.addLayout(row)
        layout.addWidget(self.plot)

        self._signals: dict[str, tuple[list[float], list[float]]] = {}
        self.load_dummy_data()

    def load_dummy_data(self) -> None:
        """Used if no parsed raw file is available yet."""
        x = [n * 1e-9 for n in range(200)]
        self._signals = {
            "v(out)": (x, [1.2 * (n % 40) / 40 for n in range(200)]),
            "v(in)": (x, [0.8 + 0.1 * random.random() for _ in range(200)]),
            "i(vdd)": (x, [0.001 + 0.0003 * random.random() for _ in range(200)]),
        }
        self.signal_select.clear()
        self.signal_select.addItems(self._signals.keys())
        self._render_selected(self.signal_select.currentText())

    def set_signals(self, signals: dict[str, tuple[list[float], list[float]]]) -> None:
        """Load parsed real signals."""
        self._signals = signals
        self.signal_select.clear()
        self.signal_select.addItems(self._signals.keys())
        self._render_selected(self.signal_select.currentText())

    def _render_selected(self, name: str) -> None:
        self.plot.clear()
        if not name or name not in self._signals:
            return
        x, y = self._signals[name]
        self.plot.plot(x, y, pen=pg.mkPen("#00d4ff", width=2))
