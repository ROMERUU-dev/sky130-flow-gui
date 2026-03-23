"""Simulation tab UI and ngspice workflow."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.command_runner import CommandRunner
from app.core.log_parser import LogParser
from app.core.ngspice_raw_parser import NgspiceRawParser
from app.core.output_manager import OutputPaths
from app.core.settings_manager import AppSettings
from app.core.spice_tools import (
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
        self.file_view.setPlaceholderText("Load a netlist, tweak it here, and the original file will remain untouched.")
        self.extra_directives = QTextEdit()
        self.extra_directives.setPlaceholderText("Optional extra directives (.meas, .ic, .param, etc.)")
        self.wave = WaveformViewer()
        self.spectrum_plot = pg.PlotWidget(title="Frequency Spectrum")
        self.spectrum_plot.setLabel("bottom", "Frequency", units="Hz")
        self.spectrum_plot.setLabel("left", "Magnitude")
        self.spectrum_plot.showGrid(x=True, y=True)
        self.spectrum_plot.hide()

        self.history_select = QComboBox()
        self.history_select.setPlaceholderText("No previous simulations")
        self.load_history_btn = QPushButton("Load Previous")
        self.refresh_history_btn = QPushButton("Refresh History")

        self.run_btn = QPushButton("Run")
        self.stop_btn = QPushButton("Stop")
        self.rerun_btn = QPushButton("Re-run")
        self.show_log_btn = QPushButton("Mostrar log")
        self.open_out_btn = QPushButton("Open Output Folder")
        self.add_probe_btn = QPushButton("Add Probe Point")
        self.refresh_points_btn = QPushButton("Refresh Points")
        self.edit_netlist_btn = QToolButton()
        self.edit_netlist_btn.setText("Modificar netlist (beta)")
        self.edit_netlist_btn.setCheckable(True)
        self.edit_netlist_btn.setChecked(False)

        self.sim_type = QComboBox()
        self.sim_type.addItems(["Transient", "DC"])
        self.sim_stack = QStackedWidget()
        self.content_tabs = QTabWidget()
        self.log_dialog: QDialog | None = None
        self.log_viewer: QTextEdit | None = None

        self.tran_step = QLineEdit("1n")
        self.tran_stop = QLineEdit("1u")
        self.tran_start = QLineEdit("0")

        self.ac_sweep = QComboBox()
        self.ac_sweep.addItems(["dec", "lin", "oct"])
        self.ac_points = QLineEdit("20")
        self.ac_start = QLineEdit("1")
        self.ac_stop = QLineEdit("1G")

        self.dc_source = QLineEdit("V1")
        self.dc_start = QLineEdit("0")
        self.dc_stop = QLineEdit("1.8")
        self.dc_step = QLineEdit("0.01")

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

        self._build_ui()
        self._wire()
        self.refresh_history()
        self._refresh_probe_points()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("Netlist:"))
        row.addWidget(self.netlist_edit)
        pick = QPushButton("Browse")
        pick.clicked.connect(self._pick_file)
        row.addWidget(pick)
        layout.addLayout(row)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Output Dir:"))
        path_row.addWidget(self.output_dir)
        path_row.addWidget(self.open_out_btn)
        layout.addLayout(path_row)

        gen_row = QHBoxLayout()
        gen_row.addWidget(QLabel("Generated Netlist:"))
        gen_row.addWidget(self.generated_path_edit)
        layout.addLayout(gen_row)

        btns = QHBoxLayout()
        btns.addWidget(self.run_btn)
        btns.addWidget(self.stop_btn)
        btns.addWidget(self.rerun_btn)
        btns.addWidget(self.show_log_btn)
        layout.addLayout(btns)

        history_row = QHBoxLayout()
        history_row.addWidget(QLabel("Previous simulations:"))
        history_row.addWidget(self.history_select, 1)
        history_row.addWidget(self.load_history_btn)
        history_row.addWidget(self.refresh_history_btn)
        layout.addLayout(history_row)

        sim_page = QWidget()
        sim_layout = QVBoxLayout(sim_page)
        sim_layout.addWidget(self._build_simulation_setup())
        sim_layout.addWidget(self._build_probe_editor())
        sim_layout.addWidget(self.edit_netlist_btn)
        sim_layout.addWidget(self._build_netlist_editor())

        vis_page = QWidget()
        vis_layout = QVBoxLayout(vis_page)
        vis_layout.addWidget(self.wave)
        vis_layout.addWidget(self._build_measurement_panel())
        vis_layout.addWidget(self.spectrum_plot)

        self.content_tabs.addTab(sim_page, "Simulation")
        self.content_tabs.addTab(vis_page, "Visualization")
        layout.addWidget(self.content_tabs)

    def _build_simulation_setup(self) -> QWidget:
        box = QGroupBox("Simulation Setup")
        form = QFormLayout(box)
        form.addRow("Type:", self.sim_type)

        tran_page = QWidget()
        tran_form = QFormLayout(tran_page)
        tran_form.addRow("Step:", self.tran_step)
        tran_form.addRow("Stop:", self.tran_stop)
        tran_form.addRow("Start:", self.tran_start)

        ac_page = QWidget()
        ac_form = QFormLayout(ac_page)
        ac_form.addRow("Sweep:", self.ac_sweep)
        ac_form.addRow("Points/dec:", self.ac_points)
        ac_form.addRow("Start freq:", self.ac_start)
        ac_form.addRow("Stop freq:", self.ac_stop)

        dc_page = QWidget()
        dc_form = QFormLayout(dc_page)
        dc_form.addRow("Source:", self.dc_source)
        dc_form.addRow("Start:", self.dc_start)
        dc_form.addRow("Stop:", self.dc_stop)
        dc_form.addRow("Step:", self.dc_step)

        self.sim_stack.addWidget(tran_page)
        self.sim_stack.addWidget(ac_page)
        self.sim_stack.addWidget(dc_page)
        form.addRow(self.sim_stack)
        return box

    def _build_probe_editor(self) -> QWidget:
        box = QGroupBox("Probe Points")
        outer = QVBoxLayout(box)
        top = QHBoxLayout()
        top.addWidget(QLabel("Choose nodes or type expressions like v(out) / i(v1):"))
        top.addWidget(self.add_probe_btn)
        top.addWidget(self.refresh_points_btn)
        outer.addLayout(top)

        container = QWidget()
        self.probe_layout = QVBoxLayout(container)
        self.probe_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)
        return box

    def _build_netlist_editor(self) -> QWidget:
        box = QGroupBox("Netlist Editor")
        box.setVisible(False)
        outer = QVBoxLayout(box)
        outer.addWidget(QLabel("Temporary Simulation Netlist Editor:"))
        outer.addWidget(self.file_view)
        outer.addWidget(QLabel("Extra Directives:"))
        outer.addWidget(self.extra_directives)
        self.netlist_editor_box = box
        return box

    def _build_measurement_panel(self) -> QWidget:
        box = QGroupBox("Measurements")
        form = QFormLayout(box)
        form.addRow("Signal:", self.metric_signal)
        form.addRow("Phase reference:", self.metric_reference)
        form.addRow("Min:", self.metric_labels["minimum"])
        form.addRow("Max:", self.metric_labels["maximum"])
        form.addRow("Mean:", self.metric_labels["mean"])
        form.addRow("RMS:", self.metric_labels["rms"])
        form.addRow("Peak-to-peak:", self.metric_labels["peak_to_peak"])
        form.addRow("Amplitude:", self.metric_labels["amplitude"])
        form.addRow("Frequency:", self.metric_labels["frequency_hz"])
        form.addRow("Period:", self.metric_labels["period_s"])
        form.addRow("Phase:", self.metric_labels["phase_deg"])
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
        self.wave.signal_changed.connect(self._sync_metric_selection)
        self.edit_netlist_btn.toggled.connect(self._toggle_netlist_editor)

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

        outputs = self.outputs_getter()
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
        self.spectrum_plot.clear()
        self.spectrum_plot.hide()
        self.refresh_history()
        self.send_status.emit("Simulation running")
        self.runner.run(self.builder.build(cmd, cwd=run_cwd))

    def rerun(self) -> None:
        self.run()

    def _finished(self, code: int, status: str) -> None:
        summary = f"\nSimulation finished: exit={code} status={status}\n"
        self._append_log(summary)
        full_text = self.log.toPlainText()
        if LogParser.has_errors(full_text) or code != 0:
            self.send_status.emit("Simulation failed")
        else:
            self._load_waveforms()
            self.refresh_history()
            self.content_tabs.setCurrentIndex(1)
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
        self._load_waveforms_from_path(Path(raw_path))

    def refresh_history(self) -> None:
        outputs = self.outputs_getter()
        self._last_outputs = outputs
        self.output_dir.setText(str(outputs.results))

        current_path = str(self.history_select.currentData()) if self.history_select.currentData() else None
        raw_files = sorted(outputs.results.glob("*.raw"), key=lambda path: path.stat().st_mtime, reverse=True)

        self.history_select.blockSignals(True)
        self.history_select.clear()
        for raw_file in raw_files:
            label = f"{raw_file.name}  [{self._format_timestamp(raw_file)}]"
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
            self.spectrum_plot.clear()
            self.spectrum_plot.hide()
            return

        try:
            signals = NgspiceRawParser.load_signals(raw_path)
        except (OSError, ValueError) as exc:
            self._append_log(f"Failed to load waveform data: {exc}\n")
            self.wave.set_signals({})
            self._clear_measurements()
            self.spectrum_plot.clear()
            self.spectrum_plot.hide()
            return

        self._last_raw_path = raw_path
        self.wave.set_signals(signals)
        self._refresh_measurement_targets()
        self._update_measurements()
        self._append_log(f"Loaded waveform data from: {raw_path}\n")

    def _resolve_raw_path(self) -> Path | None:
        candidates: list[Path] = []
        if self._last_raw_path:
            candidates.append(self._last_raw_path)
        if self._last_outputs:
            candidates.extend(sorted(self._last_outputs.results.glob("*.raw")))

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
        source_text = self.file_view.toPlainText()
        analysis_type = self.sim_type.currentText()
        params = {
            "tran_step": self.tran_step.text().strip(),
            "tran_stop": self.tran_stop.text().strip(),
            "tran_start": self.tran_start.text().strip(),
            "ac_sweep": self.ac_sweep.currentText(),
            "ac_points": self.ac_points.text().strip(),
            "ac_start": self.ac_start.text().strip(),
            "ac_stop": self.ac_stop.text().strip(),
            "dc_source": self.dc_source.text().strip(),
            "dc_start": self.dc_start.text().strip(),
            "dc_stop": self.dc_stop.text().strip(),
            "dc_step": self.dc_step.text().strip(),
        }
        generated = build_generated_netlist(
            source_text=source_text,
            analysis_type=analysis_type,
            analysis_params=params,
            save_points=self._selected_probe_points(),
            extra_directives=self.extra_directives.toPlainText(),
        )

        stem = Path(self.netlist_edit.text().strip() or "simulation").stem or "simulation"
        generated_path = outputs.results / f"{stem}_generated.spice"
        generated_path.write_text(generated)
        return generated_path

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
            self.spectrum_plot.clear()
            self.spectrum_plot.hide()
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
            self.spectrum_plot.clear()
            self.spectrum_plot.hide()
            return

        self.metric_labels["minimum"].setText(format_value(metrics.minimum, "V"))
        self.metric_labels["maximum"].setText(format_value(metrics.maximum, "V"))
        self.metric_labels["mean"].setText(format_value(metrics.mean, "V"))
        self.metric_labels["rms"].setText(format_value(metrics.rms, "V"))
        self.metric_labels["peak_to_peak"].setText(format_value(metrics.peak_to_peak, "V"))
        self.metric_labels["amplitude"].setText(format_value(metrics.amplitude, "V"))
        if metrics.x_label == "time":
            self.metric_labels["frequency_hz"].setText(format_value(metrics.frequency_hz, "Hz"))
            self.metric_labels["period_s"].setText(format_value(metrics.period_s, "s"))
            self.metric_labels["phase_deg"].setText(format_value(metrics.phase_deg, "deg"))
        else:
            self.metric_labels["frequency_hz"].setText("N/A")
            self.metric_labels["period_s"].setText("N/A")
            self.metric_labels["phase_deg"].setText("N/A")

        self.spectrum_plot.clear()
        if spectrum.frequencies and spectrum.magnitudes:
            self.spectrum_plot.plot(spectrum.frequencies, spectrum.magnitudes, pen=pg.mkPen("#ffb000", width=2))
            self.spectrum_plot.show()
        else:
            self.spectrum_plot.hide()

    def _clear_measurements(self) -> None:
        for label in self.metric_labels.values():
            label.setText("N/A")

    def _toggle_netlist_editor(self, checked: bool) -> None:
        self.netlist_editor_box.setVisible(checked)

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
