"""Helpers for launching xschem with a consistent SKY130 PDK context."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.env_validator import EnvValidator
from app.core.settings_manager import AppSettings


@dataclass(frozen=True)
class XschemLaunchSpec:
    """Complete subprocess configuration for launching xschem."""

    command: list[str]
    cwd: str | None
    env: dict[str, str]


class XschemLaunchBuilder:
    """Construct a robust xschem launch context from app settings and environment."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.validator = EnvValidator()

    def build(
        self,
        project_path: str | None = None,
        screen_size: tuple[int, int] | None = None,
    ) -> XschemLaunchSpec:
        sky130a = self.validator._find_sky130a(self.settings)
        env = os.environ.copy()
        command = [self.settings.tool_paths.xschem]
        cwd: str | None = None

        geometry = self.initial_geometry(screen_size)
        if geometry:
            # --tcl runs after xschemrc is sourced, so this overrides the
            # fixed `initial_geometry` the SKY130 xschemrc sets. That value is
            # in physical pixels, and xschem runs unscaled under XWayland, so
            # on a HiDPI screen the window came up at about a quarter area.
            command.extend(["--tcl", f"set initial_geometry {{{geometry}}}"])

        if sky130a is not None:
            pdk_root = sky130a.parent
            xschem_dir = sky130a / "libs.tech" / "xschem"
            xschemrc = xschem_dir / "xschemrc"
            models_dir = sky130a / "libs.tech" / "combined"
            stdcells_dir = sky130a / "libs.ref" / "sky130_fd_sc_hd" / "spice"

            env["PDK_ROOT"] = str(pdk_root)
            env["SKY130A"] = str(sky130a)
            if models_dir.is_dir():
                env["SKYWATER_MODELS"] = str(models_dir)
            if stdcells_dir.is_dir():
                env["SKYWATER_STDCELLS"] = str(stdcells_dir)
            if xschemrc.is_file():
                command.extend(["--rcfile", str(xschemrc)])
            if xschem_dir.is_dir():
                cwd = str(xschem_dir)

        if project_path:
            project = Path(project_path).expanduser().resolve()
            if project.is_dir():
                cwd = str(project)
            else:
                if project.parent.is_dir():
                    cwd = str(project.parent)
                command.append(str(project))

        return XschemLaunchSpec(command=command, cwd=cwd, env=env)

    @staticmethod
    def initial_geometry(screen_size: tuple[int, int] | None) -> str:
        """Build an xschem geometry string covering most of the screen."""
        if not screen_size:
            return ""
        width, height = screen_size
        if width < 640 or height < 480:
            return ""
        target_width = max(1024, int(width * 0.82))
        target_height = max(700, int(height * 0.82))
        offset_x = max(0, (width - target_width) // 2)
        offset_y = max(0, (height - target_height) // 2)
        return f"{target_width}x{target_height}+{offset_x}+{offset_y}"
