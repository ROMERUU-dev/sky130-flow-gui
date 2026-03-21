"""Main application window and tab orchestration."""

from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox, QStatusBar, QTabWidget

from app.core.project_manager import ProjectManager
from app.core.settings_manager import AppSettings, SettingsManager
from app.ui.antenna_tab import AntennaTab
from app.ui.extraction_tab import ExtractionTab
from app.ui.lvs_tab import LvsTab
from app.ui.preferences_tab import PreferencesTab
from app.ui.project_tab import ProjectTab
from app.ui.simulation_tab import SimulationTab


class MainWindow(QMainWindow):
    """Top-level window for SKY130 workflow management."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SKY130 Flow GUI")
        self.resize(1400, 900)

        self.settings_mgr = SettingsManager()
        self.app_settings: AppSettings = self.settings_mgr.load()
        self.project_mgr = ProjectManager()
        self._current_project = self.app_settings.last_project

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.state_label = QLabel("Idle")
        self.status.addPermanentWidget(self.state_label)

        self._build_tabs()
        self._build_menu()

    def _build_tabs(self) -> None:
        self.project_tab = ProjectTab(self.project_mgr, self.app_settings.recent_projects)
        self.project_tab.project_changed.connect(self._on_project_changed)

        self.sim_tab = SimulationTab(self.app_settings, self.current_project)
        self.lvs_tab = LvsTab(self.app_settings, self.current_project)
        self.ext_tab = ExtractionTab(self.app_settings, self.current_project)
        self.ant_tab = AntennaTab(self.app_settings, self.current_project)
        self.pref_tab = PreferencesTab(self.app_settings)

        self.ext_tab.netlist_ready.connect(self._receive_extracted_netlist)
        self.pref_tab.settings_updated.connect(self._on_settings_updated)

        for tab in [self.sim_tab, self.lvs_tab, self.ext_tab, self.ant_tab]:
            tab.send_status.connect(self.set_status)

        self.tabs.addTab(self.sim_tab, "Simulation")
        self.tabs.addTab(self.lvs_tab, "LVS")
        self.tabs.addTab(self.ext_tab, "Extraction / Post-layout")
        self.tabs.addTab(self.ant_tab, "Antenna Check")
        self.tabs.addTab(self.project_tab, "Project / Files")
        self.tabs.addTab(self.pref_tab, "Preferences")

        if self._current_project:
            self.project_tab.set_project(self._current_project)

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("Tools")
        open_xschem = QAction("Open xschem", self)
        open_xschem.triggered.connect(self._open_xschem)
        menu.addAction(open_xschem)

    def _open_xschem(self) -> None:
        import subprocess

        cmd = [self.app_settings.tool_paths.xschem]
        if self._current_project:
            cmd.append(self._current_project)
        try:
            subprocess.Popen(cmd)
        except OSError as exc:
            QMessageBox.warning(self, "Launch error", f"Failed to launch xschem: {exc}")

    def _on_project_changed(self, path: str) -> None:
        self._current_project = path
        self.app_settings.last_project = path
        self.app_settings.recent_projects = self.project_tab.recent_projects
        self.settings_mgr.save(self.app_settings)

    def _receive_extracted_netlist(self, netlist_path: str) -> None:
        self.sim_tab.netlist_edit.setText(netlist_path)
        self.tabs.setCurrentWidget(self.sim_tab)

    def _on_settings_updated(self, new_settings: AppSettings) -> None:
        self.app_settings = new_settings
        self.settings_mgr.save(self.app_settings)
        self.set_status("Preferences saved")

    def current_project(self) -> str:
        return self._current_project

    def set_status(self, text: str) -> None:
        self.state_label.setText(text)
