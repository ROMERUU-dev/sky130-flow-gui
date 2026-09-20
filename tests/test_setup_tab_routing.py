"""Regression tests for setup assistant step routing."""

from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace


class _DummySignal:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def connect(self, *args, **kwargs) -> None:
        pass

    def emit(self, *args, **kwargs) -> None:
        pass


class _DummyWidget:
    def __init__(self, *args, **kwargs) -> None:
        pass


class _DummyQProcess:
    NotRunning = 0
    Running = 1

    class ExitStatus:
        pass

    class ProcessError:
        FailedToStart = 0


class _DummyQt:
    class AlignmentFlag:
        AlignCenter = 0

    ItemIsEnabled = 1
    ItemIsSelectable = 2
    WA_StyledBackground = 3


from tests.qt_stubs import install_qtwidgets_stub

install_qtwidgets_stub(_DummyWidget)

from app.ui.setup_tab import SetupTab


class _Log:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def append(self, text: str) -> None:
        self.lines.append(text)


class SetupTabRoutingTest(unittest.TestCase):
    def _tab_with_diagnosis(self, diagnosis: SimpleNamespace) -> SetupTab:
        tab = SetupTab.__new__(SetupTab)
        tab.lang = "es"
        tab.log = _Log()
        tab._last_diagnosis = diagnosis
        tab.selected_steps = []
        tab._set_step = tab.selected_steps.append
        return tab

    def test_after_pdk_ready_routes_to_tools_when_tools_are_missing(self) -> None:
        diagnosis = SimpleNamespace(
            tools={
                "xschem": SimpleNamespace(status="missing"),
                "ngspice": SimpleNamespace(status="ok"),
            },
            pdk=SimpleNamespace(status="present"),
        )
        tab = self._tab_with_diagnosis(diagnosis)

        tab._route_after_pdk_ready()

        self.assertEqual(tab.selected_steps, [SetupTab.STEP_TOOLS])
        self.assertIn("faltan tools", tab.log.lines[-1])

    def test_after_pdk_ready_routes_to_apply_when_tools_are_ready(self) -> None:
        diagnosis = SimpleNamespace(
            tools={
                "xschem": SimpleNamespace(status="ok"),
                "netgen": SimpleNamespace(status="alias"),
            },
            pdk=SimpleNamespace(status="present"),
        )
        tab = self._tab_with_diagnosis(diagnosis)

        tab._route_after_pdk_ready()

        self.assertEqual(tab.selected_steps, [SetupTab.STEP_APPLY])


if __name__ == "__main__":
    unittest.main()
