"""Main application window and tab orchestration."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.i18n import pick
from app.core.layout_tools import resolve_layout_dir
from app.core.magic_launcher import MagicLaunchBuilder
from app.core.output_manager import OutputManager
from app.core.project_manager import ProjectManager
from app.core.settings_manager import AppSettings, SettingsManager
from app.core.xschem_launcher import XschemLaunchBuilder
from app.ui.antenna_tab import AntennaTab
from app.ui.em_sizing_tab import EmSizingTab
from app.ui.extraction_tab import ExtractionTab
from app.ui.lvs_tab import LvsTab
from app.ui.preferences_tab import PreferencesTab
from app.ui.project_tab import ProjectTab
from app.ui.simulation_tab import SimulationTab
from app.ui.theme import LIGHT, build_palette, build_stylesheet, heading_style, resolve


class MainWindow(QMainWindow):
    """Top-level window for SKY130 workflow management."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SKY130 Flow")
        self.setMinimumSize(1024, 640)
        self.resize(1400, 900)

        self.settings_mgr = SettingsManager()
        self.app_settings: AppSettings = self.settings_mgr.load()
        self.output_manager = OutputManager()
        self.project_mgr = ProjectManager(self.output_manager)
        self._current_project = self.app_settings.last_project
        self._startup_project_prompt_shown = False

        self.root = QWidget()
        self.root_layout = QHBoxLayout(self.root)
        self.root_layout.setContentsMargins(12, 10, 12, 10)
        self.root_layout.setSpacing(12)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebarNav")
        self.sidebar.setSpacing(3)
        self.sidebar.setUniformItemSizes(True)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()

        self.sidebar_card = QFrame()
        self.sidebar_card.setObjectName("sidebarCard")
        self.sidebar_layout = QVBoxLayout(self.sidebar_card)
        self.sidebar_layout.setContentsMargins(8, 8, 8, 8)
        self.sidebar_layout.setSpacing(8)
        self.sidebar_layout.addWidget(self.sidebar)
        # The navigation holds seven short labels. Letting it claim ~280px
        # pushed the working area below the width the tab content needs and
        # forced a horizontal scrollbar at the default window size.
        self.sidebar_card.setMinimumWidth(168)
        self.sidebar_card.setMaximumWidth(208)

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
        self._install_shortcuts()
        self._restore_geometry()
        if self.app_settings.prompt_project_on_start:
            QTimer.singleShot(250, self._prompt_for_project_on_start)

    def _install_shortcuts(self) -> None:
        """Ctrl+1..7 jump straight to a section."""
        for index in range(self.tabs.count()):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self)
            shortcut.activated.connect(lambda idx=index: self.tabs.setCurrentIndex(idx))

    def _restore_geometry(self) -> None:
        saved = self.app_settings.window_geometry
        if not saved:
            return
        try:
            self.restoreGeometry(QByteArray.fromBase64(saved.encode("ascii")))
        except (ValueError, UnicodeEncodeError):
            pass

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Remember where the window was before shutting down."""
        self.app_settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.settings_mgr.save(self.app_settings)
        super().closeEvent(event)

    def _build_tabs(self) -> None:
        self.project_tab = ProjectTab(self.project_mgr, self.app_settings.recent_projects, self.app_settings.language)
        self.project_tab.project_changed.connect(self._on_project_changed)

        self.sim_tab = SimulationTab(self.app_settings, self.project_mgr.outputs)
        self.lvs_tab = LvsTab(self.app_settings, self.project_mgr.outputs)
        self.ext_tab = ExtractionTab(self.app_settings, self.project_mgr.outputs)
        self.ant_tab = AntennaTab(self.app_settings, self.project_mgr.outputs)
        self.em_tab = EmSizingTab(self.app_settings, self.project_mgr.outputs)
        self.pref_tab = PreferencesTab(self.app_settings)

        self.ext_tab.netlist_ready.connect(self._receive_extracted_netlist)
        self.project_tab.project_changed.connect(lambda _path: self.sim_tab.load_project_profile())
        self.pref_tab.settings_updated.connect(self._on_settings_updated)

        for tab in [self.sim_tab, self.lvs_tab, self.ext_tab, self.ant_tab, self.em_tab, self.pref_tab]:
            tab.send_status.connect(self.set_status)

        self.tabs.addTab(self.sim_tab, pick(self.app_settings.language, "∿ Simulación", "∿ Simulation"))
        self.tabs.addTab(self.lvs_tab, "≣ LVS")
        self.tabs.addTab(self.ext_tab, pick(self.app_settings.language, "◫ Extracción", "◫ Extraction"))
        self.tabs.addTab(self.ant_tab, pick(self.app_settings.language, "⌁ Antena", "⌁ Antenna"))
        self.tabs.addTab(self.em_tab, "≈ EM")
        self.tabs.addTab(self.project_tab, pick(self.app_settings.language, "⌂ Proyecto", "⌂ Project"))
        self.tabs.addTab(self.pref_tab, pick(self.app_settings.language, "⚙ Preferencias", "⚙ Preferences"))
        self._populate_sidebar()

        if self._current_project:
            self.project_tab.set_project(self._current_project)
        else:
            self.project_mgr.ensure_structure()

    def _build_toolbar(self) -> None:
        import subprocess

        toolbar = QToolBar(pick(self.app_settings.language, "Quick Actions", "Quick Actions"), self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(toolbar.iconSize())
        self.addToolBar(toolbar)

        self._toolbar_subprocess = subprocess

        xschem_button = QToolButton(self)
        xschem_button.setObjectName("toolbarXschemButton")
        xschem_button.setText(pick(self.app_settings.language, "◫ xschem", "◫ xschem"))
        xschem_button.setToolTip(pick(self.app_settings.language, "Abrir xschem", "Open xschem"))
        xschem_button.clicked.connect(self._open_xschem)
        toolbar.addWidget(xschem_button)

        magic_button = QToolButton(self)
        magic_button.setObjectName("toolbarMagicButton")
        magic_button.setText(pick(self.app_settings.language, "⬢ Magic", "⬢ Magic"))
        magic_button.setToolTip(pick(self.app_settings.language, "Abrir Magic", "Open Magic"))
        magic_button.clicked.connect(self._open_magic)
        toolbar.addWidget(magic_button)

    def _apply_window_style(self) -> None:
        self.tabs.setDocumentMode(True)
        if self.menuBar() is not None:
            self.menuBar().hide()
        self._theme = resolve(self.app_settings.theme)
        self.setStyleSheet(build_stylesheet(self._theme))
        app = QApplication.instance()
        if app is not None:
            app.setPalette(build_palette(self._theme))
        self._repaint_sidebar_accents()

    def apply_theme(self, preference: str) -> None:
        """Repaint the whole window for a new theme preference, without a restart."""
        self.app_settings.theme = preference
        self._apply_window_style()

    SIDEBAR_ACCENTS = {
        "light": ("#2563eb", "#e76f51", "#0f9d8a", "#d97706", "#7c3aed", "#059669", "#db2777"),
        "dark": ("#7fa9ff", "#ff9f80", "#4fd1bd", "#fbbf24", "#b696ff", "#34d399", "#f472b6"),
    }

    def _populate_sidebar(self) -> None:
        self.sidebar.clear()
        for index in range(self.tabs.count()):
            item = QListWidgetItem(self.tabs.tabText(index))
            self.sidebar.addItem(item)
        self._repaint_sidebar_accents()
        if self.sidebar.count():
            self.sidebar.setCurrentRow(self.tabs.currentIndex())

    def _repaint_sidebar_accents(self) -> None:
        """Tint each navigation entry with a theme-appropriate accent."""
        accents = self.SIDEBAR_ACCENTS[getattr(self, "_theme", LIGHT).mode]
        for index in range(self.sidebar.count()):
            item = self.sidebar.item(index)
            if item is not None:
                item.setForeground(QColor(accents[index % len(accents)]))

    def _wire_navigation(self) -> None:
        self.sidebar.currentRowChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.sidebar.setCurrentRow)

    def _prompt_for_project_on_start(self) -> None:
        if self._startup_project_prompt_shown:
            return
        self._startup_project_prompt_shown = True

        dialog = QDialog(self)
        dialog.setWindowTitle(pick(self.app_settings.language, "Selecciona proyecto", "Select project"))
        layout = QVBoxLayout(dialog)
        title = QLabel(
            pick(
                self.app_settings.language,
                "¿En qué proyecto vas a trabajar?",
                "Which project are you working on?",
            )
        )
        title.setStyleSheet(heading_style(self._theme, 18))
        layout.addWidget(title)

        current_text = self._current_project or pick(self.app_settings.language, "Workspace local sin proyecto", "Local workspace without a project")
        current_label = QLabel(f"{pick(self.app_settings.language, 'Actual', 'Current')}: {current_text}")
        current_label.setWordWrap(True)
        layout.addWidget(current_label)

        recent = QListWidget()
        for path in self.app_settings.recent_projects:
            recent.addItem(path)
        layout.addWidget(recent)

        actions = QHBoxLayout()
        open_btn = QPushButton(pick(self.app_settings.language, "Abrir repo existente", "Open existing repo"))
        create_btn = QPushButton(pick(self.app_settings.language, "Crear proyecto Tiny Tapeout", "Create Tiny Tapeout project"))
        workspace_btn = QPushButton(pick(self.app_settings.language, "Usar workspace", "Use workspace"))
        actions.addWidget(open_btn)
        actions.addWidget(create_btn)
        actions.addWidget(workspace_btn)
        layout.addLayout(actions)

        remember = QCheckBox(
            pick(
                self.app_settings.language,
                "No volver a preguntar al iniciar",
                "Do not ask again on startup",
            )
        )
        layout.addWidget(remember)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(pick(self.app_settings.language, "Continuar", "Continue"))
        buttons.button(QDialogButtonBox.Cancel).setText(pick(self.app_settings.language, "Cerrar", "Close"))
        layout.addWidget(buttons)

        def select_recent() -> None:
            item = recent.currentItem()
            if item:
                self.project_tab.set_project(item.text())
                dialog.accept()

        def open_existing() -> None:
            path = QFileDialog.getExistingDirectory(self, pick(self.app_settings.language, "Selecciona repo/proyecto", "Select repo/project"))
            if path:
                self.project_tab.set_project(path)
                dialog.accept()

        def create_project() -> None:
            dialog.accept()
            self.tabs.setCurrentWidget(self.project_tab)
            QTimer.singleShot(0, self.project_tab.create_tiny_tapeout_project)

        def use_workspace() -> None:
            self.project_mgr.current_project = None
            self._current_project = ""
            self.app_settings.last_project = ""
            self.settings_mgr.save(self.app_settings)
            self.project_tab._refresh_context_label()
            self.project_tab._index_files()
            self.sim_tab.load_project_profile()
            dialog.accept()

        recent.itemDoubleClicked.connect(lambda _item: select_recent())
        open_btn.clicked.connect(open_existing)
        create_btn.clicked.connect(create_project)
        workspace_btn.clicked.connect(use_workspace)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

        if remember.isChecked():
            self.app_settings.prompt_project_on_start = False
            self.settings_mgr.save(self.app_settings)

    def _open_xschem(self) -> None:
        launch = XschemLaunchBuilder(self.app_settings).build(self._current_project)
        try:
            self._toolbar_subprocess.Popen(launch.command, cwd=launch.cwd, env=launch.env)
        except OSError as exc:
            QMessageBox.warning(
                self,
                pick(self.app_settings.language, "Error al abrir", "Launch error"),
                f"{pick(self.app_settings.language, 'No se pudo abrir xschem', 'Failed to launch xschem')}: {exc}",
            )

    def _open_magic(self) -> None:
        project_path = Path(self._current_project).expanduser() if self._current_project else None
        target_path = None
        if project_path is not None and project_path.exists():
            target_path = str(resolve_layout_dir(project_path.resolve()))
        launch = MagicLaunchBuilder(self.app_settings).build(target_path)
        try:
            self._toolbar_subprocess.Popen(launch.command, cwd=launch.cwd, env=launch.env)
        except OSError as exc:
            QMessageBox.warning(
                self,
                pick(self.app_settings.language, "Error al abrir", "Launch error"),
                f"{pick(self.app_settings.language, 'No se pudo abrir Magic', 'Failed to launch Magic')}: {exc}",
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
        theme_changed = new_settings.theme != self.app_settings.theme
        self.app_settings = new_settings
        self.settings_mgr.save(self.app_settings)
        if theme_changed:
            self._apply_window_style()
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
