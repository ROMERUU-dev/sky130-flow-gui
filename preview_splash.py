"""Small helper to preview the startup splash in a desktop session."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.ui.splash import StartupSplash


def main() -> int:
    app = QApplication(sys.argv)
    splash = StartupSplash()
    splash.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
