"""Netgen LVS command generation."""

from __future__ import annotations

from pathlib import Path

from app.core.output_manager import OutputPaths
from app.runners.base_runner import BaseRunner


class LvsRunner(BaseRunner):
    """Build netgen LVS command."""

    def run_spec(
        self,
        layout_netlist: str,
        schematic_netlist: str,
        setup_tcl: str,
        outputs: OutputPaths,
    ) -> tuple[list[str], str]:
        layout_stem = Path(layout_netlist).stem or "layout"
        schematic_stem = Path(schematic_netlist).stem or "schematic"
        report_path = str(outputs.lvs / f"lvs_{layout_stem}_vs_{schematic_stem}.log")

        self.ensure_parent(report_path)
        command = [
            self.settings.tool_paths.netgen,
            "-batch",
            "lvs",
            layout_netlist,
            schematic_netlist,
            setup_tcl,
            report_path,
        ]
        return command, report_path
