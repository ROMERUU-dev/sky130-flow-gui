"""User-owned Python environment management for SKY130 Flow GUI."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import pwd
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

REQUIRED_IMPORTS = ("PySide6", "pyqtgraph")

# Every subprocess probe costs 40-80 ms, and the setup assistant re-runs the
# diagnosis on each refresh, so the interpreter is asked everything at once.
SYSTEM_PROBE = (
    "import platform, sys;"
    "print('Python ' + sys.version.split()[0]);"
    "print(platform.machine())"
)

VENV_PROBE = (
    "import json, sys, traceback\n"
    "report = {'prefix': sys.prefix, 'version': sys.version.split()[0], 'pip': '', 'packages': {}, 'error': ''}\n"
    "try:\n"
    "    import pip\n"
    "    report['pip'] = getattr(pip, '__version__', 'unknown')\n"
    "except Exception:\n"
    "    pass\n"
    "try:\n"
    "    import importlib, importlib.metadata\n"
    "    for name in " + repr(list(REQUIRED_IMPORTS)) + ":\n"
    "        importlib.import_module(name)\n"
    "        report['packages'][name] = importlib.metadata.version(name)\n"
    "except Exception:\n"
    "    report['error'] = traceback.format_exc()\n"
    "print(json.dumps(report))"
)


def user_data_home(environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    env = os.environ if environ is None else environ
    configured = env.get("XDG_DATA_HOME", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise ValueError("XDG_DATA_HOME must be an absolute path")
        return path
    return (home or Path.home()) / ".local" / "share"


def venv_path(environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    return user_data_home(environ, home) / "sky130-flow-gui" / "venv"


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class PythonEnvironmentStatus:
    status: str
    system_python: str = ""
    system_version: str = ""
    architecture: str = ""
    venv_path: str = ""
    python_bin: str = ""
    venv_exists: bool = False
    venv_owner: str = ""
    venv_writable: bool = False
    pip_available: bool = False
    requirements_exists: bool = False
    packages: dict[str, str] = field(default_factory=dict)
    missing_packages: list[str] = field(default_factory=list)
    import_error: str = ""
    legacy_path: str = ""
    legacy_owner: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == "ready"


class PythonEnvironmentManager:
    def __init__(self, app_root: Path | None = None, *, environ: Mapping[str, str] | None = None,
                 home: Path | None = None, system_python: str | None = None) -> None:
        self.app_root = (app_root or Path(__file__).resolve().parents[2]).resolve()
        self.environ = dict(os.environ if environ is None else environ)
        self.home = home or Path.home()
        self.path = venv_path(self.environ, self.home)
        self.requirements = self.app_root / "requirements.txt"
        self.legacy_path = self.app_root / ".venv"
        self.system_python = system_python or shutil.which("python3", path=self.environ.get("PATH")) or ""

    @staticmethod
    def _owner(path: Path) -> str:
        try:
            uid = path.stat().st_uid
            return pwd.getpwuid(uid).pw_name
        except (KeyError, OSError):
            return "unknown"

    @staticmethod
    def _run(command: Sequence[str]) -> CommandResult:
        cmd = [str(item) for item in command]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            return CommandResult(cmd, result.returncode, result.stdout, result.stderr)
        except OSError as exc:
            return CommandResult(cmd, 127, "", str(exc))

    def diagnose(self) -> PythonEnvironmentStatus:
        status = PythonEnvironmentStatus(
            status="venv_missing", system_python=self.system_python,
            venv_path=str(self.path), python_bin=str(self.path / "bin" / "python"),
            requirements_exists=self.requirements.is_file(),
        )
        if self.legacy_path.exists():
            status.legacy_path = str(self.legacy_path)
            status.legacy_owner = self._owner(self.legacy_path)

        if not self.system_python:
            status.status = "python_missing"
            status.problems.append("python3 is not available in PATH")
            return status

        system = self._run([self.system_python, "-c", SYSTEM_PROBE])
        system_lines = system.stdout.splitlines()
        status.system_version = system_lines[0].strip() if system_lines else ""
        status.architecture = system_lines[1].strip() if len(system_lines) > 1 else ""

        if not self.path.exists():
            capability = self.check_venv_capability()
            if capability.returncode:
                status.status = "venv_module_missing"
                status.problems.append(
                    "Python cannot create virtual environments; install the Ubuntu package python3-venv. "
                    + (capability.stderr or capability.stdout).strip()
                )
                return status
            status.problems.append(f"User virtual environment does not exist at {self.path}")
            return status

        status.venv_exists = True
        status.venv_owner = self._owner(self.path)
        status.venv_writable = os.access(self.path, os.W_OK)
        if self.path.stat().st_uid != os.geteuid() or not status.venv_writable:
            status.status = "permission_error"
            status.problems.append(
                f"Virtual environment is not owned and writable by the current user ({status.venv_owner})"
            )
            return status

        python = self.path / "bin" / "python"
        if not python.is_file():
            status.status = "venv_corrupt"
            status.problems.append(f"Virtual environment Python is missing: {python}")
            return status

        probe = self._run([str(python), "-c", VENV_PROBE])
        if probe.returncode:
            status.status = "venv_corrupt"
            status.problems.append(
                (probe.stderr or "Virtual environment interpreter could not be queried").strip()
            )
            return status
        try:
            report = json.loads(probe.stdout)
        except (ValueError, TypeError):
            status.status = "venv_corrupt"
            status.problems.append("Virtual environment interpreter returned an unreadable report")
            return status
        if Path(report.get("prefix", "")).resolve() != self.path.resolve():
            status.status = "venv_corrupt"
            status.problems.append("Virtual environment interpreter has an invalid prefix")
            return status

        status.pip_available = bool(report.get("pip"))
        if not status.pip_available:
            status.status = "pip_missing"
            status.problems.append("pip is unavailable inside the virtual environment")
            return status
        if not status.requirements_exists:
            status.status = "requirements_missing"
            status.problems.append(f"Requirements file is missing: {self.requirements}")
            return status

        error = str(report.get("error", "")).strip()
        if error:
            status.import_error = error
            missing = [name for name in REQUIRED_IMPORTS if f"No module named '{name}'" in error]
            status.missing_packages = missing
            status.status = "packages_missing" if missing else "import_error"
            status.problems.append(error)
            return status

        status.packages = dict(report.get("packages", {}))
        status.status = "ready"
        return status

    def check_venv_capability(self) -> CommandResult:
        if not self.system_python:
            return CommandResult([], 127, "", "python3 is not available in PATH")
        return self._run([self.system_python, "-c", "import venv, ensurepip"])

    def repair(self) -> list[CommandResult]:
        if os.geteuid() == 0:
            raise PermissionError("Refusing to create a user environment as root. Start SKY130 Flow GUI as the desktop user.")
        if not self.requirements.is_file():
            raise FileNotFoundError(f"Requirements file is missing: {self.requirements}")
        capability = self.check_venv_capability()
        results = [capability]
        if capability.returncode:
            raise RuntimeError("Python cannot create virtual environments. Install the Ubuntu package python3-venv.\n" + capability.stderr)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.diagnose().status in {"venv_corrupt", "pip_missing"}:
            backup = self.path.with_name(f"venv.backup-{time.strftime('%Y%m%d-%H%M%S')}")
            self.path.rename(backup)
        if not self.path.exists():
            result = self._run([self.system_python, "-m", "venv", str(self.path)])
            results.append(result)
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout)
        python = self.path / "bin" / "python"
        for command in ([str(python), "-m", "pip", "install", "--upgrade", "pip"],
                        [str(python), "-m", "pip", "install", "-r", str(self.requirements)]):
            result = self._run(command)
            results.append(result)
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout)
        final = self.diagnose()
        if not final.ready:
            raise RuntimeError("Dependency validation failed: " + "\n".join(final.problems))
        return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("diagnose", "repair"))
    parser.add_argument("--app-root", type=Path)
    args = parser.parse_args(argv)
    manager = PythonEnvironmentManager(args.app_root)
    if args.action == "diagnose":
        print(json.dumps(asdict(manager.diagnose()), indent=2))
        return 0
    try:
        for result in manager.repair():
            print("$ " + " ".join(result.command))
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="")
            print(f"[exit={result.returncode}]")
        return 0
    except Exception as exc:
        print(f"Python environment repair failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
