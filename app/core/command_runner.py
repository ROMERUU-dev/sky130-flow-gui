"""Background subprocess runner with streaming logs and a job queue."""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QProcess, Signal


@dataclass
class CommandSpec:
    command: list[str]
    cwd: str | None = None
    env: dict[str, str] | None = None
    label: str = ""
    tag: str = ""


@dataclass
class QueuedJob:
    spec: CommandSpec
    position: int = 0
    extras: dict = field(default_factory=dict)


class CommandRunner(QObject):
    """Qt-based process runner that keeps the UI responsive.

    Requests that arrive while something is running used to be dropped with a
    log line. They are queued instead, so a user can line up an extraction and
    an LVS run without babysitting the first one.
    """

    line_output = Signal(str)
    started = Signal(str)
    finished = Signal(int, str)
    queue_changed = Signal(int)
    job_started = Signal(object)
    job_finished = Signal(object, int)

    def __init__(self, queue_enabled: bool = True) -> None:
        super().__init__()
        self._proc: QProcess | None = None
        self._queue: deque[CommandSpec] = deque()
        self._current: CommandSpec | None = None
        self._queue_enabled = queue_enabled

    # ------------------------------------------------------------------ state

    @property
    def busy(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.NotRunning

    def pending(self) -> int:
        """Number of jobs waiting behind the running one."""
        return len(self._queue)

    def queued_labels(self) -> list[str]:
        return [spec.label or " ".join(spec.command) for spec in self._queue]

    def current_label(self) -> str:
        if self._current is None:
            return ""
        return self._current.label or " ".join(self._current.command)

    # ------------------------------------------------------------------ control

    def run(self, spec: CommandSpec) -> None:
        """Start the command, or queue it when something else is running."""
        if self.busy:
            if not self._queue_enabled:
                self.line_output.emit("A process is already running.\n")
                return
            self._queue.append(spec)
            self.queue_changed.emit(len(self._queue))
            self.line_output.emit(
                f"Queued ({len(self._queue)} waiting): {spec.label or ' '.join(spec.command)}\n"
            )
            return
        self._start(spec)

    def clear_queue(self) -> int:
        """Drop everything that has not started yet. Returns how many were dropped."""
        dropped = len(self._queue)
        self._queue.clear()
        if dropped:
            self.queue_changed.emit(0)
        return dropped

    def stop(self) -> None:
        """Try a graceful stop, then a hard kill, and abandon the queue."""
        self.clear_queue()
        if not self._proc:
            return
        if self._proc.state() != QProcess.NotRunning:
            self._proc.terminate()
            if not self._proc.waitForFinished(1500):
                self._proc.kill()

    # ------------------------------------------------------------------ internals

    def _start(self, spec: CommandSpec) -> None:
        self._current = spec
        proc = QProcess(self)
        self._proc = proc
        proc.setProgram(spec.command[0])
        proc.setArguments(spec.command[1:])

        env = os.environ.copy()
        if spec.env:
            env.update(spec.env)
        qenv = proc.processEnvironment()
        for key, value in env.items():
            qenv.insert(key, value)
        proc.setProcessEnvironment(qenv)

        if spec.cwd:
            proc.setWorkingDirectory(spec.cwd)

        proc.readyReadStandardOutput.connect(self._read_stdout)
        proc.readyReadStandardError.connect(self._read_stderr)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)

        self.started.emit(" ".join(spec.command))
        self.job_started.emit(spec)
        proc.start()

    def _read_stdout(self) -> None:
        if self._proc:
            self.line_output.emit(bytes(self._proc.readAllStandardOutput()).decode(errors="replace"))

    def _read_stderr(self) -> None:
        if self._proc:
            self.line_output.emit(bytes(self._proc.readAllStandardError()).decode(errors="replace"))

    def _on_finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        self._release(code, "success" if code == 0 else "failed")

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.FailedToStart:
            message = self._proc.errorString() if self._proc else "Failed to start process."
            self.line_output.emit(f"{message}\n")
            self._release(-1, "failed_to_start")
            return
        if self._proc:
            message = self._proc.errorString()
            if message:
                self.line_output.emit(f"{message}\n")

    def _release(self, code: int, status: str) -> None:
        """Retire the finished process and start whatever is next in line."""
        spec = self._current
        proc = self._proc
        self._current = None
        self._proc = None
        if proc is not None:
            # A process that failed to start never emits `finished`, so the
            # QProcess used to be dropped without being cleaned up.
            if proc.state() != QProcess.NotRunning:
                proc.kill()
                proc.waitForFinished(500)
            proc.deleteLater()
        if spec is not None:
            self.job_finished.emit(spec, code)
        self.finished.emit(code, status)
        if self._queue:
            next_spec = self._queue.popleft()
            self.queue_changed.emit(len(self._queue))
            self._start(next_spec)
