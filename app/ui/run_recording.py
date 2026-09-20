"""Shared run-history bookkeeping for the tool tabs.

Simulation, extraction, LVS and antenna all follow the same shape: build a
command, start it, and report when it ends. Recording that in each tab
separately invites the four copies to drift apart.
"""

from __future__ import annotations

from pathlib import Path

from app.core.error_advisor import analyze, format_advice, has_blocking_errors
from app.core.run_history import RunHistory


class RunRecordingMixin:
    """Record a tab's runs, and judge them by the tool's own output."""

    RUN_KIND = ""
    ADVISOR_TOOL = ""

    def _begin_run_record(self, outputs, label: str, inputs: dict[str, str] | None = None) -> str:
        """Open a history entry. Returns the run id."""
        self._active_run_record = RunHistory(outputs.runs).start(
            self.RUN_KIND,
            label=label,
            project=str(outputs.base),
            inputs={key: value for key, value in (inputs or {}).items() if value},
        )
        self._run_outputs = outputs
        return self._active_run_record.run_id

    def _end_run_record(
        self,
        exit_code: int,
        artifacts: dict[str, str] | None = None,
        summary: str = "",
        text: str = "",
    ) -> list:
        """Close the entry, letting a recognised failure override the exit code."""
        advices = analyze(text, tool=self.ADVISOR_TOOL) if text else []
        record = getattr(self, "_active_run_record", None)
        if record is None:
            return advices
        outputs = getattr(self, "_run_outputs", None)
        if outputs is None:
            return advices
        effective = exit_code if exit_code else (1 if has_blocking_errors(advices) else 0)
        if advices:
            summary = "; ".join(advice.title for advice in advices[:2]) or summary
        try:
            RunHistory(outputs.runs).finish(record.run_id, effective, artifacts or {}, summary)
        except OSError:
            pass
        self._active_run_record = None
        return advices

    @staticmethod
    def _read_report(path: str | Path | None) -> str:
        """Read a report the tool wrote, which is where its errors usually are."""
        if not path:
            return ""
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def _report_advice(self, advices: list, log_widget) -> None:
        from app.ui.widgets import append_log

        if advices:
            append_log(log_widget, "\n" + format_advice(advices))
