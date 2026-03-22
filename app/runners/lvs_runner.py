"""Netgen LVS command generation."""

from __future__ import annotations

from app.runners.base_runner import BaseRunner


class LvsRunner(BaseRunner):
    """Build netgen LVS command."""

    def run_spec(
        self,
        layout_netlist: str,
        schematic_netlist: str,
        setup_tcl: str,
        report_path: str,
    ) -> list[str]:
        self.ensure_parent(report_path)
        return [
            self.settings.tool_paths.netgen,
            "-batch",
            "lvs",
            layout_netlist,
            schematic_netlist,
            setup_tcl,
            report_path,
        ]
