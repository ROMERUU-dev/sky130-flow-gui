"""KLayout antenna check tab."""

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
from app.runners.antenna_runner import AntennaRunner
from app.ui.widgets import append_log


class AntennaTab(QWidget):
    """Run KLayout antenna checks in batch mode."""

    send_status = Signal(str)

    def __init__(self, settings: AppSettings, project_dir_getter) -> None:
        super().__init__()
        self.settings = settings
        self.project_dir_getter = project_dir_getter
        self.builder = AntennaRunner(settings)
        self.runner = CommandRunner()

        self.gds_edit = QLineEdit()
        self.deck_edit = QLineEdit(settings.pdk_paths.klayout_antenna_deck)
        self.top_cell_edit = QLineEdit()
        self.summary = QLineEdit()
        self.summary.setReadOnly(True)
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self._build_ui()
        self._wire()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("GDS File", self._row_file(self.gds_edit, "Select GDS", "GDS (*.gds *.gdsii);;All Files (*)"))
        form.addRow("Antenna Deck", self._row_file(self.deck_edit, "Select antenna deck", "Ruby/Tcl (*.rb *.tcl);;All Files (*)"))
        form.addRow("Top Cell", self.top_cell_edit)
        layout.addLayout(form)

        btns = QHBoxLayout()
        run = QPushButton("Run")
        stop = QPushButton("Stop")
        clear = QPushButton("Clear log")
        btns.addWidget(run)
        btns.addWidget(stop)
        btns.addWidget(clear)
        layout.addLayout(btns)

        run.clicked.connect(self.run)
        stop.clicked.connect(self.runner.stop)
        clear.clicked.connect(self.log.clear)

        layout.addWidget(self.summary)
        layout.addWidget(self.log)

    def _wire(self) -> None:
        self.runner.started.connect(lambda cmd: append_log(self.log, f"\n$ {cmd}\n"))
        self.runner.line_output.connect(lambda txt: append_log(self.log, txt))
        self.runner.finished.connect(self._finished)

    def _row_file(self, edit: QLineEdit, title: str, filt: str):
        row = QHBoxLayout()
        row.addWidget(edit)
        b = QPushButton("Browse")
        b.clicked.connect(lambda: self._pick(edit, title, filt))
        row.addWidget(b)
        return row

    def _pick(self, edit: QLineEdit, title: str, filt: str) -> None:
        p, _ = QFileDialog.getOpenFileName(self, title, "", filt)
        if p:
            edit.setText(p)

    def run(self) -> None:
        project = Path(self.project_dir_getter() or ".")
        report = str(project / "results" / "antenna_report.txt")
        cmd = self.builder.run_spec(self.gds_edit.text(), self.deck_edit.text(), report, self.top_cell_edit.text().strip())
        self.send_status.emit("Antenna check running")
        self.runner.run(self.builder.build(cmd, cwd=str(project)))

    def _finished(self, code: int, _status: str) -> None:
        text = self.log.toPlainText()
        summary = LogParser.antenna_summary(text)
        if code != 0:
            summary = "Antenna check failed"
        self.summary.setText(summary)
        self.send_status.emit(summary)
