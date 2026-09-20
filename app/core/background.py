"""Run a slow call on a worker thread and deliver the result to the UI thread."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _Task(QRunnable):
    def __init__(self, work: Callable[[], object], signals: _TaskSignals) -> None:
        super().__init__()
        self._work = work
        self._signals = signals

    def _emit(self, signal, payload) -> None:
        """Emit unless the owning widget was destroyed while the task ran."""
        try:
            signal.emit(payload)
        except RuntimeError:
            pass

    def run(self) -> None:  # pragma: no cover - exercised through BackgroundTask
        try:
            result = self._work()
        except Exception as exc:  # noqa: BLE001 - a task must never kill the worker thread
            self._emit(self._signals.failed, str(exc))
            return
        self._emit(self._signals.finished, result)


class BackgroundTask(QObject):
    """Run one callable at a time off the UI thread.

    ``finished`` carries whatever the callable returned. A second ``start``
    while one is in flight is refused rather than queued, which is what the
    single-shot buttons that use this need.
    """

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._signals = _TaskSignals(self)
        self._signals.finished.connect(self._on_finished)
        self._signals.failed.connect(self._on_failed)

    @property
    def busy(self) -> bool:
        return self._busy

    def start(self, work: Callable[[], object]) -> bool:
        """Queue the callable. Returns False when one is already running."""
        if self._busy:
            return False
        self._busy = True
        QThreadPool.globalInstance().start(_Task(work, self._signals))
        return True

    def _on_finished(self, result: object) -> None:
        self._busy = False
        self.finished.emit(result)

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self.failed.emit(message)
