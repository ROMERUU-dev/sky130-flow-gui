"""Magic extraction command generation."""

from __future__ import annotations

from pathlib import Path

from app.core.output_manager import OutputPaths
from app.runners.base_runner import BaseRunner


class MagicRunner(BaseRunner):
    """Build magic batch extraction command and script."""

    def create_extraction_script(self, outputs: OutputPaths, top_cell: str, output_netlist: str) -> str:
        script_path = outputs.extraction / f"extract_{top_cell}.tcl"
        self.ensure_parent(str(script_path))
        content = f"""
crashbackups stop
if {{[catch {{load {top_cell}}} msg]}} {{
    puts stderr $msg
    exit 1
}}
extract all
ext2spice lvs
ext2spice -o {output_netlist}
quit -noprompt
""".strip()
        script_path.write_text(content)
        return str(script_path)

    def run_spec(
        self,
        outputs: OutputPaths,
        top_cell: str,
        script_path: str | None = None,
        rcfile: str | None = None,
    ) -> tuple[list[str], str, str]:
        out_netlist = str(outputs.extraction / f"{top_cell}_extracted.spice")
        self.ensure_parent(out_netlist)

        script = script_path or self.create_extraction_script(outputs, top_cell, out_netlist)
        cmd = [self.settings.tool_paths.magic, "-dnull", "-noconsole"]
        if rcfile:
            cmd.extend(["-rcfile", rcfile])
        cmd.extend(["-T", script])
        return cmd, script, out_netlist
