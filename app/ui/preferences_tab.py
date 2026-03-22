"""Preferences tab for tools and PDK configuration."""

from __future__ import annotations

from dataclasses import asdict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.command_runner import CommandRunner, CommandSpec
from app.core.env_validator import EnvValidator
from app.core.integration_manager import IntegrationManager
from app.core.settings_manager import AppSettings
from app.core.update_manager import UpdateManager
from app.ui.widgets import browse_dir, browse_file


class PreferencesTab(QWidget):
    """Configure tool and PDK paths and validate environment."""

    settings_updated = Signal(object)

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings
        self.validator = EnvValidator()
        self.update_mgr = UpdateManager()
        self.integration_mgr = IntegrationManager()
        self.cmd_runner = CommandRunner()

        self.fields: dict[str, QLineEdit] = {}
        self.status_table = QTableWidget(0, 3)
        self.status_table.setHorizontalHeaderLabels(["Item", "Status", "Detail"])
        self.ops_log = QTextEdit()
        self.ops_log.setReadOnly(True)

        self._pending_status_check = False
        self._last_action = ""

        self._build_ui()
        self._wire_runner()
        self.refresh_validation()

    def _add_path_row(self, form: QFormLayout, key: str, label: str, value: str, is_dir: bool = False) -> None:
        edit = QLineEdit(value)
        self.fields[key] = edit
        row = QHBoxLayout()
        row.addWidget(edit)
        b = QPushButton("Browse")
        if is_dir:
            b.clicked.connect(lambda: browse_dir(self, edit, f"Select {label}"))
        else:
            b.clicked.connect(lambda: browse_file(self, edit, f"Select {label}"))
        row.addWidget(b)
        form.addRow(label, row)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        tools = asdict(self.settings.tool_paths)
        pdk = asdict(self.settings.pdk_paths)

        for key, value in tools.items():
            self._add_path_row(form, f"tools.{key}", key, value)

        self._add_path_row(form, "pdk.pdk_root", "PDK_ROOT", pdk["pdk_root"], is_dir=True)
        self._add_path_row(form, "pdk.sky130a", "SKY130A", pdk["sky130a"], is_dir=True)
        self._add_path_row(form, "pdk.magic_rc", "Magic rcfile", pdk["magic_rc"])
        self._add_path_row(form, "pdk.netgen_setup", "Netgen setup", pdk["netgen_setup"])
        self._add_path_row(form, "pdk.klayout_antenna_deck", "KLayout antenna deck", pdk["klayout_antenna_deck"])

        layout.addLayout(form)

        btns = QHBoxLayout()
        save = QPushButton("Save Preferences")
        validate = QPushButton("Validate")
        btns.addWidget(save)
        btns.addWidget(validate)
        layout.addLayout(btns)

        save.clicked.connect(self.save)
        validate.clicked.connect(self.refresh_validation)

        layout.addWidget(QLabel("Environment Validation"))
        layout.addWidget(self.status_table)

        ops_buttons = QHBoxLayout()
        check_updates = QPushButton("Buscar actualizaciones")
        update_now = QPushButton("Actualizar ahora")
        install_icon = QPushButton("Instalar icono de aplicación")
        ops_buttons.addWidget(check_updates)
        ops_buttons.addWidget(update_now)
        ops_buttons.addWidget(install_icon)

        check_updates.clicked.connect(self.check_updates)
        update_now.clicked.connect(self.apply_updates)
        install_icon.clicked.connect(self.install_icon)

        layout.addWidget(QLabel("Operaciones de instalación / actualización"))
        layout.addLayout(ops_buttons)
        layout.addWidget(self.ops_log)

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
        self.refresh_validation()
        self.settings_updated.emit(self.settings)

    def refresh_validation(self) -> None:
        rows = self.validator.validate(self.settings)
        self.status_table.setRowCount(len(rows))
        for i, (item, (ok, detail)) in enumerate(rows.items()):
            self.status_table.setItem(i, 0, QTableWidgetItem(item))
            self.status_table.setItem(i, 1, QTableWidgetItem("OK" if ok else "MISSING"))
            self.status_table.setItem(i, 2, QTableWidgetItem(detail))
        self.status_table.resizeColumnsToContents()

    def check_updates(self) -> None:
        cmds = self.update_mgr.commands()
        self._pending_status_check = True
        self._last_action = "check"
        self.cmd_runner.run(self._spec(cmds.fetch))

    def apply_updates(self) -> None:
        self._pending_status_check = False
        self._last_action = "pull"
        self.cmd_runner.run(self._spec(self.update_mgr.commands().pull))

    def install_icon(self) -> None:
        launcher, desktop, icon = self.integration_mgr.install_desktop_entry()
        self.ops_log.append(
            "Instalación completada:\n"
            f"- Launcher: {launcher}\n"
            f"- Desktop entry: {desktop}\n"
            f"- Icono: {icon}\n"
        )

    def _on_cmd_finished(self, code: int, _status: str) -> None:
        action = self._last_action

        if self._pending_status_check and code == 0:
            self._pending_status_check = False
            self.cmd_runner.run(self._spec(self.update_mgr.commands().status))
            return

        if code != 0:
            self.ops_log.append(f"\nComando finalizó con error (exit={code}).\n")
            self._pending_status_check = False
            self._last_action = ""
            return

        if action == "check":
            status = self.update_mgr.parse_update_status(self.ops_log.toPlainText())
            self.ops_log.append(f"\n{status}\n")
        elif action == "pull":
            self.ops_log.append("\nActualización aplicada (si había cambios remotos). Reinicia la app.\n")

        self._last_action = ""

    def _spec(self, command: list[str]) -> CommandSpec:
        return CommandSpec(command=command)
