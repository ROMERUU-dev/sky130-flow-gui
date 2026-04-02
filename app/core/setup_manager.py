"""Setup assistant helpers for Ubuntu bootstrap and environment detection."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.core.settings_manager import AppSettings


class SetupManager:
    """Detect common installations and provide installer entrypoints."""

    def __init__(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]

    def installer_script(self) -> Path:
        return self.repo_root / "scripts" / "install_vlsi_env_ubuntu.sh"

    def installer_command(self) -> list[str]:
        return ["pkexec", "/bin/bash", str(self.installer_script())]

    def detect_tool_defaults(self) -> dict[str, str]:
        names = {
            "xschem": "xschem",
            "ngspice": "ngspice",
            "magic": "magic",
            "netgen": "netgen",
            "klayout": "klayout",
        }
        detected: dict[str, str] = {}
        for key, command in names.items():
            resolved = shutil.which(command)
            if resolved:
                detected[key] = resolved
        return detected

    def detect_pdk_defaults(self) -> dict[str, str]:
        env_pdk_root = os.environ.get("PDK_ROOT", "").strip()
        env_sky130a = os.environ.get("SKY130A", "").strip()
        candidates = [
            Path(env_pdk_root) if env_pdk_root else None,
            Path(env_sky130a).parent if env_sky130a else None,
            Path("/usr/share/pdk"),
            Path("/usr/local/share/pdk"),
            Path.home() / "pdk",
            Path.home() / ".volare",
        ]
        detected: dict[str, str] = {}

        if env_sky130a and Path(env_sky130a).exists():
            return self._build_pdk_mapping(Path(env_sky130a))

        for root in candidates:
            if root is None or not root.exists():
                continue
            sky130a = self._find_sky130a(root)
            if sky130a is None:
                continue
            detected.update(self._build_pdk_mapping(sky130a))
            break

        return detected

    def apply_detected_defaults(self, settings: AppSettings) -> bool:
        changed = False

        for key, value in self.detect_tool_defaults().items():
            current = getattr(settings.tool_paths, key)
            if not current or shutil.which(current) is None:
                setattr(settings.tool_paths, key, value)
                changed = True

        for key, value in self.detect_pdk_defaults().items():
            current = getattr(settings.pdk_paths, key)
            if not current or not Path(current).exists():
                setattr(settings.pdk_paths, key, value)
                changed = True

        return changed

    def summarize_detection(self, settings: AppSettings) -> list[str]:
        lines: list[str] = []
        tool_defaults = self.detect_tool_defaults()
        pdk_defaults = self.detect_pdk_defaults()
        python_defaults = self.detect_python_environment()

        if tool_defaults:
            lines.append("Detected tools:")
            lines.extend(f"- {name}: {path}" for name, path in tool_defaults.items())
        if pdk_defaults:
            lines.append("Detected PDK paths:")
            lines.extend(f"- {name}: {path}" for name, path in pdk_defaults.items())
        if python_defaults:
            lines.append("Detected Python environment:")
            lines.extend(f"- {name}: {path}" for name, path in python_defaults.items())
        if not lines:
            lines.append("No common Ubuntu VLSI installation was detected automatically.")
        return lines

    def detect_python_environment(self) -> dict[str, str]:
        detected: dict[str, str] = {}
        venv_python = self.repo_root / ".venv" / "bin" / "python"
        requirements = self.repo_root / "requirements.txt"
        if venv_python.exists():
            detected["venv"] = str(venv_python)
        if requirements.exists():
            detected["requirements"] = str(requirements)
        return detected

    @staticmethod
    def _find_sky130a(root: Path) -> Path | None:
        direct = root / "sky130A"
        if direct.exists():
            return direct

        for match in sorted(root.glob("**/sky130A")):
            if match.is_dir():
                return match
        return None

    @staticmethod
    def _build_pdk_mapping(sky130a: Path) -> dict[str, str]:
        detected = {
            "sky130a": str(sky130a),
            "pdk_root": str(sky130a.parent),
        }
        magic_rc = sky130a / "libs.tech" / "magic" / "sky130A.magicrc"
        netgen_setup = sky130a / "libs.tech" / "netgen" / "sky130A_setup.tcl"
        antenna_deck = sky130a / "libs.tech" / "klayout" / "drc" / "sky130A_ant.rb"
        if magic_rc.exists():
            detected["magic_rc"] = str(magic_rc)
        if netgen_setup.exists():
            detected["netgen_setup"] = str(netgen_setup)
        if antenna_deck.exists():
            detected["klayout_antenna_deck"] = str(antenna_deck)
        return detected
