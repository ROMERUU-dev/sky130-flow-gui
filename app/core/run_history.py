"""Persistent record of what was run, when, and how it ended.

The previous "history" was a glob of `*.raw` files on disk. That told you a
simulation had produced output at some point, but not which netlist it came
from, how long it took, whether it actually succeeded, or anything at all
about extraction, LVS and antenna runs. Closing the app lost the thread.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

HISTORY_FILENAME = "history.json"
SCHEMA_VERSION = 1
DEFAULT_LIMIT = 200

KIND_SIMULATION = "simulation"
KIND_EXTRACTION = "extraction"
KIND_LVS = "lvs"
KIND_ANTENNA = "antenna"
KIND_EM = "em"

STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


@dataclass
class RunRecord:
    """One execution of one tool."""

    run_id: str = ""
    kind: str = KIND_SIMULATION
    label: str = ""
    status: str = STATUS_RUNNING
    exit_code: int | None = None
    started_at: float = 0.0
    finished_at: float | None = None
    project: str = ""
    inputs: dict[str, str] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    command: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None or not self.started_at:
            return None
        return max(0.0, self.finished_at - self.started_at)

    @property
    def succeeded(self) -> bool:
        return self.status == STATUS_SUCCESS

    def describe_duration(self) -> str:
        """Human-readable duration, or an empty string while still running."""
        seconds = self.duration_seconds
        if seconds is None:
            return ""
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes, rest = divmod(int(seconds), 60)
        if minutes < 60:
            return f"{minutes}m {rest:02d}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes:02d}m"

    def describe(self) -> str:
        """One line for a combo box or a list row."""
        stamp = time.strftime("%d %b %H:%M", time.localtime(self.started_at)) if self.started_at else "—"
        marks = {STATUS_SUCCESS: "OK", STATUS_FAILED: "ERROR", STATUS_RUNNING: "..."}
        mark = marks.get(self.status, self.status)
        duration = self.describe_duration()
        tail = f" · {duration}" if duration else ""
        return f"[{mark}] {stamp} · {self.label or self.kind}{tail}"


class RunHistory:
    """Append-only run log stored beside a project's outputs."""

    def __init__(self, runs_dir: Path | str, limit: int = DEFAULT_LIMIT) -> None:
        self.runs_dir = Path(runs_dir)
        self.path = self.runs_dir / HISTORY_FILENAME
        self.limit = limit

    # ------------------------------------------------------------- reading

    def records(self, kind: str | None = None, limit: int | None = None) -> list[RunRecord]:
        """Return records newest first, optionally filtered by kind."""
        records = self._load()
        if kind:
            records = [record for record in records if record.kind == kind]
        records.sort(key=lambda record: record.started_at, reverse=True)
        if limit:
            records = records[:limit]
        return records

    def get(self, run_id: str) -> RunRecord | None:
        for record in self._load():
            if record.run_id == run_id:
                return record
        return None

    def last(self, kind: str | None = None) -> RunRecord | None:
        found = self.records(kind=kind, limit=1)
        return found[0] if found else None

    # ------------------------------------------------------------- writing

    def start(
        self,
        kind: str,
        label: str = "",
        project: str = "",
        inputs: dict[str, str] | None = None,
        command: list[str] | None = None,
    ) -> RunRecord:
        """Record the beginning of a run and return its record."""
        record = RunRecord(
            run_id=uuid.uuid4().hex[:12],
            kind=kind,
            label=label,
            status=STATUS_RUNNING,
            started_at=time.time(),
            project=project,
            inputs=dict(inputs or {}),
            command=list(command or []),
        )
        self._append(record)
        return record

    def finish(
        self,
        run_id: str,
        exit_code: int,
        artifacts: dict[str, str] | None = None,
        summary: str = "",
    ) -> RunRecord | None:
        """Close out a run that was previously started."""
        records = self._load()
        updated: RunRecord | None = None
        for record in records:
            if record.run_id == run_id:
                record.status = STATUS_SUCCESS if exit_code == 0 else STATUS_FAILED
                record.exit_code = exit_code
                record.finished_at = time.time()
                if artifacts:
                    record.artifacts.update({key: value for key, value in artifacts.items() if value})
                if summary:
                    record.summary = summary
                updated = record
                break
        if updated is not None:
            self._write(records)
        return updated

    def clear(self) -> None:
        records = self._load()
        if records:
            self._write([])

    # ----------------------------------------------------------- internals

    def _load(self) -> list[RunRecord]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            return []
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            # A truncated write must not take the whole history with it.
            return []
        if not isinstance(payload, dict):
            return []
        records = []
        for item in payload.get("runs", []):
            if not isinstance(item, dict):
                continue
            known = {key: item.get(key) for key in RunRecord.__dataclass_fields__ if key in item}
            try:
                records.append(RunRecord(**known))
            except TypeError:
                continue
        return records

    def _append(self, record: RunRecord) -> None:
        records = self._load()
        records.append(record)
        self._write(records)

    def _write(self, records: list[RunRecord]) -> None:
        records.sort(key=lambda item: item.started_at)
        if self.limit and len(records) > self.limit:
            records = records[-self.limit :]
        payload = {"schema_version": SCHEMA_VERSION, "runs": [asdict(record) for record in records]}
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        # Written to a sibling file and moved into place, so an interrupted
        # write cannot leave a half-written history behind.
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.runs_dir, prefix=".history-", suffix=".tmp", delete=False
        )
        try:
            with handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(handle.name, self.path)
        except OSError:
            Path(handle.name).unlink(missing_ok=True)
            raise
