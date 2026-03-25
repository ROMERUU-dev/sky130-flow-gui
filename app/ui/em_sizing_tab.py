"""EM sizing tab for branch current waveform analysis."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.i18n import pick
from app.core.settings_manager import AppSettings
from app.models.em_models import AnalysisBundle
from app.services.em_service import EmService


class EmSizingTab(QWidget):
    """Analyze ngspice current waveforms and estimate routing needs."""

    send_status = Signal(str)

    def __init__(self, settings: AppSettings, outputs_getter) -> None:
        super().__init__()
        self.settings = settings
        self.lang = settings.language
        self.outputs_getter = outputs_getter
        self.service = EmService()

        self.current_bundle: AnalysisBundle | None = None
        self.current_source_path: Path | None = None
        self.manual_types: dict[str, str] = {}

        self.file_edit = QLineEdit()
        self.source_summary = QLabel(pick(self.lang, "Sin archivo cargado", "No file loaded"))
        self.instrumented_nets_view = QTextEdit()
        self.profile_combo = QComboBox()
        self.project_mode_combo = QComboBox()
        self.allow_metal5_checkbox = QCheckBox(pick(self.lang, "Permitir Metal 5", "Allow Metal 5"))
        self.metric_combo = QComboBox()
        self.metal_combo = QComboBox()
        self.via_combo = QComboBox()
        self.margin_spin = QDoubleSpinBox()
        self.results_table = QTableWidget(0, 13)
        self.detail_text = QTextEdit()
        self.warning_text = QTextEdit()
        self.branch_type_override = QComboBox()
        self.branch_type_apply_btn = QPushButton(pick(self.lang, "Aplicar tipo", "Apply Type"))
        self.magic_wire_value = QLabel("-")
        self.copy_magic_btn = QToolButton()

        self._build_ui()
        self._populate_controls()
        self._wire()
        self._refresh_instrumented_nets_view()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        file_group = QGroupBox(pick(self.lang, "Archivo de corrientes", "Current Waveform File"))
        file_form = QFormLayout(file_group)

        file_row = QHBoxLayout()
        file_row.addWidget(self.file_edit)
        browse_btn = QPushButton(pick(self.lang, "Buscar", "Browse"))
        reload_btn = QPushButton(pick(self.lang, "Recargar", "Reload"))
        latest_btn = QPushButton(pick(self.lang, "Cargar último resultado EM", "Load Latest EM Result"))
        file_row.addWidget(browse_btn)
        file_row.addWidget(reload_btn)
        file_row.addWidget(latest_btn)
        file_form.addRow(pick(self.lang, "Archivo", "File"), file_row)
        file_form.addRow(pick(self.lang, "Estado", "Status"), self.source_summary)
        self.instrumented_nets_view.setReadOnly(True)
        self.instrumented_nets_view.setFixedHeight(80)
        file_form.addRow(pick(self.lang, "Nets instrumentadas (última corrida)", "Instrumented nets (from last run)"), self.instrumented_nets_view)

        controls_group = QGroupBox(pick(self.lang, "Reglas y criterio", "Rules and Design Metric"))
        controls_form = QFormLayout(controls_group)
        controls_form.addRow(pick(self.lang, "Perfil EM", "EM Profile"), self.profile_combo)
        controls_form.addRow(pick(self.lang, "Modo de proyecto", "Project Mode"), self.project_mode_combo)
        controls_form.addRow("", self.allow_metal5_checkbox)
        controls_form.addRow(pick(self.lang, "Métrica de diseño", "Design Metric"), self.metric_combo)
        controls_form.addRow(pick(self.lang, "Metal objetivo", "Target Metal"), self.metal_combo)
        controls_form.addRow(pick(self.lang, "Tipo de vía", "Via Type"), self.via_combo)
        controls_form.addRow(pick(self.lang, "Factor de margen", "Margin Factor"), self.margin_spin)

        top_row = QHBoxLayout()
        top_row.addWidget(file_group, 3)
        top_row.addWidget(controls_group, 2)
        layout.addLayout(top_row)

        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setHorizontalHeaderLabels(
            [
                pick(self.lang, "Branch", "Branch"),
                pick(self.lang, "Tipo", "Type"),
                "I_avg [A]",
                "I_rms [A]",
                "I_peak [A]",
                pick(self.lang, "Métrica", "Metric"),
                "I_design [A]",
                pick(self.lang, "Metal", "Metal"),
                "Width req [um]",
                "Width final [um]",
                pick(self.lang, "Vías", "Vias"),
                pick(self.lang, "Arreglo", "Array"),
                pick(self.lang, "Estado", "Status"),
            ]
        )

        self.detail_text.setReadOnly(True)
        self.warning_text.setReadOnly(True)

        detail_group = QGroupBox(pick(self.lang, "Detalle de rama", "Branch Detail"))
        detail_layout = QVBoxLayout(detail_group)
        override_row = QHBoxLayout()
        override_row.addWidget(QLabel(pick(self.lang, "Override de tipo", "Type Override")))
        override_row.addWidget(self.branch_type_override)
        override_row.addWidget(self.branch_type_apply_btn)
        detail_layout.addLayout(override_row)
        magic_row = QHBoxLayout()
        magic_row.addWidget(QLabel(pick(self.lang, "Magic wire", "Magic wire")))
        magic_row.addWidget(self.magic_wire_value, 1)
        self.copy_magic_btn.setText("Copy")
        self.copy_magic_btn.setToolTip(pick(self.lang, "Copiar comando de wire para Magic", "Copy Magic wire command"))
        self.copy_magic_btn.setAutoRaise(True)
        self.copy_magic_btn.setEnabled(False)
        magic_row.addWidget(self.copy_magic_btn)
        detail_layout.addLayout(magic_row)
        detail_layout.addWidget(self.detail_text)

        warnings_group = QGroupBox(pick(self.lang, "Advertencias y supuestos", "Warnings and Assumptions"))
        warnings_layout = QVBoxLayout(warnings_group)
        warnings_layout.addWidget(self.warning_text)

        export_row = QHBoxLayout()
        export_csv_btn = QPushButton("Export CSV")
        export_json_btn = QPushButton("Export JSON")
        export_txt_btn = QPushButton(pick(self.lang, "Exportar reporte TXT", "Export Text Report"))
        export_row.addWidget(export_csv_btn)
        export_row.addWidget(export_json_btn)
        export_row.addWidget(export_txt_btn)
        warnings_layout.addLayout(export_row)

        splitter = QSplitter(Qt.Vertical)
        upper = QWidget()
        upper_layout = QVBoxLayout(upper)
        upper_layout.addWidget(self.results_table)
        lower = QWidget()
        lower_layout = QHBoxLayout(lower)
        lower_layout.addWidget(detail_group, 3)
        lower_layout.addWidget(warnings_group, 2)
        splitter.addWidget(upper)
        splitter.addWidget(lower)
        splitter.setSizes([520, 280])
        layout.addWidget(splitter, 1)

        browse_btn.clicked.connect(self._pick_file)
        reload_btn.clicked.connect(self.reload_current_file)
        latest_btn.clicked.connect(self.load_latest_result)
        export_csv_btn.clicked.connect(lambda: self._export_bundle("csv"))
        export_json_btn.clicked.connect(lambda: self._export_bundle("json"))
        export_txt_btn.clicked.connect(lambda: self._export_bundle("txt"))

    def _populate_controls(self) -> None:
        self.profile_combo.addItems(self.service.list_profiles())
        self.project_mode_combo.addItem("Tiny Tapeout", "tiny_tapeout")
        self.project_mode_combo.addItem("Custom SKY130", "custom_sky130")
        self.metric_combo.addItem(pick(self.lang, "Auto", "Auto"), "auto")
        self.metric_combo.addItem(pick(self.lang, "Promedio", "Average"), "average")
        self.metric_combo.addItem("RMS", "rms")
        self.metric_combo.addItem(pick(self.lang, "Pico", "Peak"), "peak")
        self.margin_spin.setDecimals(2)
        self.margin_spin.setRange(1.00, 10.0)
        self.margin_spin.setSingleStep(0.05)
        self.margin_spin.setValue(1.25)
        self.allow_metal5_checkbox.setChecked(False)
        self.branch_type_override.addItem("power", "power")
        self.branch_type_override.addItem("output", "output")
        self.branch_type_override.addItem("signal", "signal")
        self._refresh_profile_dependent_controls()

    def _wire(self) -> None:
        self.profile_combo.currentIndexChanged.connect(self._refresh_profile_dependent_controls)
        self.project_mode_combo.currentIndexChanged.connect(self._handle_project_mode_changed)
        self.allow_metal5_checkbox.toggled.connect(self._handle_allow_metal5_changed)
        self.metal_combo.currentIndexChanged.connect(self._sync_default_via)
        self.via_combo.currentIndexChanged.connect(self._reanalyze_if_ready)
        self.metric_combo.currentIndexChanged.connect(self._reanalyze_if_ready)
        self.margin_spin.valueChanged.connect(self._reanalyze_if_ready)
        self.results_table.itemSelectionChanged.connect(self._update_detail_panel)
        self.results_table.itemSelectionChanged.connect(self._update_warning_panel)
        self.branch_type_apply_btn.clicked.connect(self._apply_branch_type_override)
        self.copy_magic_btn.clicked.connect(self._copy_magic_wire_command)

    def _refresh_profile_dependent_controls(self) -> None:
        profile = self.service.get_profile(self.profile_combo.currentText())
        current_metal = self.metal_combo.currentData()
        current_via = self.via_combo.currentData()
        allowed_metals = self._allowed_metal_names(profile)

        self.metal_combo.blockSignals(True)
        self.via_combo.blockSignals(True)
        self.metal_combo.clear()
        self.via_combo.clear()
        for metal_name in allowed_metals:
            self.metal_combo.addItem(metal_name, metal_name)
        for via_name in profile.vias:
            self.via_combo.addItem(via_name, via_name)
        self.via_combo.addItem(pick(self.lang, "Auto (según metal)", "Auto (from metal)"), "auto")
        self.metal_combo.blockSignals(False)
        self.via_combo.blockSignals(False)

        if current_metal:
            index = self.metal_combo.findData(current_metal)
            if index >= 0:
                self.metal_combo.setCurrentIndex(index)
        if current_via:
            index = self.via_combo.findData(current_via)
            if index >= 0:
                self.via_combo.setCurrentIndex(index)
        if self.metal_combo.currentIndex() < 0:
            self.metal_combo.setCurrentIndex(0)
        self._sync_default_via()
        self._reanalyze_if_ready()

    def _sync_default_via(self) -> None:
        if self.via_combo.findData("auto") >= 0:
            self.via_combo.setCurrentIndex(self.via_combo.findData("auto"))
        self._reanalyze_if_ready()

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            pick(self.lang, "Selecciona archivo de corrientes", "Select Current Waveform File"),
            "",
            "Waveforms (*.csv *.txt *.dat *.out);;All Files (*)",
        )
        if path:
            self.file_edit.setText(path)
            self.load_current_file(path)

    def reload_current_file(self) -> None:
        if not self.file_edit.text().strip():
            QMessageBox.information(self, "EM Sizing", pick(self.lang, "Selecciona un archivo primero.", "Select a file first."))
            return
        self.load_current_file(self.file_edit.text().strip())

    def load_latest_result(self) -> None:
        em_inputs = self._em_inputs_dir()
        em_candidates = []
        if em_inputs.exists():
            em_candidates = [path for path in em_inputs.rglob("*") if path.suffix.lower() in {".csv", ".txt", ".dat", ".out"}]
        if em_candidates:
            latest = max(em_candidates, key=lambda path: path.stat().st_mtime)
            self.file_edit.setText(str(latest))
            self._refresh_instrumented_nets_view()
            self.load_current_file(latest)
            return

        candidates: list[Path] = []
        for folder in [self.outputs_getter().results, self.outputs_getter().logs, self.outputs_getter().base]:
            if folder.exists():
                candidates.extend(path for path in folder.rglob("*") if path.suffix.lower() in {".csv", ".txt", ".dat", ".out"})
        if not candidates:
            QMessageBox.information(
                self,
                "EM Sizing",
                pick(
                    self.lang,
                    "No se encontraron archivos de corrientes en workspace/em/inputs ni en la raíz activa de outputs.",
                    "No current waveform files were found in workspace/em/inputs or the active output root.",
                ),
            )
            return
        latest = max(candidates, key=lambda path: path.stat().st_mtime)
        self.file_edit.setText(str(latest))
        self._refresh_instrumented_nets_view()
        self.load_current_file(latest)

    def load_current_file(self, path: str | Path) -> None:
        self.current_bundle = None
        self._clear_detail_state()
        self.warning_text.clear()
        try:
            parsed = self.service.parse_waveform_file(path, probe_map_path=self._matching_probe_map_path(path))
        except Exception as exc:
            QMessageBox.warning(self, "EM Sizing", str(exc))
            self.source_summary.setText(pick(self.lang, "Error al cargar archivo", "Failed to load file"))
            self.send_status.emit(pick(self.lang, "Error cargando archivo de EM", "Failed to load EM waveform file"))
            return

        self.current_source_path = parsed.source_path
        self.manual_types.clear()
        self.source_summary.setText(
            f"{pick(self.lang, 'Ramas', 'Branches')}: {len(parsed.branches)} | "
            f"{pick(self.lang, 'Muestras', 'Samples')}: {len(parsed.time_values_s)} | "
            f"{pick(self.lang, 'Formato', 'Format')}: {parsed.detected_delimiter}"
        )
        self._refresh_instrumented_nets_view()
        self._run_analysis(parsed)

    def _run_analysis(self, parsed=None) -> None:
        if parsed is None:
            if not self.current_source_path:
                return
            try:
                parsed = self.service.parse_waveform_file(self.current_source_path)
            except Exception as exc:
                QMessageBox.warning(self, "EM Sizing", str(exc))
                return
        try:
            bundle = self.service.analyze(
                parsed=parsed,
                profile_name=self.profile_combo.currentText(),
                metric_mode=str(self.metric_combo.currentData()),
                target_metal=str(self.metal_combo.currentData()),
                via_type=str(self.via_combo.currentData()),
                margin_factor=float(self.margin_spin.value()),
                manual_types=self.manual_types,
            )
        except Exception as exc:
            QMessageBox.warning(self, "EM Sizing", str(exc))
            return

        previous_branch_name = self._selected_branch_name()
        self.current_bundle = bundle
        self._populate_results_table(previous_branch_name)
        self._update_warning_panel()
        self.send_status.emit(pick(self.lang, "Análisis EM actualizado", "EM analysis updated"))

    def _reanalyze_if_ready(self, *_args) -> None:
        if self.current_source_path:
            self._run_analysis()

    def _populate_results_table(self, preferred_branch_name: str = "") -> None:
        bundle = self.current_bundle
        if bundle is None:
            return
        self.results_table.clearContents()
        self.results_table.clearSelection()
        self.results_table.setRowCount(len(bundle.branches))
        for row, branch in enumerate(bundle.branches):
            values = [
                branch.branch_name,
                branch.branch_type,
                self._fmt(branch.metrics.average_a),
                self._fmt(branch.metrics.rms_a),
                self._fmt(branch.metrics.peak_abs_a),
                branch.metric_used,
                self._fmt(branch.design_current_a),
                branch.target_metal,
                self._fmt(branch.width_required_um),
                self._fmt(branch.width_final_um),
                str(branch.vias_required),
                f"{branch.via_rows}x{branch.via_cols}",
                branch.status,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col >= 2 and col not in {5, 7, 10, 11, 12}:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.results_table.setItem(row, col, item)
        self.results_table.resizeColumnsToContents()
        if bundle.branches:
            selected_row = self._find_branch_row(preferred_branch_name)
            if selected_row < 0:
                selected_row = 0
            self.results_table.setCurrentCell(selected_row, 0)
            self.results_table.selectRow(selected_row)
            self._update_detail_panel()
            self._update_warning_panel()
        else:
            self._clear_detail_state()
            self.warning_text.clear()

    def _update_detail_panel(self) -> None:
        bundle = self.current_bundle
        row = self.results_table.currentRow()
        if bundle is None or row < 0 or row >= len(bundle.branches):
            self._clear_detail_state()
            return
        branch = bundle.branches[row]
        profile = self.service.get_profile(bundle.profile_name)
        metal = profile.metals[branch.target_metal]
        via = profile.vias[branch.via_type]
        self._set_branch_override_combo(branch.branch_name, branch.branch_type)
        self._set_magic_wire_command(branch)
        detail = [
            f"Source file: {branch.source_file}",
            f"Profile: {bundle.profile_name}",
            f"Branch: {branch.branch_name}",
            f"Classification: {branch.branch_type}",
            f"Selected metric: {branch.metric_used}",
            f"Requested mode: {branch.metric_mode_requested}",
            f"Margin factor: {branch.margin_factor:.3f}",
            "",
            "Formulas:",
            "I_avg = mean(i)",
            "I_rms = sqrt(mean(i^2))",
            "I_peak = max(abs(i))",
            "A_req = I_design / J_allow",
            "width_req = A_req / thickness",
            "N_vias = ceil(I_design / I_via_allow)",
            "",
            "Calculation details:",
            f"I_avg = {branch.metrics.average_a:.6g} A",
            f"I_rms = {branch.metrics.rms_a:.6g} A",
            f"I_peak = {branch.metrics.peak_abs_a:.6g} A",
            f"I_design = {branch.selected_metric_a:.6g} A * {branch.margin_factor:.3f} = {branch.design_current_a:.6g} A",
            f"Metal thickness [um] = {metal.thickness_um:.6g}",
            f"J_allow [mA/um^2] = {metal.allowed_current_density_ma_per_um2:.6g}",
            f"Width required [um] = {branch.width_required_um:.6g}",
            f"Width final [um] = max(width_req, {metal.minimum_width_um:.6g} um) rounded to {metal.routing_grid_um:.6g} um = {branch.width_final_um:.6g}",
            f"Via type = {via.name}",
            f"I_via_allow [mA] = {via.allowed_current_ma:.6g}",
            f"Via recommendation = {branch.vias_required} as {branch.via_rows}x{branch.via_cols}",
            "",
            "Warnings:",
        ]
        if branch.warnings:
            detail.extend(f"- {warning}" for warning in branch.warnings)
        else:
            detail.append("- None")
        self.detail_text.setPlainText("\n".join(detail))

    def _set_branch_override_combo(self, branch_name: str, branch_type: str) -> None:
        stored = self.manual_types.get(branch_name, branch_type)
        index = self.branch_type_override.findData(stored)
        if index >= 0:
            self.branch_type_override.setCurrentIndex(index)

    def _apply_branch_type_override(self) -> None:
        bundle = self.current_bundle
        row = self.results_table.currentRow()
        if bundle is None or row < 0 or row >= len(bundle.branches):
            return
        branch = bundle.branches[row]
        self.manual_types[branch.branch_name] = str(self.branch_type_override.currentData())
        self._run_analysis()

    def _update_warning_panel(self) -> None:
        if self.current_bundle is None:
            self.warning_text.clear()
            return
        lines = ["Global assumptions:"]
        lines.extend(f"- {warning}" for warning in self.current_bundle.general_warnings)
        if self.allow_metal5_checkbox.isChecked():
            lines.append("- Metal 5 is user-enabled. Verify routing stack constraints before relying on this recommendation.")
        selected_row = self.results_table.currentRow()
        if 0 <= selected_row < len(self.current_bundle.branches):
            branch = self.current_bundle.branches[selected_row]
            lines.append("")
            lines.append(f"Selected branch status: {branch.status}")
            lines.extend(f"- {warning}" for warning in branch.warnings)
        self.warning_text.setPlainText("\n".join(lines))

    def _export_bundle(self, export_kind: str) -> None:
        if self.current_bundle is None:
            QMessageBox.information(self, "EM Sizing", pick(self.lang, "No hay resultados para exportar.", "No results available to export."))
            return

        outputs = self.outputs_getter()
        default_dir = outputs.results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = self.current_source_path.stem if self.current_source_path else "em_sizing"
        if export_kind == "csv":
            file_name = default_dir / f"{stem}_em_sizing_{timestamp}.csv"
            selected, _ = QFileDialog.getSaveFileName(self, "Export CSV", str(file_name), "CSV (*.csv)")
            if selected:
                self.service.export_csv(self.current_bundle, selected)
                self.send_status.emit(pick(self.lang, "Exportación EM completada", "EM export completed"))
        elif export_kind == "json":
            file_name = default_dir / f"{stem}_em_sizing_{timestamp}.json"
            selected, _ = QFileDialog.getSaveFileName(self, "Export JSON", str(file_name), "JSON (*.json)")
            if selected:
                self.service.export_json(self.current_bundle, selected)
                self.send_status.emit(pick(self.lang, "Exportación EM completada", "EM export completed"))
        else:
            file_name = default_dir / f"{stem}_em_sizing_{timestamp}.txt"
            selected, _ = QFileDialog.getSaveFileName(self, "Export Text Report", str(file_name), "Text (*.txt)")
            if selected:
                self.service.export_text_report(self.current_bundle, selected)
                self.send_status.emit(pick(self.lang, "Exportación EM completada", "EM export completed"))

    def _selected_branch_name(self) -> str:
        bundle = self.current_bundle
        row = self.results_table.currentRow()
        if bundle is None or row < 0 or row >= len(bundle.branches):
            return ""
        return bundle.branches[row].branch_name

    def _find_branch_row(self, branch_name: str) -> int:
        if not branch_name or self.current_bundle is None:
            return -1
        for row, branch in enumerate(self.current_bundle.branches):
            if branch.branch_name == branch_name:
                return row
        return -1

    def _clear_detail_state(self) -> None:
        self.detail_text.clear()
        self.magic_wire_value.setText("-")
        self.copy_magic_btn.setEnabled(False)

    def _set_magic_wire_command(self, branch) -> None:
        command = self._magic_wire_command(branch.target_metal, branch.width_final_um)
        self.magic_wire_value.setText(command)
        self.copy_magic_btn.setEnabled(True)

    def _copy_magic_wire_command(self) -> None:
        branch = self._current_branch()
        if branch is None:
            self.copy_magic_btn.setEnabled(False)
            return
        command = self._magic_wire_command(branch.target_metal, branch.width_final_um)
        QApplication.clipboard().setText(command)
        self.send_status.emit(f"Copied: {command}")

    def _current_branch(self):
        bundle = self.current_bundle
        row = self.results_table.currentRow()
        if bundle is None or row < 0 or row >= len(bundle.branches):
            return None
        return bundle.branches[row]

    @staticmethod
    def _magic_wire_command(metal: str, width_um: float) -> str:
        return f"wire type {metal}\nwire width {width_um:.3f}um"

    def _handle_project_mode_changed(self) -> None:
        mode = str(self.project_mode_combo.currentData())
        if mode == "custom_sky130":
            self.allow_metal5_checkbox.setChecked(True)
        else:
            self.allow_metal5_checkbox.setChecked(False)
        self._refresh_profile_dependent_controls()

    def _handle_allow_metal5_changed(self, enabled: bool) -> None:
        self._refresh_profile_dependent_controls()
        if enabled:
            self.send_status.emit("Metal 5 enabled for EM sizing review")
        self._update_warning_panel()

    def _allowed_metal_names(self, profile) -> list[str]:
        metals = list(profile.metals)
        if self.allow_metal5_checkbox.isChecked():
            return metals
        return [metal for metal in metals if metal != "met5"]

    @staticmethod
    def _em_inputs_dir() -> Path:
        return Path(__file__).resolve().parents[2] / "workspace" / "em" / "inputs"

    def _refresh_instrumented_nets_view(self) -> None:
        latest_map = self._matching_probe_map_path(self.current_source_path) if self.current_source_path else self._latest_probe_map_path()
        if latest_map is None:
            self.instrumented_nets_view.setPlainText(pick(self.lang, "Sin mapa de probes EM todavía.", "No EM probe map available yet."))
            return
        try:
            payload = json.loads(latest_map.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.instrumented_nets_view.setPlainText(pick(self.lang, "No se pudo leer el mapa de probes EM.", "Failed to read the EM probe map."))
            return
        nets = [item.get("original_net", "") for item in payload.get("probes", []) if item.get("original_net")]
        if not nets:
            self.instrumented_nets_view.setPlainText(pick(self.lang, "No hay nets instrumentadas en el último mapa.", "No instrumented nets were found in the latest map."))
            return
        self.instrumented_nets_view.setPlainText("\n".join(nets))

    @staticmethod
    def _latest_probe_map_path() -> Path | None:
        netlists_dir = Path(__file__).resolve().parents[2] / "workspace" / "em" / "netlists"
        if not netlists_dir.exists():
            return None
        candidates = sorted(netlists_dir.glob("*__emprobe_map.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        return candidates[0] if candidates else None

    @staticmethod
    def _matching_probe_map_path(data_path: str | Path | None) -> Path | None:
        if data_path is None:
            return EmSizingTab._latest_probe_map_path()
        path = Path(data_path).expanduser().resolve()
        netlists_dir = Path(__file__).resolve().parents[2] / "workspace" / "em" / "netlists"
        if not netlists_dir.exists():
            return None
        stem = path.stem
        if stem.endswith("_currents"):
            candidate = netlists_dir / f"{stem[:-9]}__emprobe_map.json"
            if candidate.exists():
                return candidate
        if stem.endswith("_currents_manual"):
            candidate = netlists_dir / f"{stem[:-16]}__emprobe_manual_map.json"
            if candidate.exists():
                return candidate
        return EmSizingTab._latest_probe_map_path()

    @staticmethod
    def _fmt(value: float) -> str:
        return f"{value:.6g}"
