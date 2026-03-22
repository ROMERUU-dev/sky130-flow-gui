"""Ngspice command generation."""

from __future__ import annotations

from pathlib import Path

from app.runners.base_runner import BaseRunner


class NgspiceRunner(BaseRunner):
    """Build ngspice commands for batch simulation."""

    def run_spec(self, netlist: str, log_path: str, raw_out: str | None = None) -> list[str]:
        self.ensure_parent(log_path)
        command = [self.settings.tool_paths.ngspice, "-b", "-o", log_path]
        if raw_out:
            self.ensure_parent(raw_out)
            command += ["-r", raw_out]
        command += [str(Path(netlist))]
        return command
