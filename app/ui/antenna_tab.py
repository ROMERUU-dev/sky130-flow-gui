"""KLayout antenna check tab."""

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
from app.core.i18n import pick
from app.core.log_parser import LogParser
from app.core.settings_manager import AppSettings
from app.runners.antenna_runner import AntennaRunner
from app.ui.widgets import append_log


class AntennaTab(QWidget):
    """Run KLayout antenna checks in batch mode."""

    send_status = Signal(str)

    def __init__(self, settings: AppSettings, outputs_getter) -> None:
        super().__init__()
        self.settings = settings
        self.lang = settings.language
        self.outputs_getter = outputs_getter
        self.builder = AntennaRunner(settings)
        self.runner = CommandRunner()

        self.gds_edit = QLineEdit()
        self.deck_edit = QLineEdit(settings.pdk_paths.klayout_antenna_deck)
        self.top_cell_edit = QLineEdit()
        self.output_dir = QLineEdit()
        self.output_dir.setReadOnly(True)
        self.summary = QLineEdit()
        self.summary.setReadOnly(True)
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self._build_ui()
        self._wire()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow(pick(self.lang, "Archivo GDS", "GDS File"), self._row_file(self.gds_edit, pick(self.lang, "Selecciona GDS", "Select GDS"), "GDS (*.gds *.gdsii);;All Files (*)"))
        form.addRow(pick(self.lang, "Deck de antena", "Antenna Deck"), self._row_file(self.deck_edit, pick(self.lang, "Selecciona deck de antena", "Select antenna deck"), "Ruby/Tcl (*.rb *.tcl);;All Files (*)"))
        form.addRow(pick(self.lang, "Celda top", "Top Cell"), self.top_cell_edit)

        out_row = QHBoxLayout()
        out_row.addWidget(self.output_dir)
        open_btn = QPushButton(pick(self.lang, "Abrir carpeta de salida", "Open Output Folder"))
        open_btn.clicked.connect(self.open_output_folder)
        out_row.addWidget(open_btn)
        form.addRow(pick(self.lang, "Directorio de salida", "Output Dir"), out_row)

        layout.addLayout(form)

        btns = QHBoxLayout()
        run = QPushButton(pick(self.lang, "Correr", "Run"))
        stop = QPushButton(pick(self.lang, "Detener", "Stop"))
        clear = QPushButton(pick(self.lang, "Limpiar log", "Clear log"))
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
        b = QPushButton(pick(self.lang, "Buscar", "Browse"))
        b.clicked.connect(lambda: self._pick(edit, title, filt))
        row.addWidget(b)
        return row

    def _pick(self, edit: QLineEdit, title: str, filt: str) -> None:
        p, _ = QFileDialog.getOpenFileName(self, title, "", filt)
        if p:
            edit.setText(p)

    def run(self) -> None:
        outputs = self.outputs_getter()
        self.output_dir.setText(str(outputs.antenna))

        cmd, report = self.builder.run_spec(self.gds_edit.text(), self.deck_edit.text(), outputs, self.top_cell_edit.text().strip())
        append_log(
            self.log,
            f"{pick(self.lang, 'Carpeta de salida', 'Output folder')}: {outputs.antenna}\n"
            f"{pick(self.lang, 'Reporte', 'Report')}: {report}\n",
        )

        self.send_status.emit(pick(self.lang, "Chequeo de antena corriendo", "Antenna check running"))
        self.runner.run(self.builder.build(cmd, cwd=str(outputs.base)))

    def _finished(self, code: int, _status: str) -> None:
        text = self.log.toPlainText()
        summary = LogParser.antenna_summary(text)
        if code != 0:
            summary = pick(self.lang, "Chequeo de antena falló", "Antenna check failed")
        self.summary.setText(summary)
        self.send_status.emit(summary)

    def open_output_folder(self) -> None:
        if self.output_dir.text().strip():
            QDesktopServices.openUrl(Path(self.output_dir.text().strip()).as_uri())
