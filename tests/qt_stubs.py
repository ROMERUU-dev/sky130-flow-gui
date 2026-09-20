"""Opt-in PySide6 stand-ins for tests that must run without a Qt install.

Installing a stub unconditionally poisons ``sys.modules`` for every test module
imported afterwards, which silently turns the real Qt tests into skips.  These
helpers only fall back to a stub when PySide6 is genuinely unavailable.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace


def pyside6_available() -> bool:
    """Return True when the real PySide6 package can be imported."""
    try:
        import PySide6.QtCore  # noqa: F401
    except ImportError:
        return False
    return True


def install_qtcore_stub() -> None:
    """Provide a minimal ``PySide6.QtCore`` when the real package is missing."""
    if pyside6_available():
        return
    qtcore_stub = SimpleNamespace(QSettings=object)
    sys.modules.setdefault("PySide6", SimpleNamespace(QtCore=qtcore_stub))
    sys.modules.setdefault("PySide6.QtCore", qtcore_stub)


def install_qtwidgets_stub(widget_factory: type) -> None:
    """Provide minimal ``QtCore``/``QtWidgets`` modules built from one dummy widget."""
    if pyside6_available():
        return
    qtcore_stub = SimpleNamespace(QSettings=object, Qt=SimpleNamespace(), Signal=lambda *a, **k: None)
    names = (
        "QComboBox", "QFrame", "QGridLayout", "QHBoxLayout", "QLabel",
        "QListWidget", "QListWidgetItem", "QProgressBar", "QPushButton",
        "QScrollArea", "QSizePolicy", "QStackedWidget", "QTableWidget",
        "QTableWidgetItem", "QTextEdit", "QVBoxLayout", "QWidget",
    )
    qtwidgets_stub = SimpleNamespace(**{name: widget_factory for name in names})
    sys.modules["PySide6"] = SimpleNamespace(QtCore=qtcore_stub, QtWidgets=qtwidgets_stub)
    sys.modules["PySide6.QtCore"] = qtcore_stub
    sys.modules["PySide6.QtWidgets"] = qtwidgets_stub
