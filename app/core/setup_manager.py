"""Setup assistant helpers for Ubuntu bootstrap and environment detection."""

from __future__ import annotations

from pathlib import Path

from app.core.env_validator import EnvValidator
from app.core.settings_manager import AppSettings


class SetupManager:
    """Detect common installations and provide installer entrypoints."""

    def __init__(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.validator = EnvValidator()

    def installer_script(self) -> Path:
        return self.repo_root / "scripts" / "install_vlsi_env_ubuntu.sh"

    def installer_command(self) -> list[str]:
        return ["pkexec", "/bin/bash", str(self.installer_script())]

    def detect_tool_defaults(self) -> dict[str, str]:
        detected: dict[str, str] = {}
        diagnosis = self.validator.diagnose(AppSettings())
        for key, tool in diagnosis.tools.items():
            if tool.status in {"ok", "alias"} and tool.resolved_path:
                detected[key] = tool.resolved_path
        return detected

    def detect_pdk_defaults(self) -> dict[str, str]:
        detected: dict[str, str] = {}
        pdk = self.validator.diagnose(AppSettings()).pdk
        if pdk.found and pdk.sky130a_path:
            detected.update(self._build_pdk_mapping(Path(pdk.sky130a_path)))
        return detected

    def apply_detected_defaults(self, settings: AppSettings) -> bool:
        changed = False

        for key, value in self.detect_tool_defaults().items():
            current = getattr(settings.tool_paths, key)
            if not current or self.validator._resolve_command(current) is None:
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
        diagnosis = self.validator.diagnose(settings)
        python_defaults = self.detect_python_environment()

        if diagnosis.tools:
            lines.append("Detected tools:")
            for name, tool in diagnosis.tools.items():
                if tool.status in {"ok", "alias"}:
                    suffix = f" (alias: {tool.found_binary})" if tool.status == "alias" else ""
                    lines.append(f"- {name}: {tool.resolved_path}{suffix}")
                else:
                    lines.append(f"- {name}: missing")
        lines.append("Detected PDK paths:")
        if diagnosis.pdk.found:
            pdk_defaults = self.detect_pdk_defaults()
            lines.extend(f"- {name}: {path}" for name, path in pdk_defaults.items())
            if diagnosis.pdk.status == "incomplete":
                lines.append(f"- sky130A status: incomplete ({', '.join(diagnosis.pdk.missing_subdirs)})")
        else:
            lines.append("- sky130A: missing")
        lines.append("Detected Python environment:")
        if python_defaults:
            lines.extend(f"- {name}: {path}" for name, path in python_defaults.items())
        if diagnosis.python_env.problems:
            lines.extend(f"- warning: {problem}" for problem in diagnosis.python_env.problems)
        if not lines:
            lines.append("No common Ubuntu VLSI installation was detected automatically.")
        return lines

    def detect_python_environment(self) -> dict[str, str]:
        detected: dict[str, str] = {}
        diagnosis = self.validator.diagnose(AppSettings()).python_env
        venv_python = Path(diagnosis.python_bin)
        requirements = self.repo_root / "requirements.txt"
        if venv_python.exists():
            detected["venv"] = str(venv_python)
        if requirements.exists():
            detected["requirements"] = str(requirements)
        return detected

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
