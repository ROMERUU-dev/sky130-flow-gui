"""Waveform viewer widget using pyqtgraph."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget
import pyqtgraph as pg


class WaveformViewer(QWidget):
    """Waveform viewer ready for real parsed ngspice signals."""

    def __init__(self) -> None:
        super().__init__()
        self.plot = pg.PlotWidget(title="Waveform Viewer")
        self.plot.showGrid(x=True, y=True)
        self.signal_select = QComboBox()
        self.signal_select.currentTextChanged.connect(self._render_selected)
        self.empty_label = QLabel("Sin datos de simulación todavía")

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Signal:"))
        row.addWidget(self.signal_select)
        layout.addLayout(row)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.plot)

        self._signals: dict[str, tuple[list[float], list[float]]] = {}
        self.plot.setLabel("bottom", "Time")
        self.plot.setLabel("left", "Value")
        self.plot.hide()

    def set_signals(self, signals: dict[str, tuple[list[float], list[float]]]) -> None:
        """Load parsed real signals."""
        self._signals = signals
        self.signal_select.clear()
        self.signal_select.addItems(self._signals.keys())
        if self._signals:
            self.empty_label.hide()
            self.plot.show()
            self._render_selected(self.signal_select.currentText())
        else:
            self.plot.clear()
            self.plot.hide()
            self.empty_label.show()

    def _render_selected(self, name: str) -> None:
        self.plot.clear()
        if not name or name not in self._signals:
            return
        x, y = self._signals[name]
        self.plot.setTitle(f"Waveform Viewer · {name}")
        self.plot.plot(x, y, pen=pg.mkPen("#00d4ff", width=2))
