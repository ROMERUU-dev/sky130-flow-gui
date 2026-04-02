"""Simulation tab UI and ngspice workflow."""

from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path

import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtCore import QSignalBlocker
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.command_runner import CommandRunner
from app.core.i18n import pick
from app.core.log_parser import LogParser
from app.core.ngspice_raw_parser import NgspiceRawParser
from app.core.output_manager import OutputPaths
from app.core.settings_manager import AppSettings
from app.core.spice_tools import (
    apply_model_corner,
    analyze_signal,
    build_generated_netlist,
    ensure_sky130_model_lib,
    extract_candidate_points,
    format_value,
)
from app.runners.ngspice_runner import NgspiceRunner
from app.services.em_netlist_instrumentation import (
    ensure_em_workspace,
    inspect_internal_net_candidates,
    instrument_netlist_for_em,
    normalize_em_current_file,
    preview_manual_instrumentation,
    write_manual_instrumented_netlist,
    write_em_probe_map,
)
from app.ui.waveform_viewer import WaveformViewer
from app.ui.widgets import CollapsibleSection, append_log


class SimulationTab(QWidget):
    """Run and inspect ngspice simulations."""

    send_status = Signal(str)

    def __init__(self, settings: AppSettings, outputs_getter) -> None:
        super().__init__()
        self.settings = settings
        self.lang = settings.language
        self.outputs_getter = outputs_getter
        self.runner = CommandRunner()
        self.builder = NgspiceRunner(settings)

        self.netlist_edit = QLineEdit()
        self.output_dir = QLineEdit()
        self.output_dir.setReadOnly(True)
        self.generated_path_edit = QLineEdit()
        self.generated_path_edit.setReadOnly(True)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.file_view = QTextEdit()
        self.file_view.setPlaceholderText(
            pick(self.lang, "Carga un netlist y ajustalo aqui; el archivo original no se sobrescribe.", "Load a netlist, tweak it here, and the original file will remain untouched.")
        )
        self.extra_directives = QTextEdit()
        self.extra_directives.setPlaceholderText(pick(self.lang, "Directivas extra opcionales (.meas, .ic, .param, etc.)", "Optional extra directives (.meas, .ic, .param, etc.)"))
        self.wave = WaveformViewer(self.lang)
        self.spectrum_plot = pg.PlotWidget(title="")
        self.spectrum_plot.setLabel("bottom", pick(self.lang, "Frecuencia", "Frequency"), units="Hz")
        self.spectrum_plot.setLabel("left", "dB", units="dB")
        self.spectrum_plot.showGrid(x=True, y=True)
        self.spectrum_plot.hide()
        self.spectrum_plot.setMinimumHeight(320)
        self.spectrum_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._configure_spectrum_plot_appearance()
        self.spectrum_x_scale = QDoubleSpinBox()
        self.spectrum_y_scale = QDoubleSpinBox()
        self.spectrum_reset_view_btn = QPushButton(pick(self.lang, "Reset vista", "Reset View"))
        self.spectrum_reset_scale_btn = QPushButton(pick(self.lang, "Reset escala", "Reset Scale"))
        self.spectrum_export_png_btn = QPushButton("Export PNG")
        self.spectrum_export_svg_btn = QPushButton("Export SVG")
        self.spectrum_stats = QLabel(pick(self.lang, "Sin datos", "No data"))

        self.history_select = QComboBox()
        self.history_select.setPlaceholderText(pick(self.lang, "Sin simulaciones previas", "No previous simulations"))
        self.load_history_btn = QPushButton(pick(self.lang, "Cargar anterior", "Load Previous"))
        self.refresh_history_btn = QPushButton(pick(self.lang, "Refrescar historial", "Refresh History"))

        self.run_btn = QPushButton(pick(self.lang, "Correr", "Run"))
        self.run_btn.setStyleSheet(
            """
            QPushButton:disabled {
                background-color: #9aa0a6;
                color: #f3f4f6;
                border: 1px solid #7d848c;
            }
            """
        )
        self.stop_btn = QPushButton(pick(self.lang, "Detener", "Stop"))
        self.stop_btn.setEnabled(False)
        self.rerun_btn = QPushButton(pick(self.lang, "Repetir", "Re-run"))
        self.show_log_btn = QPushButton(pick(self.lang, "Mostrar log", "Show log"))
        self.open_out_btn = QPushButton(pick(self.lang, "Abrir carpeta de salida", "Open Output Folder"))
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedWidth(150)
        self.loading_bar.setVisible(False)
        self.loading_bar.setToolTip(pick(self.lang, "Simulación en progreso", "Simulation in progress"))
        self.add_probe_btn = QPushButton(pick(self.lang, "Agregar probe", "Add Probe Point"))
        self.refresh_points_btn = QPushButton(pick(self.lang, "Refrescar probes", "Refresh Points"))
        self.paste_netlist_btn = QToolButton()
        self.paste_netlist_btn.setText(pick(self.lang, "Pegar netlist", "Paste netlist"))
        self.page_title = QLabel(pick(self.lang, "Simulación", "Simulation"))
        self.page_subtitle = QLabel(
            pick(
                self.lang,
                "Corre, abre el waveform y ajusta sólo lo que necesites.",
                "Run, inspect the waveform, and adjust only what you need.",
            )
        )
        self.summary_status_value = QLabel(pick(self.lang, "Listo", "Idle"))
        self.summary_output_value = QLabel("—")
        self.summary_generated_value = QLabel("—")
        self.summary_waveform_value = QLabel(pick(self.lang, "Sin cargar", "Not loaded"))

        self.sim_type = QComboBox()
        self.sim_type.addItems(
            [
                pick(self.lang, "Transitorio", "Transient"),
                "AC",
                "DC",
                pick(self.lang, "Punto de operación", "Operating Point"),
            ]
        )
        self.sim_stack = QStackedWidget()
        self.log_dialog: QDialog | None = None
        self.log_viewer: QTextEdit | None = None

        self.tran_step = QLineEdit("1n")
        self.tran_stop = QLineEdit("1u")
        self.tran_start = QLineEdit("0")
        self.tran_uic = QCheckBox("UIC")

        self.ac_sweep = QComboBox()
        self.ac_sweep.addItems(["dec", "lin", "oct"])
        self.ac_points = QLineEdit("20")
        self.ac_start = QLineEdit("1")
        self.ac_stop = QLineEdit("1G")

        self.dc_source = QLineEdit("V1")
        self.dc_start = QLineEdit("0")
        self.dc_stop = QLineEdit("1.8")
        self.dc_step = QLineEdit("0.01")
        self.save_mode = QComboBox()
        self.save_mode.addItems(
            [
                pick(self.lang, "Todas las señales", "All signals"),
                pick(self.lang, "Sólo probes seleccionados", "Selected probes only"),
            ]
        )
        self.corner = QComboBox()
        self.corner.addItems(["tt", "ss", "ff", "sf", "fs"])
        self.temp_c = QLineEdit()
        self.temp_c.setPlaceholderText(pick(self.lang, "Opcional, ej. 27", "Optional, e.g. 27"))
        self.postlayout_use_ic = QCheckBox(pick(self.lang, "Post-layout: usar condiciones iniciales", "Post-layout: use initial conditions"))
        self.postlayout_use_ic.setChecked(True)
        self.postlayout_load_mode = QComboBox()
        self.postlayout_load_mode.addItem(pick(self.lang, "Sin carga", "No load"), "none")
        self.postlayout_load_mode.addItem(pick(self.lang, "Capacitiva", "Capacitive"), "cap")
        self.postlayout_load_mode.addItem(pick(self.lang, "RC serie", "Series RC"), "rc")
        self.postlayout_load_mode.setCurrentIndex(1)
        self.postlayout_load_cap = QLineEdit("10f")
        self.postlayout_load_res = QLineEdit("1k")
        self.spectrum_mode = QComboBox()
        self.spectrum_mode.addItems(
            [
                pick(self.lang, "Auto", "Auto"),
                pick(self.lang, "Mostrar", "Show"),
                pick(self.lang, "Ocultar", "Hide"),
            ]
        )
        self.spectrum_x_axis = QComboBox()
        self.spectrum_x_axis.addItems(
            [
                pick(self.lang, "Hz lineal", "Linear Hz"),
                pick(self.lang, "Hz log", "Log Hz"),
            ]
        )

        self.metric_signal = QComboBox()
        self.metric_reference = QComboBox()
        self.metric_reference.addItem("None", "")
        self.generate_em_checkbox = QCheckBox(pick(self.lang, "Generar análisis EM (netlist instrumentado)", "Generate EM analysis (instrumented netlist)"))
        self.debug_em_only_checkbox = QCheckBox(pick(self.lang, "Debug: exportar sólo netlist instrumentado", "Debug: export instrumented netlist only"))
        self.keep_em_files_checkbox = QCheckBox(pick(self.lang, "Conservar archivos intermedios EM", "Keep EM intermediate files"))
        self.em_project_mode = QComboBox()
        self.em_project_mode.addItem("Tiny Tapeout", "tiny_tapeout")
        self.em_project_mode.addItem("Custom SKY130", "custom_sky130")
        self.open_em_netlists_btn = QPushButton(pick(self.lang, "Abrir carpeta de netlists EM", "Open EM netlist folder"))
        self.open_em_inputs_btn = QPushButton(pick(self.lang, "Abrir carpeta de inputs EM", "Open EM inputs folder"))
        self.internal_net_combo = QComboBox()
        self.internal_connections_table = QTableWidget(0, 4)
        self.preview_internal_btn = QPushButton(pick(self.lang, "Previsualizar instrumentación", "Preview instrumentation"))
        self.apply_internal_btn = QPushButton(pick(self.lang, "Aplicar instrumentación para esta net", "Apply instrumentation for this net"))
        self.metric_labels = {
            "minimum": QLabel("N/A"),
            "maximum": QLabel("N/A"),
            "mean": QLabel("N/A"),
            "rms": QLabel("N/A"),
            "peak_to_peak": QLabel("N/A"),
            "amplitude": QLabel("N/A"),
            "frequency_hz": QLabel("N/A"),
            "period_s": QLabel("N/A"),
            "phase_deg": QLabel("N/A"),
        }

        self._probe_rows: list[tuple[QHBoxLayout, QComboBox, QPushButton]] = []
        self._candidate_points: list[str] = []
        self._last_command: list[str] = []
        self._last_outputs: OutputPaths | None = None
        self._last_raw_path: Path | None = None
        self._last_generated_netlist: Path | None = None
        self._pending_em_run = None
        self._running_em_followup = False
        self._em_workspace_paths: dict[str, Path] = {}
        self._last_em_metadata_path: Path | None = None
        self._internal_net_candidates: list[dict] = []
        self._spectrum_base_x_range: tuple[float, float] | None = None
        self._spectrum_base_y_range: tuple[float, float] | None = None
        self._current_spectrum_signal_name = ""
        self._current_spectrum_has_data = False
        self.setup_section = None
        self.probes_section = None
        self.internal_section = None
        self.netlist_section = None
        self.visual_section = None
        self.measurements_section = None
        self.spectrum_section = None

        for control in (self.spectrum_x_scale, self.spectrum_y_scale):
            control.setDecimals(2)
            control.setRange(0.1, 10.0)
            control.setSingleStep(0.1)
            control.setValue(1.0)

        self._build_ui()
        self._apply_visual_style()
        self._wire()
        self.refresh_history()
        self._refresh_probe_points()
        self._update_run_summary()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        layout.addWidget(scroll)

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(28, 24, 28, 36)
        page_layout.setSpacing(18)

        page_layout.addWidget(self._build_header())
        page_layout.addWidget(self._build_run_summary())

        row = QHBoxLayout()
        row.addWidget(QLabel(pick(self.lang, "Netlist:", "Netlist:")))
        row.addWidget(self.netlist_edit)
        browse_btn = QPushButton(pick(self.lang, "Buscar", "Browse"))
        browse_btn.clicked.connect(self._pick_file)
        row.addWidget(browse_btn)
        page_layout.addLayout(row)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel(pick(self.lang, "Directorio de salida:", "Output Dir:")))
        path_row.addWidget(self.output_dir)
        path_row.addWidget(self.open_out_btn)
        page_layout.addLayout(path_row)

        gen_row = QHBoxLayout()
        gen_row.addWidget(QLabel(pick(self.lang, "Netlist generado:", "Generated Netlist:")))
        gen_row.addWidget(self.generated_path_edit)
        page_layout.addLayout(gen_row)

        btns = QHBoxLayout()
        btns.addWidget(self.run_btn)
        btns.addWidget(self.stop_btn)
        btns.addWidget(self.rerun_btn)
        btns.addWidget(self.show_log_btn)
        btns.addWidget(self.loading_bar)
        btns.addStretch(1)
        page_layout.addLayout(btns)

        history_row = QHBoxLayout()
        history_row.addWidget(QLabel(pick(self.lang, "Simulaciones previas:", "Previous simulations:")))
        history_row.addWidget(self.history_select, 1)
        history_row.addWidget(self.load_history_btn)
        history_row.addWidget(self.refresh_history_btn)
        page_layout.addLayout(history_row)

        self.setup_section = CollapsibleSection(
            pick(self.lang, "Configuración", "Run Setup"),
            self._build_simulation_setup(),
            expanded=True,
        )
        self.probes_section = CollapsibleSection(
            pick(self.lang, "Puntos de prueba", "Probe Points"),
            self._build_probe_editor(),
            expanded=False,
        )
        self.internal_section = CollapsibleSection(
            pick(self.lang, "Inspector de nets internas", "Internal Net Inspector"),
            self._build_internal_net_inspector(),
            expanded=False,
        )
        page_layout.addWidget(self.setup_section)
        page_layout.addWidget(self.probes_section)
        page_layout.addWidget(self.internal_section)
        netlist_tools = QHBoxLayout()
        netlist_hint = QLabel(
            pick(
                self.lang,
                "Opcional: pega un deck propio o abre el editor cuando quieras afinar el netlist generado.",
                "Optional: paste your own deck or open the editor when you want to refine the generated netlist.",
            )
        )
        netlist_hint.setObjectName("inlineHint")
        netlist_tools.addWidget(netlist_hint)
        netlist_tools.addStretch(1)
        netlist_tools.addWidget(self.paste_netlist_btn)
        page_layout.addLayout(netlist_tools)
        self.netlist_section = CollapsibleSection(
            pick(self.lang, "Editor de netlist", "Netlist Editor"),
            self._build_netlist_editor(),
            expanded=False,
        )
        self.visual_section = CollapsibleSection(
            pick(self.lang, "Visualización", "Visualization Options"),
            self._build_visualization_options(),
            expanded=False,
        )
        page_layout.addWidget(self.netlist_section)
        page_layout.addWidget(self.visual_section)
        page_layout.addWidget(self.wave)
        self.measurements_section = CollapsibleSection(
            pick(self.lang, "Mediciones", "Measurements"),
            self._build_measurement_panel(),
            expanded=False,
        )
        self.spectrum_section = CollapsibleSection(
            pick(self.lang, "Espectro de frecuencia", "Frequency Spectrum"),
            self._build_spectrum_panel(),
            expanded=False,
        )
        page_layout.addWidget(self.measurements_section)
        page_layout.addWidget(self.spectrum_section)
        page_layout.addStretch(1)

        scroll.setWidget(page)

    def _build_header(self) -> QWidget:
        card = QFrame()
        card.setObjectName("heroCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(4)
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle.setObjectName("pageSubtitle")
        layout.addWidget(self.page_title)
        layout.addWidget(self.page_subtitle)
        return card

    def _build_run_summary(self) -> QWidget:
        card = QFrame()
        card.setObjectName("summaryCard")
        grid = QGridLayout(card)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        items = [
            (pick(self.lang, "Estado", "Status"), self.summary_status_value),
            (pick(self.lang, "Salida", "Output"), self.summary_output_value),
            (pick(self.lang, "Deck generado", "Deck"), self.summary_generated_value),
            (pick(self.lang, "Forma de onda", "Waveform"), self.summary_waveform_value),
        ]
        for index, (label_text, value_label) in enumerate(items):
            panel = QFrame()
            panel.setObjectName("summaryItem")
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(14, 12, 14, 12)
            panel_layout.setSpacing(4)
            label = QLabel(label_text)
            label.setObjectName("summaryLabel")
            value_label.setObjectName("summaryValue")
            panel_layout.addWidget(label)
            panel_layout.addWidget(value_label)
            grid.addWidget(panel, 0, index)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)
        return card

    def _build_section_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("sectionCard")
        return card

    def _build_subsection_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("subCard")
        return card

    def _make_section_heading(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionHeading")
        return label

    def _make_hint_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("hintLabel")
        return label

    def _build_simulation_setup(self) -> QWidget:
        card = self._build_section_card()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(16)

        basics = QFormLayout()
        basics.setHorizontalSpacing(16)
        basics.setVerticalSpacing(10)
        basics.addRow(pick(self.lang, "Tipo:", "Type:"), self.sim_type)
        basics.addRow(pick(self.lang, "Modo de guardado:", "Save mode:"), self.save_mode)
        outer.addWidget(self._make_section_heading(pick(self.lang, "General", "General")))
        outer.addLayout(basics)

        postlayout_box = self._build_subsection_card()
        postlayout_layout = QVBoxLayout(postlayout_box)
        postlayout_layout.setContentsMargins(16, 16, 16, 16)
        postlayout_layout.setSpacing(10)
        postlayout_layout.addWidget(self._make_section_heading(pick(self.lang, "Post-layout Wrapper", "Post-layout Wrapper")))
        postlayout_layout.addWidget(
            self._make_hint_label(
                pick(
                    self.lang,
                    "Arranque y carga para netlists extraídos sin testbench manual.",
                    "Startup and loading for extracted netlists without a manual testbench.",
                )
            )
        )
        postlayout_form = QFormLayout()
        postlayout_form.setHorizontalSpacing(16)
        postlayout_form.setVerticalSpacing(10)
        postlayout_form.addRow("", self.postlayout_use_ic)
        postlayout_form.addRow(pick(self.lang, "Modelo de carga:", "Load model:"), self.postlayout_load_mode)
        postlayout_form.addRow(pick(self.lang, "Capacitancia:", "Capacitance:"), self.postlayout_load_cap)
        postlayout_form.addRow(pick(self.lang, "Resistencia serie:", "Series resistance:"), self.postlayout_load_res)
        postlayout_layout.addLayout(postlayout_form)
        outer.addWidget(postlayout_box)

        advanced_box = self._build_subsection_card()
        advanced_layout = QVBoxLayout(advanced_box)
        advanced_layout.setContentsMargins(16, 16, 16, 16)
        advanced_layout.setSpacing(10)
        advanced_layout.addWidget(self._make_section_heading(pick(self.lang, "Avanzado", "Advanced")))
        advanced_form = QFormLayout()
        advanced_form.setHorizontalSpacing(16)
        advanced_form.setVerticalSpacing(10)
        advanced_form.addRow(pick(self.lang, "Corner:", "Corner:"), self.corner)
        advanced_form.addRow(pick(self.lang, "Temperatura (C):", "Temperature (C):"), self.temp_c)
        advanced_form.addRow("", self.generate_em_checkbox)
        advanced_form.addRow("", self.debug_em_only_checkbox)
        advanced_form.addRow("", self.keep_em_files_checkbox)
        advanced_form.addRow(pick(self.lang, "Modo de proyecto EM:", "EM Project Mode:"), self.em_project_mode)
        em_folder_row = QHBoxLayout()
        em_folder_row.addWidget(self.open_em_netlists_btn)
        em_folder_row.addWidget(self.open_em_inputs_btn)
        advanced_form.addRow("", em_folder_row)
        advanced_layout.addLayout(advanced_form)
        outer.addWidget(advanced_box)

        tran_page = QWidget()
        tran_form = QFormLayout(tran_page)
        tran_form.addRow(pick(self.lang, "Paso:", "Step:"), self.tran_step)
        tran_form.addRow(pick(self.lang, "Fin:", "Stop:"), self.tran_stop)
        tran_form.addRow(pick(self.lang, "Inicio:", "Start:"), self.tran_start)
        tran_form.addRow("", self.tran_uic)

        ac_page = QWidget()
        ac_form = QFormLayout(ac_page)
        ac_form.addRow(pick(self.lang, "Barrido:", "Sweep:"), self.ac_sweep)
        ac_form.addRow(pick(self.lang, "Puntos/dec:", "Points/dec:"), self.ac_points)
        ac_form.addRow(pick(self.lang, "Frecuencia inicial:", "Start freq:"), self.ac_start)
        ac_form.addRow(pick(self.lang, "Frecuencia final:", "Stop freq:"), self.ac_stop)

        dc_page = QWidget()
        dc_form = QFormLayout(dc_page)
        dc_form.addRow(pick(self.lang, "Fuente:", "Source:"), self.dc_source)
        dc_form.addRow(pick(self.lang, "Inicio:", "Start:"), self.dc_start)
        dc_form.addRow(pick(self.lang, "Fin:", "Stop:"), self.dc_stop)
        dc_form.addRow(pick(self.lang, "Paso:", "Step:"), self.dc_step)

        op_page = QWidget()
        op_form = QFormLayout(op_page)
        op_form.addRow(
            QLabel(
                pick(
                    self.lang,
                    "Ejecuta un único punto de operación DC (.op) con el netlist y las fuentes actuales.",
                    "Run a single DC operating point (.op) with the current netlist and sources.",
                )
            )
        )

        self.sim_stack.addWidget(tran_page)
        self.sim_stack.addWidget(ac_page)
        self.sim_stack.addWidget(dc_page)
        self.sim_stack.addWidget(op_page)
        outer.addWidget(self.sim_stack)
        return card

    def _build_probe_editor(self) -> QWidget:
        card = self._build_section_card()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(14)
        outer.addWidget(
            self._make_hint_label(
                pick(self.lang, "Elige nodos o escribe expresiones como v(out) o i(v1).", "Choose nodes or type expressions like v(out) or i(v1).")
            )
        )
        top = QHBoxLayout()
        top.addWidget(self.add_probe_btn)
        top.addWidget(self.refresh_points_btn)
        top.addStretch(1)
        outer.addLayout(top)

        container = QWidget()
        self.probe_layout = QVBoxLayout(container)
        self.probe_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)
        return card

    def _build_internal_net_inspector(self) -> QWidget:
        card = self._build_section_card()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(14)
        top = QHBoxLayout()
        top.addWidget(self._make_hint_label(pick(self.lang, "Selecciona una net interna para previsualizar y mover instrumentación.", "Select an internal net to preview and move instrumentation.")))
        top.addStretch(1)
        outer.addLayout(top)
        combo_row = QHBoxLayout()
        combo_row.addWidget(QLabel(pick(self.lang, "Net interna:", "Internal net:")))
        combo_row.addWidget(self.internal_net_combo, 1)
        outer.addLayout(combo_row)

        self.internal_connections_table.setHorizontalHeaderLabels(
            [
                pick(self.lang, "Instancia", "Instance name"),
                pick(self.lang, "Tipo", "Type"),
                pick(self.lang, "Línea", "Line preview"),
                pick(self.lang, "Mover al lado driver", "Move to driver side"),
            ]
        )
        outer.addWidget(self.internal_connections_table)

        buttons = QHBoxLayout()
        buttons.addWidget(self.preview_internal_btn)
        buttons.addWidget(self.apply_internal_btn)
        buttons.addStretch(1)
        outer.addLayout(buttons)
        return card

    def _build_netlist_editor(self) -> QWidget:
        card = self._build_section_card()
        card.setVisible(False)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(12)
        outer.addWidget(self._make_hint_label(pick(self.lang, "Editor temporal del deck de simulación. El archivo original no se sobrescribe.", "Temporary editor for the simulation deck. The original file is not overwritten.")))
        outer.addWidget(self.file_view)
        outer.addWidget(self._make_section_heading(pick(self.lang, "Directivas extra", "Extra Directives")))
        outer.addWidget(self.extra_directives)
        self.netlist_editor_box = card
        return card

    def _build_measurement_panel(self) -> QWidget:
        card = self._build_section_card()
        form = QFormLayout(card)
        form.setContentsMargins(18, 18, 18, 18)
        form.addRow(pick(self.lang, "Señal:", "Signal:"), self.metric_signal)
        form.addRow(pick(self.lang, "Referencia de fase:", "Phase reference:"), self.metric_reference)
        form.addRow("Min:", self.metric_labels["minimum"])
        form.addRow("Max:", self.metric_labels["maximum"])
        form.addRow(pick(self.lang, "Media:", "Mean:"), self.metric_labels["mean"])
        form.addRow("RMS:", self.metric_labels["rms"])
        form.addRow("Peak-to-peak:", self.metric_labels["peak_to_peak"])
        form.addRow("Amplitude:", self.metric_labels["amplitude"])
        form.addRow(pick(self.lang, "Frecuencia:", "Frequency:"), self.metric_labels["frequency_hz"])
        form.addRow(pick(self.lang, "Período:", "Period:"), self.metric_labels["period_s"])
        form.addRow(pick(self.lang, "Fase:", "Phase:"), self.metric_labels["phase_deg"])
        return card

    def _apply_visual_style(self) -> None:
        self.setStyleSheet(
            """
            QFrame#heroCard, QFrame#summaryCard {
                background: #ffffff;
                border: 1px solid #e8eef7;
                border-radius: 18px;
            }
            QFrame#summaryItem, QFrame#sectionCard, QFrame#subCard {
                background: #ffffff;
                border: 1px solid #e8eef7;
                border-radius: 16px;
            }
            QLabel#pageTitle {
                font-size: 24px;
                font-weight: 800;
                color: #2563eb;
            }
            QLabel#pageSubtitle {
                font-size: 13px;
                color: #667085;
            }
            QLabel#summaryLabel {
                font-size: 11px;
                font-weight: 700;
                color: #7a8699;
            }
            QLabel#summaryValue {
                font-size: 14px;
                font-weight: 700;
                color: #111827;
            }
            QLabel#sectionHeading {
                font-size: 13px;
                font-weight: 800;
                color: #2563eb;
            }
            QLabel#hintLabel, QLabel#inlineHint {
                color: #667085;
                font-size: 12px;
            }
            QLabel {
                color: #273142;
            }
            QScrollArea {
                border: 0;
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 12px;
                margin: 4px 4px 4px 0;
            }
            QScrollBar::handle:vertical {
                background: #d8e2f0;
                min-height: 36px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background: #bfd0e8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
                height: 0;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 12px;
                margin: 0 4px 4px 4px;
            }
            QScrollBar::handle:horizontal {
                background: #d8e2f0;
                min-width: 36px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #bfd0e8;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
                width: 0;
            }
            QFrame#subCard {
                background: #fbfdff;
            }
            QToolButton {
                background: #ffffff;
                border: 1px solid transparent;
                border-radius: 14px;
                padding: 10px 12px;
                color: #1f2937;
                font-weight: 800;
                text-align: left;
            }
            QToolButton:hover {
                background: #f8fbff;
                border: 1px solid #d6e4ff;
            }
            QLineEdit, QComboBox, QTextEdit, QDoubleSpinBox, QTableWidget {
                background: #ffffff;
                border: 1px solid #dfe7f2;
                border-radius: 12px;
                padding: 7px 9px;
                color: #111827;
            }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QDoubleSpinBox:focus, QTableWidget:focus {
                border: 1px solid #93c5fd;
            }
            QPushButton, QToolButton {
                background: #ffffff;
                border: 1px solid transparent;
                border-radius: 12px;
                padding: 8px 13px;
                color: #111827;
                font-weight: 600;
            }
            QPushButton:hover, QToolButton:hover {
                background: #f5f8ff;
                border: 1px solid #d6e4ff;
            }
            """
        )

    def _build_visualization_options(self) -> QWidget:
        card = self._build_section_card()
        form = QFormLayout(card)
        form.setContentsMargins(18, 18, 18, 18)
        form.addRow(pick(self.lang, "Espectro:", "Spectrum:"), self.spectrum_mode)
        form.addRow(pick(self.lang, "Eje X del espectro:", "Spectrum X axis:"), self.spectrum_x_axis)
        form.addRow(self._make_hint_label(pick(self.lang, "La gráfica inferior es un espectro tipo FFT y aparece para señales en el dominio del tiempo.", "The lower chart is an FFT-like spectrum and appears for time-domain signals.")))
        return card

    def _build_spectrum_panel(self) -> QWidget:
        card = self._build_section_card()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(18, 18, 18, 18)
        controls = QHBoxLayout()
        controls.addWidget(QLabel(pick(self.lang, "Escala X:", "X scale:")))
        controls.addWidget(self.spectrum_x_scale)
        controls.addWidget(QLabel(pick(self.lang, "Escala Y:", "Y scale:")))
        controls.addWidget(self.spectrum_y_scale)
        controls.addWidget(self.spectrum_reset_view_btn)
        controls.addWidget(self.spectrum_reset_scale_btn)
        controls.addWidget(self.spectrum_export_png_btn)
        controls.addWidget(self.spectrum_export_svg_btn)
        controls.addStretch(1)
        outer.addLayout(controls)
        outer.addWidget(self.spectrum_plot)
        outer.addWidget(self.spectrum_stats)
        return card

    def _wire(self) -> None:
        self.run_btn.clicked.connect(self.run)
        self.stop_btn.clicked.connect(self.runner.stop)
        self.rerun_btn.clicked.connect(self.rerun)
        self.show_log_btn.clicked.connect(self._show_log_dialog)
        self.open_out_btn.clicked.connect(self.open_output_folder)
        self.load_history_btn.clicked.connect(self.load_selected_history)
        self.refresh_history_btn.clicked.connect(self.refresh_history)
        self.add_probe_btn.clicked.connect(lambda: self._add_probe_row())
        self.refresh_points_btn.clicked.connect(self._refresh_probe_points)
        self.sim_type.currentIndexChanged.connect(self.sim_stack.setCurrentIndex)
        self.file_view.textChanged.connect(self._refresh_probe_points)
        self.file_view.textChanged.connect(self._refresh_internal_net_inspector)
        self.metric_signal.currentTextChanged.connect(self._update_measurements)
        self.metric_reference.currentTextChanged.connect(self._update_measurements)
        self.spectrum_mode.currentTextChanged.connect(self._update_measurements)
        self.spectrum_x_axis.currentTextChanged.connect(self._update_spectrum_axis)
        self.spectrum_x_scale.valueChanged.connect(self._apply_spectrum_scale)
        self.spectrum_y_scale.valueChanged.connect(self._apply_spectrum_scale)
        self.spectrum_reset_view_btn.clicked.connect(self._reset_spectrum_view)
        self.spectrum_reset_scale_btn.clicked.connect(self._reset_spectrum_scale)
        self.spectrum_export_png_btn.clicked.connect(lambda: self._export_spectrum_plot("png"))
        self.spectrum_export_svg_btn.clicked.connect(lambda: self._export_spectrum_plot("svg"))
        self.wave.signal_changed.connect(self._sync_metric_selection)
        self.paste_netlist_btn.clicked.connect(self._paste_netlist)
        self.generate_em_checkbox.toggled.connect(self._sync_em_options_state)
        self.debug_em_only_checkbox.toggled.connect(self._sync_em_options_state)
        self.em_project_mode.currentIndexChanged.connect(self._refresh_internal_net_inspector)
        self.open_em_netlists_btn.clicked.connect(self._open_em_netlists_folder)
        self.open_em_inputs_btn.clicked.connect(self._open_em_inputs_folder)
        self.internal_net_combo.currentIndexChanged.connect(self._populate_internal_net_table)
        self.preview_internal_btn.clicked.connect(self._preview_internal_instrumentation)
        self.apply_internal_btn.clicked.connect(self._apply_internal_instrumentation)

        self.runner.started.connect(lambda cmd: self._append_log(f"\n$ {cmd}\n"))
        self.runner.line_output.connect(self._append_log)
        self.runner.finished.connect(self._finished)
        self._sync_em_options_state()
        self._sync_postlayout_load_controls()
        self._refresh_internal_net_inspector()
        self.postlayout_load_mode.currentIndexChanged.connect(self._sync_postlayout_load_controls)

    def _pick_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select netlist", "", "SPICE Files (*.spice *.sp *.cir)")
        if file_path:
            self.load_netlist_path(file_path)

    def load_netlist_path(self, file_path: str) -> None:
        self.netlist_edit.setText(file_path)
        self._update_run_summary()
        try:
            self.file_view.setPlainText(Path(file_path).read_text())
            self._refresh_probe_points()
        except OSError as exc:
            self._append_log(f"Failed to read file: {exc}\n")

    def run(self) -> None:
        source_netlist = self._ensure_editor_content()
        if not source_netlist:
            self._append_log(pick(self.lang, "Selecciona un netlist primero.\n", "Select a netlist first.\n"))
            return

        outputs = self._create_simulation_outputs()
        self._last_outputs = outputs
        self.output_dir.setText(str(outputs.results))

        generated_netlist = self._write_generated_netlist(outputs)
        self._last_generated_netlist = generated_netlist
        self.generated_path_edit.setText(str(generated_netlist))
        self._update_run_summary(status=pick(self.lang, "Preparando corrida", "Preparing run"))
        self._pending_em_run = None
        self._running_em_followup = False
        if self._em_workflow_requested():
            self._pending_em_run = self._prepare_em_followup(generated_netlist, outputs)
            if self._pending_em_run and self._pending_em_run.get("debug_only"):
                self._show_em_debug_summary(self._pending_em_run)
                self._append_log(
                    f"EM debug export generated.\n"
                    f"Instrumented netlist: {self._pending_em_run['netlist_path']}\n"
                    f"Probe map: {self._pending_em_run['metadata_path']}\n"
                )
                self.send_status.emit("EM instrumented netlist generated")
                return

        cmd, log_path, raw_path, run_cwd = self.builder.run_spec(str(generated_netlist), outputs)
        self._append_log(f"Output folder: {outputs.results}\nGenerated netlist: {generated_netlist}\nLog file: {log_path}\n")
        self._last_command = cmd
        self._last_raw_path = Path(raw_path)
        self.wave.set_signals({})
        self._clear_measurements()
        self._clear_spectrum_plot()
        self.refresh_history()
        self.send_status.emit(pick(self.lang, "Simulación corriendo", "Simulation running"))
        self._set_simulation_running(True)
        self.runner.run(self.builder.build(cmd, cwd=run_cwd))
        self._update_run_summary(status=pick(self.lang, "Corriendo", "Running"))

    def rerun(self) -> None:
        self.run()

    def _finished(self, code: int, status: str) -> None:
        if self._running_em_followup:
            self._running_em_followup = False
            self._set_simulation_running(False)
            summary = f"\nEM extraction finished: exit={code} status={status}\n"
            self._append_log(summary)
            if code != 0:
                self._pending_em_run = None
                self.send_status.emit("EM extraction failed")
            else:
                try:
                    normalization = normalize_em_current_file(
                        raw_path=self._pending_em_run["raw_currents_path"],
                        normalized_path=self._pending_em_run["currents_path"],
                        probe_map_path=self._pending_em_run["metadata_path"],
                    )
                    self._append_log(
                        f"Normalized EM current file: {normalization['normalized_path']}\n"
                        f"Probe count: {normalization['probe_count']}\n"
                    )
                    for warning in normalization["warnings"]:
                        self._append_log(f"EM normalization warning: {warning}\n")
                except Exception as exc:
                    self._append_log(f"EM normalization failed: {exc}\n")
                    self._pending_em_run = None
                    self.send_status.emit("EM extraction failed")
                    return
                self._cleanup_em_reports_if_needed()
                self._pending_em_run = None
                self.send_status.emit(pick(self.lang, "Simulación completada", "Simulation completed"))
                self._update_run_summary(status=pick(self.lang, "EM listo", "EM ready"))
            return

        if code == 0 and self._pending_em_run is not None:
            summary = pick(
                self.lang,
                f"\nSimulación finalizada: exit={code} estado={status}\n",
                f"\nSimulation finished: exit={code} status={status}\n",
            )
            self._append_log(summary)
            self._load_waveforms()
            self.refresh_history()
            if self._pending_em_run.get("debug_only"):
                self._set_simulation_running(False)
                self._pending_em_run = None
                self.send_status.emit("EM instrumented netlist generated")
                self._update_run_summary(status=pick(self.lang, "Netlist EM listo", "EM netlist ready"))
                return
            self._append_log(
                f"Starting EM extraction using instrumented netlist: {self._pending_em_run['netlist_path']}\n"
                f"EM current output: {self._pending_em_run['currents_path']}\n"
            )
            self.send_status.emit("EM extraction running")
            self._running_em_followup = True
            self._update_run_summary(status=pick(self.lang, "Extracción EM", "EM extraction"))
            self.runner.run(self._pending_em_run["spec"])
            return

        self._set_simulation_running(False)
        summary = pick(
            self.lang,
            f"\nSimulación finalizada: exit={code} estado={status}\n",
            f"\nSimulation finished: exit={code} status={status}\n",
        )
        self._append_log(summary)
        full_text = self.log.toPlainText()
        if LogParser.has_errors(full_text) or code != 0:
            self._pending_em_run = None
            self.send_status.emit(pick(self.lang, "Simulación fallida", "Simulation failed"))
            self._update_run_summary(status=pick(self.lang, "Falló", "Failed"))
        else:
            self._load_waveforms()
            self.refresh_history()
            self.send_status.emit(pick(self.lang, "Simulación completada", "Simulation completed"))
            self._update_run_summary(status=pick(self.lang, "Lista", "Ready"))

    def open_output_folder(self) -> None:
        if self.output_dir.text().strip():
            QDesktopServices.openUrl(Path(self.output_dir.text().strip()).as_uri())

    def _load_waveforms(self) -> None:
        raw_path = self._resolve_raw_path()
        self._load_waveforms_from_path(raw_path)

    def load_selected_history(self) -> None:
        raw_path = self.history_select.currentData()
        if not raw_path:
            self._append_log("No previous simulation is selected.\n")
            return
        try:
            self._load_waveforms_from_path(Path(raw_path))
            self._update_run_summary(status=pick(self.lang, "Historial cargado", "History loaded"))
        except Exception as exc:
            self._append_log(f"Failed to load selected history: {exc}\n")
            self.send_status.emit("Failed to load previous simulation")

    def refresh_history(self) -> None:
        outputs = self.outputs_getter()
        active_output_dir = self._last_outputs.results if self._last_outputs else outputs.results
        self.output_dir.setText(str(active_output_dir))

        current_path = str(self.history_select.currentData()) if self.history_select.currentData() else None
        raw_files = sorted(outputs.results.rglob("*.raw"), key=lambda path: path.stat().st_mtime, reverse=True)

        self.history_select.blockSignals(True)
        self.history_select.clear()
        for raw_file in raw_files:
            rel_path = raw_file.relative_to(outputs.results)
            label = f"{rel_path}  [{self._format_timestamp(raw_file)}]"
            self.history_select.addItem(label, str(raw_file))

        if current_path:
            index = self.history_select.findData(current_path)
            if index >= 0:
                self.history_select.setCurrentIndex(index)
        elif self.history_select.count():
            self.history_select.setCurrentIndex(0)
        self.history_select.blockSignals(False)
        self._update_run_summary()

    def _load_waveforms_from_path(self, raw_path: Path | None) -> None:
        if not raw_path:
            self._append_log("No waveform raw file was found after simulation.\n")
            self.wave.set_signals({})
            self._clear_measurements()
            self._clear_spectrum_plot()
            return

        try:
            signals = NgspiceRawParser.load_signals(raw_path)
        except (OSError, ValueError) as exc:
            self._append_log(f"Failed to load waveform data: {exc}\n")
            self.wave.set_signals({})
            self._clear_measurements()
            self._clear_spectrum_plot()
            return

        self._last_raw_path = raw_path
        self._clear_spectrum_plot()

        with QSignalBlocker(self.metric_signal), QSignalBlocker(self.metric_reference):
            self.wave.set_signals(signals)
            self._refresh_measurement_targets()

        self._update_measurements()
        self._append_log(f"Loaded waveform data from: {raw_path}\n")
        self._update_run_summary(status=pick(self.lang, "Waveform cargado", "Waveform loaded"))

    def _resolve_raw_path(self) -> Path | None:
        candidates: list[Path] = []
        if self._last_raw_path:
            candidates.append(self._last_raw_path)
        if self._last_outputs:
            candidates.extend(sorted(self._last_outputs.results.rglob("*.raw")))

        seen: set[Path] = set()
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _refresh_probe_points(self) -> None:
        self._candidate_points = extract_candidate_points(self.file_view.toPlainText())
        for _, combo, _ in self._probe_rows:
            current_text = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(self._candidate_points)
            combo.setEditText(current_text)
            combo.blockSignals(False)

        if not self._probe_rows:
            self._add_probe_row()

    def _refresh_internal_net_inspector(self) -> None:
        self._internal_net_candidates = inspect_internal_net_candidates(
            self.file_view.toPlainText(),
            project_mode=str(self.em_project_mode.currentData()),
        )
        self._append_log(f"Internal Net Inspector: found {len(self._internal_net_candidates)} candidate nets.\n")
        current_net = self._normalized_net_name(self.internal_net_combo.currentData() or self.internal_net_combo.currentText())
        self.internal_net_combo.blockSignals(True)
        self.internal_net_combo.clear()
        for candidate in self._internal_net_candidates:
            self.internal_net_combo.addItem(candidate["net_name"], candidate["net_name"])
        if current_net:
            for index in range(self.internal_net_combo.count()):
                candidate_name = self.internal_net_combo.itemData(index) or self.internal_net_combo.itemText(index)
                if self._normalized_net_name(candidate_name) == current_net:
                    self.internal_net_combo.setCurrentIndex(index)
                    break
        if self.internal_net_combo.count() and self.internal_net_combo.currentIndex() < 0:
            self.internal_net_combo.setCurrentIndex(0)
        self.internal_net_combo.blockSignals(False)
        self._populate_internal_net_table()

    def _populate_internal_net_table(self, *_args) -> None:
        candidate = self._selected_internal_candidate()
        self.internal_connections_table.clearContents()
        if not candidate:
            self.internal_connections_table.setRowCount(0)
            self.preview_internal_btn.setEnabled(False)
            self.apply_internal_btn.setEnabled(False)
            selected_net = self.internal_net_combo.currentText().strip()
            if selected_net:
                self._append_log(f"Internal Net Inspector: no candidate matched selected net '{selected_net}'.\n")
            return

        elements = candidate["connected_elements"]
        self._append_log(
            f"Internal Net Inspector: selected net '{candidate['net_name']}' has {len(elements)} connected top-level statements.\n"
        )
        self.internal_connections_table.setRowCount(len(elements))
        has_driver = False
        for row, element in enumerate(elements):
            instance_item = QTableWidgetItem(element["instance_name"])
            type_item = QTableWidgetItem(element["classification"])
            line_item = QTableWidgetItem(element["line_preview"])
            move_item = QTableWidgetItem()
            move_item.setFlags(move_item.flags() | Qt.ItemIsUserCheckable)
            checked = element["move_default"]
            move_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            if element["classification"] == "driver":
                has_driver = True
            self._append_log(
                f"  - {element['instance_name']} ({element['statement_type']}) [{element['classification']}]\n"
            )
            self.internal_connections_table.setItem(row, 0, instance_item)
            self.internal_connections_table.setItem(row, 1, type_item)
            self.internal_connections_table.setItem(row, 2, line_item)
            self.internal_connections_table.setItem(row, 3, move_item)
        self.internal_connections_table.resizeColumnsToContents()
        can_apply = len(elements) >= 2 and has_driver
        self.preview_internal_btn.setEnabled(can_apply)
        self.apply_internal_btn.setEnabled(can_apply)

    def _selected_internal_candidate(self) -> dict | None:
        net_name = self._normalized_net_name(self.internal_net_combo.currentData() or self.internal_net_combo.currentText())
        if not net_name:
            return None
        for candidate in self._internal_net_candidates:
            if self._normalized_net_name(candidate["net_name"]) == net_name:
                return candidate
        return None

    def _selected_internal_driver_statements(self) -> list[str]:
        candidate = self._selected_internal_candidate()
        if not candidate:
            return []
        selected: list[str] = []
        for row, element in enumerate(candidate["connected_elements"]):
            item = self.internal_connections_table.item(row, 3)
            if item and item.checkState() == Qt.Checked:
                selected.append(element["instance_name"])
        return selected

    def _preview_internal_instrumentation(self) -> None:
        candidate = self._selected_internal_candidate()
        if not candidate:
            return
        moved_statements = self._selected_internal_driver_statements()
        if not moved_statements:
            QMessageBox.warning(self, "EM Manual", "Select at least one driver-side statement to move.")
            return
        try:
            preview = preview_manual_instrumentation(
                self.file_view.toPlainText(),
                candidate["net_name"],
                moved_statements,
                self._ensure_em_workspace_dirs()["inputs"] / "preview_manual_currents.txt",
            )
        except Exception as exc:
            QMessageBox.warning(self, "EM Manual", str(exc))
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("EM Manual Preview")
        dialog.setText(f"Preview for internal net {candidate['net_name']}")
        dialog.setDetailedText(preview["preview_text"])
        dialog.exec()

    def _apply_internal_instrumentation(self) -> None:
        candidate = self._selected_internal_candidate()
        if not candidate:
            return
        moved_statements = self._selected_internal_driver_statements()
        if not moved_statements:
            QMessageBox.warning(self, "EM Manual", "Select at least one driver-side statement to move.")
            return
        if len(candidate["connected_elements"]) < 2:
            QMessageBox.warning(self, "EM Manual", "Internal net requires at least two connected top-level elements.")
            return
        if all(element["classification"] == "passive" for element in candidate["connected_elements"]):
            QMessageBox.warning(self, "EM Manual", "Only passive elements are connected to this net. Skipping instrumentation.")
            return

        paths = self._ensure_em_workspace_dirs()
        run_name = self._compact_timestamp()
        netlist_path = paths["netlists"] / f"{run_name}__emprobe_manual.spice"
        map_path = paths["netlists"] / f"{run_name}__emprobe_manual_map.json"
        currents_path = paths["inputs"] / f"{run_name}_currents_manual.txt"
        try:
            metadata = write_manual_instrumented_netlist(
                source_text=self.file_view.toPlainText(),
                output_netlist_path=netlist_path,
                probe_map_path=map_path,
                net_name=candidate["net_name"],
                moved_statements=moved_statements,
                wrdata_output=currents_path,
            )
        except Exception as exc:
            QMessageBox.warning(self, "EM Manual", str(exc))
            return
        self._last_em_metadata_path = map_path
        self._append_log(
            f"Manual EM instrumentation written:\n"
            f"- Netlist: {netlist_path}\n"
            f"- Probe map: {map_path}\n"
        )
        QMessageBox.information(
            self,
            "EM Manual",
            f"Manual instrumentation created:\n{netlist_path}\n\nMoved statements:\n" + "\n".join(f"- {name}" for name in moved_statements),
        )

    @staticmethod
    def _normalized_net_name(value: str | None) -> str:
        return (value or "").strip().lower()

    def _add_probe_row(self, initial_text: str = "") -> None:
        row = QHBoxLayout()
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(self._candidate_points)
        if initial_text:
            combo.setEditText(initial_text)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda: self._remove_probe_row(combo))
        row.addWidget(combo, 1)
        row.addWidget(remove_btn)
        self.probe_layout.addLayout(row)
        self._probe_rows.append((row, combo, remove_btn))

    def _remove_probe_row(self, combo: QComboBox) -> None:
        if len(self._probe_rows) <= 1:
            combo.setEditText("")
            return

        for row, current_combo, button in list(self._probe_rows):
            if current_combo is not combo:
                continue
            while row.count():
                item = row.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            self.probe_layout.removeItem(row)
            self._probe_rows.remove((row, current_combo, button))
            return

    def _selected_probe_points(self) -> list[str]:
        points: list[str] = []
        for _, combo, _ in self._probe_rows:
            text = combo.currentText().strip()
            if text:
                points.append(text)
        return points

    def _write_generated_netlist(self, outputs: OutputPaths) -> Path:
        source_text = ensure_sky130_model_lib(
            self.file_view.toPlainText(),
            self.settings.pdk_paths.sky130a,
        )
        source_text = apply_model_corner(source_text, self.corner.currentText())
        analysis_type = self._analysis_type_key()
        params = {
            "tran_step": self.tran_step.text().strip(),
            "tran_stop": self.tran_stop.text().strip(),
            "tran_start": self.tran_start.text().strip(),
            "tran_uic": "1" if self.tran_uic.isChecked() else "",
            "ac_sweep": self.ac_sweep.currentText(),
            "ac_points": self.ac_points.text().strip(),
            "ac_start": self.ac_start.text().strip(),
            "ac_stop": self.ac_stop.text().strip(),
            "dc_source": self.dc_source.text().strip(),
            "dc_start": self.dc_start.text().strip(),
            "dc_stop": self.dc_stop.text().strip(),
            "dc_step": self.dc_step.text().strip(),
            "save_mode": self._save_mode_key(),
            "temp_c": self.temp_c.text().strip(),
        }
        generated = build_generated_netlist(
            source_text=source_text,
            analysis_type=analysis_type,
            analysis_params=params,
            save_points=self._selected_probe_points(),
            extra_directives=self.extra_directives.toPlainText(),
            preferred_subckt=Path(self.netlist_edit.text().strip() or "").stem,
            wrapper_options={
                "tiny_tapeout_initial_conditions": self.postlayout_use_ic.isChecked(),
                "tiny_tapeout_load_mode": str(self.postlayout_load_mode.currentData()),
                "tiny_tapeout_load_cap_value": self.postlayout_load_cap.text().strip(),
                "tiny_tapeout_load_res_value": self.postlayout_load_res.text().strip(),
            },
        )

        generated_path = outputs.results / "run.spice"
        generated_path.write_text(generated)
        return generated_path

    def _create_simulation_outputs(self) -> OutputPaths:
        base_outputs = self.outputs_getter()
        run_name = self._compact_timestamp()
        results_dir = base_outputs.results / run_name
        logs_dir = base_outputs.logs / run_name
        results_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        return OutputPaths(
            base=base_outputs.base,
            runs=base_outputs.runs,
            logs=logs_dir,
            results=results_dir,
            lvs=base_outputs.lvs,
            extraction=base_outputs.extraction,
            antenna=base_outputs.antenna,
        )

    def _prepare_em_followup(self, generated_netlist: Path, outputs: OutputPaths):
        try:
            repo_root = Path(__file__).resolve().parents[2]
            self._em_workspace_paths = ensure_em_workspace(repo_root)
            run_name = outputs.results.name
            instrumented_path = self._em_workspace_paths["netlists"] / f"{run_name}__emprobe.spice"
            currents_path = self._em_workspace_paths["inputs"] / f"{run_name}_currents.txt"
            raw_currents_path = self._em_workspace_paths["reports"] / f"{run_name}_currents_raw.txt"
            metadata_path = self._em_workspace_paths["netlists"] / f"{run_name}__emprobe_map.json"
            em_log_path = self._em_workspace_paths["reports"] / f"{run_name}_em_ngspice.log"
            em_raw_path = self._em_workspace_paths["reports"] / f"{run_name}_em.raw"
            metadata = instrument_netlist_for_em(
                input_netlist_path=str(generated_netlist),
                output_netlist_path=str(instrumented_path),
                config={
                    "project_mode": str(self.em_project_mode.currentData()),
                    "wrdata_output": str(raw_currents_path),
                },
            )
            write_em_probe_map(metadata_path, metadata)
            self._last_em_metadata_path = metadata_path
            command = [
                self.settings.tool_paths.ngspice,
                "-b",
                "-o",
                str(em_log_path),
                "-r",
                str(em_raw_path),
                str(instrumented_path),
            ]
            self._append_log(
                f"Prepared EM instrumented netlist: {instrumented_path}\n"
                f"EM probe map: {metadata_path}\n"
            )
            return {
                "spec": self.builder.build(command, cwd=str(self._em_workspace_paths["reports"])),
                "netlist_path": instrumented_path,
                "currents_path": currents_path,
                "raw_currents_path": raw_currents_path,
                "metadata_path": metadata_path,
                "metadata": metadata,
                "debug_only": self.debug_em_only_checkbox.isChecked(),
                "report_paths": [em_log_path, em_raw_path],
            }
        except Exception as exc:
            self._append_log(f"EM instrumentation skipped: {exc}\n")
            self.send_status.emit("EM instrumentation skipped")
            return None

    def _em_workflow_requested(self) -> bool:
        return self.generate_em_checkbox.isChecked() or self.debug_em_only_checkbox.isChecked()

    def _sync_em_options_state(self) -> None:
        em_enabled = self._em_workflow_requested()
        self.em_project_mode.setEnabled(em_enabled)
        self.keep_em_files_checkbox.setEnabled(em_enabled)

    def _sync_postlayout_load_controls(self) -> None:
        mode = str(self.postlayout_load_mode.currentData())
        self.postlayout_load_cap.setEnabled(mode in {"cap", "rc"})
        self.postlayout_load_res.setEnabled(mode == "rc")

    def _update_run_summary(self, status: str | None = None) -> None:
        self.summary_status_value.setText(status or self.summary_status_value.text())
        output_text = self.output_dir.text().strip() or "—"
        deck_text = self.generated_path_edit.text().strip() or "—"
        waveform_path = self._resolve_raw_path()
        waveform_text = waveform_path.name if waveform_path else pick(self.lang, "Sin cargar", "Not loaded")
        self.summary_output_value.setText(Path(output_text).name if output_text != "—" else output_text)
        self.summary_generated_value.setText(Path(deck_text).name if deck_text != "—" else deck_text)
        self.summary_waveform_value.setText(waveform_text)

    def _ensure_em_workspace_dirs(self) -> dict[str, Path]:
        if not self._em_workspace_paths:
            repo_root = Path(__file__).resolve().parents[2]
            self._em_workspace_paths = ensure_em_workspace(repo_root)
        return self._em_workspace_paths

    def _open_em_netlists_folder(self) -> None:
        paths = self._ensure_em_workspace_dirs()
        QDesktopServices.openUrl(paths["netlists"].as_uri())

    def _open_em_inputs_folder(self) -> None:
        paths = self._ensure_em_workspace_dirs()
        QDesktopServices.openUrl(paths["inputs"].as_uri())

    def _show_em_debug_summary(self, em_run: dict) -> None:
        lines = [f"Instrumented netlist generated:\n{em_run['netlist_path']}"]
        nets = [item["original_net"] for item in em_run["metadata"].get("probes", [])]
        if nets:
            lines.append("")
            lines.append("Instrumented nets:")
            lines.extend(f"- {net}" for net in nets)
        QMessageBox.information(self, "EM Debug", "\n".join(lines))

    def _cleanup_em_reports_if_needed(self) -> None:
        if self.keep_em_files_checkbox.isChecked() or not self._pending_em_run:
            return
        for path in self._pending_em_run.get("report_paths", []):
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

    def _refresh_measurement_targets(self) -> None:
        signal_names = self.wave.signal_names()
        current_metric = self.metric_signal.currentText()
        current_reference = self.metric_reference.currentData() or ""

        self.metric_signal.blockSignals(True)
        self.metric_signal.clear()
        self.metric_signal.addItems(signal_names)
        if current_metric:
            index = self.metric_signal.findText(current_metric)
            if index >= 0:
                self.metric_signal.setCurrentIndex(index)
        elif signal_names:
            self.metric_signal.setCurrentText(self.wave.current_signal_name() or signal_names[0])
        self.metric_signal.blockSignals(False)

        self.metric_reference.blockSignals(True)
        self.metric_reference.clear()
        self.metric_reference.addItem("None", "")
        for name in signal_names:
            self.metric_reference.addItem(name, name)
        if current_reference:
            index = self.metric_reference.findData(current_reference)
            if index >= 0:
                self.metric_reference.setCurrentIndex(index)
        self.metric_reference.blockSignals(False)

    def _sync_metric_selection(self, signal_name: str) -> None:
        if not signal_name:
            return
        index = self.metric_signal.findText(signal_name)
        if index >= 0:
            self.metric_signal.setCurrentIndex(index)

    def _update_measurements(self) -> None:
        signal_name = self.metric_signal.currentText() or self.wave.current_signal_name()
        signal_data = self.wave.signal_data(signal_name)
        if not signal_data:
            self._clear_measurements()
            self._clear_spectrum_plot()
            return

        reference_name = self.metric_reference.currentData()
        reference = self.wave.signal_data(reference_name) if reference_name else None
        if "time" in self.wave.signal_names():
            x_label = "time"
        elif "frequency" in self.wave.signal_names():
            x_label = "frequency"
        else:
            x_label = "sweep"

        try:
            metrics, spectrum = analyze_signal(signal_data[0], signal_data[1], x_label=x_label, reference=reference)
        except ValueError:
            self._clear_measurements()
            self._clear_spectrum_plot()
            return

        unit = self._signal_unit(signal_name)
        self.metric_labels["minimum"].setText(format_value(metrics.minimum, unit))
        self.metric_labels["maximum"].setText(format_value(metrics.maximum, unit))
        self.metric_labels["mean"].setText(format_value(metrics.mean, unit))
        self.metric_labels["rms"].setText(format_value(metrics.rms, unit))
        self.metric_labels["peak_to_peak"].setText(format_value(metrics.peak_to_peak, unit))
        self.metric_labels["amplitude"].setText(format_value(metrics.amplitude, unit))
        if metrics.x_label == "time":
            self.metric_labels["frequency_hz"].setText(format_value(metrics.frequency_hz, "Hz"))
            self.metric_labels["period_s"].setText(format_value(metrics.period_s, "s"))
            self.metric_labels["phase_deg"].setText(format_value(metrics.phase_deg, "deg"))
        else:
            self.metric_labels["frequency_hz"].setText("N/A")
            self.metric_labels["period_s"].setText("N/A")
            self.metric_labels["phase_deg"].setText("N/A")

        self.spectrum_plot.clear()
        self._update_spectrum_axis()
        spectrum_mode = self._spectrum_mode_key()
        should_show_spectrum = spectrum_mode == "Show" or (
            spectrum_mode == "Auto" and spectrum.frequencies and spectrum.magnitudes
        )
        if should_show_spectrum and spectrum.frequencies and spectrum.magnitudes:
            self._current_spectrum_signal_name = signal_name
            self._current_spectrum_has_data = True
            peak_magnitude = max(spectrum.magnitudes)
            spectrum_db = [
                20.0 * math.log10(max(value, 1e-15) / max(peak_magnitude, 1e-15))
                for value in spectrum.magnitudes
            ]
            self.spectrum_plot.setTitle(
                f"{pick(self.lang, 'Espectro', 'Spectrum')}  {signal_name}",
                color="#0f172a",
                size="12pt",
            )
            self.spectrum_plot.setLabel("left", "dB", units="dB")
            self.spectrum_plot.plot(spectrum.frequencies, spectrum_db, pen=pg.mkPen("#d97706", width=2.2))
            self._capture_spectrum_ranges(spectrum.frequencies, spectrum_db)
            self._update_spectrum_stats(
                spectrum.frequencies,
                spectrum_db,
                spectrum.dominant_frequency_hz,
            )
            self._apply_spectrum_scale()
            self.spectrum_plot.show()
        else:
            self._clear_spectrum_plot()

    def _update_spectrum_axis(self) -> None:
        use_log = self._spectrum_x_axis_key() == "log"
        self.spectrum_plot.setLogMode(x=use_log, y=False)
        self._apply_spectrum_scale()

    def _configure_spectrum_plot_appearance(self) -> None:
        self.spectrum_plot.setBackground("#ffffff")
        plot_item = self.spectrum_plot.getPlotItem()
        plot_item.showAxis("left")
        plot_item.showAxis("bottom")
        plot_item.getViewBox().setBackgroundColor("#ffffff")
        self.spectrum_plot.showGrid(x=True, y=True, alpha=0.24)
        for axis_name in ("left", "bottom"):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen("#94a3b8", width=1.15))
            axis.setTextPen(pg.mkPen("#334155"))
            axis.setTickPen(pg.mkPen("#cbd5e1", width=1.0))
        plot_item.getAxis("left").setStyle(tickTextOffset=10)
        plot_item.getAxis("bottom").setStyle(tickTextOffset=10)

    def _capture_spectrum_ranges(self, x: list[float], y: list[float]) -> None:
        if not x or not y:
            self._spectrum_base_x_range = None
            self._spectrum_base_y_range = None
            return

        self._spectrum_base_x_range = (min(x), max(x))
        y_max = max(y)
        y_min = max(min(y), y_max - 80.0)
        if y_min == y_max:
            pad = abs(y_min) * 0.05 or 1.0
            y_min -= pad
            y_max += pad
        self._spectrum_base_y_range = (y_min, y_max)

    def _apply_spectrum_scale(self) -> None:
        if not self._spectrum_base_x_range or not self._spectrum_base_y_range:
            return

        x_min, x_max = self._scaled_range(self._spectrum_base_x_range, self.spectrum_x_scale.value())
        base_y_min, base_y_max = self._spectrum_base_y_range
        base_span = max(base_y_max - base_y_min, 1.0)
        y_span = max(base_span * self.spectrum_y_scale.value(), 1.0)
        y_max = base_y_max + 3.0
        y_min = y_max - y_span
        if self._spectrum_x_axis_key() == "log":
            x_min = max(x_min, 1e-12)
            x_max = max(x_max, x_min * 1.01)
        self.spectrum_plot.enableAutoRange(x=False, y=False)
        self.spectrum_plot.setXRange(x_min, x_max, padding=0.0)
        self.spectrum_plot.setYRange(y_min, y_max, padding=0.05)

    def _reset_spectrum_view(self) -> None:
        self.spectrum_plot.enableAutoRange()
        self._apply_spectrum_scale()

    def _reset_spectrum_scale(self) -> None:
        self.spectrum_x_scale.blockSignals(True)
        self.spectrum_y_scale.blockSignals(True)
        self.spectrum_x_scale.setValue(1.0)
        self.spectrum_y_scale.setValue(1.0)
        self.spectrum_x_scale.blockSignals(False)
        self.spectrum_y_scale.blockSignals(False)
        self._apply_spectrum_scale()

    def _update_spectrum_stats(
        self,
        frequencies: list[float],
        magnitudes: list[float],
        dominant_frequency_hz: float | None,
    ) -> None:
        if not frequencies or not magnitudes:
            self.spectrum_stats.setText(pick(self.lang, "Sin datos", "No data"))
            return

        dominant = format_value(dominant_frequency_hz, "Hz") if dominant_frequency_hz else "N/A"
        self.spectrum_stats.setText(
            f"{pick(self.lang, 'Frecuencia dominante', 'Dominant frequency')}: {dominant}    "
            f"Hz: {self._format_plot_value(min(frequencies))} -> {self._format_plot_value(max(frequencies))}    "
            f"{pick(self.lang, 'Magnitud relativa', 'Relative magnitude')}: {self._format_plot_value(min(magnitudes))} -> {self._format_plot_value(max(magnitudes))} dB"
        )

    def _clear_spectrum_plot(self) -> None:
        self.spectrum_plot.clear()
        self.spectrum_plot.hide()
        self.spectrum_plot.setTitle("")
        self._spectrum_base_x_range = None
        self._spectrum_base_y_range = None
        self._current_spectrum_signal_name = ""
        self._current_spectrum_has_data = False
        self.spectrum_stats.setText(pick(self.lang, "Sin datos", "No data"))

    def _export_spectrum_plot(self, fmt: str) -> None:
        if not self._current_spectrum_signal_name or not self._current_spectrum_has_data:
            QMessageBox.information(
                self,
                pick(self.lang, "Sin gráfica", "No plot"),
                pick(self.lang, "Genera un espectro válido antes de exportar.", "Generate a valid spectrum before exporting."),
            )
            return

        suffix = ".png" if fmt == "png" else ".svg"
        default_name = f"{self._safe_name(self._current_spectrum_signal_name)}_spectrum{suffix}"
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {fmt.upper()}",
            str(Path.cwd() / default_name),
            f"{fmt.upper()} Files (*{suffix})",
        )
        if not selected_path:
            return

        target = Path(selected_path)
        if target.suffix.lower() != suffix:
            target = target.with_suffix(suffix)

        plot_item = self.spectrum_plot.getPlotItem()
        axes = {name: plot_item.getAxis(name) for name in ("left", "bottom")}
        original_background = self.spectrum_plot.backgroundBrush()
        original_title = plot_item.titleLabel.text
        try:
            self.spectrum_plot.setBackground("w")
            plot_item.setTitle(
                f"{pick(self.lang, 'Espectro de frecuencia', 'Frequency Spectrum')} · {self._current_spectrum_signal_name}",
                color="#111827",
                size="12pt",
            )
            for axis in axes.values():
                axis.setPen(pg.mkPen("#111827", width=1.2))
                axis.setTextPen(pg.mkPen("#111827"))
            exporter = (
                pyqtgraph.exporters.ImageExporter(plot_item)
                if fmt == "png"
                else pyqtgraph.exporters.SVGExporter(plot_item)
            )
            if fmt == "png":
                exporter.parameters()["width"] = 1600
                exporter.parameters()["height"] = 900
            exporter.export(str(target))
        except Exception as exc:
            QMessageBox.warning(
                self,
                pick(self.lang, "Error de exportación", "Export error"),
                f"{pick(self.lang, 'No se pudo exportar la gráfica', 'Failed to export plot')}: {exc}",
            )
            return
        finally:
            self.spectrum_plot.setBackground(original_background)
            plot_item.setTitle(original_title)
            self._configure_spectrum_plot_appearance()

        QMessageBox.information(
            self,
            pick(self.lang, "Exportación completa", "Export complete"),
            f"{pick(self.lang, 'Gráfica guardada en', 'Saved plot to')}:\n{target}",
        )

    def _clear_measurements(self) -> None:
        for label in self.metric_labels.values():
            label.setText("N/A")

    @staticmethod
    def _scaled_range(range_values: tuple[float, float], scale: float) -> tuple[float, float]:
        start, end = range_values
        if start == end:
            pad = abs(start) * 0.05 or 1.0
            return start - pad, end + pad

        center = (start + end) / 2.0
        span = (end - start) * scale
        half = span / 2.0
        return center - half, center + half

    @staticmethod
    def _format_plot_value(value: float) -> str:
        magnitude = abs(value)
        if magnitude >= 1:
            return f"{value:.4g}"
        if magnitude >= 1e-3:
            return f"{value:.4g}"
        return f"{value:.3e}"

    @staticmethod
    def _signal_unit(signal_name: str) -> str:
        if signal_name.startswith("mag("):
            return "dB"
        if signal_name.startswith("phase("):
            return "deg"
        if signal_name.startswith("i("):
            return "A"
        return "V"

    def _toggle_netlist_editor(self, checked: bool) -> None:
        if self.netlist_section is not None:
            self.netlist_section.set_expanded(checked)
        else:
            self.netlist_editor_box.setVisible(checked)

    def _paste_netlist(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Pegar netlist")
        dialog.resize(720, 520)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        file_name_edit = QLineEdit("pasted_netlist")
        form.addRow("Nombre:", file_name_edit)
        layout.addLayout(form)

        text_edit = QTextEdit()
        text_edit.setPlaceholderText("Pega aqui el contenido del netlist SPICE...")
        layout.addWidget(text_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        netlist_text = text_edit.toPlainText().strip()
        if not netlist_text:
            QMessageBox.warning(self, "Netlist vacio", "Pega el contenido del netlist antes de guardar.")
            return

        saved_path = self._store_pasted_netlist(file_name_edit.text(), netlist_text)
        self.load_netlist_path(str(saved_path))
        if self.netlist_section is not None:
            self.netlist_section.set_expanded(True)
        else:
            self.netlist_editor_box.setVisible(True)
        self._append_log(f"Pasted netlist saved to: {saved_path}\n")

    def _store_pasted_netlist(self, requested_name: str, netlist_text: str) -> Path:
        outputs = self.outputs_getter()
        netlists_dir = outputs.runs / "netlists"
        netlists_dir.mkdir(parents=True, exist_ok=True)

        base_name = self._short_name(Path(requested_name.strip() or "net").stem or "net", max_length=12)
        netlist_path = netlists_dir / f"{base_name}.spice"
        if netlist_path.exists():
            netlist_path = netlists_dir / f"{base_name}-{self._compact_timestamp()}.spice"
        netlist_path.write_text(netlist_text.rstrip() + "\n")
        return netlist_path

    def _show_log_dialog(self) -> None:
        if self.log_dialog is None:
            self.log_dialog = QDialog(self)
            self.log_dialog.setWindowTitle(pick(self.lang, "Log de simulación", "Simulation Log"))
            self.log_dialog.resize(900, 700)
            dialog_layout = QVBoxLayout(self.log_dialog)
            self.log_viewer = QTextEdit()
            self.log_viewer.setReadOnly(True)
            clear_btn = QPushButton("Clear log")
            clear_btn.clicked.connect(self._clear_log_views)
            dialog_layout.addWidget(self.log_viewer)
            dialog_layout.addWidget(clear_btn)

        if self.log_viewer is not None:
            self.log_viewer.setPlainText(self.log.toPlainText())
        self.log_dialog.show()
        self.log_dialog.raise_()
        self.log_dialog.activateWindow()

    def _clear_log_views(self) -> None:
        self.log.clear()
        if self.log_viewer is not None:
            self.log_viewer.clear()

    def _append_log(self, text: str) -> None:
        append_log(self.log, text)
        if self.log_viewer is not None:
            append_log(self.log_viewer, text)

    def _set_simulation_running(self, running: bool) -> None:
        self.run_btn.setDisabled(running)
        self.rerun_btn.setDisabled(running)
        self.stop_btn.setEnabled(running)
        self.loading_bar.setVisible(running)
        if running:
            self.summary_status_value.setText(pick(self.lang, "Corriendo", "Running"))

    def _ensure_editor_content(self) -> str:
        if self.file_view.toPlainText().strip():
            return self.file_view.toPlainText()

        netlist_path = self.netlist_edit.text().strip()
        if not netlist_path:
            return ""

        try:
            contents = Path(netlist_path).read_text()
        except OSError as exc:
            self._append_log(f"Failed to read file: {exc}\n")
            return ""

        self.file_view.setPlainText(contents)
        self._refresh_probe_points()
        return contents

    @staticmethod
    def _format_timestamp(raw_path: Path) -> str:
        return datetime.fromtimestamp(raw_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
        return cleaned.strip("_") or "simulation"

    @classmethod
    def _short_name(cls, value: str, max_length: int = 12) -> str:
        return cls._safe_name(value)[:max_length].rstrip("_") or "sim"

    @staticmethod
    def _compact_timestamp() -> str:
        return datetime.now().strftime("%y%m%d-%H%M")

    def _analysis_type_key(self) -> str:
        mapping = {
            pick(self.lang, "Transitorio", "Transient"): "Transient",
            "AC": "AC",
            "DC": "DC",
            pick(self.lang, "Punto de operación", "Operating Point"): "Operating Point",
        }
        return mapping.get(self.sim_type.currentText(), "Transient")

    def _save_mode_key(self) -> str:
        mapping = {
            pick(self.lang, "Todas las señales", "All signals"): "All signals",
            pick(self.lang, "Sólo probes seleccionados", "Selected probes only"): "Selected probes only",
        }
        return mapping.get(self.save_mode.currentText(), "All signals")

    def _spectrum_mode_key(self) -> str:
        mapping = {
            pick(self.lang, "Auto", "Auto"): "Auto",
            pick(self.lang, "Mostrar", "Show"): "Show",
            pick(self.lang, "Ocultar", "Hide"): "Hide",
        }
        return mapping.get(self.spectrum_mode.currentText(), "Auto")

    def _spectrum_x_axis_key(self) -> str:
        mapping = {
            pick(self.lang, "Hz lineal", "Linear Hz"): "linear",
            pick(self.lang, "Hz log", "Log Hz"): "log",
        }
        return mapping.get(self.spectrum_x_axis.currentText(), "linear")
