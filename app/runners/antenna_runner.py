"""Antenna check command generation for KLayout decks and for Magic."""

from __future__ import annotations

from pathlib import Path

from app.core.antenna_tools import build_magic_antenna_script
from app.core.output_manager import OutputPaths
from app.runners.base_runner import BaseRunner


class AntennaRunner(BaseRunner):
    """Build klayout batch command for antenna checks."""

    def run_spec(
        self,
        gds_file: str,
        deck_path: str,
        outputs: OutputPaths,
        top_cell: str = "",
    ) -> tuple[list[str], str]:
        gds_stem = Path(gds_file).stem or "layout"
        report_path = str(outputs.antenna / f"antenna_{gds_stem}.txt")

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
        return cmd, report_path

    def magic_run_spec(
        self,
        layout_file: str,
        outputs: OutputPaths,
        top_cell: str = "",
        magic_rc: str = "",
    ) -> tuple[list[str], str]:
        """Drive Magic's built-in `antennacheck`.

        sky130A carries its antenna rules in the Magic techfile and ships no
        KLayout antenna deck, so this is the route that actually works there.
        """
        layout_path = Path(layout_file)
        stem = layout_path.stem or "layout"
        report_path = str(outputs.antenna / f"antenna_{stem}.txt")
        script_path = str(outputs.antenna / f"antenna_{stem}.tcl")

        self.ensure_parent(report_path)
        Path(script_path).write_text(
            build_magic_antenna_script(layout_path, report_path, top_cell),
            encoding="utf-8",
        )

        cmd = [self.settings.tool_paths.magic, "-dnull", "-noconsole"]
        rcfile = magic_rc or self.settings.pdk_paths.magic_rc
        if rcfile:
            cmd += ["-rcfile", rcfile]
        cmd.append(script_path)
        return cmd, report_path
