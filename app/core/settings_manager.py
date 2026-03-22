"""Persistent user settings management."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings


@dataclass
class ToolPaths:
    xschem: str = "xschem"
    ngspice: str = "ngspice"
    magic: str = "magic"
    netgen: str = "netgen"
    klayout: str = "klayout"


@dataclass
class PdkPaths:
    pdk_root: str = ""
    sky130a: str = ""
    magic_rc: str = ""
    netgen_setup: str = ""
    klayout_antenna_deck: str = ""


@dataclass
class AppSettings:
    tool_paths: ToolPaths = field(default_factory=ToolPaths)
    pdk_paths: PdkPaths = field(default_factory=PdkPaths)
    recent_projects: list[str] = field(default_factory=list)
    last_project: str = ""


class SettingsManager:
    """Wrapper around QSettings with typed helpers."""

    def __init__(self) -> None:
        self._settings = QSettings("sky130-flow-gui", "sky130-flow-gui")

    def load(self) -> AppSettings:
        """Load app settings with defaults."""
        tool_paths = ToolPaths(
            xschem=self._settings.value("tools/xschem", "xschem", type=str),
            ngspice=self._settings.value("tools/ngspice", "ngspice", type=str),
            magic=self._settings.value("tools/magic", "magic", type=str),
            netgen=self._settings.value("tools/netgen", "netgen", type=str),
            klayout=self._settings.value("tools/klayout", "klayout", type=str),
        )
        pdk_paths = PdkPaths(
            pdk_root=self._settings.value("pdk/pdk_root", "", type=str),
            sky130a=self._settings.value("pdk/sky130a", "", type=str),
            magic_rc=self._settings.value("pdk/magic_rc", "", type=str),
            netgen_setup=self._settings.value("pdk/netgen_setup", "", type=str),
            klayout_antenna_deck=self._settings.value("pdk/klayout_antenna_deck", "", type=str),
        )
        recent_projects = self._settings.value("projects/recent", [], type=list)
        if isinstance(recent_projects, str):
            recent_projects = [recent_projects]
        return AppSettings(
            tool_paths=tool_paths,
            pdk_paths=pdk_paths,
            recent_projects=list(recent_projects),
            last_project=self._settings.value("projects/last", "", type=str),
        )

    def save(self, app_settings: AppSettings) -> None:
        """Save all settings to disk."""
        self._settings.setValue("tools/xschem", app_settings.tool_paths.xschem)
        self._settings.setValue("tools/ngspice", app_settings.tool_paths.ngspice)
        self._settings.setValue("tools/magic", app_settings.tool_paths.magic)
        self._settings.setValue("tools/netgen", app_settings.tool_paths.netgen)
        self._settings.setValue("tools/klayout", app_settings.tool_paths.klayout)

        self._settings.setValue("pdk/pdk_root", app_settings.pdk_paths.pdk_root)
        self._settings.setValue("pdk/sky130a", app_settings.pdk_paths.sky130a)
        self._settings.setValue("pdk/magic_rc", app_settings.pdk_paths.magic_rc)
        self._settings.setValue("pdk/netgen_setup", app_settings.pdk_paths.netgen_setup)
        self._settings.setValue("pdk/klayout_antenna_deck", app_settings.pdk_paths.klayout_antenna_deck)

        self._settings.setValue("projects/recent", app_settings.recent_projects)
        self._settings.setValue("projects/last", app_settings.last_project)
        self._settings.sync()

    def export_to_dict(self, app_settings: AppSettings) -> dict[str, Any]:
        """Useful for generating environment/config objects."""
        return {
            "tools": vars(app_settings.tool_paths),
            "pdk": vars(app_settings.pdk_paths),
            "projects": {
                "recent": app_settings.recent_projects,
                "last": app_settings.last_project,
            },
        }

    @staticmethod
    def default_results_dir(project_dir: str) -> Path:
        """Return default results path inside project runs."""
        return Path(project_dir).joinpath("runs", "results")

    @staticmethod
    def default_logs_dir(project_dir: str) -> Path:
        """Return default logs path inside project runs."""
        return Path(project_dir).joinpath("runs", "logs")
