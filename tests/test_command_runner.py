"""Tests for the queued subprocess runner."""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from app.core.command_runner import CommandRunner, CommandSpec


class CommandRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _wait_until(self, predicate, timeout_ms: int = 8000) -> bool:
        loop = QEventLoop()
        elapsed = {"ms": 0}

        def tick() -> None:
            elapsed["ms"] += 25
            if predicate() or elapsed["ms"] >= timeout_ms:
                loop.quit()

        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(25)
        loop.exec()
        timer.stop()
        return predicate()

    @staticmethod
    def _python(script: str, label: str = "") -> CommandSpec:
        return CommandSpec(command=[sys.executable, "-c", script], label=label)

    def test_successful_command_reports_zero(self) -> None:
        runner = CommandRunner()
        results: list[tuple[int, str]] = []
        runner.finished.connect(lambda code, status: results.append((code, status)))

        runner.run(self._python("print('hello')"))
        self._wait_until(lambda: bool(results))

        self.assertEqual(results[0], (0, "success"))

    def test_nonzero_exit_is_reported_as_failed(self) -> None:
        runner = CommandRunner()
        results: list[tuple[int, str]] = []
        runner.finished.connect(lambda code, status: results.append((code, status)))

        runner.run(self._python("raise SystemExit(3)"))
        self._wait_until(lambda: bool(results))

        self.assertEqual(results[0], (3, "failed"))

    def test_second_command_is_queued_and_runs_afterwards(self) -> None:
        """Requests arriving during a run used to be dropped with a log line."""
        runner = CommandRunner()
        order: list[str] = []
        runner.job_started.connect(lambda spec: order.append(f"start:{spec.label}"))
        runner.job_finished.connect(lambda spec, _code: order.append(f"done:{spec.label}"))

        runner.run(self._python("import time; time.sleep(0.4)", label="first"))
        runner.run(self._python("pass", label="second"))

        self.assertEqual(runner.pending(), 1)
        self.assertEqual(runner.queued_labels(), ["second"])

        self._wait_until(lambda: order.count("done:second") == 1)

        self.assertEqual(order, ["start:first", "done:first", "start:second", "done:second"])
        self.assertEqual(runner.pending(), 0)

    def test_queue_can_be_cleared(self) -> None:
        runner = CommandRunner()
        runner.run(self._python("import time; time.sleep(0.4)", label="first"))
        runner.run(self._python("pass", label="second"))
        runner.run(self._python("pass", label="third"))

        dropped = runner.clear_queue()

        self.assertEqual(dropped, 2)
        self.assertEqual(runner.pending(), 0)
        self._wait_until(lambda: not runner.busy)

    def test_queueing_can_be_turned_off(self) -> None:
        runner = CommandRunner(queue_enabled=False)
        runner.run(self._python("import time; time.sleep(0.3)", label="first"))
        runner.run(self._python("pass", label="second"))

        self.assertEqual(runner.pending(), 0)
        self._wait_until(lambda: not runner.busy)

    def test_missing_executable_reports_failure_and_releases_the_runner(self) -> None:
        runner = CommandRunner()
        results: list[tuple[int, str]] = []
        runner.finished.connect(lambda code, status: results.append((code, status)))

        runner.run(CommandSpec(command=["sky130-flow-gui-no-such-binary"], label="missing"))
        self._wait_until(lambda: bool(results))

        self.assertEqual(results[0][1], "failed_to_start")
        self.assertFalse(runner.busy)

    def test_a_failed_start_does_not_block_the_queue(self) -> None:
        runner = CommandRunner()
        finished: list[str] = []
        runner.job_finished.connect(lambda spec, _code: finished.append(spec.label))

        runner.run(CommandSpec(command=["sky130-flow-gui-no-such-binary"], label="missing"))
        runner.run(self._python("pass", label="after"))

        self._wait_until(lambda: "after" in finished)

        self.assertIn("missing", finished)
        self.assertIn("after", finished)

    def test_output_is_streamed(self) -> None:
        runner = CommandRunner()
        chunks: list[str] = []
        runner.line_output.connect(chunks.append)
        done: list[int] = []
        runner.finished.connect(lambda code, _status: done.append(code))

        runner.run(self._python("print('streamed-line')"))
        self._wait_until(lambda: bool(done))

        self.assertIn("streamed-line", "".join(chunks))


if __name__ == "__main__":
    unittest.main()
