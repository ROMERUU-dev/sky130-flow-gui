"""Desktop integration helpers (launcher/icon)."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


class IntegrationManager:
    """Install a Linux desktop launcher and app icon for current user."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]

    def install_desktop_entry(self) -> tuple[Path, Path, Path]:
        """Create launcher script, icon and .desktop entry for the app."""
        home = Path.home()
        bin_dir = home / ".local" / "bin"
        apps_dir = home / ".local" / "share" / "applications"
        icon_dir = home / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"

        bin_dir.mkdir(parents=True, exist_ok=True)
        apps_dir.mkdir(parents=True, exist_ok=True)
        icon_dir.mkdir(parents=True, exist_ok=True)

        launcher_path = bin_dir / "sky130-flow-gui"
        desktop_path = apps_dir / "sky130-flow-gui.desktop"
        icon_path = icon_dir / "sky130-flow-gui.svg"

        icon_src = self.repo_root / "app" / "resources" / "sky130-flow-gui.svg"
        if icon_src.exists():
            icon_path.write_text(icon_src.read_text())

        launcher_content = (
            "#!/usr/bin/env bash\n"
            f"cd '{self.repo_root}'\n"
            f"exec '{sys.executable}' -m app.main \"$@\"\n"
        )
        launcher_path.write_text(launcher_content)
        launcher_path.chmod(launcher_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        desktop_content = f"""[Desktop Entry]
Type=Application
Name=SKY130 Flow GUI
Comment=Workflow manager for SKY130 analog/custom IC tasks
Exec={launcher_path}
Icon={icon_path}
Terminal=false
Categories=Development;Electronics;Engineering;
StartupNotify=true
"""
        desktop_path.write_text(desktop_content)

        os.system("update-desktop-database ~/.local/share/applications >/dev/null 2>&1")
        return launcher_path, desktop_path, icon_path
