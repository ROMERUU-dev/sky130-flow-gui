"""Background subprocess runner with streaming logs."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from PySide6.QtCore import QObject, QProcess, Signal


@dataclass
class CommandSpec:
    command: list[str]
    cwd: str | None = None
    env: dict[str, str] | None = None


class CommandRunner(QObject):
    """Qt-based process runner that keeps UI responsive."""

    line_output = Signal(str)
    started = Signal(str)
    finished = Signal(int, str)

    def __init__(self) -> None:
        super().__init__()
        self._proc: QProcess | None = None

    def run(self, spec: CommandSpec) -> None:
        """Start the command asynchronously."""
        if self._proc and self._proc.state() != QProcess.NotRunning:
            self.line_output.emit("A process is already running.")
            return

        self._proc = QProcess(self)
        self._proc.setProgram(spec.command[0])
        self._proc.setArguments(spec.command[1:])

        env = os.environ.copy()
        if spec.env:
            env.update(spec.env)
        qenv = self._proc.processEnvironment()
        for key, value in env.items():
            qenv.insert(key, value)
        self._proc.setProcessEnvironment(qenv)

        if spec.cwd:
            self._proc.setWorkingDirectory(spec.cwd)

        self._proc.readyReadStandardOutput.connect(self._read_stdout)
        self._proc.readyReadStandardError.connect(self._read_stderr)
        self._proc.finished.connect(self._on_finished)

        self.started.emit(" ".join(spec.command))
        self._proc.start()

    def stop(self) -> None:
        """Try graceful stop, then hard kill if needed."""
        if not self._proc:
            return
        if self._proc.state() == QProcess.Running:
            self._proc.terminate()
            if not self._proc.waitForFinished(1500):
                self._proc.kill()

    def _read_stdout(self) -> None:
        if self._proc:
            data = bytes(self._proc.readAllStandardOutput()).decode(errors="replace")
            self.line_output.emit(data)

    def _read_stderr(self) -> None:
        if self._proc:
            data = bytes(self._proc.readAllStandardError()).decode(errors="replace")
            self.line_output.emit(data)

    def _on_finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        self.finished.emit(code, "success" if code == 0 else "failed")
