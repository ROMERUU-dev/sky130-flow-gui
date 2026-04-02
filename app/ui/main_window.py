"""Main application window and tab orchestration."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.core.i18n import pick
from app.core.output_manager import OutputManager
from app.core.project_manager import ProjectManager
from app.core.settings_manager import AppSettings, SettingsManager
from app.ui.antenna_tab import AntennaTab
from app.ui.em_sizing_tab import EmSizingTab
from app.ui.extraction_tab import ExtractionTab
from app.ui.lvs_tab import LvsTab
from app.ui.preferences_tab import PreferencesTab
from app.ui.project_tab import ProjectTab
from app.ui.setup_tab import SetupTab
from app.ui.simulation_tab import SimulationTab


class MainWindow(QMainWindow):
    """Top-level window for SKY130 workflow management."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SKY130 Flow")
        self.resize(1400, 900)

        self.settings_mgr = SettingsManager()
        self.app_settings: AppSettings = self.settings_mgr.load()
        self.output_manager = OutputManager()
        self.project_mgr = ProjectManager(self.output_manager)
        self._current_project = self.app_settings.last_project

        self.root = QWidget()
        self.root_layout = QHBoxLayout(self.root)
        self.root_layout.setContentsMargins(18, 12, 18, 12)
        self.root_layout.setSpacing(18)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebarNav")
        self.sidebar.setSpacing(6)
        self.sidebar.setUniformItemSizes(True)

        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()

        self.sidebar_card = QFrame()
        self.sidebar_card.setObjectName("sidebarCard")
        self.sidebar_layout = QVBoxLayout(self.sidebar_card)
        self.sidebar_layout.setContentsMargins(12, 12, 12, 12)
        self.sidebar_layout.setSpacing(10)
        self.sidebar_layout.addWidget(self.sidebar)

        self.root_layout.addWidget(self.sidebar_card, 0)
        self.root_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(self.root)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.state_label = QLabel(pick(self.app_settings.language, "Listo", "Idle"))
        self.status.addPermanentWidget(self.state_label)

        self._build_tabs()
        self._build_toolbar()
        self._apply_window_style()
        self._wire_navigation()

    def _build_tabs(self) -> None:
        self.project_tab = ProjectTab(self.project_mgr, self.app_settings.recent_projects, self.app_settings.language)
        self.project_tab.project_changed.connect(self._on_project_changed)

        self.sim_tab = SimulationTab(self.app_settings, self.project_mgr.outputs)
        self.lvs_tab = LvsTab(self.app_settings, self.project_mgr.outputs)
        self.ext_tab = ExtractionTab(self.app_settings, self.project_mgr.outputs)
        self.ant_tab = AntennaTab(self.app_settings, self.project_mgr.outputs)
        self.em_tab = EmSizingTab(self.app_settings, self.project_mgr.outputs)
        self.setup_tab = SetupTab(self.app_settings)
        self.pref_tab = PreferencesTab(self.app_settings)

        self.ext_tab.netlist_ready.connect(self._receive_extracted_netlist)
        self.pref_tab.settings_updated.connect(self._on_settings_updated)
        self.setup_tab.settings_updated.connect(self._on_settings_updated)

        for tab in [self.sim_tab, self.lvs_tab, self.ext_tab, self.ant_tab, self.em_tab, self.setup_tab]:
            tab.send_status.connect(self.set_status)

        self.tabs.addTab(self.sim_tab, pick(self.app_settings.language, "∿ Simulación", "∿ Simulation"))
        self.tabs.addTab(self.lvs_tab, "≣ LVS")
        self.tabs.addTab(self.ext_tab, pick(self.app_settings.language, "◫ Extracción", "◫ Extraction"))
        self.tabs.addTab(self.ant_tab, pick(self.app_settings.language, "⌁ Antena", "⌁ Antenna"))
        self.tabs.addTab(self.em_tab, "≈ EM")
        self.tabs.addTab(self.setup_tab, pick(self.app_settings.language, "⬢ Entorno", "⬢ Setup"))
        self.tabs.addTab(self.project_tab, pick(self.app_settings.language, "⌂ Proyecto", "⌂ Project"))
        self.tabs.addTab(self.pref_tab, pick(self.app_settings.language, "⚙ Preferencias", "⚙ Preferences"))
        self._populate_sidebar()

        if self._current_project:
            self.project_tab.set_project(self._current_project)
        else:
            self.project_mgr.ensure_structure()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar(pick(self.app_settings.language, "Quick Actions", "Quick Actions"), self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(toolbar.iconSize())
        self.addToolBar(toolbar)

        open_xschem = QAction(pick(self.app_settings.language, "◫ Abrir xschem", "◫ Open xschem"), self)
        open_xschem.triggered.connect(self._open_xschem)
        toolbar.addAction(open_xschem)

    def _apply_window_style(self) -> None:
        self.tabs.setDocumentMode(True)
        if self.menuBar() is not None:
            self.menuBar().hide()
        self.setStyleSheet(
            """
            QMainWindow {
                background: #ffffff;
            }
            QWidget {
                color: #172033;
            }
            QToolBar#mainToolbar {
                background: #ffffff;
                border: 0;
                border-bottom: 1px solid #eef2f7;
                spacing: 8px;
                padding: 10px 18px 8px 18px;
            }
            QToolBar#mainToolbar QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 12px;
                padding: 9px 15px;
                color: #1d4ed8;
                font-weight: 700;
            }
            QToolBar#mainToolbar QToolButton:hover {
                background: #eef5ff;
                border: 1px solid #cfe0ff;
            }
            QFrame#sidebarCard {
                background: #ffffff;
                border: 1px solid #eef2f7;
                border-radius: 18px;
            }
            QTabWidget::pane {
                border: 0;
                background: #ffffff;
            }
            QListWidget#sidebarNav {
                background: transparent;
                border: 0;
                outline: 0;
                padding: 2px;
            }
            QListWidget#sidebarNav::item {
                min-height: 42px;
                padding: 10px 14px;
                margin: 0;
                border: 1px solid transparent;
                border-radius: 14px;
                font-weight: 700;
                color: #475569;
            }
            QListWidget#sidebarNav::item:selected {
                background: #f5f9ff;
                border: 1px solid #d8e5ff;
            }
            QListWidget#sidebarNav::item:hover {
                background: #f8fafc;
                border: 1px solid #edf2f7;
            }
            QStatusBar {
                background: #ffffff;
                border-top: 1px solid #eef2f7;
                color: #475569;
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
                background: #d7e2f0;
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
                background: #d7e2f0;
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
            QGroupBox {
                background: #ffffff;
                border: 1px solid #edf2f7;
                border-radius: 14px;
                margin-top: 14px;
                padding-top: 14px;
                font-weight: 700;
                color: #1d4ed8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: #1d4ed8;
                background: transparent;
            }
            QLineEdit, QComboBox, QTextEdit, QDoubleSpinBox, QTableWidget {
                background: #ffffff;
                border: 1px solid #e6ebf2;
                border-radius: 12px;
                padding: 7px 9px;
                color: #172033;
                selection-background-color: #dbeafe;
                selection-color: #172033;
            }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QDoubleSpinBox:focus, QTableWidget:focus {
                border: 1px solid #93c5fd;
            }
            QPushButton, QToolButton {
                background: #ffffff;
                border: 1px solid transparent;
                border-radius: 12px;
                padding: 8px 13px;
                color: #172033;
                font-weight: 600;
            }
            QPushButton:hover, QToolButton:hover {
                background: #f8fafc;
                border: 1px solid #dde5ef;
            }
            QPushButton:disabled, QToolButton:disabled {
                background: #fafbfd;
                color: #9aa3b2;
                border: 1px solid transparent;
            }
            QLabel {
                color: #344054;
            }
            """
        )

    def _populate_sidebar(self) -> None:
        self.sidebar.clear()
        accent_colors = [
            "#2563eb",  # Simulation
            "#e76f51",  # LVS
            "#0f9d8a",  # Extraction
            "#d97706",  # Antenna
            "#7c3aed",  # EM
            "#0891b2",  # Setup
            "#059669",  # Project
            "#db2777",  # Preferences
        ]
        for index in range(self.tabs.count()):
            item = QListWidgetItem(self.tabs.tabText(index))
            item.setForeground(QColor(accent_colors[index % len(accent_colors)]))
            self.sidebar.addItem(item)
        if self.sidebar.count():
            self.sidebar.setCurrentRow(self.tabs.currentIndex())

    def _wire_navigation(self) -> None:
        self.sidebar.currentRowChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.sidebar.setCurrentRow)

    def _open_xschem(self) -> None:
        import subprocess

        cmd = [self.app_settings.tool_paths.xschem]
        if self._current_project:
            cmd.append(self._current_project)
        try:
            subprocess.Popen(cmd)
        except OSError as exc:
            QMessageBox.warning(
                self,
                pick(self.app_settings.language, "Error al abrir", "Launch error"),
                f"{pick(self.app_settings.language, 'No se pudo abrir xschem', 'Failed to launch xschem')}: {exc}",
            )

    def _on_project_changed(self, path: str) -> None:
        self._current_project = path
        self.app_settings.last_project = path
        self.app_settings.recent_projects = self.project_tab.recent_projects
        self.settings_mgr.save(self.app_settings)

    def _receive_extracted_netlist(self, netlist_path: str) -> None:
        inferred_project = ProjectManager.normalize_project_root(Path(netlist_path).parent)
        if self._current_project != str(inferred_project):
            self.project_tab.set_project(str(inferred_project))
        self.sim_tab.load_netlist_path(netlist_path)
        self.tabs.setCurrentWidget(self.sim_tab)

    def _on_settings_updated(self, new_settings: AppSettings) -> None:
        self.app_settings = new_settings
        self.settings_mgr.save(self.app_settings)
        self.set_status(
            pick(
                self.app_settings.language,
                "Preferencias guardadas. Reinicia la app para aplicar cambios de idioma.",
                "Preferences saved. Restart the app to apply language changes.",
            )
        )

    def current_project(self) -> str:
        return self._current_project

    def set_status(self, text: str) -> None:
        self.state_label.setText(text)
