"""Preferences tab for tools and PDK configuration."""

from __future__ import annotations

import sys
from dataclasses import asdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.command_runner import CommandRunner, CommandSpec
from app.core.antenna_tools import detect_antenna_support
from app.core.background import BackgroundTask
from app.core.env_probe import EnvProbe
from app.core.env_validator import EnvValidator
from app.core.i18n import pick
from app.core.integration_manager import IntegrationManager
from app.core.settings_manager import AppSettings
from app.core.update_manager import UpdateManager
from app.ui.setup_tab import SetupTab
from app.ui.theme import THEME_DARK, THEME_LIGHT, THEME_SYSTEM, hint_style, resolve
from app.ui.widgets import MAX_LOG_BLOCKS, browse_dir, browse_file


class PreferencesTab(QWidget):
    """Configure tool and PDK paths and validate environment."""

    settings_updated = Signal(object)
    send_status = Signal(str)

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings
        self.lang = settings.language
        self._theme = resolve(settings.theme)
        self.validator = EnvValidator()
        self.update_mgr = UpdateManager()
        self._update_task = BackgroundTask(self)
        self._update_task.finished.connect(self._on_update_checked)
        self._update_task.failed.connect(self._on_update_check_failed)
        self.integration_mgr = IntegrationManager()
        self.cmd_runner = CommandRunner()

        self.fields: dict[str, QLineEdit] = {}
        self.language_combo = QComboBox()
        self.language_combo.addItem("Español", "es")
        self.language_combo.addItem("English", "en")
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(self.settings.language)))

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(pick(self.lang, "Seguir al sistema", "Follow system"), THEME_SYSTEM)
        self.theme_combo.addItem(pick(self.lang, "Claro", "Light"), THEME_LIGHT)
        self.theme_combo.addItem(pick(self.lang, "Oscuro", "Dark"), THEME_DARK)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.settings.theme)))

        self.prompt_project_check = QCheckBox(
            pick(self.lang, "Preguntar por proyecto al iniciar", "Ask for a project on startup")
        )
        self.prompt_project_check.setChecked(self.settings.prompt_project_on_start)
        self.status_table = QTableWidget(0, 3)
        self.status_table.setHorizontalHeaderLabels(
            [
                pick(self.lang, "Elemento", "Item"),
                pick(self.lang, "Estado", "Status"),
                pick(self.lang, "Detalle", "Detail"),
            ]
        )
        self.ops_log = QTextEdit()
        self.ops_log.document().setMaximumBlockCount(MAX_LOG_BLOCKS)
        self.ops_log.setReadOnly(True)
        self.subtabs = QTabWidget()
        self.subtabs.setDocumentMode(True)
        self.subtabs.setObjectName("preferencesSubtabs")
        self.general_page = QWidget()
        self.general_page.setObjectName("preferencesGeneralPage")
        self.general_page.setAttribute(Qt.WA_StyledBackground, True)
        self.setup_tab = SetupTab(self.settings)
        self.setup_tab.setObjectName("preferencesSetupPage")
        self.setup_tab.setAttribute(Qt.WA_StyledBackground, True)

        self._pending_status_check = False
        self._last_action = ""

        self._build_ui()
        self._wire_runner()
        self.setup_tab.settings_updated.connect(self.settings_updated.emit)
        self.setup_tab.send_status.connect(self.send_status.emit)
        self._probe = EnvProbe(self)
        self._probe.finished.connect(lambda _diagnosis: self.refresh_validation())
        self._probe.start(self.settings, self.lang)

    def _add_path_row(self, form: QFormLayout, key: str, label: str, value: str,
                      is_dir: bool = False, placeholder: str = "") -> None:
        edit = QLineEdit(value)
        if placeholder:
            # An empty path field with no explanation reads as something
            # missing, even when there is genuinely nothing to put there.
            edit.setPlaceholderText(placeholder)
            edit.setToolTip(placeholder)
        self.fields[key] = edit
        row = QHBoxLayout()
        row.addWidget(edit)
        b = QPushButton(pick(self.lang, "Buscar", "Browse"))
        if is_dir:
            b.clicked.connect(lambda: browse_dir(self, edit, pick(self.lang, f"Selecciona {label}", f"Select {label}")))
        else:
            b.clicked.connect(lambda: browse_file(self, edit, pick(self.lang, f"Selecciona {label}", f"Select {label}")))
        row.addWidget(b)
        form.addRow(label, row)

    def _antenna_deck_placeholder(self, sky130a: str) -> str:
        """Explain an empty deck field in terms of what the PDK actually ships."""
        support = detect_antenna_support(sky130a)
        if support.has_klayout_deck:
            return ""
        if support.magic_available:
            return pick(
                self.lang,
                "Opcional — este PDK no trae deck de antena; Antena usa Magic antennacheck",
                "Optional — this PDK ships no antenna deck; Antenna uses Magic antennacheck",
            )
        return pick(
            self.lang,
            "Opcional — no se detectaron reglas de antena en este PDK",
            "Optional — no antenna rules were detected in this PDK",
        )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        general_outer = QVBoxLayout(self.general_page)
        general_outer.setContentsMargins(0, 0, 0, 0)
        general_scroll = QScrollArea()
        general_scroll.setWidgetResizable(True)
        general_scroll.setFrameShape(QScrollArea.NoFrame)
        general_outer.addWidget(general_scroll)
        general_content = QWidget()
        general_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        general_scroll.setWidget(general_content)

        general_layout = QVBoxLayout(general_content)
        general_layout.setContentsMargins(14, 14, 14, 14)
        general_layout.setSpacing(12)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        tools = asdict(self.settings.tool_paths)
        pdk = asdict(self.settings.pdk_paths)

        form.addRow(pick(self.lang, "Idioma", "Language"), self.language_combo)
        form.addRow(pick(self.lang, "Tema", "Theme"), self.theme_combo)
        form.addRow("", self.prompt_project_check)
        form.addRow(QLabel(pick(self.lang, "Reinicia la app para aplicar el cambio de idioma.", "Restart the app to apply the language change.")))

        for key, value in tools.items():
            self._add_path_row(form, f"tools.{key}", key, value)

        self._add_path_row(form, "pdk.pdk_root", "PDK_ROOT", pdk["pdk_root"], is_dir=True)
        self._add_path_row(form, "pdk.sky130a", "SKY130A", pdk["sky130a"], is_dir=True)
        self._add_path_row(form, "pdk.magic_rc", "Magic rcfile", pdk["magic_rc"])
        self._add_path_row(form, "pdk.netgen_setup", "Netgen setup", pdk["netgen_setup"])
        self._add_path_row(
            form,
            "pdk.klayout_antenna_deck",
            "KLayout antenna deck",
            pdk["klayout_antenna_deck"],
            placeholder=self._antenna_deck_placeholder(pdk["sky130a"]),
        )

        general_layout.addLayout(form)
        pdk_usage_note = QLabel(
            pick(
                self.lang,
                "Uso real de estas rutas PDK: PDK_ROOT y SKY130A se usan para detección y contexto general; Magic rcfile lo usan Extracción y Magic; Netgen setup lo usa LVS; KLayout antenna deck lo usa Antena.",
                "Actual use of these PDK paths: PDK_ROOT and SKY130A are used for detection and general context; Magic rcfile is used by Extraction and Magic; Netgen setup is used by LVS; KLayout antenna deck is used by Antenna.",
            )
        )
        pdk_usage_note.setWordWrap(True)
        pdk_usage_note.setStyleSheet(hint_style(self._theme))
        general_layout.addWidget(pdk_usage_note)

        btns = QHBoxLayout()
        save = QPushButton(pick(self.lang, "Guardar preferencias", "Save Preferences"))
        validate = QPushButton(pick(self.lang, "Validar", "Validate"))
        repair_python = QPushButton(pick(self.lang, "Crear/Reparar entorno Python", "Create/Repair Python Environment"))
        btns.addWidget(save)
        btns.addWidget(validate)
        btns.addWidget(repair_python)
        general_layout.addLayout(btns)

        save.clicked.connect(self.save)
        validate.clicked.connect(self.rescan_environment)
        repair_python.clicked.connect(self.repair_python_environment)

        general_layout.addWidget(QLabel(pick(self.lang, "Validación de entorno", "Environment Validation")))
        general_layout.addWidget(self.status_table)

        ops_buttons = QHBoxLayout()
        check_updates = QPushButton(pick(self.lang, "Buscar actualizaciones", "Check for updates"))
        update_now = QPushButton(pick(self.lang, "Actualizar ahora", "Update now"))
        install_icon = QPushButton(pick(self.lang, "Instalar icono de aplicación", "Install application icon"))
        ops_buttons.addWidget(check_updates)
        ops_buttons.addWidget(update_now)
        ops_buttons.addWidget(install_icon)

        check_updates.clicked.connect(self.check_updates)
        update_now.clicked.connect(self.apply_updates)
        install_icon.clicked.connect(self.install_icon)

        general_layout.addWidget(
            QLabel(pick(self.lang, "Operaciones de instalación / actualización", "Installation / update operations"))
        )
        general_layout.addLayout(ops_buttons)
        general_layout.addWidget(self.ops_log)

        self.subtabs.addTab(self.general_page, pick(self.lang, "General", "General"))
        self.subtabs.addTab(self.setup_tab, pick(self.lang, "Entorno", "Setup"))
        layout.addWidget(self.subtabs)
    def _wire_runner(self) -> None:
        self.cmd_runner.started.connect(lambda cmd: self.ops_log.append(f"$ {cmd}"))
        self.cmd_runner.line_output.connect(lambda txt: self.ops_log.insertPlainText(txt))
        self.cmd_runner.finished.connect(self._on_cmd_finished)

    def save(self) -> None:
        for key, edit in self.fields.items():
            value = edit.text().strip()
            section, attr = key.split(".", 1)
            target = self.settings.tool_paths if section == "tools" else self.settings.pdk_paths
            setattr(target, attr, value)
        self.settings.language = str(self.language_combo.currentData() or "es")
        self.settings.theme = str(self.theme_combo.currentData() or THEME_SYSTEM)
        self.settings.prompt_project_on_start = self.prompt_project_check.isChecked()
        self.refresh_validation()
        self.settings_updated.emit(self.settings)

    def rescan_environment(self) -> None:
        """Re-probe the machine after something changed, without blocking the UI."""
        EnvValidator.invalidate_cache()
        self._probe.start(self.settings, self.lang, refresh=True)

    def refresh_validation(self) -> None:
        diagnosis = self.validator.diagnose(self.settings, lang=self.lang)
        rows = self.validator.validation_rows(diagnosis, lang=self.lang)
        self.status_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self.status_table.setItem(i, 0, QTableWidgetItem(row.item))
            self.status_table.setItem(i, 1, QTableWidgetItem(row.status))
            self.status_table.setItem(i, 2, QTableWidgetItem(row.detail))
        self.status_table.resizeColumnsToContents()

    def repair_python_environment(self) -> None:
        """Run the user-only environment repair without blocking the Qt event loop."""
        self._pending_status_check = False
        self._last_action = "repair_python"
        self.ops_log.append(pick(
            self.lang,
            "Preparando el entorno Python del usuario (sin sudo/pkexec)...\n",
            "Preparing the user Python environment (without sudo/pkexec)...\n",
        ))
        command = [sys.executable, "-m", "app.core.python_env", "repair", "--app-root", str(self.validator.repo_root)]
        self.cmd_runner.run(CommandSpec(command=command, cwd=str(self.validator.repo_root)))

    def check_updates(self) -> None:
        """Check for a newer release, or ask git when running from a clone."""
        if self.update_mgr.is_git_checkout():
            self._pending_status_check = True
            self._last_action = "check"
            self.cmd_runner.run(self._spec(self.update_mgr.commands().fetch))
            return

        if not self._update_task.start(self.update_mgr.check):
            return
        self.ops_log.append(
            pick(self.lang, "Consultando releases en GitHub...\n", "Checking GitHub releases...\n")
        )

    def _on_update_checked(self, result: object) -> None:
        self.ops_log.append(f"\n{result.message}\n")
        if result.update_available:
            self.ops_log.append(
                pick(self.lang, f"Descarga: {result.release_url}\n", f"Download: {result.release_url}\n")
            )
            if result.download_url:
                self.ops_log.append(f"  {result.download_url}\n")
            self.ops_log.append(
                pick(
                    self.lang,
                    "Instálala con: sudo apt install ./<archivo>.deb\n",
                    "Install it with: sudo apt install ./<file>.deb\n",
                )
            )
        self.send_status.emit(result.message)

    def _on_update_check_failed(self, message: str) -> None:
        self.ops_log.append(
            pick(self.lang, f"\nNo se pudo buscar actualizaciones: {message}\n",
                 f"\nUpdate check failed: {message}\n")
        )

    def apply_updates(self) -> None:
        """Pull from git, which only makes sense for a source checkout."""
        if not self.update_mgr.is_git_checkout():
            self.ops_log.append(
                pick(
                    self.lang,
                    "\nEsta es una instalación empaquetada, no un clon de git, así que no puede "
                    "actualizarse sola. Usa `Buscar actualizaciones` y descarga el .deb publicado.\n",
                    "\nThis is a packaged install rather than a git clone, so it cannot update "
                    "itself. Use `Check for updates` and download the published .deb.\n",
                )
            )
            return
        self._pending_status_check = False
        self._last_action = "pull"
        self.cmd_runner.run(self._spec(self.update_mgr.commands().pull))

    def install_icon(self) -> None:
        launcher, desktop, icon = self.integration_mgr.install_desktop_entry()
        self.ops_log.append(
            pick(self.lang, "Instalación completada:\n", "Installation completed:\n")
            + f"- Launcher: {launcher}\n"
            + f"- Desktop entry: {desktop}\n"
            + f"- {pick(self.lang, 'Icono', 'Icon')}: {icon}\n"
        )

    def _on_cmd_finished(self, code: int, _status: str) -> None:
        action = self._last_action

        if self._pending_status_check and code == 0:
            self._pending_status_check = False
            self.cmd_runner.run(self._spec(self.update_mgr.commands().status))
            return

        if code != 0:
            self.ops_log.append(
                pick(self.lang, f"\nComando finalizó con error (exit={code}).\n", f"\nCommand finished with error (exit={code}).\n")
            )
            self._pending_status_check = False
            self._last_action = ""
            if action == "repair_python":
                self.rescan_environment()
            return

        if action == "check":
            status = self.update_mgr.parse_update_status(self.ops_log.toPlainText())
            self.ops_log.append(f"\n{status}\n")
        elif action == "pull":
            self.ops_log.append(
                pick(
                    self.lang,
                    "\nActualización aplicada (si había cambios remotos). Reinicia la app.\n",
                    "\nUpdate applied (if remote changes existed). Restart the app.\n",
                )
            )
        elif action == "repair_python":
            self.ops_log.append(pick(
                self.lang,
                "\nEntorno Python creado y validado correctamente.\n",
                "\nPython environment created and validated successfully.\n",
            ))
            self.rescan_environment()

        self._last_action = ""

    def _spec(self, command: list[str]) -> CommandSpec:
        return CommandSpec(command=command)
