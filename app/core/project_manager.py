"""Project discovery and quick file indexing."""

from __future__ import annotations

from pathlib import Path

COMMON_PATTERNS = {
    "schematics": ["*.sch"],
    "spice": ["*.spice", "*.sp", "*.cir"],
    "layout": ["*.mag", "*.gds", "*.gdsii"],
    "scripts": ["*.tcl"],
    "reports": ["*.rpt", "*.report", "*.log"],
}


class ProjectManager:
    """Handles project folder indexing and helper locations."""

    def __init__(self) -> None:
        self.current_project: Path | None = None

    def set_project(self, path: str) -> None:
        self.current_project = Path(path)

    def ensure_structure(self) -> None:
        """Create default results/log folders for the project."""
        if not self.current_project:
            return
        self.current_project.joinpath("results").mkdir(parents=True, exist_ok=True)
        self.current_project.joinpath("logs").mkdir(parents=True, exist_ok=True)

    def find_common_files(self) -> dict[str, list[Path]]:
        """Scan for common SKY130 flow files."""
        if not self.current_project or not self.current_project.exists():
            return {key: [] for key in COMMON_PATTERNS}

        found: dict[str, list[Path]] = {key: [] for key in COMMON_PATTERNS}
        for category, patterns in COMMON_PATTERNS.items():
            for pattern in patterns:
                found[category].extend(self.current_project.rglob(pattern))
            found[category] = sorted(found[category])[:200]
        return found
