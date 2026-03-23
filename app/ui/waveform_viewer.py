"""Waveform viewer widget using pyqtgraph."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import pyqtgraph as pg


class WaveformViewer(QWidget):
    """Waveform viewer ready for real parsed ngspice signals."""

    signal_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.plot = pg.PlotWidget(title="Waveform Viewer")
        self.plot.showGrid(x=True, y=True)
        self.signal_select = QComboBox()
        self.signal_select.currentTextChanged.connect(self._render_selected)
        self.empty_label = QLabel("Sin datos de simulación todavía")
        self.x_scale = QDoubleSpinBox()
        self.y_scale = QDoubleSpinBox()
        self.reset_view_btn = QPushButton("Reset View")
        self.reset_scale_btn = QPushButton("Reset Scale")

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Signal:"))
        controls.addWidget(self.signal_select, 1)
        controls.addWidget(QLabel("X scale:"))
        controls.addWidget(self.x_scale)
        controls.addWidget(QLabel("Y scale:"))
        controls.addWidget(self.y_scale)
        controls.addWidget(self.reset_view_btn)
        controls.addWidget(self.reset_scale_btn)
        layout.addLayout(controls)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.plot)

        self._signals: dict[str, tuple[list[float], list[float]]] = {}
        self._base_x_range: tuple[float, float] | None = None
        self._base_y_range: tuple[float, float] | None = None
        self.plot.setLabel("bottom", "Time")
        self.plot.setLabel("left", "Value")
        self.plot.hide()
        self.plot.setMouseEnabled(x=True, y=True)

        for control in (self.x_scale, self.y_scale):
            control.setDecimals(2)
            control.setRange(0.1, 10.0)
            control.setSingleStep(0.1)
            control.setValue(1.0)
            control.setAlignment(Qt.AlignRight)

        self.x_scale.valueChanged.connect(self._apply_scale)
        self.y_scale.valueChanged.connect(self._apply_scale)
        self.reset_view_btn.clicked.connect(self._reset_view)
        self.reset_scale_btn.clicked.connect(self._reset_scale)
        self.signal_select.currentTextChanged.connect(self.signal_changed.emit)

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
            self._base_x_range = None
            self._base_y_range = None

    def _render_selected(self, name: str) -> None:
        self.plot.clear()
        if not name or name not in self._signals:
            return
        x, y = self._signals[name]
        self.plot.setTitle(f"Waveform Viewer · {name}")
        self._apply_axis_labels(name)
        self.plot.plot(x, y, pen=pg.mkPen("#00d4ff", width=2))
        self._capture_base_ranges(x, y)
        self._apply_scale()

    def _capture_base_ranges(self, x: list[float], y: list[float]) -> None:
        if not x or not y:
            self._base_x_range = None
            self._base_y_range = None
            return

        self._base_x_range = (min(x), max(x))
        y_min = min(y)
        y_max = max(y)
        if y_min == y_max:
            pad = abs(y_min) * 0.05 or 1.0
            y_min -= pad
            y_max += pad
        self._base_y_range = (y_min, y_max)

    def _apply_scale(self) -> None:
        if not self._base_x_range or not self._base_y_range:
            return

        x_min, x_max = self._scaled_range(self._base_x_range, self.x_scale.value())
        y_min, y_max = self._scaled_range(self._base_y_range, self.y_scale.value())
        self.plot.setXRange(x_min, x_max, padding=0.0)
        self.plot.setYRange(y_min, y_max, padding=0.05)

    def _reset_view(self) -> None:
        self.plot.enableAutoRange()
        self._apply_scale()

    def _reset_scale(self) -> None:
        self.x_scale.blockSignals(True)
        self.y_scale.blockSignals(True)
        self.x_scale.setValue(1.0)
        self.y_scale.setValue(1.0)
        self.x_scale.blockSignals(False)
        self.y_scale.blockSignals(False)
        self._apply_scale()

    @staticmethod
    def _scaled_range(range_values: tuple[float, float], scale: float) -> tuple[float, float]:
        start, end = range_values
        if start == end:
            pad = abs(start) * 0.05 or 1.0
            return start - pad, end + pad

        center = (start + end) / 2.0
        span = (end - start) * scale
        half = span / 2.0
        return center - half, center + half

    def signal_names(self) -> list[str]:
        return list(self._signals.keys())

    def current_signal_name(self) -> str:
        return self.signal_select.currentText()

    def signal_data(self, name: str) -> tuple[list[float], list[float]] | None:
        return self._signals.get(name)

    def _apply_axis_labels(self, signal_name: str) -> None:
        if "frequency" in self._signals and signal_name != "time":
            self.plot.setLabel("bottom", "Frequency")
        else:
            self.plot.setLabel("bottom", "Time")

        if signal_name.startswith("mag("):
            self.plot.setLabel("left", "Magnitude", units="dB")
        elif signal_name.startswith("phase("):
            self.plot.setLabel("left", "Phase", units="deg")
        elif signal_name.startswith("i("):
            self.plot.setLabel("left", "Current", units="A")
        else:
            self.plot.setLabel("left", "Value")
