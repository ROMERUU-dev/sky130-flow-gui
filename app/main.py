"""Application entry point for SKY130 Flow GUI."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from app.core.i18n import pick
from app.core.settings_manager import SettingsManager
from app.ui.main_window import MainWindow
from app.ui.splash import StartupSplash

MIN_SPLASH_SECONDS = 10.0


def main() -> int:
    """Run the Qt application."""
    start_time = time.monotonic()
    app = QApplication(sys.argv)
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
