"""Simulation tab UI and ngspice workflow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
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
from app.core.settings_manager import AppSettings
from app.runners.ngspice_runner import NgspiceRunner
from app.ui.waveform_viewer import WaveformViewer
from app.ui.widgets import append_log


class SimulationTab(QWidget):
    """Run and inspect ngspice simulations."""

    send_status = Signal(str)

    def __init__(self, settings: AppSettings, project_dir_getter) -> None:
        super().__init__()
        self.settings = settings
        self.project_dir_getter = project_dir_getter
        self.runner = CommandRunner()
        self.builder = NgspiceRunner(settings)

        self.netlist_edit = QLineEdit()
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.file_view = QTextEdit()
        self.wave = WaveformViewer()

        self.run_btn = QPushButton("Run")
        self.stop_btn = QPushButton("Stop")
        self.rerun_btn = QPushButton("Re-run")
        self.clear_btn = QPushButton("Clear log")

        self._last_command: list[str] = []

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

        project = Path(self.project_dir_getter() or Path(netlist).parent)
        logs = project / "logs"
        results = project / "results"
        logs.mkdir(parents=True, exist_ok=True)
        results.mkdir(parents=True, exist_ok=True)

        log_path = str(logs / "ngspice.log")
        raw_path = str(results / "sim.raw")
        cmd = self.builder.run_spec(netlist, log_path, raw_path)
        self._last_command = cmd
        self.send_status.emit("Simulation running")
        self.runner.run(self.builder.build(cmd, cwd=str(project)))

    def rerun(self) -> None:
        if not self._last_command:
            self.run()
            return
        self.send_status.emit("Simulation running")
        self.runner.run(self.builder.build(self._last_command))

    def _finished(self, code: int, status: str) -> None:
        summary = f"\nSimulation finished: exit={code} status={status}\n"
        append_log(self.log, summary)
        full_text = self.log.toPlainText()
        if LogParser.has_errors(full_text) or code != 0:
            self.send_status.emit("Simulation failed")
        else:
            self.send_status.emit("Simulation completed")
