"""Environment and path validation helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.core.settings_manager import AppSettings


class EnvValidator:
    """Validate configured executables and required PDK paths."""

    def validate(self, settings: AppSettings) -> dict[str, tuple[bool, str]]:
        """Return per-item validity and description."""
        out: dict[str, tuple[bool, str]] = {}

        for name, value in vars(settings.tool_paths).items():
            resolved = shutil.which(value) if value else None
            if resolved:
                out[f"tool:{name}"] = (True, resolved)
            else:
                path = Path(value)
                if value and path.exists() and path.is_file():
                    out[f"tool:{name}"] = (True, str(path))
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

        return out
