"""Simulation tab UI and ngspice workflow."""

from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path

import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtCore import QSignalBlocker
from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.command_runner import CommandRunner
from app.core.i18n import pick
from app.core.log_parser import LogParser
from app.core.ngspice_raw_parser import NgspiceRawParser
from app.core.output_manager import OutputPaths
from app.core.settings_manager import AppSettings
from app.core.spice_tools import (
    apply_model_corner,
    analyze_signal,
    build_generated_netlist,
    extract_candidate_points,
    format_value,
)
from app.runners.ngspice_runner import NgspiceRunner
from app.ui.waveform_viewer import WaveformViewer
from app.ui.widgets import append_log


class SimulationTab(QWidget):
    """Run and inspect ngspice simulations."""

    send_status = Signal(str)

    def __init__(self, settings: AppSettings, outputs_getter) -> None:
        super().__init__()
        self.settings = settings
        self.lang = settings.language
        self.outputs_getter = outputs_getter
        self.runner = CommandRunner()
        self.builder = NgspiceRunner(settings)

        self.netlist_edit = QLineEdit()
        self.output_dir = QLineEdit()
        self.output_dir.setReadOnly(True)
        self.generated_path_edit = QLineEdit()
        self.generated_path_edit.setReadOnly(True)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.file_view = QTextEdit()
        self.file_view.setPlaceholderText(
            pick(self.lang, "Carga un netlist y ajustalo aqui; el archivo original no se sobrescribe.", "Load a netlist, tweak it here, and the original file will remain untouched.")
        )
        self.extra_directives = QTextEdit()
        self.extra_directives.setPlaceholderText(pick(self.lang, "Directivas extra opcionales (.meas, .ic, .param, etc.)", "Optional extra directives (.meas, .ic, .param, etc.)"))
        self.wave = WaveformViewer(self.lang)
        self.spectrum_plot = pg.PlotWidget(title=pick(self.lang, "Espectro de frecuencia", "Frequency Spectrum"))
        self.spectrum_plot.setLabel("bottom", pick(self.lang, "Frecuencia", "Frequency"), units="Hz")
        self.spectrum_plot.setLabel("left", "dB", units="dB")
        self.spectrum_plot.showGrid(x=True, y=True)
        self.spectrum_plot.hide()
        self.spectrum_plot.setMinimumHeight(320)
        self.spectrum_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._configure_spectrum_plot_appearance()
        self.spectrum_x_scale = QDoubleSpinBox()
        self.spectrum_y_scale = QDoubleSpinBox()
        self.spectrum_reset_view_btn = QPushButton(pick(self.lang, "Reset vista", "Reset View"))
        self.spectrum_reset_scale_btn = QPushButton(pick(self.lang, "Reset escala", "Reset Scale"))
        self.spectrum_export_png_btn = QPushButton("Export PNG")
        self.spectrum_export_svg_btn = QPushButton("Export SVG")
        self.spectrum_stats = QLabel(pick(self.lang, "Sin datos", "No data"))

        self.history_select = QComboBox()
        self.history_select.setPlaceholderText(pick(self.lang, "Sin simulaciones previas", "No previous simulations"))
        self.load_history_btn = QPushButton(pick(self.lang, "Cargar anterior", "Load Previous"))
        self.refresh_history_btn = QPushButton(pick(self.lang, "Refrescar historial", "Refresh History"))

        self.run_btn = QPushButton(pick(self.lang, "Correr", "Run"))
        self.run_btn.setStyleSheet(
            """
            QPushButton:disabled {
                background-color: #9aa0a6;
                color: #f3f4f6;
                border: 1px solid #7d848c;
            }
            """
        )
        self.stop_btn = QPushButton(pick(self.lang, "Detener", "Stop"))
        self.stop_btn.setEnabled(False)
        self.rerun_btn = QPushButton(pick(self.lang, "Repetir", "Re-run"))
        self.show_log_btn = QPushButton(pick(self.lang, "Mostrar log", "Show log"))
        self.open_out_btn = QPushButton(pick(self.lang, "Abrir carpeta de salida", "Open Output Folder"))
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedWidth(150)
        self.loading_bar.setVisible(False)
        self.loading_bar.setToolTip(pick(self.lang, "Simulación en progreso", "Simulation in progress"))
        self.add_probe_btn = QPushButton(pick(self.lang, "Agregar probe", "Add Probe Point"))
        self.refresh_points_btn = QPushButton(pick(self.lang, "Refrescar probes", "Refresh Points"))
        self.edit_netlist_btn = QToolButton()
        self.edit_netlist_btn.setText(pick(self.lang, "Modificar netlist (beta)", "Edit netlist (beta)"))
        self.edit_netlist_btn.setCheckable(True)
        self.edit_netlist_btn.setChecked(False)
        self.paste_netlist_btn = QToolButton()
        self.paste_netlist_btn.setText(pick(self.lang, "Pegar netlist", "Paste netlist"))

        self.sim_type = QComboBox()
        self.sim_type.addItems(
            [
                pick(self.lang, "Transitorio", "Transient"),
                "AC",
                "DC",
                pick(self.lang, "Punto de operación", "Operating Point"),
            ]
        )
        self.sim_stack = QStackedWidget()
        self.log_dialog: QDialog | None = None
        self.log_viewer: QTextEdit | None = None

        self.tran_step = QLineEdit("1n")
        self.tran_stop = QLineEdit("1u")
        self.tran_start = QLineEdit("0")
        self.tran_uic = QCheckBox("UIC")

        self.ac_sweep = QComboBox()
        self.ac_sweep.addItems(["dec", "lin", "oct"])
        self.ac_points = QLineEdit("20")
        self.ac_start = QLineEdit("1")
        self.ac_stop = QLineEdit("1G")

        self.dc_source = QLineEdit("V1")
        self.dc_start = QLineEdit("0")
        self.dc_stop = QLineEdit("1.8")
        self.dc_step = QLineEdit("0.01")
        self.save_mode = QComboBox()
        self.save_mode.addItems(
            [
                pick(self.lang, "Todas las señales", "All signals"),
                pick(self.lang, "Sólo probes seleccionados", "Selected probes only"),
            ]
        )
        self.corner = QComboBox()
        self.corner.addItems(["tt", "ss", "ff", "sf", "fs"])
        self.temp_c = QLineEdit()
        self.temp_c.setPlaceholderText(pick(self.lang, "Opcional, ej. 27", "Optional, e.g. 27"))
        self.spectrum_mode = QComboBox()
        self.spectrum_mode.addItems(
            [
                pick(self.lang, "Auto", "Auto"),
                pick(self.lang, "Mostrar", "Show"),
                pick(self.lang, "Ocultar", "Hide"),
            ]
        )
        self.spectrum_x_axis = QComboBox()
        self.spectrum_x_axis.addItems(
            [
                pick(self.lang, "Hz lineal", "Linear Hz"),
                pick(self.lang, "Hz log", "Log Hz"),
            ]
        )

        self.metric_signal = QComboBox()
        self.metric_reference = QComboBox()
        self.metric_reference.addItem("None", "")
        self.metric_labels = {
            "minimum": QLabel("N/A"),
            "maximum": QLabel("N/A"),
            "mean": QLabel("N/A"),
            "rms": QLabel("N/A"),
            "peak_to_peak": QLabel("N/A"),
            "amplitude": QLabel("N/A"),
            "frequency_hz": QLabel("N/A"),
            "period_s": QLabel("N/A"),
            "phase_deg": QLabel("N/A"),
        }

        self._probe_rows: list[tuple[QHBoxLayout, QComboBox, QPushButton]] = []
        self._candidate_points: list[str] = []
        self._last_command: list[str] = []
        self._last_outputs: OutputPaths | None = None
        self._last_raw_path: Path | None = None
        self._last_generated_netlist: Path | None = None
        self._spectrum_base_x_range: tuple[float, float] | None = None
        self._spectrum_base_y_range: tuple[float, float] | None = None
        self._current_spectrum_signal_name = ""
        self._current_spectrum_has_data = False

        for control in (self.spectrum_x_scale, self.spectrum_y_scale):
            control.setDecimals(2)
            control.setRange(0.1, 10.0)
            control.setSingleStep(0.1)
            control.setValue(1.0)

        self._build_ui()
        self._wire()
        self.refresh_history()
        self._refresh_probe_points()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        layout.addWidget(scroll)

        page = QWidget()
        page_layout = QVBoxLayout(page)

        row = QHBoxLayout()
        row.addWidget(QLabel(pick(self.lang, "Netlist:", "Netlist:")))
        row.addWidget(self.netlist_edit)
        browse_btn = QPushButton(pick(self.lang, "Buscar", "Browse"))
        browse_btn.clicked.connect(self._pick_file)
        row.addWidget(browse_btn)
        page_layout.addLayout(row)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel(pick(self.lang, "Directorio de salida:", "Output Dir:")))
        path_row.addWidget(self.output_dir)
        path_row.addWidget(self.open_out_btn)
        page_layout.addLayout(path_row)

        gen_row = QHBoxLayout()
        gen_row.addWidget(QLabel(pick(self.lang, "Netlist generado:", "Generated Netlist:")))
        gen_row.addWidget(self.generated_path_edit)
        page_layout.addLayout(gen_row)

        btns = QHBoxLayout()
        btns.addWidget(self.run_btn)
        btns.addWidget(self.stop_btn)
        btns.addWidget(self.rerun_btn)
        btns.addWidget(self.show_log_btn)
        btns.addWidget(self.loading_bar)
        btns.addStretch(1)
        page_layout.addLayout(btns)

        history_row = QHBoxLayout()
        history_row.addWidget(QLabel(pick(self.lang, "Simulaciones previas:", "Previous simulations:")))
        history_row.addWidget(self.history_select, 1)
        history_row.addWidget(self.load_history_btn)
        history_row.addWidget(self.refresh_history_btn)
        page_layout.addLayout(history_row)

        page_layout.addWidget(self._build_simulation_setup())
        page_layout.addWidget(self._build_probe_editor())
        netlist_tools = QHBoxLayout()
        netlist_tools.addWidget(self.edit_netlist_btn)
        netlist_tools.addWidget(self.paste_netlist_btn)
        netlist_tools.addStretch(1)
        page_layout.addLayout(netlist_tools)
        page_layout.addWidget(self._build_netlist_editor())
        page_layout.addWidget(self._build_visualization_options())
        page_layout.addWidget(self.wave)
        page_layout.addWidget(self._build_measurement_panel())
        page_layout.addWidget(self._build_spectrum_panel())
        page_layout.addStretch(1)

        scroll.setWidget(page)

    def _build_simulation_setup(self) -> QWidget:
        box = QGroupBox(pick(self.lang, "Configuración de simulación", "Simulation Setup"))
        form = QFormLayout(box)
        form.addRow(pick(self.lang, "Tipo:", "Type:"), self.sim_type)
        form.addRow(pick(self.lang, "Modo de guardado:", "Save mode:"), self.save_mode)
        form.addRow(pick(self.lang, "Corner:", "Corner:"), self.corner)
        form.addRow(pick(self.lang, "Temperatura (C):", "Temperature (C):"), self.temp_c)

        tran_page = QWidget()
        tran_form = QFormLayout(tran_page)
        tran_form.addRow(pick(self.lang, "Paso:", "Step:"), self.tran_step)
        tran_form.addRow(pick(self.lang, "Fin:", "Stop:"), self.tran_stop)
        tran_form.addRow(pick(self.lang, "Inicio:", "Start:"), self.tran_start)
        tran_form.addRow("", self.tran_uic)

        ac_page = QWidget()
        ac_form = QFormLayout(ac_page)
        ac_form.addRow(pick(self.lang, "Barrido:", "Sweep:"), self.ac_sweep)
        ac_form.addRow(pick(self.lang, "Puntos/dec:", "Points/dec:"), self.ac_points)
        ac_form.addRow(pick(self.lang, "Frecuencia inicial:", "Start freq:"), self.ac_start)
        ac_form.addRow(pick(self.lang, "Frecuencia final:", "Stop freq:"), self.ac_stop)

        dc_page = QWidget()
        dc_form = QFormLayout(dc_page)
        dc_form.addRow(pick(self.lang, "Fuente:", "Source:"), self.dc_source)
        dc_form.addRow(pick(self.lang, "Inicio:", "Start:"), self.dc_start)
        dc_form.addRow(pick(self.lang, "Fin:", "Stop:"), self.dc_stop)
        dc_form.addRow(pick(self.lang, "Paso:", "Step:"), self.dc_step)

        op_page = QWidget()
        op_form = QFormLayout(op_page)
        op_form.addRow(
            QLabel(
                pick(
                    self.lang,
                    "Ejecuta un único punto de operación DC (.op) con el netlist y las fuentes actuales.",
                    "Run a single DC operating point (.op) with the current netlist and sources.",
                )
            )
        )

        self.sim_stack.addWidget(tran_page)
        self.sim_stack.addWidget(ac_page)
        self.sim_stack.addWidget(dc_page)
        self.sim_stack.addWidget(op_page)
        form.addRow(self.sim_stack)
        return box

    def _build_probe_editor(self) -> QWidget:
        box = QGroupBox(pick(self.lang, "Puntos de prueba", "Probe Points"))
        outer = QVBoxLayout(box)
        top = QHBoxLayout()
        top.addWidget(QLabel(pick(self.lang, "Elige nodos o escribe expresiones como v(out) / i(v1):", "Choose nodes or type expressions like v(out) / i(v1):")))
        top.addWidget(self.add_probe_btn)
        top.addWidget(self.refresh_points_btn)
        outer.addLayout(top)

        container = QWidget()
        self.probe_layout = QVBoxLayout(container)
        self.probe_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)
        return box

    def _build_netlist_editor(self) -> QWidget:
        box = QGroupBox(pick(self.lang, "Editor de netlist", "Netlist Editor"))
        box.setVisible(False)
        outer = QVBoxLayout(box)
        outer.addWidget(QLabel(pick(self.lang, "Editor temporal del netlist de simulación:", "Temporary Simulation Netlist Editor:")))
        outer.addWidget(self.file_view)
        outer.addWidget(QLabel(pick(self.lang, "Directivas extra:", "Extra Directives:")))
        outer.addWidget(self.extra_directives)
        self.netlist_editor_box = box
        return box

    def _build_measurement_panel(self) -> QWidget:
        box = QGroupBox(pick(self.lang, "Mediciones", "Measurements"))
        form = QFormLayout(box)
        form.addRow(pick(self.lang, "Señal:", "Signal:"), self.metric_signal)
        form.addRow(pick(self.lang, "Referencia de fase:", "Phase reference:"), self.metric_reference)
        form.addRow("Min:", self.metric_labels["minimum"])
        form.addRow("Max:", self.metric_labels["maximum"])
        form.addRow(pick(self.lang, "Media:", "Mean:"), self.metric_labels["mean"])
        form.addRow("RMS:", self.metric_labels["rms"])
        form.addRow("Peak-to-peak:", self.metric_labels["peak_to_peak"])
        form.addRow("Amplitude:", self.metric_labels["amplitude"])
        form.addRow(pick(self.lang, "Frecuencia:", "Frequency:"), self.metric_labels["frequency_hz"])
        form.addRow(pick(self.lang, "Período:", "Period:"), self.metric_labels["period_s"])
        form.addRow(pick(self.lang, "Fase:", "Phase:"), self.metric_labels["phase_deg"])
        return box

    def _build_visualization_options(self) -> QWidget:
        box = QGroupBox(pick(self.lang, "Opciones de visualización", "Visualization Options"))
        form = QFormLayout(box)
        form.addRow(pick(self.lang, "Espectro:", "Spectrum:"), self.spectrum_mode)
        form.addRow(pick(self.lang, "Eje X del espectro:", "Spectrum X axis:"), self.spectrum_x_axis)
        form.addRow(QLabel(pick(self.lang, "Tip: la gráfica inferior es un espectro tipo FFT y aparece para señales en el dominio del tiempo.", "Tip: the lower graph is an FFT-like spectrum and is available for time-domain signals.")))
        return box

    def _build_spectrum_panel(self) -> QWidget:
        box = QGroupBox(pick(self.lang, "Espectro de frecuencia", "Frequency Spectrum"))
        outer = QVBoxLayout(box)
        controls = QHBoxLayout()
        controls.addWidget(QLabel(pick(self.lang, "Escala X:", "X scale:")))
        controls.addWidget(self.spectrum_x_scale)
        controls.addWidget(QLabel(pick(self.lang, "Escala Y:", "Y scale:")))
        controls.addWidget(self.spectrum_y_scale)
        controls.addWidget(self.spectrum_reset_view_btn)
        controls.addWidget(self.spectrum_reset_scale_btn)
        controls.addWidget(self.spectrum_export_png_btn)
        controls.addWidget(self.spectrum_export_svg_btn)
        controls.addStretch(1)
        outer.addLayout(controls)
        outer.addWidget(self.spectrum_plot)
        outer.addWidget(self.spectrum_stats)
        return box

    def _wire(self) -> None:
        self.run_btn.clicked.connect(self.run)
        self.stop_btn.clicked.connect(self.runner.stop)
        self.rerun_btn.clicked.connect(self.rerun)
        self.show_log_btn.clicked.connect(self._show_log_dialog)
        self.open_out_btn.clicked.connect(self.open_output_folder)
        self.load_history_btn.clicked.connect(self.load_selected_history)
        self.refresh_history_btn.clicked.connect(self.refresh_history)
        self.add_probe_btn.clicked.connect(lambda: self._add_probe_row())
        self.refresh_points_btn.clicked.connect(self._refresh_probe_points)
        self.sim_type.currentIndexChanged.connect(self.sim_stack.setCurrentIndex)
        self.file_view.textChanged.connect(self._refresh_probe_points)
        self.metric_signal.currentTextChanged.connect(self._update_measurements)
        self.metric_reference.currentTextChanged.connect(self._update_measurements)
        self.spectrum_mode.currentTextChanged.connect(self._update_measurements)
        self.spectrum_x_axis.currentTextChanged.connect(self._update_spectrum_axis)
        self.spectrum_x_scale.valueChanged.connect(self._apply_spectrum_scale)
        self.spectrum_y_scale.valueChanged.connect(self._apply_spectrum_scale)
        self.spectrum_reset_view_btn.clicked.connect(self._reset_spectrum_view)
        self.spectrum_reset_scale_btn.clicked.connect(self._reset_spectrum_scale)
        self.spectrum_export_png_btn.clicked.connect(lambda: self._export_spectrum_plot("png"))
        self.spectrum_export_svg_btn.clicked.connect(lambda: self._export_spectrum_plot("svg"))
        self.wave.signal_changed.connect(self._sync_metric_selection)
        self.edit_netlist_btn.toggled.connect(self._toggle_netlist_editor)
        self.paste_netlist_btn.clicked.connect(self._paste_netlist)

        self.runner.started.connect(lambda cmd: self._append_log(f"\n$ {cmd}\n"))
        self.runner.line_output.connect(self._append_log)
        self.runner.finished.connect(self._finished)

    def _pick_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select netlist", "", "SPICE Files (*.spice *.sp *.cir)")
        if file_path:
            self.load_netlist_path(file_path)

    def load_netlist_path(self, file_path: str) -> None:
        self.netlist_edit.setText(file_path)
        try:
            self.file_view.setPlainText(Path(file_path).read_text())
            self._refresh_probe_points()
        except OSError as exc:
            self._append_log(f"Failed to read file: {exc}\n")

    def run(self) -> None:
        source_netlist = self._ensure_editor_content()
        if not source_netlist:
            self._append_log("Select a netlist first.\n")
            return

        outputs = self._create_simulation_outputs()
        self._last_outputs = outputs
        self.output_dir.setText(str(outputs.results))

        generated_netlist = self._write_generated_netlist(outputs)
        self._last_generated_netlist = generated_netlist
        self.generated_path_edit.setText(str(generated_netlist))

        cmd, log_path, raw_path, run_cwd = self.builder.run_spec(str(generated_netlist), outputs)
        self._append_log(f"Output folder: {outputs.results}\nGenerated netlist: {generated_netlist}\nLog file: {log_path}\n")
        self._last_command = cmd
        self._last_raw_path = Path(raw_path)
        self.wave.set_signals({})
        self._clear_measurements()
        self._clear_spectrum_plot()
        self.refresh_history()
        self.send_status.emit("Simulation running")
        self._set_simulation_running(True)
        self.runner.run(self.builder.build(cmd, cwd=run_cwd))

    def rerun(self) -> None:
        self.run()

    def _finished(self, code: int, status: str) -> None:
        self._set_simulation_running(False)
        summary = f"\nSimulation finished: exit={code} status={status}\n"
        self._append_log(summary)
        full_text = self.log.toPlainText()
        if LogParser.has_errors(full_text) or code != 0:
            self.send_status.emit("Simulation failed")
        else:
            self._load_waveforms()
            self.refresh_history()
            self.send_status.emit("Simulation completed")

    def open_output_folder(self) -> None:
        if self.output_dir.text().strip():
            QDesktopServices.openUrl(Path(self.output_dir.text().strip()).as_uri())

    def _load_waveforms(self) -> None:
        raw_path = self._resolve_raw_path()
        self._load_waveforms_from_path(raw_path)

    def load_selected_history(self) -> None:
        raw_path = self.history_select.currentData()
        if not raw_path:
            self._append_log("No previous simulation is selected.\n")
            return
        try:
            self._load_waveforms_from_path(Path(raw_path))
        except Exception as exc:
            self._append_log(f"Failed to load selected history: {exc}\n")
            self.send_status.emit("Failed to load previous simulation")

    def refresh_history(self) -> None:
        outputs = self.outputs_getter()
        active_output_dir = self._last_outputs.results if self._last_outputs else outputs.results
        self.output_dir.setText(str(active_output_dir))

        current_path = str(self.history_select.currentData()) if self.history_select.currentData() else None
        raw_files = sorted(outputs.results.rglob("*.raw"), key=lambda path: path.stat().st_mtime, reverse=True)

        self.history_select.blockSignals(True)
        self.history_select.clear()
        for raw_file in raw_files:
            rel_path = raw_file.relative_to(outputs.results)
            label = f"{rel_path}  [{self._format_timestamp(raw_file)}]"
            self.history_select.addItem(label, str(raw_file))

        if current_path:
            index = self.history_select.findData(current_path)
            if index >= 0:
                self.history_select.setCurrentIndex(index)
        elif self.history_select.count():
            self.history_select.setCurrentIndex(0)
        self.history_select.blockSignals(False)

    def _load_waveforms_from_path(self, raw_path: Path | None) -> None:
        if not raw_path:
            self._append_log("No waveform raw file was found after simulation.\n")
            self.wave.set_signals({})
            self._clear_measurements()
            self._clear_spectrum_plot()
            return

        try:
            signals = NgspiceRawParser.load_signals(raw_path)
        except (OSError, ValueError) as exc:
            self._append_log(f"Failed to load waveform data: {exc}\n")
            self.wave.set_signals({})
            self._clear_measurements()
            self._clear_spectrum_plot()
            return

        self._last_raw_path = raw_path
        self._clear_spectrum_plot()

        with QSignalBlocker(self.metric_signal), QSignalBlocker(self.metric_reference):
            self.wave.set_signals(signals)
            self._refresh_measurement_targets()

        self._update_measurements()
        self._append_log(f"Loaded waveform data from: {raw_path}\n")

    def _resolve_raw_path(self) -> Path | None:
        candidates: list[Path] = []
        if self._last_raw_path:
            candidates.append(self._last_raw_path)
        if self._last_outputs:
            candidates.extend(sorted(self._last_outputs.results.rglob("*.raw")))

        seen: set[Path] = set()
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _refresh_probe_points(self) -> None:
        self._candidate_points = extract_candidate_points(self.file_view.toPlainText())
        for _, combo, _ in self._probe_rows:
            current_text = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(self._candidate_points)
            combo.setEditText(current_text)
            combo.blockSignals(False)

        if not self._probe_rows:
            self._add_probe_row()

    def _add_probe_row(self, initial_text: str = "") -> None:
        row = QHBoxLayout()
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(self._candidate_points)
        if initial_text:
            combo.setEditText(initial_text)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda: self._remove_probe_row(combo))
        row.addWidget(combo, 1)
        row.addWidget(remove_btn)
        self.probe_layout.addLayout(row)
        self._probe_rows.append((row, combo, remove_btn))

    def _remove_probe_row(self, combo: QComboBox) -> None:
        if len(self._probe_rows) <= 1:
            combo.setEditText("")
            return

        for row, current_combo, button in list(self._probe_rows):
            if current_combo is not combo:
                continue
            while row.count():
                item = row.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            self.probe_layout.removeItem(row)
            self._probe_rows.remove((row, current_combo, button))
            return

    def _selected_probe_points(self) -> list[str]:
        points: list[str] = []
        for _, combo, _ in self._probe_rows:
            text = combo.currentText().strip()
            if text:
                points.append(text)
        return points

    def _write_generated_netlist(self, outputs: OutputPaths) -> Path:
        source_text = apply_model_corner(self.file_view.toPlainText(), self.corner.currentText())
        analysis_type = self._analysis_type_key()
        params = {
            "tran_step": self.tran_step.text().strip(),
            "tran_stop": self.tran_stop.text().strip(),
            "tran_start": self.tran_start.text().strip(),
            "tran_uic": "1" if self.tran_uic.isChecked() else "",
            "ac_sweep": self.ac_sweep.currentText(),
            "ac_points": self.ac_points.text().strip(),
            "ac_start": self.ac_start.text().strip(),
            "ac_stop": self.ac_stop.text().strip(),
            "dc_source": self.dc_source.text().strip(),
            "dc_start": self.dc_start.text().strip(),
            "dc_stop": self.dc_stop.text().strip(),
            "dc_step": self.dc_step.text().strip(),
            "save_mode": self._save_mode_key(),
            "temp_c": self.temp_c.text().strip(),
        }
        generated = build_generated_netlist(
            source_text=source_text,
            analysis_type=analysis_type,
            analysis_params=params,
            save_points=self._selected_probe_points(),
            extra_directives=self.extra_directives.toPlainText(),
        )

        generated_path = outputs.results / "run.spice"
        generated_path.write_text(generated)
        return generated_path

    def _create_simulation_outputs(self) -> OutputPaths:
        base_outputs = self.outputs_getter()
        run_name = self._compact_timestamp()
        results_dir = base_outputs.results / run_name
        logs_dir = base_outputs.logs / run_name
        results_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        return OutputPaths(
            base=base_outputs.base,
            runs=base_outputs.runs,
            logs=logs_dir,
            results=results_dir,
            lvs=base_outputs.lvs,
            extraction=base_outputs.extraction,
            antenna=base_outputs.antenna,
        )

    def _refresh_measurement_targets(self) -> None:
        signal_names = self.wave.signal_names()
        current_metric = self.metric_signal.currentText()
        current_reference = self.metric_reference.currentData() or ""

        self.metric_signal.blockSignals(True)
        self.metric_signal.clear()
        self.metric_signal.addItems(signal_names)
        if current_metric:
            index = self.metric_signal.findText(current_metric)
            if index >= 0:
                self.metric_signal.setCurrentIndex(index)
        elif signal_names:
            self.metric_signal.setCurrentText(self.wave.current_signal_name() or signal_names[0])
        self.metric_signal.blockSignals(False)

        self.metric_reference.blockSignals(True)
        self.metric_reference.clear()
        self.metric_reference.addItem("None", "")
        for name in signal_names:
            self.metric_reference.addItem(name, name)
        if current_reference:
            index = self.metric_reference.findData(current_reference)
            if index >= 0:
                self.metric_reference.setCurrentIndex(index)
        self.metric_reference.blockSignals(False)

    def _sync_metric_selection(self, signal_name: str) -> None:
        if not signal_name:
            return
        index = self.metric_signal.findText(signal_name)
        if index >= 0:
            self.metric_signal.setCurrentIndex(index)

    def _update_measurements(self) -> None:
        signal_name = self.metric_signal.currentText() or self.wave.current_signal_name()
        signal_data = self.wave.signal_data(signal_name)
        if not signal_data:
            self._clear_measurements()
            self._clear_spectrum_plot()
            return

        reference_name = self.metric_reference.currentData()
        reference = self.wave.signal_data(reference_name) if reference_name else None
        if "time" in self.wave.signal_names():
            x_label = "time"
        elif "frequency" in self.wave.signal_names():
            x_label = "frequency"
        else:
            x_label = "sweep"

        try:
            metrics, spectrum = analyze_signal(signal_data[0], signal_data[1], x_label=x_label, reference=reference)
        except ValueError:
            self._clear_measurements()
            self._clear_spectrum_plot()
            return

        unit = self._signal_unit(signal_name)
        self.metric_labels["minimum"].setText(format_value(metrics.minimum, unit))
        self.metric_labels["maximum"].setText(format_value(metrics.maximum, unit))
        self.metric_labels["mean"].setText(format_value(metrics.mean, unit))
        self.metric_labels["rms"].setText(format_value(metrics.rms, unit))
        self.metric_labels["peak_to_peak"].setText(format_value(metrics.peak_to_peak, unit))
        self.metric_labels["amplitude"].setText(format_value(metrics.amplitude, unit))
        if metrics.x_label == "time":
            self.metric_labels["frequency_hz"].setText(format_value(metrics.frequency_hz, "Hz"))
            self.metric_labels["period_s"].setText(format_value(metrics.period_s, "s"))
            self.metric_labels["phase_deg"].setText(format_value(metrics.phase_deg, "deg"))
        else:
            self.metric_labels["frequency_hz"].setText("N/A")
            self.metric_labels["period_s"].setText("N/A")
            self.metric_labels["phase_deg"].setText("N/A")

        self.spectrum_plot.clear()
        self._update_spectrum_axis()
        spectrum_mode = self._spectrum_mode_key()
        should_show_spectrum = spectrum_mode == "Show" or (
            spectrum_mode == "Auto" and spectrum.frequencies and spectrum.magnitudes
        )
        if should_show_spectrum and spectrum.frequencies and spectrum.magnitudes:
            self._current_spectrum_signal_name = signal_name
            self._current_spectrum_has_data = True
            peak_magnitude = max(spectrum.magnitudes)
            spectrum_db = [
                20.0 * math.log10(max(value, 1e-15) / max(peak_magnitude, 1e-15))
                for value in spectrum.magnitudes
            ]
            self.spectrum_plot.setTitle(
                f"{pick(self.lang, 'Espectro de frecuencia', 'Frequency Spectrum')} · {signal_name}"
            )
            self.spectrum_plot.setLabel("left", "dB", units="dB")
            self.spectrum_plot.plot(spectrum.frequencies, spectrum_db, pen=pg.mkPen("#ffb000", width=2))
            self._capture_spectrum_ranges(spectrum.frequencies, spectrum_db)
            self._update_spectrum_stats(
                spectrum.frequencies,
                spectrum_db,
                spectrum.dominant_frequency_hz,
            )
            self._apply_spectrum_scale()
            self.spectrum_plot.show()
        else:
            self._clear_spectrum_plot()

    def _update_spectrum_axis(self) -> None:
        use_log = self._spectrum_x_axis_key() == "log"
        self.spectrum_plot.setLogMode(x=use_log, y=False)
        self._apply_spectrum_scale()

    def _configure_spectrum_plot_appearance(self) -> None:
        self.spectrum_plot.setBackground("#0f1722")
        plot_item = self.spectrum_plot.getPlotItem()
        plot_item.showAxis("left")
        plot_item.showAxis("bottom")
        self.spectrum_plot.showGrid(x=True, y=True, alpha=0.28)
        for axis_name in ("left", "bottom"):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen("#c7d2e2", width=1.2))
            axis.setTextPen(pg.mkPen("#e6edf7"))

    def _capture_spectrum_ranges(self, x: list[float], y: list[float]) -> None:
        if not x or not y:
            self._spectrum_base_x_range = None
            self._spectrum_base_y_range = None
            return

        self._spectrum_base_x_range = (min(x), max(x))
        y_max = max(y)
        y_min = max(min(y), y_max - 80.0)
        if y_min == y_max:
            pad = abs(y_min) * 0.05 or 1.0
            y_min -= pad
            y_max += pad
        self._spectrum_base_y_range = (y_min, y_max)

    def _apply_spectrum_scale(self) -> None:
        if not self._spectrum_base_x_range or not self._spectrum_base_y_range:
            return

        x_min, x_max = self._scaled_range(self._spectrum_base_x_range, self.spectrum_x_scale.value())
        base_y_min, base_y_max = self._spectrum_base_y_range
        base_span = max(base_y_max - base_y_min, 1.0)
        y_span = max(base_span * self.spectrum_y_scale.value(), 1.0)
        y_max = base_y_max + 3.0
        y_min = y_max - y_span
        if self._spectrum_x_axis_key() == "log":
            x_min = max(x_min, 1e-12)
            x_max = max(x_max, x_min * 1.01)
        self.spectrum_plot.enableAutoRange(x=False, y=False)
        self.spectrum_plot.setXRange(x_min, x_max, padding=0.0)
        self.spectrum_plot.setYRange(y_min, y_max, padding=0.05)

    def _reset_spectrum_view(self) -> None:
        self.spectrum_plot.enableAutoRange()
        self._apply_spectrum_scale()

    def _reset_spectrum_scale(self) -> None:
        self.spectrum_x_scale.blockSignals(True)
        self.spectrum_y_scale.blockSignals(True)
        self.spectrum_x_scale.setValue(1.0)
        self.spectrum_y_scale.setValue(1.0)
        self.spectrum_x_scale.blockSignals(False)
        self.spectrum_y_scale.blockSignals(False)
        self._apply_spectrum_scale()

    def _update_spectrum_stats(
        self,
        frequencies: list[float],
        magnitudes: list[float],
        dominant_frequency_hz: float | None,
    ) -> None:
        if not frequencies or not magnitudes:
            self.spectrum_stats.setText(pick(self.lang, "Sin datos", "No data"))
            return

        dominant = format_value(dominant_frequency_hz, "Hz") if dominant_frequency_hz else "N/A"
        self.spectrum_stats.setText(
            f"{pick(self.lang, 'Frecuencia dominante', 'Dominant frequency')}: {dominant}    "
            f"Hz: {self._format_plot_value(min(frequencies))} -> {self._format_plot_value(max(frequencies))}    "
            f"{pick(self.lang, 'Magnitud relativa', 'Relative magnitude')}: {self._format_plot_value(min(magnitudes))} -> {self._format_plot_value(max(magnitudes))} dB"
        )

    def _clear_spectrum_plot(self) -> None:
        self.spectrum_plot.clear()
        self.spectrum_plot.hide()
        self.spectrum_plot.setTitle(pick(self.lang, "Espectro de frecuencia", "Frequency Spectrum"))
        self._spectrum_base_x_range = None
        self._spectrum_base_y_range = None
        self._current_spectrum_signal_name = ""
        self._current_spectrum_has_data = False
        self.spectrum_stats.setText(pick(self.lang, "Sin datos", "No data"))

    def _export_spectrum_plot(self, fmt: str) -> None:
        if not self._current_spectrum_signal_name or not self._current_spectrum_has_data:
            QMessageBox.information(
                self,
                pick(self.lang, "Sin gráfica", "No plot"),
                pick(self.lang, "Genera un espectro válido antes de exportar.", "Generate a valid spectrum before exporting."),
            )
            return

        suffix = ".png" if fmt == "png" else ".svg"
        default_name = f"{self._safe_name(self._current_spectrum_signal_name)}_spectrum{suffix}"
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

        plot_item = self.spectrum_plot.getPlotItem()
        axes = {name: plot_item.getAxis(name) for name in ("left", "bottom")}
        original_background = self.spectrum_plot.backgroundBrush()
        original_title = plot_item.titleLabel.text
        try:
            self.spectrum_plot.setBackground("w")
            plot_item.setTitle(
                f"{pick(self.lang, 'Espectro de frecuencia', 'Frequency Spectrum')} · {self._current_spectrum_signal_name}",
                color="#111827",
                size="12pt",
            )
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
            QMessageBox.warning(
                self,
                pick(self.lang, "Error de exportación", "Export error"),
                f"{pick(self.lang, 'No se pudo exportar la gráfica', 'Failed to export plot')}: {exc}",
            )
            return
        finally:
            self.spectrum_plot.setBackground(original_background)
            plot_item.setTitle(original_title)
            for axis in axes.values():
                axis.setPen(pg.mkPen("#c7d2e2", width=1.2))
                axis.setTextPen(pg.mkPen("#e6edf7"))

        QMessageBox.information(
            self,
            pick(self.lang, "Exportación completa", "Export complete"),
            f"{pick(self.lang, 'Gráfica guardada en', 'Saved plot to')}:\n{target}",
        )

    def _clear_measurements(self) -> None:
        for label in self.metric_labels.values():
            label.setText("N/A")

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

    @staticmethod
    def _format_plot_value(value: float) -> str:
        magnitude = abs(value)
        if magnitude >= 1:
            return f"{value:.4g}"
        if magnitude >= 1e-3:
            return f"{value:.4g}"
        return f"{value:.3e}"

    @staticmethod
    def _signal_unit(signal_name: str) -> str:
        if signal_name.startswith("mag("):
            return "dB"
        if signal_name.startswith("phase("):
            return "deg"
        if signal_name.startswith("i("):
            return "A"
        return "V"

    def _toggle_netlist_editor(self, checked: bool) -> None:
        self.netlist_editor_box.setVisible(checked)

    def _paste_netlist(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Pegar netlist")
        dialog.resize(720, 520)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        file_name_edit = QLineEdit("pasted_netlist")
        form.addRow("Nombre:", file_name_edit)
        layout.addLayout(form)

        text_edit = QTextEdit()
        text_edit.setPlaceholderText("Pega aqui el contenido del netlist SPICE...")
        layout.addWidget(text_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        netlist_text = text_edit.toPlainText().strip()
        if not netlist_text:
            QMessageBox.warning(self, "Netlist vacio", "Pega el contenido del netlist antes de guardar.")
            return

        saved_path = self._store_pasted_netlist(file_name_edit.text(), netlist_text)
        self.load_netlist_path(str(saved_path))
        self.edit_netlist_btn.setChecked(True)
        self._append_log(f"Pasted netlist saved to: {saved_path}\n")

    def _store_pasted_netlist(self, requested_name: str, netlist_text: str) -> Path:
        outputs = self.outputs_getter()
        netlists_dir = outputs.runs / "netlists"
        netlists_dir.mkdir(parents=True, exist_ok=True)

        base_name = self._short_name(Path(requested_name.strip() or "net").stem or "net", max_length=12)
        netlist_path = netlists_dir / f"{base_name}.spice"
        if netlist_path.exists():
            netlist_path = netlists_dir / f"{base_name}-{self._compact_timestamp()}.spice"
        netlist_path.write_text(netlist_text.rstrip() + "\n")
        return netlist_path

    def _show_log_dialog(self) -> None:
        if self.log_dialog is None:
            self.log_dialog = QDialog(self)
            self.log_dialog.setWindowTitle("Simulation Log")
            self.log_dialog.resize(900, 700)
            dialog_layout = QVBoxLayout(self.log_dialog)
            self.log_viewer = QTextEdit()
            self.log_viewer.setReadOnly(True)
            clear_btn = QPushButton("Clear log")
            clear_btn.clicked.connect(self._clear_log_views)
            dialog_layout.addWidget(self.log_viewer)
            dialog_layout.addWidget(clear_btn)

        if self.log_viewer is not None:
            self.log_viewer.setPlainText(self.log.toPlainText())
        self.log_dialog.show()
        self.log_dialog.raise_()
        self.log_dialog.activateWindow()

    def _clear_log_views(self) -> None:
        self.log.clear()
        if self.log_viewer is not None:
            self.log_viewer.clear()

    def _append_log(self, text: str) -> None:
        append_log(self.log, text)
        if self.log_viewer is not None:
            append_log(self.log_viewer, text)

    def _set_simulation_running(self, running: bool) -> None:
        self.run_btn.setDisabled(running)
        self.rerun_btn.setDisabled(running)
        self.stop_btn.setEnabled(running)
        self.loading_bar.setVisible(running)

    def _ensure_editor_content(self) -> str:
        if self.file_view.toPlainText().strip():
            return self.file_view.toPlainText()

        netlist_path = self.netlist_edit.text().strip()
        if not netlist_path:
            return ""

        try:
            contents = Path(netlist_path).read_text()
        except OSError as exc:
            self._append_log(f"Failed to read file: {exc}\n")
            return ""

        self.file_view.setPlainText(contents)
        self._refresh_probe_points()
        return contents

    @staticmethod
    def _format_timestamp(raw_path: Path) -> str:
        return datetime.fromtimestamp(raw_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
        return cleaned.strip("_") or "simulation"

    @classmethod
    def _short_name(cls, value: str, max_length: int = 12) -> str:
        return cls._safe_name(value)[:max_length].rstrip("_") or "sim"

    @staticmethod
    def _compact_timestamp() -> str:
        return datetime.now().strftime("%y%m%d-%H%M")

    def _analysis_type_key(self) -> str:
        mapping = {
            pick(self.lang, "Transitorio", "Transient"): "Transient",
            "AC": "AC",
            "DC": "DC",
            pick(self.lang, "Punto de operación", "Operating Point"): "Operating Point",
        }
        return mapping.get(self.sim_type.currentText(), "Transient")

    def _save_mode_key(self) -> str:
        mapping = {
            pick(self.lang, "Todas las señales", "All signals"): "All signals",
            pick(self.lang, "Sólo probes seleccionados", "Selected probes only"): "Selected probes only",
        }
        return mapping.get(self.save_mode.currentText(), "All signals")

    def _spectrum_mode_key(self) -> str:
        mapping = {
            pick(self.lang, "Auto", "Auto"): "Auto",
            pick(self.lang, "Mostrar", "Show"): "Show",
            pick(self.lang, "Ocultar", "Hide"): "Hide",
        }
        return mapping.get(self.spectrum_mode.currentText(), "Auto")

    def _spectrum_x_axis_key(self) -> str:
        mapping = {
            pick(self.lang, "Hz lineal", "Linear Hz"): "linear",
            pick(self.lang, "Hz log", "Log Hz"): "log",
        }
        return mapping.get(self.spectrum_x_axis.currentText(), "linear")
