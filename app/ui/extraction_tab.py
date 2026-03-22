"""Magic extraction/post-layout tab."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.command_runner import CommandRunner
from app.core.settings_manager import AppSettings
from app.runners.magic_runner import MagicRunner
from app.ui.widgets import append_log


class ExtractionTab(QWidget):
    """Run magic-based extraction in batch mode."""

    send_status = Signal(str)
    netlist_ready = Signal(str)

    def __init__(self, settings: AppSettings, project_dir_getter) -> None:
        super().__init__()
        self.settings = settings
        self.project_dir_getter = project_dir_getter
        self.builder = MagicRunner(settings)
        self.runner = CommandRunner()

        self.top_cell = QLineEdit()
        self.script_path = QLineEdit()
        self.layout_dir = QLineEdit()
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self._out_netlist = ""
        self._build_ui()
        self._wire()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        row_dir = QHBoxLayout()
        row_dir.addWidget(self.layout_dir)
        bdir = QPushButton("Browse")
        bdir.clicked.connect(self._pick_dir)
        row_dir.addWidget(bdir)
        form.addRow("Project/Layout Dir", row_dir)

        form.addRow("Top Cell", self.top_cell)

        row_script = QHBoxLayout()
        row_script.addWidget(self.script_path)
        bs = QPushButton("Browse")
        bs.clicked.connect(self._pick_script)
        row_script.addWidget(bs)
        form.addRow("Magic Script (optional)", row_script)

        layout.addLayout(form)

        btns = QHBoxLayout()
        run = QPushButton("Run")
        stop = QPushButton("Stop")
        send = QPushButton("Send result to Simulation")
        btns.addWidget(run)
        btns.addWidget(stop)
        btns.addWidget(send)
        layout.addLayout(btns)

        run.clicked.connect(self.run)
        stop.clicked.connect(self.runner.stop)
        send.clicked.connect(self._send_result)

        layout.addWidget(self.log)

    def _wire(self) -> None:
        self.runner.started.connect(lambda cmd: append_log(self.log, f"\n$ {cmd}\n"))
        self.runner.line_output.connect(lambda txt: append_log(self.log, txt))
        self.runner.finished.connect(self._finished)

    def _pick_dir(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Select layout directory")
        if p:
            self.layout_dir.setText(p)

    def _pick_script(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Select magic script", "", "Tcl (*.tcl)")
        if p:
            self.script_path.setText(p)

    def run(self) -> None:
        project = Path(self.project_dir_getter() or self.layout_dir.text() or ".")
        project.mkdir(parents=True, exist_ok=True)
        results = project / "results"
        scripts = project / "scripts"
        results.mkdir(parents=True, exist_ok=True)
        scripts.mkdir(parents=True, exist_ok=True)

        top = self.top_cell.text().strip() or "top"
        self._out_netlist = str(results / f"{top}_extracted.spice")
        script = self.script_path.text().strip() or str(scripts / "extract_magic.tcl")

        if not self.script_path.text().strip():
            self.builder.create_extraction_script(script, top, self._out_netlist)

        cmd = self.builder.run_spec(script, rcfile=self.settings.pdk_paths.magic_rc or None, cwd=str(project))
        self.send_status.emit("Extraction running")
        self.runner.run(self.builder.build(cmd, cwd=str(project)))

    def _finished(self, code: int, _status: str) -> None:
        if code == 0:
            self.send_status.emit("Extraction complete")
            append_log(self.log, f"\nExtracted netlist: {self._out_netlist}\n")
        else:
            self.send_status.emit("Extraction failed")

    def _send_result(self) -> None:
        if self._out_netlist:
            self.netlist_ready.emit(self._out_netlist)
