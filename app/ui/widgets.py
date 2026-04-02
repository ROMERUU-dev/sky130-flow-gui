"""Reusable widgets and helpers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


def browse_file(parent: QWidget, line_edit: QLineEdit, title: str, flt: str = "All Files (*)") -> None:
    file_path, _ = QFileDialog.getOpenFileName(parent, title, "", flt)
    if file_path:
        line_edit.setText(file_path)


def browse_dir(parent: QWidget, line_edit: QLineEdit, title: str) -> None:
    path = QFileDialog.getExistingDirectory(parent, title)
    if path:
        line_edit.setText(path)


def append_log(log_widget: QTextEdit, text: str) -> None:
    log_widget.moveCursor(log_widget.textCursor().MoveOperation.End)
    log_widget.insertPlainText(text)
    log_widget.moveCursor(log_widget.textCursor().MoveOperation.End)


def ensure_file(path: str, label: str) -> bool:
    if not path or not Path(path).exists():
        QMessageBox.warning(None, "Missing path", f"{label} not found: {path}")
        return False
    return True


class CollapsibleSection(QWidget):
    """A compact collapsible section with a clickable header."""

    def __init__(self, title: str, content: QWidget, expanded: bool = False) -> None:
        super().__init__()
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.toggle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.content = content
        self.content.setVisible(expanded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)

        self.toggle.toggled.connect(self.set_expanded)

    def set_expanded(self, expanded: bool) -> None:
        self.toggle.setChecked(expanded)
        self.toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.content.setVisible(expanded)

    def is_expanded(self) -> bool:
        return self.toggle.isChecked()
