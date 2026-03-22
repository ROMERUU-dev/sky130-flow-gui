"""LVS tab UI and netgen workflow."""

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
from app.core.log_parser import LogParser
from app.core.settings_manager import AppSettings
from app.runners.lvs_runner import LvsRunner
from app.ui.widgets import append_log


class LvsTab(QWidget):
    """Run netgen LVS and summarize result."""

    send_status = Signal(str)

    def __init__(self, settings: AppSettings, project_dir_getter) -> None:
        super().__init__()
        self.settings = settings
        self.project_dir_getter = project_dir_getter
        self.builder = LvsRunner(settings)
        self.runner = CommandRunner()

        self.layout_edit = QLineEdit()
        self.schematic_edit = QLineEdit()
        self.setup_edit = QLineEdit(settings.pdk_paths.netgen_setup)
        self.summary = QLineEdit()
        self.summary.setReadOnly(True)
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self._build_ui()
        self._wire()

    def _file_row(self, edit: QLineEdit, title: str, filt: str = "All Files (*)") -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(edit)
        b = QPushButton("Browse")
        b.clicked.connect(lambda: self._pick(edit, title, filt))
        row.addWidget(b)
        return row

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Layout/Extracted Netlist", self._file_row(self.layout_edit, "Select layout netlist", "Netlist (*.spice *.sp *.cir)"))
        form.addRow("Schematic Netlist", self._file_row(self.schematic_edit, "Select schematic netlist", "Netlist (*.spice *.sp *.cir)"))
        form.addRow("Netgen Setup Tcl", self._file_row(self.setup_edit, "Select netgen setup", "Tcl (*.tcl);;All Files (*)"))
        layout.addLayout(form)

        btns = QHBoxLayout()
        run = QPushButton("Run")
        stop = QPushButton("Stop")
        clear = QPushButton("Clear log")
        save = QPushButton("Export Report")
        btns.addWidget(run)
        btns.addWidget(stop)
        btns.addWidget(clear)
        btns.addWidget(save)
        layout.addLayout(btns)

        run.clicked.connect(self.run)
        stop.clicked.connect(self.runner.stop)
        clear.clicked.connect(self.log.clear)
        save.clicked.connect(self.export_report)

        layout.addWidget(self.summary)
        layout.addWidget(self.log)

    def _wire(self) -> None:
        self.runner.started.connect(lambda cmd: append_log(self.log, f"\n$ {cmd}\n"))
        self.runner.line_output.connect(lambda txt: append_log(self.log, txt))
        self.runner.finished.connect(self._finished)

    def _pick(self, edit: QLineEdit, title: str, filt: str) -> None:
        p, _ = QFileDialog.getOpenFileName(self, title, "", filt)
        if p:
            edit.setText(p)

    def run(self) -> None:
        project = Path(self.project_dir_getter() or ".")
        report = str(project / "results" / "lvs_report.log")
        cmd = self.builder.run_spec(self.layout_edit.text(), self.schematic_edit.text(), self.setup_edit.text(), report)
        self.send_status.emit("LVS running")
        self.runner.run(self.builder.build(cmd, cwd=str(project)))

    def _finished(self, code: int, _status: str) -> None:
        text = self.log.toPlainText()
        summary = LogParser.lvs_summary(text)
        if code != 0:
            summary = "LVS failed"
        self.summary.setText(summary)
        self.send_status.emit(summary)

    def export_report(self) -> None:
        out, _ = QFileDialog.getSaveFileName(self, "Save LVS report", "lvs_report.txt", "Text (*.txt)")
        if out:
            Path(out).write_text(self.log.toPlainText())
