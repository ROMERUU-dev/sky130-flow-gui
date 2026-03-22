"""Base class for external tool runners."""

from __future__ import annotations

from pathlib import Path

from app.core.command_runner import CommandSpec
from app.core.settings_manager import AppSettings


class BaseRunner:
    """Base helper class for constructing command specs."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    @staticmethod
    def ensure_parent(path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def env(self) -> dict[str, str]:
        pdk = self.settings.pdk_paths
        env: dict[str, str] = {}
        if pdk.pdk_root:
            env["PDK_ROOT"] = pdk.pdk_root
        if pdk.sky130a:
            env["SKY130A"] = pdk.sky130a
        return env

    def build(self, command: list[str], cwd: str | None = None) -> CommandSpec:
        return CommandSpec(command=command, cwd=cwd, env=self.env())
