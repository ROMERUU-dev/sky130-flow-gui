"""Project/files tab."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.project_manager import ProjectManager


class ProjectTab(QWidget):
    """Project folder selection and file discovery."""

    project_changed = Signal(str)

    def __init__(self, manager: ProjectManager, recent_projects: list[str]) -> None:
        super().__init__()
        self.manager = manager
        self.recent_projects = recent_projects

        self.current_label = QLabel("No project selected")
        self.files = QListWidget()
        self.recent = QListWidget()
        self.info = QTextEdit()
        self.info.setReadOnly(True)

        self._build_ui()
        self._load_recent()
        self._refresh_context_label()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        pick = QPushButton("Select Project Folder")
        pick.clicked.connect(self.pick_project)
        row.addWidget(pick)

        open_results = QPushButton("Open Runs/Results")
        open_results.clicked.connect(lambda: self._open_output_subfolder("results"))
        row.addWidget(open_results)

        open_logs = QPushButton("Open Runs/Logs")
        open_logs.clicked.connect(lambda: self._open_output_subfolder("logs"))
        row.addWidget(open_logs)

        open_workspace = QPushButton("Open Active Output Root")
        open_workspace.clicked.connect(self._open_output_root)
        row.addWidget(open_workspace)

        layout.addLayout(row)
        layout.addWidget(self.current_label)
        layout.addWidget(QLabel("Detected Flow Files"))
        layout.addWidget(self.files)
        layout.addWidget(QLabel("Recent Projects"))
        layout.addWidget(self.recent)
        layout.addWidget(self.info)

        self.recent.itemDoubleClicked.connect(self._open_recent)

    def _load_recent(self) -> None:
        self.recent.clear()
        for item in self.recent_projects:
            self.recent.addItem(item)

    def pick_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select project")
        if path:
            self.set_project(path)

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
        self.current_label.setText(f"Active output root: {outputs.runs}")

    def _index_files(self) -> None:
        found = self.manager.find_common_files()
        self.files.clear()
        summary = []
        for category, files in found.items():
            summary.append(f"{category}: {len(files)}")
            for file in files[:25]:
                self.files.addItem(f"[{category}] {file}")
        if not summary:
            summary.append("No project selected; using fallback workspace outputs.")
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
