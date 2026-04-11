"""Project/files tab."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.i18n import pick
from app.core.project_manager import ProjectManager
from app.core.repo_readiness import RepoReadinessChecker


class ProjectTab(QWidget):
    """Project folder selection and file discovery."""

    project_changed = Signal(str)

    def __init__(self, manager: ProjectManager, recent_projects: list[str], language: str = "es") -> None:
        super().__init__()
        self.manager = manager
        self.recent_projects = recent_projects
        self.lang = language
        self.readiness_checker = RepoReadinessChecker()

        self.current_label = QLabel(pick(self.lang, "No hay proyecto seleccionado", "No project selected"))
        self.files = QListWidget()
        self.recent = QListWidget()
        self.info = QTextEdit()
        self.info.setReadOnly(True)

        self._build_ui()
        self._load_recent()
        self._refresh_context_label()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        row = QGridLayout()
        row.setHorizontalSpacing(8)
        row.setVerticalSpacing(8)
        create_tt = QPushButton(pick(self.lang, "Crear proyecto Tiny Tapeout", "Create Tiny Tapeout Project"))
        create_tt.clicked.connect(self.create_tiny_tapeout_project)
        row.addWidget(create_tt, 0, 0)

        pick_btn = QPushButton(pick(self.lang, "Seleccionar carpeta de proyecto", "Select Project Folder"))
        pick_btn.clicked.connect(self.pick_project)
        row.addWidget(pick_btn, 0, 1)

        open_results = QPushButton(pick(self.lang, "Abrir Runs/Results", "Open Runs/Results"))
        open_results.clicked.connect(lambda: self._open_output_subfolder("results"))
        row.addWidget(open_results, 1, 0)

        open_logs = QPushButton(pick(self.lang, "Abrir Runs/Logs", "Open Runs/Logs"))
        open_logs.clicked.connect(lambda: self._open_output_subfolder("logs"))
        row.addWidget(open_logs, 1, 1)

        open_workspace = QPushButton(pick(self.lang, "Abrir raíz de outputs activa", "Open Active Output Root"))
        open_workspace.clicked.connect(self._open_output_root)
        row.addWidget(open_workspace, 2, 0, 1, 2)
        check_repo = QPushButton(pick(self.lang, "Revisar repo para GitHub", "Check repo for GitHub"))
        check_repo.clicked.connect(self.check_repo_readiness)
        row.addWidget(check_repo, 3, 0, 1, 2)
        row.setColumnStretch(0, 1)
        row.setColumnStretch(1, 1)

        layout.addLayout(row)
        layout.addWidget(self.current_label)
        layout.addWidget(QLabel(pick(self.lang, "Archivos detectados del flujo", "Detected Flow Files")))
        layout.addWidget(self.files)
        layout.addWidget(QLabel(pick(self.lang, "Proyectos recientes", "Recent Projects")))
        layout.addWidget(self.recent)
        layout.addWidget(self.info)

        self.recent.itemDoubleClicked.connect(self._open_recent)

    def _load_recent(self) -> None:
        self.recent.clear()
        for item in self.recent_projects:
            self.recent.addItem(item)

    def pick_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, pick(self.lang, "Selecciona proyecto", "Select project"))
        if path:
            self.set_project(path)

    def check_repo_readiness(self) -> None:
        if not self.manager.current_project:
            QMessageBox.warning(
                self,
                pick(self.lang, "Sin proyecto", "No project"),
                pick(self.lang, "Selecciona o crea un proyecto primero.", "Select or create a project first."),
            )
            return
        checks = self.readiness_checker.check(self.manager.current_project)
        counts = {
            "ok": sum(1 for check in checks if check.status == "ok"),
            "warning": sum(1 for check in checks if check.status == "warning"),
            "error": sum(1 for check in checks if check.status == "error"),
        }
        icon = {"ok": "OK", "warning": "WARN", "error": "ERROR"}
        lines = [
            pick(self.lang, "Revision local para GitHub / Tiny Tapeout", "Local GitHub / Tiny Tapeout readiness check"),
            f"OK: {counts['ok']} | WARN: {counts['warning']} | ERROR: {counts['error']}",
            "",
        ]
        for check in checks:
            path_text = f" ({check.path})" if check.path else ""
            lines.append(f"[{icon.get(check.status, check.status.upper())}] {check.title}: {check.detail}{path_text}")
        self.info.setPlainText("\n".join(lines))

    def create_tiny_tapeout_project(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(pick(self.lang, "Nuevo proyecto Tiny Tapeout", "New Tiny Tapeout Project"))
        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        parent_edit = QLineEdit(str(Path.home()))
        browse_parent = QPushButton(pick(self.lang, "Buscar", "Browse"))
        parent_row = QHBoxLayout()
        parent_row.addWidget(parent_edit, 1)
        parent_row.addWidget(browse_parent)
        form.addRow(pick(self.lang, "Carpeta padre", "Parent folder"), parent_row)

        name_edit = QLineEdit("tt_um_new_project")
        top_edit = QLineEdit("tt_um_new_project")
        title_edit = QLineEdit("Nuevo proyecto Tiny Tapeout")
        author_edit = QLineEdit("")
        desc_edit = QTextEdit()
        desc_edit.setMaximumHeight(80)
        desc_edit.setPlaceholderText(pick(self.lang, "Describe qué hace el chip.", "Describe what the chip does."))
        kind_combo = QComboBox()
        kind_combo.addItem(pick(self.lang, "Digital", "Digital"), "digital")
        kind_combo.addItem(pick(self.lang, "Analógico", "Analog"), "analog")
        kind_combo.addItem("Mixed-signal", "mixed_signal")
        tile_combo = QComboBox()
        tile_combo.addItems(["1x2", "2x2"])
        analog_pins_combo = QComboBox()
        analog_pins_combo.addItems([str(index) for index in range(7)])
        analog_pins_combo.setCurrentText("2")
        uses_3v3_combo = QComboBox()
        uses_3v3_combo.addItem(pick(self.lang, "No, sólo 1.8V", "No, 1.8V only"), "false")
        uses_3v3_combo.addItem(pick(self.lang, "Sí, usa VAPWR 3.3V", "Yes, uses VAPWR 3.3V"), "true")
        clock_hz_edit = QLineEdit("0")
        discord_edit = QLineEdit("")
        form.addRow(pick(self.lang, "Nombre del repo", "Repository name"), name_edit)
        form.addRow(pick(self.lang, "Celda top", "Top cell"), top_edit)
        form.addRow(pick(self.lang, "Título", "Title"), title_edit)
        form.addRow(pick(self.lang, "Autor", "Author"), author_edit)
        form.addRow("Discord", discord_edit)
        form.addRow(pick(self.lang, "Descripción", "Description"), desc_edit)
        form.addRow(pick(self.lang, "Tipo de diseño", "Design type"), kind_combo)
        form.addRow(pick(self.lang, "Tamaño / tiles", "Size / tiles"), tile_combo)
        form.addRow(pick(self.lang, "Pines analógicos", "Analog pins"), analog_pins_combo)
        form.addRow("3.3V / VAPWR", uses_3v3_combo)
        form.addRow("Clock Hz", clock_hz_edit)
        layout.addLayout(form)

        hint = QLabel(
            pick(
                self.lang,
                "Se crearán carpetas de trabajo, runs y configuración local de SKY130 Flow GUI.",
                "Work folders, runs, and local SKY130 Flow GUI configuration will be created.",
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        browse_parent.clicked.connect(
            lambda: self._pick_project_parent(parent_edit, pick(self.lang, "Selecciona carpeta padre", "Select parent folder"))
        )

        if dialog.exec() != QDialog.Accepted:
            return

        parent = Path(parent_edit.text().strip()).expanduser()
        project_name = self._safe_project_name(name_edit.text().strip() or "tt_um_new_project")
        top_cell = self._safe_project_name(top_edit.text().strip() or project_name)
        metadata = {
            "repo_name": project_name,
            "top_cell": top_cell,
            "title": title_edit.text().strip() or top_cell,
            "author": author_edit.text().strip() or "Autor pendiente",
            "discord": discord_edit.text().strip(),
            "description": desc_edit.toPlainText().strip() or "Proyecto Tiny Tapeout creado desde SKY130 Flow GUI.",
            "design_type": str(kind_combo.currentData()),
            "tiles": tile_combo.currentText(),
            "analog_pins": analog_pins_combo.currentText(),
            "uses_3v3": str(uses_3v3_combo.currentData()),
            "clock_hz": clock_hz_edit.text().strip() or "0",
        }
        project_root = parent / project_name
        if project_root.exists() and any(project_root.iterdir()):
            answer = QMessageBox.question(
                self,
                pick(self.lang, "Carpeta no vacía", "Non-empty folder"),
                pick(
                    self.lang,
                    f"La carpeta ya existe y no está vacía:\n{project_root}\n\n¿Crear/actualizar sólo las carpetas faltantes?",
                    f"The folder already exists and is not empty:\n{project_root}\n\nCreate/update only missing folders?",
                ),
            )
            if answer != QMessageBox.Yes:
                return

        self._create_tiny_tapeout_structure(project_root, metadata)
        self.set_project(str(project_root))
        self.info.append(pick(self.lang, "\nProyecto Tiny Tapeout creado.", "\nTiny Tapeout project created."))

    def _pick_project_parent(self, edit: QLineEdit, title: str) -> None:
        path = QFileDialog.getExistingDirectory(self, title, edit.text().strip() or str(Path.home()))
        if path:
            edit.setText(path)

    def _create_tiny_tapeout_structure(self, project_root: Path, metadata: dict[str, str]) -> None:
        top_cell = metadata["top_cell"]
        design_type = metadata["design_type"]
        folders = [
            "src",
            "mag",
            "xschem",
            "spice",
            "tb",
            "test",
            "docs",
            "gds",
            "lef",
            ".github/workflows",
            "runs/logs",
            "runs/results",
            "runs/lvs",
            "runs/extraction",
            "runs/antenna",
            ".sky130-flow-gui",
        ]
        for folder in folders:
            (project_root / folder).mkdir(parents=True, exist_ok=True)

        self._write_if_missing(
            project_root / "README.md",
            self._render_project_readme(metadata),
        )
        self._write_if_missing(
            project_root / "info.yaml",
            self._render_info_yaml(metadata),
        )
        self._write_if_missing(project_root / "docs" / "pinout.md", self._render_pinout_doc(metadata))
        self._write_if_missing(project_root / "docs" / "info.md", self._render_tinytapeout_docs_info(metadata))
        self._write_if_missing(project_root / "docs" / "verification.md", self._render_verification_doc(metadata))
        self._write_if_missing(project_root / "tb" / f"{top_cell}_tb.spice", self._render_spice_testbench(metadata))
        self._write_if_missing(project_root / "test" / "README.md", self._render_test_readme(metadata))
        self._write_if_missing(project_root / ".gitignore", self._render_gitignore())
        self._write_if_missing(project_root / "LICENSE", self._render_license_note(metadata))
        self._write_if_missing(project_root / ".github" / "workflows" / "README.md", self._render_workflows_note())
        if design_type in {"digital", "mixed_signal"}:
            self._write_if_missing(project_root / "src" / "project.v", self._render_verilog_stub(metadata))
        else:
            self._write_if_missing(project_root / "src" / "project.v", self._render_verilog_stub(metadata))
            self._write_if_missing(project_root / "src" / "README.md", self._render_analog_source_note(metadata))
        config_dir = project_root / ".sky130-flow-gui"
        (config_dir / "project.json").write_text(
            json.dumps(
                {
                    "project_type": "tiny_tapeout",
                    "design_type": design_type,
                    "tiles": metadata["tiles"],
                    "analog_pins": int(metadata["analog_pins"]),
                    "uses_3v3": metadata["uses_3v3"] == "true",
                    "clock_hz": int(metadata["clock_hz"]) if metadata["clock_hz"].isdigit() else 0,
                    "title": metadata["title"],
                    "author": metadata["author"],
                    "description": metadata["description"],
                    "top_cell": top_cell,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        self._write_if_missing(
            config_dir / "simulation.json",
            json.dumps(
                {
                    "testbench_mode": "tiny_tapeout",
                    "analysis_type": pick(self.lang, "Transitorio", "Transient"),
                    "save_mode": pick(self.lang, "Todas las señales", "All signals"),
                    "corner": "tt",
                    "probes": ["uo_out[0]"],
                    "postlayout": {
                        "initial_conditions": True,
                        "load_mode": "cap",
                        "load_cap": "10f",
                        "load_res": "1k",
                    },
                    "tiny_tapeout": {
                        "clock": {
                            "delay": "0",
                            "fall": "100p",
                            "high_time": "5n",
                            "mode": "pulse" if design_type == "digital" else "low",
                            "period": "10n",
                            "rise": "100p",
                            "vhigh": "1.8",
                            "vlow": "0",
                        },
                        "pin_config": {
                            f"ua[{index}]": {
                                "role": "hiz" if design_type in {"analog", "mixed_signal"} else "ground",
                                "value": "0",
                                "offset": "0",
                                "amplitude": "100m",
                                "frequency": "1Meg",
                                "load_mode": "none",
                                "load_cap": "10f",
                                "load_res": "1k",
                            }
                            for index in range(8)
                        },
                        "profile": "analog" if design_type in {"analog", "mixed_signal"} else "digital",
                        "save_currents": False,
                        "save_pins": True,
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

    @staticmethod
    def _write_if_missing(path: Path, content: str) -> None:
        if not path.exists():
            path.write_text(content)

    @staticmethod
    def _yaml_quote(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _render_info_yaml(self, metadata: dict[str, str]) -> str:
        top_cell = metadata["top_cell"]
        design_type = metadata["design_type"]
        source_files = ["project.v"]
        lines = [
            "yaml_version: 6",
            "project:",
            f"  title: {self._yaml_quote(metadata['title'])}",
            f"  author: {self._yaml_quote(metadata['author'])}",
            f"  discord: {self._yaml_quote(metadata['discord'])}",
            f"  description: {self._yaml_quote(metadata['description'])}",
            "  language: Verilog",
            f"  clock_hz: {metadata['clock_hz']}",
            f"  tiles: {metadata['tiles']}",
            f"  analog_pins: {metadata['analog_pins']}",
            f"  uses_3v3: {metadata['uses_3v3']}",
            "  top_module: " + top_cell,
            "  source_files:",
            *[f"    - {item}" for item in source_files],
            "pinout:",
            "  # Tiny Tapeout analog template exposes ua[0]..ua[5]; edit these roles for your project.",
        ]
        for index in range(8):
            lines.append(f"  ui[{index}]: Input {index}")
        for index in range(8):
            lines.append(f"  uo[{index}]: Output {index}")
        for index in range(8):
            lines.append(f"  uio[{index}]: Bidirectional IO {index}")
        for index in range(6):
            lines.append(f"  ua[{index}]: Analog pin {index}")
        lines.extend(
            [
                "documentation:",
                "  author: " + self._yaml_quote(metadata["author"]),
                "  title: " + self._yaml_quote(metadata["title"]),
                "",
                "# Local helper metadata for SKY130 Flow GUI",
                "sky130_flow_gui:",
                f"  repo_name: {metadata['repo_name']}",
                f"  design_type: {design_type}",
                "",
            ]
        )
        return "\n".join(lines)

    def _render_project_readme(self, metadata: dict[str, str]) -> str:
        return "\n".join(
            [
                f"# {metadata['title']}",
                "",
                metadata["description"],
                "",
                "This project was generated from the Tiny Tapeout SKY130 analog/custom layout template shape.",
                "",
                "## Project Data",
                "",
                f"- Top module: `{metadata['top_cell']}`",
                f"- Design type: `{metadata['design_type']}`",
                f"- Tiles: `{metadata['tiles']}`",
                f"- Analog pins: `{metadata['analog_pins']}`",
                f"- Uses 3.3V: `{metadata['uses_3v3']}`",
                f"- Clock Hz: `{metadata['clock_hz']}`",
                f"- Author: {metadata['author']}",
                "",
                "## Structure",
                "",
                "- `src/project.v`: Tiny Tapeout wrapper module placeholder",
                "- `gds/`: final or imported GDS files",
                "- `lef/`: LEF abstracts when available",
                "- `xschem/`: schematics",
                "- `mag/`: Magic layout",
                "- `spice/`: design netlists",
                "- `test/`: CI/simulation tests",
                "- `tb/`: local SPICE testbenches",
                "- `docs/`: pinout, verification, and notes",
                "- `runs/`: SKY130 Flow GUI outputs",
                "",
            ]
        )

    def _render_pinout_doc(self, metadata: dict[str, str]) -> str:
        rows = [f"# Pinout de {metadata['top_cell']}", "", "| Pin | Rol | Nota |", "| --- | --- | --- |"]
        for prefix, count in [("ui_in", 8), ("uo_out", 8), ("uio", 8), ("ua", 8)]:
            for index in range(count):
                rows.append(f"| `{prefix}[{index}]` | TBD | Editar segun el diseño |")
        rows.append("")
        return "\n".join(rows)

    def _render_verification_doc(self, metadata: dict[str, str]) -> str:
        return "\n".join(
            [
                f"# Verificación de {metadata['top_cell']}",
                "",
                "## Simulación",
                "",
                "- Define si usarás `tb/` como testbench completo o el wrapper Tiny Tapeout de la app.",
                "- Documenta estímulos, clocks, resets, cargas y nodos guardados.",
                "",
                "## LVS / Extracción",
                "",
                "- Corre extracción desde la pestaña Extracción.",
                "- Envía el netlist extraído a Simulación para validar post-layout.",
                "",
            ]
        )

    def _render_tinytapeout_docs_info(self, metadata: dict[str, str]) -> str:
        return "\n".join(
            [
                f"# {metadata['title']}",
                "",
                metadata["description"],
                "",
                "## How it works",
                "",
                "Describe the circuit architecture here.",
                "",
                "## How to test",
                "",
                "Document the expected stimulus, analog pin usage, clock/reset behavior, and measured outputs.",
                "",
                "## External hardware",
                "",
                "List any external passives, bias sources, probes, or lab equipment required.",
                "",
            ]
        )

    def _render_test_readme(self, metadata: dict[str, str]) -> str:
        return "\n".join(
            [
                f"# Tests for {metadata['top_cell']}",
                "",
                "Place cocotb, ngspice, or project-specific regression tests here.",
                "Use `tb/` for standalone SPICE decks that you want to run from SKY130 Flow GUI.",
                "",
            ]
        )

    @staticmethod
    def _render_gitignore() -> str:
        return "\n".join(
            [
                "runs/",
                "*.raw",
                "*.log",
                "*.spice~",
                "__pycache__/",
                ".DS_Store",
                "",
            ]
        )

    def _render_license_note(self, metadata: dict[str, str]) -> str:
        return "\n".join(
            [
                "Project license placeholder",
                "",
                f"Copyright (c) {metadata['author']}",
                "",
                "Replace this file with the license you want for your Tiny Tapeout submission.",
                "",
            ]
        )

    @staticmethod
    def _render_workflows_note() -> str:
        return "\n".join(
            [
                "# GitHub Actions",
                "",
                "This placeholder keeps the official template shape without installing a stale workflow.",
                "Copy the current workflow files from TinyTapeout/ttsky-analog-template before submission.",
                "",
            ]
        )

    def _render_spice_testbench(self, metadata: dict[str, str]) -> str:
        top_cell = metadata["top_cell"]
        analog_pins = [f"ua[{index}]" for index in range(8)]
        digital_inputs = [f"ui_in[{index}]" for index in range(8)]
        uio_inputs = [f"uio_in[{index}]" for index in range(8)]
        uio_outputs = [f"uio_out[{index}]" for index in range(8)]
        uio_oe = [f"uio_oe[{index}]" for index in range(8)]
        digital_outputs = [f"uo_out[{index}]" for index in range(8)]
        instance_pins = ["clk", "ena", "rst_n", *analog_pins, *digital_inputs, *uio_inputs, *uio_oe, *uio_outputs, *digital_outputs, "VDPWR", "VGND"]
        input_sources = [f"Vui_in_{index} ui_in[{index}] 0 0" for index in range(8)]
        uio_sources = [f"Vuio_in_{index} uio_in[{index}] 0 0" for index in range(8)]
        uio_oe_sources = [f"Vuio_oe_{index} uio_oe[{index}] 0 0" for index in range(8)]
        return "\n".join(
            [
                f"* Testbench inicial para {top_cell}",
                "* Edita este archivo y selecciona 'Usar netlist como testbench completo' en Simulación.",
                f".include ../spice/{top_cell}.spice",
                "Vvdpwr VDPWR 0 1.8",
                "Vvgnd VGND 0 0",
                "Vclk clk 0 PULSE(0 1.8 0 100p 100p 5n 10n)",
                "Vena ena 0 1.8",
                "Vrst_n rst_n 0 1.8",
                *input_sources,
                *uio_sources,
                *uio_oe_sources,
                f"Xdut {' '.join(instance_pins)} {top_cell}",
                ".save all",
                ".tran 1n 1u",
                ".end",
                "",
            ]
        )

    def _render_verilog_stub(self, metadata: dict[str, str]) -> str:
        top_cell = metadata["top_cell"]
        analog_count = int(metadata.get("analog_pins", "0")) if metadata.get("analog_pins", "0").isdigit() else 0
        analog_port = "    inout  wire [5:0] ua," if analog_count else "    output wire [5:0] ua,"
        return "\n".join(
            [
                f"module {top_cell} (",
                "    input  wire [7:0] ui_in,",
                "    output wire [7:0] uo_out,",
                "    input  wire [7:0] uio_in,",
                "    output wire [7:0] uio_out,",
                "    output wire [7:0] uio_oe,",
                analog_port,
                "    input  wire       ena,",
                "    input  wire       clk,",
                "    input  wire       rst_n,",
                "    input  wire       VDPWR,",
                "    input  wire       VGND",
                ");",
                "    assign uo_out = ui_in;",
                "    assign uio_out = 8'b0;",
                "    assign uio_oe = 8'b0;",
                "    assign ua = 6'bz;",
                "    wire _unused = &{ena, clk, rst_n, uio_in, VDPWR, VGND};",
                "endmodule",
                "",
            ]
        )

    def _render_analog_source_note(self, metadata: dict[str, str]) -> str:
        return "\n".join(
            [
                f"# Fuente para {metadata['top_cell']}",
                "",
                "Este proyecto fue creado como analogico/mixed-signal.",
                "Agrega aqui notas, modelos o netlists fuente que acompanen al esquematico/layout.",
                "",
            ]
        )

    @staticmethod
    def _safe_project_name(value: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
        return cleaned.strip("_") or "tt_um_new_project"

    def set_project(self, path: str) -> None:
        self.manager.set_project(path)
        self.manager.ensure_structure()
        self._refresh_context_label()
        self._index_files()
        if path not in self.recent_projects:
            self.recent_projects.insert(0, path)
            self.recent_projects[:] = self.recent_projects[:15]
            self._load_recent()
        self.project_changed.emit(path)

    def _refresh_context_label(self) -> None:
        outputs = self.manager.outputs()
        self.current_label.setText(f"{pick(self.lang, 'Raíz activa de outputs', 'Active output root')}: {outputs.runs}")

    def _index_files(self) -> None:
        found = self.manager.find_common_files()
        self.files.clear()
        summary = []
        for category, files in found.items():
            summary.append(f"{category}: {len(files)}")
            for file in files[:25]:
                self.files.addItem(f"[{category}] {file}")
        if not summary:
            summary.append(pick(self.lang, "No hay proyecto seleccionado; se usarán outputs del workspace.", "No project selected; using fallback workspace outputs."))
        self.info.setPlainText("\n".join(summary))

    def _open_recent(self) -> None:
        item = self.recent.currentItem()
        if item:
            self.set_project(item.text())

    def _open_output_subfolder(self, name: str) -> None:
        folder = getattr(self.manager.outputs(), name)
        QDesktopServices.openUrl(folder.as_uri())

    def _open_output_root(self) -> None:
        QDesktopServices.openUrl(self.manager.outputs().runs.as_uri())
