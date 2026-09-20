"""Update checks for both packaged and git-based installations.

Earlier versions only knew how to run `git fetch` against the application
directory. A `.deb` install is not a git checkout, so on a packaged system the
update check always failed with "not a git repository". Packaged installs now
ask the GitHub releases API instead and compare against the shipped VERSION.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

RELEASES_API = "https://api.github.com/repos/ROMERUU-dev/sky130-flow-gui/releases/latest"
RELEASES_PAGE = "https://github.com/ROMERUU-dev/sky130-flow-gui/releases"
REQUEST_TIMEOUT_SECONDS = 10


@dataclass
class UpdateCommands:
    fetch: list[str]
    status: list[str]
    pull: list[str]


@dataclass
class UpdateCheck:
    """Outcome of an update check, in terms the UI can show directly."""

    mode: str = "release"
    status: str = "unknown"
    installed: str = ""
    latest: str = ""
    message: str = ""
    download_url: str = ""
    release_url: str = RELEASES_PAGE
    assets: list[str] = field(default_factory=list)

    @property
    def update_available(self) -> bool:
        return self.status == "update_available"


def parse_version(text: str) -> tuple:
    """Turn a version string into a comparable tuple.

    Pre-releases sort below the matching final version, so `0.3.0-beta.2` is
    older than `0.3.0`.
    """
    cleaned = (text or "").strip().lstrip("vV")
    if not cleaned:
        return ()
    core, _, suffix = cleaned.partition("-")
    numbers = tuple(int(part) for part in re.findall(r"\d+", core))
    if not numbers:
        return ()
    # A missing suffix must outrank any suffix, hence the sentinel.
    if not suffix:
        return numbers + (1,)
    suffix_numbers = tuple(int(part) for part in re.findall(r"\d+", suffix))
    return numbers + (0,) + suffix_numbers


class UpdateManager:
    """Check for newer releases, or drive git for source checkouts."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]

    # ---------------------------------------------------------------- mode

    def is_git_checkout(self) -> bool:
        """True when the app runs from a clone that git can update in place."""
        return (self.repo_root / ".git").exists()

    def installed_version(self) -> str:
        version_file = self.repo_root / "VERSION"
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    # ------------------------------------------------------------- release

    def check(self, opener=None) -> UpdateCheck:
        """Ask GitHub for the latest release and compare it with this build."""
        installed = self.installed_version()
        result = UpdateCheck(installed=installed)

        try:
            payload = self._fetch_latest(opener)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            result.status = "unreachable"
            result.message = f"No se pudo consultar GitHub: {exc}"
            return result
        except (ValueError, TypeError) as exc:
            result.status = "unreadable"
            result.message = f"Respuesta inesperada de GitHub: {exc}"
            return result

        latest = str(payload.get("tag_name", "")).strip()
        result.latest = latest
        result.release_url = str(payload.get("html_url") or RELEASES_PAGE)
        assets = payload.get("assets") or []
        result.assets = [str(asset.get("name", "")) for asset in assets if asset.get("name")]
        for asset in assets:
            name = str(asset.get("name", ""))
            if name.endswith(".deb"):
                result.download_url = str(asset.get("browser_download_url", ""))
                break

        if not latest:
            result.status = "unreadable"
            result.message = "GitHub no devolvió una etiqueta de versión."
            return result
        if not installed:
            result.status = "unknown"
            result.message = f"Última versión publicada: {latest}. No se pudo leer la versión instalada."
            return result

        current_tuple = parse_version(installed)
        latest_tuple = parse_version(latest)
        if not current_tuple or not latest_tuple:
            result.status = "unknown"
            result.message = f"Instalada {installed}, publicada {latest}. No se pudieron comparar."
        elif latest_tuple > current_tuple:
            result.status = "update_available"
            result.message = f"Hay una versión más reciente: {latest} (tienes {installed})."
        elif latest_tuple < current_tuple:
            result.status = "ahead"
            result.message = f"Tu versión {installed} es más nueva que la publicada ({latest})."
        else:
            result.status = "up_to_date"
            result.message = f"Ya tienes la versión más reciente ({installed})."
        return result

    @staticmethod
    def _fetch_latest(opener=None) -> dict:
        request = urllib.request.Request(
            RELEASES_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "sky130-flow-gui",
            },
        )
        open_url = opener or urllib.request.urlopen
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))

    # ----------------------------------------------------------------- git

    def commands(self) -> UpdateCommands:
        repo = str(self.repo_root)
        return UpdateCommands(
            fetch=["git", "-C", repo, "fetch", "--all", "--prune"],
            status=["git", "-C", repo, "status", "-uno"],
            pull=["git", "-C", repo, "pull", "--ff-only"],
        )

    def parse_update_status(self, text: str) -> str:
        """Parse git status output into a user-facing message."""
        lowered = text.lower()
        if "behind" in lowered or "can be fast-forwarded" in lowered:
            return "Hay actualizaciones disponibles."
        if "up to date" in lowered or "up-to-date" in lowered:
            return "Ya tienes la versión más reciente."
        return "Estado de actualización no concluyente. Revisa el log."
