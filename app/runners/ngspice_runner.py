"""Ngspice command generation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.core.output_manager import OutputPaths
from app.runners.base_runner import BaseRunner


class NgspiceRunner(BaseRunner):
    """Build ngspice commands for batch simulation."""

    def run_spec(self, netlist: str, outputs: OutputPaths, run_id: str = "") -> tuple[list[str], str, str, str]:
        """Build the ngspice command, writing to per-run files when given an id.

        Every run used to write the same `raw.raw` and `log.txt`, so each one
        overwrote the last and the history could only ever reopen the newest
        result. A run id keeps each set of outputs addressable.
        """
        stem = f"run_{run_id}" if run_id else "raw"
        log_stem = f"run_{run_id}" if run_id else "log"
        log_path = str(outputs.logs / f"{log_stem}.txt")
        raw_out = str(outputs.results / f"{stem}.raw")
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
