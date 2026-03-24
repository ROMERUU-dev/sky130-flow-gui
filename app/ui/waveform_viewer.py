"""Waveform viewer widget using pyqtgraph."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import pyqtgraph as pg
import pyqtgraph.exporters

from app.core.i18n import pick


class WaveformViewer(QWidget):
    """Waveform viewer ready for real parsed ngspice signals."""

    signal_changed = Signal(str)

    def __init__(self, language: str = "es") -> None:
        super().__init__()
        self.lang = language
        self.plot = pg.PlotWidget(title=pick(self.lang, "Visor de formas de onda", "Waveform Viewer"))
        self.plot.showGrid(x=True, y=True)
        self.signal_select = QComboBox()
        self.signal_select.currentTextChanged.connect(self._render_selected)
        self.empty_label = QLabel(pick(self.lang, "Sin datos de simulación todavía", "No simulation data yet"))
        self.x_scale = QDoubleSpinBox()
        self.y_scale = QDoubleSpinBox()
        self.reset_view_btn = QPushButton(pick(self.lang, "Reset vista", "Reset View"))
        self.reset_scale_btn = QPushButton(pick(self.lang, "Reset escala", "Reset Scale"))
        self.overlay_btn = QPushButton(pick(self.lang, "Superponer", "Overlay"))
        self.clear_overlay_btn = QPushButton(pick(self.lang, "Limpiar overlay", "Clear Overlay"))
        self.export_png_btn = QPushButton("Export PNG")
        self.export_svg_btn = QPushButton("Export SVG")
        self.signal_stats = QLabel(pick(self.lang, "Sin datos", "No data"))

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel(pick(self.lang, "Señal:", "Signal:")))
        controls.addWidget(self.signal_select, 1)
        controls.addWidget(QLabel(pick(self.lang, "Escala X:", "X scale:")))
        controls.addWidget(self.x_scale)
        controls.addWidget(QLabel(pick(self.lang, "Escala Y:", "Y scale:")))
        controls.addWidget(self.y_scale)
        controls.addWidget(self.reset_view_btn)
        controls.addWidget(self.reset_scale_btn)
        controls.addWidget(self.overlay_btn)
        controls.addWidget(self.clear_overlay_btn)
        controls.addWidget(self.export_png_btn)
        controls.addWidget(self.export_svg_btn)
        layout.addLayout(controls)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.plot)
        layout.addWidget(self.signal_stats)

        self._signals: dict[str, tuple[list[float], list[float]]] = {}
        self._base_x_range: tuple[float, float] | None = None
        self._base_y_range: tuple[float, float] | None = None
        self._current_signal_name = ""
        self._overlay_signal_names: list[str] = []
        self._legend = None
        self.plot.setLabel("bottom", "Time")
        self.plot.setLabel("left", "Value")
        self.plot.hide()
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.setMinimumHeight(460)
        self.plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._configure_plot_appearance()

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
        self.overlay_btn.clicked.connect(self._choose_overlay_signals)
        self.clear_overlay_btn.clicked.connect(self._clear_overlay_signals)
        self.export_png_btn.clicked.connect(lambda: self._export_plot("png"))
        self.export_svg_btn.clicked.connect(lambda: self._export_plot("svg"))
        self.signal_select.currentTextChanged.connect(self.signal_changed.emit)

    def set_signals(self, signals: dict[str, tuple[list[float], list[float]]]) -> None:
        """Load parsed real signals."""
        previous_selection = self.signal_select.currentText()
        previous_overlays = [name for name in self._overlay_signal_names if name in signals]
        self._signals = signals
        self._overlay_signal_names = previous_overlays
        self.signal_select.blockSignals(True)
        self.signal_select.clear()
        self.signal_select.addItems(self._signals.keys())
        if self._signals:
            preferred = self._preferred_signal_name(previous_selection)
            if preferred:
                self.signal_select.setCurrentText(preferred)
        self.signal_select.blockSignals(False)
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
            self._current_signal_name = ""
            self._overlay_signal_names = []
            self.signal_stats.setText(pick(self.lang, "Sin datos", "No data"))

    def _render_selected(self, name: str) -> None:
        self.plot.clear()
        self._reset_legend()
        self._ensure_legend()
        if not name or name not in self._signals:
            return
        self._current_signal_name = name
        selected_names = self._selected_signal_names(name)
        primary_x, primary_y = self._signals[name]
        self.plot.setTitle(f"{pick(self.lang, 'Visor de formas de onda', 'Waveform Viewer')} · {', '.join(selected_names)}")
        self._apply_axis_labels(name)
        palette = ["#00d4ff", "#ffb000", "#7ee787", "#ff7b72", "#a78bfa", "#f472b6"]
        range_x: list[float] = []
        range_y: list[float] = []
        for index, signal_name in enumerate(selected_names):
            x, y = self._signals[signal_name]
            pen = pg.mkPen(palette[index % len(palette)], width=2)
            self.plot.plot(x, y, pen=pen, name=signal_name)
            range_x.extend(x)
            range_y.extend(y)
        self._capture_base_ranges(range_x, range_y)
        self._update_signal_stats(selected_names, primary_x, primary_y, range_y)
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
        self.plot.enableAutoRange(x=False, y=False)
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

    def _configure_plot_appearance(self) -> None:
        self.plot.setBackground("#0f1722")
        self.plot.getPlotItem().showAxis("left")
        self.plot.getPlotItem().showAxis("bottom")
        self.plot.showGrid(x=True, y=True, alpha=0.28)
        for axis_name in ("left", "bottom"):
            axis = self.plot.getPlotItem().getAxis(axis_name)
            axis.setPen(pg.mkPen("#c7d2e2", width=1.2))
            axis.setTextPen(pg.mkPen("#e6edf7"))

    def _update_signal_stats(
        self,
        signal_names: list[str],
        primary_x: list[float],
        primary_y: list[float],
        combined_y: list[float],
    ) -> None:
        if not primary_x or not primary_y or not combined_y:
            self.signal_stats.setText(pick(self.lang, "Sin datos", "No data"))
            return
        label = ", ".join(signal_names[:4])
        if len(signal_names) > 4:
            label += f" +{len(signal_names) - 4}"
        self.signal_stats.setText(
            f"{pick(self.lang, 'Señales', 'Signals')}: {label}    X: {self._format_axis_value(min(primary_x))} -> {self._format_axis_value(max(primary_x))}    "
            f"Y: {self._format_axis_value(min(combined_y))} -> {self._format_axis_value(max(combined_y))}"
        )

    def _export_plot(self, fmt: str) -> None:
        if not self._current_signal_name or self._current_signal_name not in self._signals:
            QMessageBox.information(
                self,
                pick(self.lang, "Sin gráfica", "No plot"),
                pick(self.lang, "Carga una simulación y selecciona una señal antes de exportar.", "Load a simulation and select a signal before exporting."),
            )
            return

        suffix = ".png" if fmt == "png" else ".svg"
        default_name = f"{self._safe_file_name(self._current_signal_name)}{suffix}"
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {fmt.upper()}",
            str(Path.cwd() / default_name),
            f"{fmt.upper()} Files (*{suffix})",
        )
        if not selected_path:
            return

        target = Path(selected_path)
        if target.suffix.lower() != suffix:
            target = target.with_suffix(suffix)

        plot_item = self.plot.getPlotItem()
        axes = {name: plot_item.getAxis(name) for name in ("left", "bottom")}
        original_background = self.plot.backgroundBrush()
        original_title = plot_item.titleLabel.text
        try:
            self.plot.setBackground("w")
            plot_item.setTitle(f"Waveform Viewer · {self._current_signal_name}", color="#111827", size="12pt")
            for axis in axes.values():
                axis.setPen(pg.mkPen("#111827", width=1.2))
                axis.setTextPen(pg.mkPen("#111827"))
            exporter = (
                pyqtgraph.exporters.ImageExporter(plot_item)
                if fmt == "png"
                else pyqtgraph.exporters.SVGExporter(plot_item)
            )
            if fmt == "png":
                exporter.parameters()["width"] = 1600
                exporter.parameters()["height"] = 900
            exporter.export(str(target))
        except Exception as exc:
            QMessageBox.warning(self, pick(self.lang, "Error de exportación", "Export error"), f"{pick(self.lang, 'No se pudo exportar la gráfica', 'Failed to export plot')}: {exc}")
            return
        finally:
            self.plot.setBackground(original_background)
            plot_item.setTitle(original_title)
            for axis_name, axis in axes.items():
                if axis_name in ("left", "bottom"):
                    axis.setPen(pg.mkPen("#c7d2e2", width=1.2))
                    axis.setTextPen(pg.mkPen("#e6edf7"))

        QMessageBox.information(
            self,
            pick(self.lang, "Exportación completa", "Export complete"),
            f"{pick(self.lang, 'Gráfica guardada en', 'Saved plot to')}:\n{target}",
        )

    def _ensure_legend(self) -> None:
        if self._legend is None:
            self._legend = self.plot.addLegend(offset=(10, 10))

    def _reset_legend(self) -> None:
        if self._legend is None:
            return
        scene = self._legend.scene()
        if scene is not None:
            scene.removeItem(self._legend)
        self._legend = None

    def _selected_signal_names(self, primary_name: str | None = None) -> list[str]:
        primary = primary_name or self._current_signal_name
        names: list[str] = []
        if primary and primary in self._signals:
            names.append(primary)
        for name in self._overlay_signal_names:
            if name in self._signals and name not in names:
                names.append(name)
        return names

    def _choose_overlay_signals(self) -> None:
        if not self._signals:
            QMessageBox.information(
                self,
                pick(self.lang, "Sin datos", "No data"),
                pick(self.lang, "Carga una simulación antes de seleccionar varias señales.", "Load a simulation before selecting multiple signals."),
            )
            return

        primary = self.current_signal_name()
        dialog = QDialog(self)
        dialog.setWindowTitle(pick(self.lang, "Superponer señales", "Overlay Signals"))
        dialog.resize(360, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(pick(self.lang, "Selecciona señales adicionales para superponer:", "Select additional signals to overlay:")))

        signal_list = QListWidget()
        signal_list.setSelectionMode(QAbstractItemView.MultiSelection)
        for name in self.signal_names():
            if name == primary:
                continue
            item = QListWidgetItem(name)
            signal_list.addItem(item)
            if name in self._overlay_signal_names:
                item.setSelected(True)
        layout.addWidget(signal_list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        self._overlay_signal_names = [item.text() for item in signal_list.selectedItems()]
        self._render_selected(primary)

    def _clear_overlay_signals(self) -> None:
        self._overlay_signal_names = []
        self._render_selected(self.current_signal_name())

    @staticmethod
    def _format_axis_value(value: float) -> str:
        magnitude = abs(value)
        if magnitude >= 1:
            return f"{value:.4g}"
        if magnitude >= 1e-3:
            return f"{value:.4g}"
        return f"{value:.3e}"

    @staticmethod
    def _safe_file_name(value: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
        return cleaned.strip("_") or "waveform"

    def _preferred_signal_name(self, previous_selection: str) -> str:
        if previous_selection in self._signals:
            return previous_selection

        best_name = ""
        best_score = (-1, -1.0)
        for name, (_, values) in self._signals.items():
            if name in {"time", "frequency"} or not values:
                continue
            span = max(values) - min(values)
            score = (self._signal_priority(name), span)
            if score > best_score:
                best_score = score
                best_name = name

        if best_name:
            return best_name

        return next(iter(self._signals), "")

    @staticmethod
    def _signal_priority(name: str) -> int:
        lowered = name.lower()
        if "#" in name or "m.x" in lowered:
            return 0
        if lowered.startswith("v(p") or lowered.startswith("i(v"):
            return 3
        if lowered.startswith("v(net") or lowered.startswith("v("):
            return 2
        if lowered.startswith("i(") or lowered.startswith("mag(") or lowered.startswith("phase("):
            return 1
        return 0

    def _apply_axis_labels(self, signal_name: str) -> None:
        if "frequency" in self._signals and signal_name != "time":
            self.plot.setLabel("bottom", pick(self.lang, "Frecuencia", "Frequency"))
        else:
            self.plot.setLabel("bottom", pick(self.lang, "Tiempo", "Time"))

        if signal_name.startswith("mag("):
            self.plot.setLabel("left", "dB", units="dB")
        elif signal_name.startswith("phase("):
            self.plot.setLabel("left", "deg", units="deg")
        elif signal_name.startswith("i("):
            self.plot.setLabel("left", "I", units="A")
        else:
            self.plot.setLabel("left", "V", units="V")
