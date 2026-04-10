"""Application entry point for SKY130 Flow GUI."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from app.core.env_validator import EnvValidator
from app.core.i18n import pick
from app.core.settings_manager import SettingsManager
from app.ui.main_window import MainWindow
from app.ui.splash import StartupSplash

MIN_SPLASH_SECONDS = 10.0


def _build_forced_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#fffdfb"))
    palette.setColor(QPalette.WindowText, QColor("#172033"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase, QColor("#fff7fb"))
    palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipText, QColor("#172033"))
    palette.setColor(QPalette.Text, QColor("#172033"))
    palette.setColor(QPalette.Button, QColor("#fff7fb"))
    palette.setColor(QPalette.ButtonText, QColor("#172033"))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Highlight, QColor("#bfdbfe"))
    palette.setColor(QPalette.HighlightedText, QColor("#172033"))
    palette.setColor(QPalette.Link, QColor("#2563eb"))
    return palette


def main() -> int:
    """Run the Qt application."""
    start_time = time.monotonic()
    gui_diag = EnvValidator()._detect_gui_dependencies("en")
    if gui_diag.missing_required:
        missing = ", ".join(gui_diag.missing_required)
        sys.stderr.write(
            "Qt/X11 runtime dependencies are missing for PySide6 on Ubuntu.\n"
            f"Missing packages: {missing}\n"
            "Install the Ubuntu bootstrap packages or install the listed libraries before starting the GUI.\n"
        )
        return 1

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(_build_forced_palette())
    app.setApplicationName("SKY130 Flow GUI")
    app.setOrganizationName("OpenLane Users")
    settings = SettingsManager().load()
    lang = settings.language

    splash = StartupSplash()
    splash.show()
    splash.update_step(pick(lang, "Inicializando entorno...", "Initializing environment..."))
    QCoreApplication.processEvents()

    config_home = Path.home().joinpath(".config", "sky130-flow-gui")
    config_home.mkdir(parents=True, exist_ok=True)
    splash.update_step(pick(lang, "Cargando configuración de usuario...", "Loading user settings..."))
    QCoreApplication.processEvents()

    splash.update_step(pick(lang, "Preparando módulos de simulación y verificación...", "Preparing simulation and verification modules..."))
    QCoreApplication.processEvents()

    window = MainWindow()
    splash.update_step(pick(lang, "Abriendo interfaz principal...", "Opening main interface..."))
    QCoreApplication.processEvents()

    elapsed = time.monotonic() - start_time
    if elapsed < MIN_SPLASH_SECONDS:
        time.sleep(MIN_SPLASH_SECONDS - elapsed)

    window.show()
    splash.finish(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
