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
    QVBoxLayout,
    QWidget,
)

from app.core.env_validator import EnvValidator
from app.core.settings_manager import AppSettings
from app.ui.widgets import browse_dir, browse_file


class PreferencesTab(QWidget):
    """Configure tool and PDK paths and validate environment."""

    settings_updated = Signal(object)

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings
        self.validator = EnvValidator()

        self.fields: dict[str, QLineEdit] = {}
        self.status_table = QTableWidget(0, 3)
        self.status_table.setHorizontalHeaderLabels(["Item", "Status", "Detail"])

        self._build_ui()
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
