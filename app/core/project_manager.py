"""Project discovery and quick file indexing."""

from __future__ import annotations

from pathlib import Path

from app.core.output_manager import OutputManager, OutputPaths

COMMON_PATTERNS = {
    "schematics": ["*.sch"],
    "spice": ["*.spice", "*.sp", "*.cir"],
    "layout": ["*.mag", "*.gds", "*.gdsii"],
    "scripts": ["*.tcl"],
    "reports": ["*.rpt", "*.report", "*.log"],
}


class ProjectManager:
    """Handles project folder indexing and helper locations."""

    def __init__(self, output_manager: OutputManager | None = None) -> None:
        self.current_project: Path | None = None
        self.output_manager = output_manager or OutputManager()

    def set_project(self, path: str) -> None:
        self.current_project = Path(path)

    def outputs(self) -> OutputPaths:
        """Return standardized outputs for current context."""
        project_dir = str(self.current_project) if self.current_project else None
        return self.output_manager.resolve(project_dir)

    def ensure_structure(self) -> None:
        """Create default output folders for project/workspace context."""
        self.outputs()

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
