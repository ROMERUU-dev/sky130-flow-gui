"""Reusable widgets and helpers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QLineEdit, QMessageBox, QTextEdit, QWidget


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
