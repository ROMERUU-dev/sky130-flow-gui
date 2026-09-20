"""A one-glance summary of where a project stands.

The information already exists — every tool records its runs — but it is spread
across five tabs, so answering "did LVS pass since the last extraction?"
means clicking through all of them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from app.core.run_history import (
    KIND_ANTENNA,
    KIND_EXTRACTION,
    KIND_LVS,
    KIND_SIMULATION,
    RunHistory,
    RunRecord,
)

STATE_NEVER_RUN = "never_run"
STATE_OK = "ok"
STATE_FAILED = "failed"
STATE_STALE = "stale"

FLOW_ORDER = (KIND_EXTRACTION, KIND_SIMULATION, KIND_LVS, KIND_ANTENNA)

FLOW_TITLES = {
    KIND_EXTRACTION: ("Extracción", "Extraction"),
    KIND_SIMULATION: ("Simulación", "Simulation"),
    KIND_LVS: ("LVS", "LVS"),
    KIND_ANTENNA: ("Antena", "Antenna"),
}


def describe_age(seconds: float, spanish: bool = True) -> str:
    """Turn an age in seconds into something readable at a glance."""
    if seconds < 90:
        return "hace un momento" if spanish else "just now"
    minutes = seconds / 60.0
    if minutes < 60:
        return f"hace {int(minutes)} min" if spanish else f"{int(minutes)} min ago"
    hours = minutes / 60.0
    if hours < 24:
        return f"hace {int(hours)} h" if spanish else f"{int(hours)} h ago"
    days = int(hours / 24.0)
    if spanish:
        return "ayer" if days == 1 else f"hace {days} días"
    return "yesterday" if days == 1 else f"{days} days ago"


def describe_stale(kinds: tuple[str, ...], spanish: bool = True) -> str:
    """Name the stages that invalidated this one, with the right agreement."""
    if not kinds:
        return ""
    names = [FLOW_TITLES.get(kind, (kind, kind))[0 if spanish else 1] for kind in kinds]
    joined = ", ".join(names)
    if spanish:
        return f"{joined} corrió después" if len(names) == 1 else f"{joined} corrieron después"
    return f"{joined} ran afterwards"


@dataclass
class StageStatus:
    """Where one stage of the flow stands."""

    kind: str
    state: str = STATE_NEVER_RUN
    detail: str = ""
    age_seconds: float | None = None
    record: RunRecord | None = None
    stale_after: tuple[str, ...] = ()

    def title(self, spanish: bool = True) -> str:
        titles = FLOW_TITLES.get(self.kind, (self.kind, self.kind))
        return titles[0] if spanish else titles[1]

    def describe_age(self, spanish: bool = True) -> str:
        if self.age_seconds is None:
            return ""
        return describe_age(self.age_seconds, spanish)


@dataclass
class ProjectStatus:
    """The whole flow, in order."""

    project: str = ""
    stages: list[StageStatus] = field(default_factory=list)

    def stage(self, kind: str) -> StageStatus | None:
        for stage in self.stages:
            if stage.kind == kind:
                return stage
        return None

    @property
    def has_any_run(self) -> bool:
        return any(stage.state != STATE_NEVER_RUN for stage in self.stages)

    def blocking_stages(self) -> list[StageStatus]:
        return [stage for stage in self.stages if stage.state == STATE_FAILED]


def build_status(runs_dir: Path | str, project: str = "", now: float | None = None) -> ProjectStatus:
    """Summarise the latest run of each stage, newest information first.

    A stage is `stale` when it succeeded but an upstream stage has run since:
    passing LVS means nothing if the layout was re-extracted afterwards.
    """
    moment = time.time() if now is None else now
    history = RunHistory(runs_dir)
    status = ProjectStatus(project=project)

    latest: dict[str, RunRecord] = {}
    for kind in FLOW_ORDER:
        record = history.last(kind=kind)
        if record is not None:
            latest[kind] = record

    for index, kind in enumerate(FLOW_ORDER):
        record = latest.get(kind)
        if record is None:
            status.stages.append(StageStatus(kind=kind))
            continue

        finished = record.finished_at or record.started_at
        stage = StageStatus(
            kind=kind,
            state=STATE_OK if record.succeeded else STATE_FAILED,
            detail=record.summary or "",
            age_seconds=max(0.0, moment - finished),
            record=record,
        )

        if stage.state == STATE_OK:
            upstream = [latest[earlier] for earlier in FLOW_ORDER[:index] if earlier in latest]
            newer = [item for item in upstream if (item.finished_at or item.started_at) > finished]
            if newer:
                stage.state = STATE_STALE
                stage.stale_after = tuple(item.kind for item in newer)
                stage.detail = describe_stale(stage.stale_after)
        status.stages.append(stage)

    return status
