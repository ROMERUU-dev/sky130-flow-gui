"""LVS tab UI and netgen workflow."""

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
from app.runners.lvs_runner import LvsRunner
from app.ui.widgets import append_log


class LvsTab(QWidget):
    """Run netgen LVS and summarize result."""

    send_status = Signal(str)

    def __init__(self, settings: AppSettings, outputs_getter) -> None:
        super().__init__()
        self.settings = settings
        self.lang = settings.language
        self.outputs_getter = outputs_getter
        self.builder = LvsRunner(settings)
        self.runner = CommandRunner()

        self.layout_edit = QLineEdit()
        self.schematic_edit = QLineEdit()
        self.setup_edit = QLineEdit(settings.pdk_paths.netgen_setup)
        self.output_dir = QLineEdit()
        self.output_dir.setReadOnly(True)
        self.summary = QLineEdit()
        self.summary.setReadOnly(True)
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self._build_ui()
        self._wire()

    def _file_row(self, edit: QLineEdit, title: str, filt: str = "All Files (*)") -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(edit)
        b = QPushButton(pick(self.lang, "Buscar", "Browse"))
        b.clicked.connect(lambda: self._pick(edit, title, filt))
        row.addWidget(b)
        return row

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow(
            pick(self.lang, "Netlist de layout / extracción", "Layout/Extracted Netlist"),
            self._file_row(self.layout_edit, pick(self.lang, "Selecciona netlist de layout", "Select layout netlist"), "Netlist (*.spice *.sp *.cir)"),
        )
        form.addRow(
            pick(self.lang, "Netlist esquemático", "Schematic Netlist"),
            self._file_row(self.schematic_edit, pick(self.lang, "Selecciona netlist esquemático", "Select schematic netlist"), "Netlist (*.spice *.sp *.cir)"),
        )
        form.addRow(
            pick(self.lang, "Setup Tcl de netgen", "Netgen Setup Tcl"),
            self._file_row(self.setup_edit, pick(self.lang, "Selecciona setup de netgen", "Select netgen setup"), "Tcl (*.tcl);;All Files (*)"),
        )

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
        save = QPushButton(pick(self.lang, "Exportar reporte", "Export Report"))
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
        outputs = self.outputs_getter()
        self.output_dir.setText(str(outputs.lvs))
        cmd, report = self.builder.run_spec(self.layout_edit.text(), self.schematic_edit.text(), self.setup_edit.text(), outputs)
        append_log(
            self.log,
            f"{pick(self.lang, 'Carpeta de salida', 'Output folder')}: {outputs.lvs}\n"
            f"{pick(self.lang, 'Reporte', 'Report')}: {report}\n",
        )
        self.send_status.emit(pick(self.lang, "LVS corriendo", "LVS running"))
        self.runner.run(self.builder.build(cmd, cwd=str(outputs.base)))

    def _finished(self, code: int, _status: str) -> None:
        text = self.log.toPlainText()
        summary = LogParser.lvs_summary(text)
        if code != 0:
            summary = pick(self.lang, "LVS falló", "LVS failed")
        self.summary.setText(summary)
        self.send_status.emit(summary)

    def export_report(self) -> None:
        out, _ = QFileDialog.getSaveFileName(
            self,
            pick(self.lang, "Guardar reporte LVS", "Save LVS report"),
            "lvs_report.txt",
            "Text (*.txt)",
        )
        if out:
            Path(out).write_text(self.log.toPlainText())

    def open_output_folder(self) -> None:
        if self.output_dir.text().strip():
            QDesktopServices.openUrl(Path(self.output_dir.text().strip()).as_uri())
