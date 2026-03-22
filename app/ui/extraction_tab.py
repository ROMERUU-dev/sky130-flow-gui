"""Magic extraction/post-layout tab."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices
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

    def __init__(self, settings: AppSettings, outputs_getter) -> None:
        super().__init__()
        self.settings = settings
        self.outputs_getter = outputs_getter
        self.builder = MagicRunner(settings)
        self.runner = CommandRunner()

        self.top_cell = QLineEdit()
        self.script_path = QLineEdit()
        self.output_dir = QLineEdit()
        self.output_dir.setReadOnly(True)
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self._out_netlist = ""
        self._build_ui()
        self._wire()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("Top Cell", self.top_cell)

        row_script = QHBoxLayout()
        row_script.addWidget(self.script_path)
        bs = QPushButton("Browse")
        bs.clicked.connect(self._pick_script)
        row_script.addWidget(bs)
        form.addRow("Magic Script (optional)", row_script)

        row_out = QHBoxLayout()
        row_out.addWidget(self.output_dir)
        bout = QPushButton("Open Output Folder")
        bout.clicked.connect(self.open_output_folder)
        row_out.addWidget(bout)
        form.addRow("Output Dir", row_out)

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

    def _pick_script(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Select magic script", "", "Tcl (*.tcl)")
        if p:
            self.script_path.setText(p)

    def run(self) -> None:
        outputs = self.outputs_getter()
        self.output_dir.setText(str(outputs.extraction))

        top = self.top_cell.text().strip() or "top"
        cmd, script, self._out_netlist = self.builder.run_spec(
            outputs=outputs,
            top_cell=top,
            script_path=self.script_path.text().strip() or None,
            rcfile=self.settings.pdk_paths.magic_rc or None,
        )
        append_log(self.log, f"Output folder: {outputs.extraction}\nScript: {script}\nNetlist: {self._out_netlist}\n")

        self.send_status.emit("Extraction running")
        self.runner.run(self.builder.build(cmd, cwd=str(outputs.base)))

    def _finished(self, code: int, _status: str) -> None:
        if code == 0:
            self.send_status.emit("Extraction complete")
            append_log(self.log, f"\nExtracted netlist: {self._out_netlist}\n")
        else:
            self.send_status.emit("Extraction failed")

    def _send_result(self) -> None:
        if self._out_netlist:
            self.netlist_ready.emit(self._out_netlist)

    def open_output_folder(self) -> None:
        if self.output_dir.text().strip():
            QDesktopServices.openUrl(Path(self.output_dir.text().strip()).as_uri())
