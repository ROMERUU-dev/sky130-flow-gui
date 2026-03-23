"""Ngspice command generation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.core.output_manager import OutputPaths
from app.runners.base_runner import BaseRunner


class NgspiceRunner(BaseRunner):
    """Build ngspice commands for batch simulation."""

    def run_spec(self, netlist: str, outputs: OutputPaths) -> tuple[list[str], str, str, str]:
        netlist_stem = Path(netlist).stem or "simulation"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = str(outputs.logs / f"{netlist_stem}_{timestamp}_ngspice.log")
        raw_out = str(outputs.results / f"{netlist_stem}_{timestamp}.raw")
        run_cwd = str(outputs.results)

        self.ensure_parent(log_path)
        self.ensure_parent(raw_out)

        command = [
            self.settings.tool_paths.ngspice,
            "-b",
            "-o",
            log_path,
            "-r",
            raw_out,
            str(Path(netlist)),
        ]
        return command, log_path, raw_out, run_cwd
