"""Environment and path validation helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.core.settings_manager import AppSettings


class EnvValidator:
    """Validate configured executables and required PDK paths."""

    def validate(self, settings: AppSettings) -> dict[str, tuple[bool, str]]:
        """Return per-item validity and description."""
        out: dict[str, tuple[bool, str]] = {}
        repo_root = Path(__file__).resolve().parents[2]

        for name, value in vars(settings.tool_paths).items():
            resolved = shutil.which(value) if value else None
            if resolved:
                out[f"tool:{name}"] = (True, resolved)
            else:
                path = Path(value)
                if value and path.exists() and path.is_file() and os.access(path, os.X_OK):
                    out[f"tool:{name}"] = (True, str(path))
                elif value and path.exists() and path.is_file():
                    out[f"tool:{name}"] = (False, f"Path exists but is not executable: {value}")
                else:
                    out[f"tool:{name}"] = (False, f"Missing executable: {value}")

        for name, value in vars(settings.pdk_paths).items():
            if not value:
                out[f"pdk:{name}"] = (False, "Not configured")
                continue
            p = Path(value)
            if p.exists():
                out[f"pdk:{name}"] = (True, str(p))
            else:
                out[f"pdk:{name}"] = (False, f"Missing path: {value}")

        venv_python = repo_root / ".venv" / "bin" / "python"
        if venv_python.exists():
            out["python:venv"] = (True, str(venv_python))
            try:
                result = subprocess.run(
                    [
                        str(venv_python),
                        "-c",
                        "import importlib.util as u; mods=['PySide6','pyqtgraph'];"
                        "missing=[m for m in mods if u.find_spec(m) is None];"
                        "print('OK' if not missing else 'MISSING:' + ','.join(missing))",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                status = result.stdout.strip()
                if result.returncode == 0 and status == "OK":
                    out["python:requirements"] = (True, "PySide6, pyqtgraph")
                else:
                    detail = status or result.stderr.strip() or "Missing Python packages"
                    out["python:requirements"] = (False, detail)
            except OSError as exc:
                out["python:requirements"] = (False, f"Failed to validate packages: {exc}")
        else:
            out["python:venv"] = (False, f"Missing venv: {venv_python}")
            out["python:requirements"] = (False, "Create .venv and install requirements.txt")

        return out
