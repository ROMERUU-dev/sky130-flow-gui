"""Self-update helpers for git-based installations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class UpdateCommands:
    fetch: list[str]
    status: list[str]
    pull: list[str]


class UpdateManager:
    """Provide git commands to check/apply updates."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]

    def commands(self) -> UpdateCommands:
        repo = str(self.repo_root)
        return UpdateCommands(
            fetch=["git", "-C", repo, "fetch", "--all", "--prune"],
            status=["git", "-C", repo, "status", "-uno"],
            pull=["git", "-C", repo, "pull", "--ff-only"],
        )

    def parse_update_status(self, text: str) -> str:
        """Parse git status output into user-facing message."""
        lowered = text.lower()
        if "behind" in lowered or "can be fast-forwarded" in lowered:
            return "Hay actualizaciones disponibles."
        if "up to date" in lowered or "up-to-date" in lowered:
            return "Ya tienes la versión más reciente."
        return "Estado de actualización no concluyente. Revisa el log."
