"""Magic extraction/post-layout tab."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.command_runner import CommandRunner
from app.core.i18n import pick
from app.core.layout_tools import infer_top_cell, resolve_layout_dir
from app.core.magic_launcher import MagicLaunchBuilder
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
        self.lang = settings.language
        self.outputs_getter = outputs_getter
        self.builder = MagicRunner(settings)
        self.launch_builder = MagicLaunchBuilder(settings)
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

        form.addRow(pick(self.lang, "Celda top", "Top Cell"), self.top_cell)

        row_script = QHBoxLayout()
        row_script.addWidget(self.script_path)
        bs = QPushButton(pick(self.lang, "Buscar", "Browse"))
        bs.clicked.connect(self._pick_script)
        row_script.addWidget(bs)
        form.addRow(pick(self.lang, "Script de Magic (opcional)", "Magic Script (optional)"), row_script)

        row_out = QHBoxLayout()
        row_out.addWidget(self.output_dir)
        bout = QPushButton(pick(self.lang, "Abrir carpeta de salida", "Open Output Folder"))
        bout.clicked.connect(self.open_output_folder)
        row_out.addWidget(bout)
        form.addRow(pick(self.lang, "Directorio de salida", "Output Dir"), row_out)

        layout.addLayout(form)

        btns = QHBoxLayout()
        run = QPushButton(pick(self.lang, "Correr", "Run"))
        stop = QPushButton(pick(self.lang, "Detener", "Stop"))
        open_selected_mag = QPushButton(pick(self.lang, "Abrir .mag actual", "Open current .mag"))
        send = QPushButton(pick(self.lang, "Enviar resultado a Simulación", "Send result to Simulation"))
        btns.addWidget(run)
        btns.addWidget(stop)
        btns.addWidget(open_selected_mag)
        btns.addWidget(send)
        layout.addLayout(btns)

        run.clicked.connect(self.run)
        stop.clicked.connect(self.runner.stop)
        open_selected_mag.clicked.connect(self.open_selected_mag)
        send.clicked.connect(self._send_result)

        layout.addWidget(self.log)

    def _wire(self) -> None:
        self.runner.started.connect(lambda cmd: append_log(self.log, f"\n$ {cmd}\n"))
        self.runner.line_output.connect(lambda txt: append_log(self.log, txt))
        self.runner.finished.connect(self._finished)

    def _pick_script(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, pick(self.lang, "Selecciona script de Magic", "Select magic script"), "", "Tcl (*.tcl)")
        if p:
            self.script_path.setText(p)

    def run(self) -> None:
        outputs = self.outputs_getter()
        self.output_dir.setText(str(outputs.extraction))

        layout_dir = resolve_layout_dir(outputs.base)
        top = self.top_cell.text().strip() or infer_top_cell(layout_dir) or "top"
        if not self.top_cell.text().strip():
            self.top_cell.setText(top)
        cmd, script, self._out_netlist = self.builder.run_spec(
            outputs=outputs,
            top_cell=top,
            script_path=self.script_path.text().strip() or None,
            rcfile=self.settings.pdk_paths.magic_rc or None,
        )
        append_log(
            self.log,
            f"{pick(self.lang, 'Carpeta de salida', 'Output folder')}: {outputs.extraction}\n"
            f"{pick(self.lang, 'Directorio de layout', 'Layout directory')}: {layout_dir}\n"
            f"{pick(self.lang, 'Script', 'Script')}: {script}\n"
            f"{pick(self.lang, 'Netlist', 'Netlist')}: {self._out_netlist}\n",
        )

        self.send_status.emit(pick(self.lang, "Extracción corriendo", "Extraction running"))
        self.runner.run(self.builder.build(cmd, cwd=str(layout_dir)))

    def _finished(self, code: int, _status: str) -> None:
        extracted_path = Path(self._out_netlist) if self._out_netlist else None
        if code == 0 and extracted_path and extracted_path.exists() and extracted_path.is_file():
            self.send_status.emit(pick(self.lang, "Extracción finalizada", "Extraction finished"))
            append_log(
                self.log,
                f"\n{pick(self.lang, 'Extracción finalizada', 'Extraction finished')}\n"
                f"{pick(self.lang, 'Netlist extraído', 'Extracted netlist')}: {self._out_netlist}\n",
            )
        else:
            self.send_status.emit(pick(self.lang, "Extracción falló", "Extraction failed"))
            if code == 0 and extracted_path:
                append_log(
                    self.log,
                    f"\n{pick(self.lang, 'Magic terminó pero no generó el netlist SPICE esperado.', 'Magic finished but did not generate the expected SPICE netlist.')}\n"
                    f"{pick(self.lang, 'Esperado en', 'Expected at')}: {self._out_netlist}\n",
                )

    def _send_result(self) -> None:
        if self._out_netlist:
            self.netlist_ready.emit(self._out_netlist)

    def open_output_folder(self) -> None:
        if self.output_dir.text().strip():
            QDesktopServices.openUrl(Path(self.output_dir.text().strip()).as_uri())

    def open_selected_mag(self) -> None:
        outputs = self.outputs_getter()
        layout_dir = resolve_layout_dir(outputs.base)
        top = self.top_cell.text().strip() or infer_top_cell(layout_dir)
        if not top:
            QMessageBox.warning(
                self,
                pick(self.lang, "Sin layout", "No layout"),
                pick(
                    self.lang,
                    "No se encontró una celda .mag para abrir. Define la celda top o agrega un layout válido.",
                    "No .mag cell was found to open. Set the top cell or add a valid layout first.",
                ),
            )
            return

        mag_path = layout_dir / f"{top}.mag"
        if not mag_path.is_file():
            QMessageBox.warning(
                self,
                pick(self.lang, "Archivo no encontrado", "File not found"),
                pick(
                    self.lang,
                    f"No existe el archivo de layout esperado: {mag_path}",
                    f"The expected layout file does not exist: {mag_path}",
                ),
            )
            return

        self.top_cell.setText(top)
        self._launch_magic(str(mag_path))

    def _launch_magic(self, target_path: str) -> None:
        launch = self.launch_builder.build(target_path)
        try:
            subprocess.Popen(launch.command, cwd=launch.cwd, env=launch.env)
        except OSError as exc:
            QMessageBox.warning(
                self,
                pick(self.lang, "Error al abrir", "Launch error"),
                f"{pick(self.lang, 'No se pudo abrir Magic', 'Failed to launch Magic')}: {exc}",
            )
            return

        append_log(
            self.log,
            f"\n{pick(self.lang, 'Magic abierto', 'Magic launched')}\n"
            f"{pick(self.lang, 'Objetivo', 'Target')}: {target_path}\n"
            f"{pick(self.lang, 'Comando', 'Command')}: {' '.join(launch.command)}\n"
            f"{pick(self.lang, 'Directorio', 'Working directory')}: {launch.cwd or '-'}\n",
        )
        self.send_status.emit(pick(self.lang, "Magic abierto", "Magic launched"))
