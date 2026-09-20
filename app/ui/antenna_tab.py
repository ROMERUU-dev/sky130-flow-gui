"""KLayout antenna check tab."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.command_runner import CommandRunner
from app.core.antenna_tools import detect_antenna_support
from app.core.i18n import pick
from app.core.run_history import KIND_ANTENNA
from app.ui.run_recording import RunRecordingMixin
from app.core.log_parser import LogParser
from app.core.settings_manager import AppSettings
from app.runners.antenna_runner import AntennaRunner
from app.ui.widgets import MAX_LOG_BLOCKS, append_log


class AntennaTab(RunRecordingMixin, QWidget):
    """Run KLayout antenna checks in batch mode."""

    RUN_KIND = KIND_ANTENNA
    ADVISOR_TOOL = "magic"

    send_status = Signal(str)

    def __init__(self, settings: AppSettings, outputs_getter) -> None:
        super().__init__()
        self.settings = settings
        self.lang = settings.language
        self.outputs_getter = outputs_getter
        self.builder = AntennaRunner(settings)
        self.runner = CommandRunner()

        self.support = detect_antenna_support(settings.pdk_paths.sky130a)

        self.engine_combo = QComboBox()
        self.engine_combo.addItem(
            pick(self.lang, "Magic · antennacheck", "Magic · antennacheck"), "magic")
        self.engine_combo.addItem(
            pick(self.lang, "KLayout · deck de reglas", "KLayout · rule deck"), "klayout")
        self.engine_note = QLabel()
        self.engine_note.setObjectName("inlineHint")
        self.engine_note.setWordWrap(True)

        self.gds_edit = QLineEdit()
        self.deck_edit = QLineEdit(settings.pdk_paths.klayout_antenna_deck or self.support.klayout_deck)
        self.top_cell_edit = QLineEdit()
        self.output_dir = QLineEdit()
        self.output_dir.setReadOnly(True)
        self.summary = QLineEdit()
        self.summary.setReadOnly(True)
        self.log = QTextEdit()
        self.log.document().setMaximumBlockCount(MAX_LOG_BLOCKS)
        self.log.setReadOnly(True)
        self._last_report_path = ""

        self._build_ui()
        self._wire()
        self._select_default_engine()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow(pick(self.lang, "Motor", "Engine"), self.engine_combo)
        form.addRow("", self.engine_note)
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
        run.setObjectName("primaryAction")
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

    def _select_default_engine(self) -> None:
        """Pick the engine this PDK actually supports and say why."""
        preferred = self.support.preferred_engine
        index = self.engine_combo.findData("klayout" if preferred == "klayout" else "magic")
        self.engine_combo.setCurrentIndex(max(0, index))
        self.engine_combo.currentIndexChanged.connect(lambda _i: self._sync_engine())
        self._sync_engine()

    def current_engine(self) -> str:
        return str(self.engine_combo.currentData() or "magic")

    def _sync_engine(self) -> None:
        engine = self.current_engine()
        uses_deck = engine == "klayout"
        self.deck_edit.setEnabled(uses_deck)
        if uses_deck and not self.deck_edit.text().strip():
            self.engine_note.setText(
                pick(
                    self.lang,
                    "Este PDK no incluye un deck de antena para KLayout: su deck DRC no trae "
                    "ninguna regla de antena. Selecciona uno manualmente o usa Magic.",
                    "This PDK ships no KLayout antenna deck: its DRC deck carries no antenna "
                    "rules. Pick one manually, or use Magic instead.",
                )
            )
        elif uses_deck:
            self.engine_note.setText(
                pick(self.lang, f"Usando el deck: {self.deck_edit.text().strip()}",
                     f"Using deck: {self.deck_edit.text().strip()}")
            )
        elif self.support.magic_available:
            self.engine_note.setText(
                pick(
                    self.lang,
                    "Las reglas de antena de sky130A viven en el techfile de Magic, así que el "
                    "chequeo corre con `antennacheck`. No necesita deck.",
                    "sky130A keeps its antenna rules in the Magic techfile, so the check runs "
                    "through `antennacheck`. No deck is needed.",
                )
            )
        else:
            self.engine_note.setText(
                pick(
                    self.lang,
                    "No se detectaron reglas de antena en este PDK, ni para Magic ni para KLayout.",
                    "No antenna rules were detected in this PDK, for Magic or for KLayout.",
                )
            )

    def run(self) -> None:
        outputs = self.outputs_getter()
        self.output_dir.setText(str(outputs.antenna))

        layout = self.gds_edit.text().strip()
        top_cell = self.top_cell_edit.text().strip()
        if self.current_engine() == "magic":
            cmd, report = self.builder.magic_run_spec(layout, outputs, top_cell)
        else:
            deck = self.deck_edit.text().strip()
            if not deck:
                append_log(
                    self.log,
                    pick(self.lang,
                         "\nFalta el deck de antena de KLayout. Este PDK no incluye uno; "
                         "cambia el motor a Magic.\n",
                         "\nThe KLayout antenna deck is missing. This PDK ships none; "
                         "switch the engine to Magic.\n"),
                )
                return
            cmd, report = self.builder.run_spec(layout, deck, outputs, top_cell)
        self._last_report_path = report
        append_log(
            self.log,
            f"{pick(self.lang, 'Carpeta de salida', 'Output folder')}: {outputs.antenna}\n"
            f"{pick(self.lang, 'Reporte', 'Report')}: {report}\n",
        )

        self._begin_run_record(
            outputs,
            label=Path(layout).name or "antenna",
            inputs={"layout": layout, "engine": self.current_engine()},
        )
        self.send_status.emit(pick(self.lang, "Chequeo de antena corriendo", "Antenna check running"))
        self.runner.run(self.builder.build(cmd, cwd=str(outputs.base)))

    def _finished(self, code: int, _status: str) -> None:
        text = self.log.toPlainText()
        if self._last_report_path:
            report_path = Path(self._last_report_path)
            if report_path.exists() and report_path.is_file():
                try:
                    report_text = report_path.read_text(encoding="utf-8", errors="replace")
                    if report_text.strip():
                        append_log(
                            self.log,
                            f"\n{pick(self.lang, 'Contenido del reporte', 'Report contents')}:\n{report_text}\n",
                        )
                        text = f"{text}\n{report_text}"
                except OSError as exc:
                    append_log(self.log, f"\nFailed to read antenna report: {exc}\n")
        summary = LogParser.antenna_summary(text)
        if code != 0:
            summary = pick(self.lang, "Chequeo de antena falló", "Antenna check failed")
        advices = self._end_run_record(
            code, {"report": str(self._last_report_path or "")}, summary, text
        )
        self._report_advice(advices, self.log)
        self.summary.setText(summary)
        self.send_status.emit(summary)

    def open_output_folder(self) -> None:
        if self.output_dir.text().strip():
            QDesktopServices.openUrl(Path(self.output_dir.text().strip()).as_uri())
