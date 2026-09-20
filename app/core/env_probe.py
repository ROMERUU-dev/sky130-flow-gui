"""Off-thread environment probing for the setup and preferences pages.

A full diagnosis shells out to every configured tool and to the user Python
environment, which takes well over a second on a cold cache.  Running that
while the widgets are being built froze the window during startup, so the scan
is pushed onto a worker thread and the result is warmed into
:class:`~app.core.env_validator.EnvValidator`'s cache before the UI reads it.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.core.env_validator import EnvValidator
from app.core.settings_manager import AppSettings


class _ProbeSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _ProbeTask(QRunnable):
    def __init__(self, settings: AppSettings, lang: str, refresh: bool, signals: _ProbeSignals) -> None:
        super().__init__()
        self._settings = settings
        self._lang = lang
        self._refresh = refresh
        self._signals = signals

    def _emit(self, signal, payload) -> None:
        """Emit unless the owning widget was destroyed while the scan ran."""
        try:
            signal.emit(payload)
        except RuntimeError:
            pass

    def run(self) -> None:  # pragma: no cover - exercised through EnvProbe
        try:
            diagnosis = EnvValidator().diagnose(self._settings, lang=self._lang, refresh=self._refresh)
        except Exception as exc:  # noqa: BLE001 - a probe must never kill the worker thread
            self._emit(self._signals.failed, str(exc))
            return
        self._emit(self._signals.finished, diagnosis)


class EnvProbe(QObject):
    """Run :meth:`EnvValidator.diagnose` on a worker thread.

    ``finished`` carries the diagnosis, which is also stored in the validator
    cache, so any subsequent synchronous call on the UI thread returns
    immediately instead of shelling out again.
    """

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._signals = _ProbeSignals(self)
        self._signals.finished.connect(self._on_finished)
        self._signals.failed.connect(self._on_failed)

    @property
    def busy(self) -> bool:
        return self._busy

    def start(self, settings: AppSettings, lang: str = "en", *, refresh: bool = False) -> bool:
        """Queue a scan. Returns False when one is already in flight."""
        if self._busy:
            return False
        self._busy = True
        QThreadPool.globalInstance().start(_ProbeTask(settings, lang, refresh, self._signals))
        return True

    def _on_finished(self, diagnosis: object) -> None:
        self._busy = False
        self.finished.emit(diagnosis)

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self.failed.emit(message)
