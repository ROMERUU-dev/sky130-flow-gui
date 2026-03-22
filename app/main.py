"""Application entry point for SKY130 Flow GUI."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.splash import StartupSplash


def main() -> int:
    """Run the Qt application."""
    app = QApplication(sys.argv)
    app.setApplicationName("SKY130 Flow GUI")
    app.setOrganizationName("OpenLane Users")

    splash = StartupSplash()
    splash.show()
    splash.update_step("Inicializando entorno...")
    QCoreApplication.processEvents()

    config_home = Path.home().joinpath(".config", "sky130-flow-gui")
    config_home.mkdir(parents=True, exist_ok=True)
    splash.update_step("Cargando configuración de usuario...")
    QCoreApplication.processEvents()

    splash.update_step("Preparando módulos de simulación y verificación...")
    QCoreApplication.processEvents()

    window = MainWindow()
    splash.update_step("Abriendo interfaz principal...")
    QCoreApplication.processEvents()

    window.show()
    splash.finish(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
