"""Helpers for launching interactive magic with a consistent SKY130 PDK context."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.env_validator import EnvValidator
from app.core.settings_manager import AppSettings


@dataclass(frozen=True)
class MagicLaunchSpec:
    """Complete subprocess configuration for launching magic interactively."""

    command: list[str]
    cwd: str | None
    env: dict[str, str]


class MagicLaunchBuilder:
    """Construct a robust interactive magic launch context from app settings."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.validator = EnvValidator()

    def build(self, target_path: str | None = None) -> MagicLaunchSpec:
        env = os.environ.copy()
        command = [self.settings.tool_paths.magic]
        cwd: str | None = None
        magic_rc: Path | None = None
        magic_dir: Path | None = None

        sky130a = self.validator._find_sky130a(self.settings)
        if sky130a is not None:
            env["PDK_ROOT"] = str(sky130a.parent)
            env["SKY130A"] = str(sky130a)
            env.setdefault("MAGTYPE", "mag")
            magic_dir = sky130a / "libs.tech" / "magic"
            derived_rc = magic_dir / "sky130A.magicrc"
            if derived_rc.is_file():
                magic_rc = derived_rc

        configured_rc = Path(self.settings.pdk_paths.magic_rc).expanduser() if self.settings.pdk_paths.magic_rc else None
        if configured_rc and configured_rc.is_file():
            magic_rc = configured_rc
        if magic_rc and magic_rc.is_file():
            command.extend(["-rcfile", str(magic_rc.resolve())])

        if target_path:
            target = Path(target_path).expanduser().resolve()
            if target.is_dir():
                cwd = str(target)
            elif target.is_file() and target.suffix == ".mag":
                cwd = str(target.parent)
                command.append(target.stem)
            else:
                cwd = str(target.parent)
                command.append(str(target))
        elif magic_dir and magic_dir.is_dir():
            cwd = str(magic_dir)

        return MagicLaunchSpec(command=command, cwd=cwd, env=env)
