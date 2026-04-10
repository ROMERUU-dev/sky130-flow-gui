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

    def build(self, project_path: str | None = None) -> XschemLaunchSpec:
        sky130a = self.validator._find_sky130a(self.settings)
        env = os.environ.copy()
        command = [self.settings.tool_paths.xschem]
        cwd: str | None = None

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
