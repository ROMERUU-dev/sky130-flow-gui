"""Simulation tab UI and ngspice workflow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.command_runner import CommandRunner
from app.core.log_parser import LogParser
from app.core.ngspice_raw_parser import NgspiceRawParser
from app.core.output_manager import OutputPaths
from app.core.settings_manager import AppSettings
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
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.file_view = QTextEdit()
        self.wave = WaveformViewer()

        self.run_btn = QPushButton("Run")
        self.stop_btn = QPushButton("Stop")
        self.rerun_btn = QPushButton("Re-run")
        self.clear_btn = QPushButton("Clear log")
        self.open_out_btn = QPushButton("Open Output Folder")

        self._last_command: list[str] = []
        self._last_outputs: OutputPaths | None = None
        self._last_raw_path: Path | None = None

        self._build_ui()
        self._wire()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("Netlist:"))
        row.addWidget(self.netlist_edit)
        pick = QPushButton("Browse")
        pick.clicked.connect(self._pick_file)
        row.addWidget(pick)
        layout.addLayout(row)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output Dir:"))
        out_row.addWidget(self.output_dir)
        out_row.addWidget(self.open_out_btn)
        layout.addLayout(out_row)

        btns = QHBoxLayout()
        btns.addWidget(self.run_btn)
        btns.addWidget(self.stop_btn)
        btns.addWidget(self.rerun_btn)
        btns.addWidget(self.clear_btn)
        layout.addLayout(btns)

        layout.addWidget(QLabel("Netlist Viewer:"))
        self.file_view.setPlaceholderText("Loaded netlist content appears here...")
        layout.addWidget(self.file_view)
        layout.addWidget(self.wave)

        layout.addWidget(QLabel("Simulation Log:"))
        layout.addWidget(self.log)

    def _wire(self) -> None:
        self.run_btn.clicked.connect(self.run)
        self.stop_btn.clicked.connect(self.runner.stop)
        self.rerun_btn.clicked.connect(self.rerun)
        self.clear_btn.clicked.connect(self.log.clear)
        self.open_out_btn.clicked.connect(self.open_output_folder)

        self.runner.started.connect(lambda cmd: append_log(self.log, f"\n$ {cmd}\n"))
        self.runner.line_output.connect(lambda txt: append_log(self.log, txt))
        self.runner.finished.connect(self._finished)

    def _pick_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select netlist", "", "SPICE Files (*.spice *.sp *.cir)")
        if not file_path:
            return
        self.netlist_edit.setText(file_path)
        try:
            self.file_view.setPlainText(Path(file_path).read_text())
        except OSError as exc:
            append_log(self.log, f"Failed to read file: {exc}\n")

    def run(self) -> None:
        netlist = self.netlist_edit.text().strip()
        if not netlist:
            append_log(self.log, "Select a netlist first.\n")
            return

        outputs = self.outputs_getter()
        self._last_outputs = outputs
        self.output_dir.setText(str(outputs.results))

        cmd, log_path, raw_path = self.builder.run_spec(netlist, outputs)
        append_log(self.log, f"Output folder: {outputs.results}\nLog file: {log_path}\n")
        self._last_command = cmd
        self._last_raw_path = Path(raw_path)
        self.wave.set_signals({})
        self.send_status.emit("Simulation running")
        self.runner.run(self.builder.build(cmd, cwd=str(outputs.base)))

    def rerun(self) -> None:
        if not self._last_command:
            self.run()
            return
        self.send_status.emit("Simulation running")
        self.runner.run(self.builder.build(self._last_command, cwd=str(self._last_outputs.base) if self._last_outputs else None))

    def _finished(self, code: int, status: str) -> None:
        summary = f"\nSimulation finished: exit={code} status={status}\n"
        append_log(self.log, summary)
        full_text = self.log.toPlainText()
        if LogParser.has_errors(full_text) or code != 0:
            self.send_status.emit("Simulation failed")
        else:
            self._load_waveforms()
            self.send_status.emit("Simulation completed")

    def open_output_folder(self) -> None:
        if self.output_dir.text().strip():
            QDesktopServices.openUrl(Path(self.output_dir.text().strip()).as_uri())

    def _load_waveforms(self) -> None:
        raw_path = self._resolve_raw_path()
        if not raw_path:
            append_log(self.log, "No waveform raw file was found after simulation.\n")
            self.wave.set_signals({})
            return

        try:
            signals = NgspiceRawParser.load_signals(raw_path)
        except (OSError, ValueError) as exc:
            append_log(self.log, f"Failed to load waveform data: {exc}\n")
            self.wave.set_signals({})
            return

        self.wave.set_signals(signals)
        append_log(self.log, f"Loaded waveform data from: {raw_path}\n")

    def _resolve_raw_path(self) -> Path | None:
        candidates: list[Path] = []
        if self._last_raw_path:
            candidates.append(self._last_raw_path)
        if self._last_outputs:
            candidates.extend(sorted(self._last_outputs.results.glob("*.raw")))
            candidates.extend(sorted(self._last_outputs.base.glob("*.raw")))

        seen: set[Path] = set()
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if candidate.exists() and candidate.is_file():
                return candidate
        return None
