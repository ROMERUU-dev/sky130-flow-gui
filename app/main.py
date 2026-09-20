"""Application entry point for SKY130 Flow GUI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.core.branding import resolve_app_icon
from app.core.env_validator import EnvValidator
from app.core.i18n import pick
from app.core.settings_manager import SettingsManager
from app.ui.main_window import MainWindow
from app.ui.splash import StartupSplash
from app.ui.theme import build_palette, resolve


def _running_on_wayland() -> bool:
    """Detect a Wayland session, where the xcb libraries are not needed."""
    platform = os.environ.get("QT_QPA_PLATFORM", "").lower()
    if platform:
        return platform.startswith("wayland")
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def _check_x11_runtime() -> int:
    """Fail early with a readable message when Qt's xcb plugin cannot load.

    The check only applies to X11 sessions. A Wayland session loads the
    wayland platform plugin instead, and refusing to start there because the
    xcb helper libraries are absent blocked the app on stock Ubuntu desktops.
    """
    if _running_on_wayland():
        return 0
    gui_diag = EnvValidator()._detect_gui_dependencies("en")
    if not gui_diag.missing_required:
        return 0
    missing = ", ".join(gui_diag.missing_required)
    sys.stderr.write(
        "Qt/X11 runtime dependencies are missing for PySide6 on Ubuntu.\n"
        f"Missing packages: {missing}\n"
        "Install the Ubuntu bootstrap packages or install the listed libraries before starting the GUI.\n"
    )
    return 1


def main() -> int:
    """Run the Qt application."""
    failure = _check_x11_runtime()
    if failure:
        return failure

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("SKY130 Flow GUI")
    app.setApplicationDisplayName("SKY130 Flow")
    app.setOrganizationName("OpenLane Users")
    # Wayland matches windows to .desktop entries through this name; without it
    # the shell shows a generic icon and a wrong application title.
    app.setDesktopFileName("sky130-flow-gui")
    # Without this the window and the task switcher fall back to a generic
    # icon; the desktop file name alone only covers Wayland.
    icon_path = resolve_app_icon()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))

    settings = SettingsManager().load()
    lang = settings.language
    app.setPalette(build_palette(resolve(settings.theme)))

    splash = StartupSplash()
    splash.show()
    splash.update_step(pick(lang, "Preparando la interfaz...", "Preparing the interface..."))
    QCoreApplication.processEvents()

    config_home = Path.home().joinpath(".config", "sky130-flow-gui")
    config_home.mkdir(parents=True, exist_ok=True)

    window = MainWindow()
    window.show()
    splash.finish(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
