"""Application entry point for SKY130 Flow GUI."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    """Run the Qt application."""
    app = QApplication(sys.argv)
    app.setApplicationName("SKY130 Flow GUI")
    app.setOrganizationName("OpenLane Users")

    # Ensure a writable runtime home exists for app state.
    Path.home().joinpath(".config", "sky130-flow-gui").mkdir(parents=True, exist_ok=True)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
