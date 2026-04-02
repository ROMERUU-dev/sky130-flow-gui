"""Magic extraction command generation."""

from __future__ import annotations

from pathlib import Path

from app.core.output_manager import OutputPaths
from app.runners.base_runner import BaseRunner


class MagicRunner(BaseRunner):
    """Build magic batch extraction command and script."""

    @staticmethod
    def _tcl_brace(value: str) -> str:
        return "{" + value.replace("}", "\\}") + "}"

    def create_extraction_script(self, outputs: OutputPaths, top_cell: str, output_netlist: str) -> str:
        script_path = outputs.extraction / f"extract_{top_cell}.tcl"
        self.ensure_parent(str(script_path))
        quoted_top = self._tcl_brace(top_cell)
        quoted_output = self._tcl_brace(output_netlist)
        content = f"""
crashbackups stop
if {{[catch {{load {quoted_top}}} msg]}} {{
    puts stderr $msg
    exit 1
}}
extract all
ext2spice lvs
ext2spice -o {quoted_output}
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
        cmd.append(script)
        return cmd, script, out_netlist
