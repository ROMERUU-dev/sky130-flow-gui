"""Magic extraction command generation."""

from __future__ import annotations

from pathlib import Path

from app.runners.base_runner import BaseRunner


class MagicRunner(BaseRunner):
    """Build magic batch extraction command and script."""

    def create_extraction_script(self, script_path: str, top_cell: str, output_netlist: str) -> None:
        self.ensure_parent(script_path)
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
        Path(script_path).write_text(content)

    def run_spec(self, script_path: str, rcfile: str | None = None, cwd: str | None = None) -> list[str]:
        cmd = [self.settings.tool_paths.magic, "-dnull", "-noconsole"]
        if rcfile:
            cmd.extend(["-rcfile", rcfile])
        cmd.extend(["-T", script_path])
        return cmd
