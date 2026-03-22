"""KLayout antenna command generation."""

from __future__ import annotations

from app.runners.base_runner import BaseRunner


class AntennaRunner(BaseRunner):
    """Build klayout batch command for antenna checks."""

    def run_spec(
        self,
        gds_file: str,
        deck_path: str,
        report_path: str,
        top_cell: str = "",
    ) -> list[str]:
        self.ensure_parent(report_path)
        cmd = [
            self.settings.tool_paths.klayout,
            "-b",
            "-r",
            deck_path,
            "-rd",
            f"input={gds_file}",
            "-rd",
            f"report={report_path}",
        ]
        if top_cell:
            cmd += ["-rd", f"topcell={top_cell}"]
        return cmd
