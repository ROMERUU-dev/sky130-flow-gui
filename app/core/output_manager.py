"""Centralized output path management for project and fallback workspace runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutputPaths:
    """Resolved run output folders for a single run context."""

    base: Path
    runs: Path
    logs: Path
    results: Path
    lvs: Path
    extraction: Path
    antenna: Path


class OutputManager:
    """Build and create standardized output directories.

    If an active project exists, outputs are created under:
      <project>/runs/{logs,results,lvs,extraction,antenna}

    Otherwise, outputs fall back to:
      <repo>/workspace/{logs,results,lvs,extraction,antenna}
    """

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]

    def resolve(self, project_dir: str | None) -> OutputPaths:
        """Return and create all output directories for the current context."""
        base = Path(project_dir).resolve() if project_dir else self.repo_root.joinpath("workspace")

        if project_dir:
            runs = base / "runs"
        else:
            runs = base

        paths = OutputPaths(
            base=base,
            runs=runs,
            logs=runs / "logs",
            results=runs / "results",
            lvs=runs / "lvs",
            extraction=runs / "extraction",
            antenna=runs / "antenna",
        )
        self._ensure(paths)
        return paths

    @staticmethod
    def _ensure(paths: OutputPaths) -> None:
        for folder in [paths.runs, paths.logs, paths.results, paths.lvs, paths.extraction, paths.antenna]:
            folder.mkdir(parents=True, exist_ok=True)
