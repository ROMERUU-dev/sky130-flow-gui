"""Reusable widgets and helpers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
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


# PySide6 does not export Qt's QWIDGETSIZE_MAX.
QWIDGETSIZE_MAX = (1 << 24) - 1


class CollapsibleSection(QWidget):
    """A compact collapsible section with a clickable header.

    Expanding used to call ``setVisible(True)`` on content that had never been
    laid out, so Qt painted one frame at the widget's default geometry before
    the parent layout moved it. That single frame is the flicker you see as the
    section opens. The content now stays in the layout and its height is
    animated from zero instead.
    """

    ANIMATION_MS = 130

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
        self.content.setMaximumHeight(QWIDGETSIZE_MAX if expanded else 0)
        self.content.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)

        self._animation = QPropertyAnimation(self.content, b"maximumHeight", self)
        self._animation.setDuration(self.ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._animation.finished.connect(self._on_animation_finished)

        self.toggle.toggled.connect(self.set_expanded)

    def set_expanded(self, expanded: bool) -> None:
        self.toggle.setChecked(expanded)
        self.toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._animation.stop()
        start = self.content.height()
        if expanded:
            # Measured while the widget is already positioned, so there is no
            # intermediate frame at the wrong geometry.
            target = max(self.content.sizeHint().height(), self.content.minimumSizeHint().height())
        else:
            target = 0
        self._animation.setStartValue(start)
        self._animation.setEndValue(target)
        self._animation.start()

    def _on_animation_finished(self) -> None:
        if self.is_expanded():
            # Release the cap so the content can still grow with its data.
            self.content.setMaximumHeight(QWIDGETSIZE_MAX)

    def is_expanded(self) -> bool:
        return self.toggle.isChecked()


MAX_LOG_BLOCKS = 5000


def make_log_view(placeholder: str = "") -> QTextEdit:
    """Create a read-only log view that discards its oldest lines.

    A long extraction or a verbose ngspice run can emit hundreds of thousands
    of lines. An unbounded QTextEdit keeps every one of them, which grew the
    process memory and made the widget slower the longer a session ran.
    """
    view = QTextEdit()
    view.setReadOnly(True)
    view.document().setMaximumBlockCount(MAX_LOG_BLOCKS)
    if placeholder:
        view.setPlaceholderText(placeholder)
    return view
