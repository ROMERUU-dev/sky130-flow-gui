"""Environment and path validation helpers."""

from __future__ import annotations

import ctypes.util
import os
import pwd
import re
import shutil
import subprocess
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from app.core.antenna_tools import find_klayout_antenna_deck
from app.core.dependency_manifest import DependencyManifest
from app.core.i18n import pick
from app.core.python_env import PythonEnvironmentManager
from app.core.settings_manager import AppSettings


TOOL_ALIASES: dict[str, tuple[str, ...]] = {
    "xschem": ("xschem",),
    "ngspice": ("ngspice",),
    "magic": ("magic",),
    "netgen": ("netgen", "netgen-lvs"),
    "klayout": ("klayout",),
    "python": ("python3", "python"),
    "pip": ("pip3", "pip"),
}

TOOL_VERSION_ARGS: dict[str, tuple[tuple[str, ...], ...]] = {
    "xschem": (("--version",), ("-v",)),
    "ngspice": (("--version",), ("-v",)),
    # Magic 8.3.6xx prints a usage error for "-version" and still exits 0, so the
    # long option has to be tried first or the usage text is stored as a version.
    "magic": (("--version",), ("-dnull", "-noconsole", "--version"), ("-dnull", "-noconsole", "-version")),
    "netgen": (("-batch", "quit"),),
    "klayout": (("-v",), ("--version",)),
    "python": (("--version",),),
    "pip": (("--version",),),
}

REQUIRED_PDK_SUBDIRS: dict[str, str] = {
    "magic": "libs.tech/magic",
    "netgen": "libs.tech/netgen",
    "klayout": "libs.tech/klayout",
    "ngspice": "libs.tech/ngspice",
    "xschem": "libs.tech/xschem",
}

QT_RUNTIME_LIBS: tuple[tuple[str, str, str], ...] = (
    ("libxcb-cursor0", "xcb-cursor", "required"),
    ("libxcb-xinerama0", "xcb-xinerama", "recommended"),
    ("libxkbcommon-x11-0", "xkbcommon-x11", "required"),
    ("libxcb-xkb1", "xcb-xkb", "required"),
    ("libxcb-icccm4", "xcb-icccm", "recommended"),
    ("libxcb-image0", "xcb-image", "recommended"),
    ("libxcb-keysyms1", "xcb-keysyms", "recommended"),
    ("libxcb-render-util0", "xcb-render-util", "recommended"),
    ("libxcb-randr0", "xcb-randr", "recommended"),
    ("libxcb-shape0", "xcb-shape", "recommended"),
    ("libxcb-xfixes0", "xcb-xfixes", "required"),
    ("libgl1", "GL", "required"),
)


@dataclass
class ToolDiagnosis:
    logical_name: str
    configured_value: str
    found_binary: str = ""
    resolved_path: str = ""
    version: str = ""
    status: str = "missing"
    message: str = ""
    minimum_version: str = ""
    outdated: bool = False


@dataclass
class PdkDiagnosis:
    found: bool
    status: str
    root: str = ""
    sky130a_path: str = ""
    missing_subdirs: list[str] = field(default_factory=list)
    message: str = ""
    magic_rc: str = ""
    netgen_setup: str = ""
    klayout_antenna_deck: str = ""


@dataclass
class PythonEnvDiagnosis:
    app_root: str
    venv_path: str
    venv_exists: bool
    venv_owner: str = ""
    venv_writable: bool = False
    repo_writable: bool = False
    requirements_ok: bool = False
    python_bin: str = ""
    problems: list[str] = field(default_factory=list)
    message: str = ""
    status: str = ""
    system_python: str = ""
    system_version: str = ""
    architecture: str = ""
    pip_available: bool = False
    packages: dict[str, str] = field(default_factory=dict)
    missing_packages: list[str] = field(default_factory=list)
    import_error: str = ""
    legacy_path: str = ""


@dataclass
class GuiDependencyDiagnosis:
    checked: bool
    missing_required: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class EnvironmentDiagnosis:
    tools: OrderedDict[str, ToolDiagnosis]
    pdk: PdkDiagnosis
    python_env: PythonEnvDiagnosis
    gui_dependencies: GuiDependencyDiagnosis
    overall_status: str
    recommendations: list[str]


@dataclass
class ValidationRow:
    key: str
    item: str
    status: str
    ok: bool
    detail: str


class EnvValidator:
    """Validate configured executables, PDK paths, and local Python environment.

    A full diagnosis shells out to every configured tool plus the user Python
    environment, which costs well over half a second.  The setup assistant and
    the preferences page each need the same answer several times while they
    build, so results are memoized process-wide for a short window and dropped
    whenever the app changes something the diagnosis depends on.
    """

    CACHE_TTL_SECONDS = 30.0
    _cache: ClassVar[dict[tuple, tuple[float, EnvironmentDiagnosis]]] = {}

    def __init__(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.manifest = DependencyManifest()

    @classmethod
    def invalidate_cache(cls) -> None:
        """Drop memoized diagnoses after the environment was modified."""
        cls._cache.clear()

    @staticmethod
    def _cache_key(settings: AppSettings, lang: str, repo_root: Path) -> tuple:
        return (
            str(repo_root),
            lang,
            tuple(sorted(vars(settings.tool_paths).items())),
            tuple(sorted(vars(settings.pdk_paths).items())),
        )

    def diagnose(self, settings: AppSettings, lang: str = "en", *, refresh: bool = False) -> EnvironmentDiagnosis:
        """Return an environment diagnosis, reusing a recent one when possible."""
        key = self._cache_key(settings, lang, self.repo_root)
        if not refresh:
            cached = self._cache.get(key)
            if cached is not None and (time.monotonic() - cached[0]) < self.CACHE_TTL_SECONDS:
                return cached[1]
        diagnosis = self._diagnose_uncached(settings, lang)
        self._cache[key] = (time.monotonic(), diagnosis)
        return diagnosis

    def _diagnose_uncached(self, settings: AppSettings, lang: str) -> EnvironmentDiagnosis:
        tools = OrderedDict(
            (name, self._detect_tool(name, getattr(settings.tool_paths, name, ""), lang))
            for name in ("xschem", "ngspice", "magic", "netgen", "klayout")
        )
        pdk = self._detect_pdk(settings, lang, magic_version=tools["magic"].version)
        python_env = self._detect_python_environment(lang)
        gui_dependencies = self._detect_gui_dependencies(lang)
        recommendations = self._build_recommendations(tools, pdk, python_env, gui_dependencies, lang)
        overall_status = self._overall_status(tools, pdk, python_env, gui_dependencies)
        return EnvironmentDiagnosis(
            tools=tools,
            pdk=pdk,
            python_env=python_env,
            gui_dependencies=gui_dependencies,
            overall_status=overall_status,
            recommendations=recommendations,
        )

    def validation_rows(self, diagnosis: EnvironmentDiagnosis, lang: str = "en") -> list[ValidationRow]:
        rows: list[ValidationRow] = []

        for logical_name, tool in diagnosis.tools.items():
            rows.append(
                ValidationRow(
                    key=f"tool:{logical_name}",
                    item=pick(lang, f"Herramienta: {logical_name}", f"Tool: {logical_name}"),
                    status=self._tool_status_label(tool.status, lang),
                    ok=tool.status in {"ok", "alias"},
                    detail=tool.message,
                )
            )

        rows.append(
            ValidationRow(
                key="pdk:sky130A",
                item=pick(lang, "PDK: sky130A", "PDK: sky130A"),
                status=self._pdk_status_label(diagnosis.pdk.status, lang),
                ok=diagnosis.pdk.status == "present",
                detail=diagnosis.pdk.message,
            )
        )
        rows.append(
            ValidationRow(
                key="python:venv",
                item=pick(lang, "Entorno Python", "Python environment"),
                status=self._python_status_label(diagnosis.python_env, lang),
                ok=not diagnosis.python_env.problems and diagnosis.python_env.requirements_ok,
                detail=diagnosis.python_env.message,
            )
        )
        if diagnosis.gui_dependencies.checked:
            rows.append(
                ValidationRow(
                    key="gui:qt_xcb",
                    item=pick(lang, "GUI: Qt/X11", "GUI: Qt/X11"),
                    status=self._gui_status_label(diagnosis.gui_dependencies, lang),
                    ok=not diagnosis.gui_dependencies.missing_required,
                    detail=diagnosis.gui_dependencies.message,
                )
            )
        return rows

    def validate(self, settings: AppSettings, lang: str = "en") -> dict[str, tuple[bool, str]]:
        """Return compatibility rows for existing UI consumers."""
        diagnosis = self.diagnose(settings, lang=lang)
        rows = OrderedDict()
        for row in self.validation_rows(diagnosis, lang=lang):
            rows[row.key] = (row.ok, row.detail)
        return rows

    def _detect_tool(self, logical_name: str, configured_value: str, lang: str) -> ToolDiagnosis:
        aliases = TOOL_ALIASES[logical_name]
        candidates: list[str] = []
        if configured_value:
            candidates.append(configured_value)
        candidates.extend(alias for alias in aliases if alias not in candidates)

        configured_path_issue = ""
        for candidate in candidates:
            result = self._resolve_command(candidate)
            if result is None:
                if candidate == configured_value and configured_value:
                    configured_path_issue = self._describe_missing_candidate(configured_value, lang)
                continue

            found_binary, resolved_path = result
            version = self._query_version(logical_name, resolved_path)
            primary_alias = aliases[0]
            status = "ok"
            if found_binary != primary_alias and Path(found_binary).name != primary_alias:
                status = "alias"

            minimum = self._minimum_version(logical_name)
            outdated = self._is_outdated(version, minimum)
            message = self._build_tool_message(
                logical_name=logical_name,
                found_binary=found_binary,
                resolved_path=resolved_path,
                version=version,
                status=status,
                lang=lang,
            )
            if outdated:
                message += " " + pick(
                    lang,
                    f"Versión por debajo del mínimo recomendado ({minimum}); "
                    "los paquetes de Ubuntu suelen ir muy por detrás del upstream.",
                    f"This is below the recommended minimum ({minimum}); "
                    "Ubuntu packages often lag far behind upstream.",
                )
            return ToolDiagnosis(
                logical_name=logical_name,
                configured_value=configured_value,
                found_binary=found_binary,
                resolved_path=resolved_path,
                version=version,
                status=status,
                message=message,
                minimum_version=minimum,
                outdated=outdated,
            )

        return ToolDiagnosis(
            logical_name=logical_name,
            configured_value=configured_value,
            status="missing",
            message=configured_path_issue
            or pick(
                lang,
                f"{logical_name} no está instalado o no está en PATH. Se probaron: {', '.join(aliases)}.",
                f"{logical_name} is not installed or not available in PATH. Tried: {', '.join(aliases)}.",
            ),
        )

    def _detect_pdk(self, settings: AppSettings, lang: str, magic_version: str = "") -> PdkDiagnosis:
        sky130a = self._find_sky130a(settings)
        if sky130a is None:
            return PdkDiagnosis(
                found=False,
                status="missing",
                message=pick(
                    lang,
                    "Las herramientas base pueden estar instaladas, pero no se encontró el PDK `sky130A` en `PDK_ROOT` ni en rutas comunes.",
                    "Base tools may be installed, but the `sky130A` PDK was not found in `PDK_ROOT` or common locations.",
                ),
            )

        missing_subdirs = [
            relative
            for relative in REQUIRED_PDK_SUBDIRS.values()
            if not sky130a.joinpath(relative).exists()
        ]
        magic_requirement = self._detect_magic_tech_requirement(sky130a, magic_version)
        if missing_subdirs:
            status = "incomplete"
            message = pick(
                lang,
                f"El PDK `sky130A` existe en {sky130a}, pero está incompleto. Faltan: {', '.join(missing_subdirs)}.",
                f"The `sky130A` PDK exists at {sky130a}, but it is incomplete. Missing: {', '.join(missing_subdirs)}.",
            )
        elif magic_requirement:
            required, detected = magic_requirement
            status = "incompatible"
            message = pick(
                lang,
                f"El PDK `sky130A` requiere Magic {required} o superior, pero se detectó Magic {detected}. Actualiza Magic o usa un PDK compatible.",
                f"The `sky130A` PDK requires Magic {required} or newer, but Magic {detected} was detected. Upgrade Magic or use a compatible PDK.",
            )
        else:
            status = "present"
            message = pick(
                lang,
                f"PDK `sky130A` detectado en: {sky130a}",
                f"`sky130A` PDK detected at: {sky130a}",
            )
        return PdkDiagnosis(
            found=True,
            status=status,
            root=str(sky130a.parent),
            sky130a_path=str(sky130a),
            missing_subdirs=missing_subdirs,
            message=message,
            magic_rc=str(sky130a / "libs.tech" / "magic" / "sky130A.magicrc"),
            netgen_setup=str(sky130a / "libs.tech" / "netgen" / "sky130A_setup.tcl"),
            klayout_antenna_deck=find_klayout_antenna_deck(sky130a),
        )

    def _detect_python_environment(self, lang: str) -> PythonEnvDiagnosis:
        app_root = self.repo_root
        manager = PythonEnvironmentManager(app_root)
        detected = manager.diagnose()
        running = None
        if not detected.ready:
            # The app is running, so some interpreter already satisfies the
            # requirements. A packaged install uses the one inside the package
            # and never needs a user virtualenv.
            running = manager.running_environment()
            if running is not None:
                detected = running
        problems = list(detected.problems)
        legacy_notice = ""
        if detected.legacy_path:
            legacy_notice = pick(lang,
                f"Se detectó un venv legacy en {detected.legacy_path} (propietario: {detected.legacy_owner}); no se usa ni se copia. Reconstrúyelo en la ruta XDG.",
                f"A legacy venv was found at {detected.legacy_path} (owner: {detected.legacy_owner}); it is neither used nor copied. Rebuild it at the XDG path.")
        if detected.ready:
            versions = ", ".join(f"{name} {version}" for name, version in detected.packages.items())
            if running is not None:
                message = pick(
                    lang,
                    f"Usando el entorno incluido con la app en {detected.venv_path}: {versions}. "
                    "No hace falta un entorno de usuario aparte.",
                    f"Using the environment shipped with the app at {detected.venv_path}: {versions}. "
                    "A separate user environment is not required.",
                )
            else:
                message = pick(lang, f"Entorno Python listo en {detected.venv_path}: {versions}.",
                               f"Python environment ready at {detected.venv_path}: {versions}.")
            if legacy_notice:
                message += " " + legacy_notice
        else:
            message = " ".join(problems)
            if legacy_notice:
                message = (message + " " + legacy_notice).strip()
        system_summary = f"{detected.system_python or 'python3'} {detected.system_version} [{detected.architecture}]".strip()
        message = pick(lang, f"Python del sistema: {system_summary}. ", f"System Python: {system_summary}. ") + message

        return PythonEnvDiagnosis(
            app_root=str(app_root),
            venv_path=detected.venv_path,
            venv_exists=detected.venv_exists,
            venv_owner=detected.venv_owner,
            venv_writable=detected.venv_writable,
            repo_writable=os.access(Path(detected.venv_path).parent, os.W_OK),
            requirements_ok=detected.ready,
            python_bin=detected.python_bin,
            problems=problems,
            message=message,
            status=detected.status,
            system_python=detected.system_python,
            system_version=detected.system_version,
            architecture=detected.architecture,
            pip_available=detected.pip_available,
            packages=detected.packages,
            missing_packages=detected.missing_packages,
            import_error=detected.import_error,
            legacy_path=detected.legacy_path,
        )

    def _detect_gui_dependencies(self, lang: str) -> GuiDependencyDiagnosis:
        if os.name != "posix" or "linux" not in os.uname().sysname.lower():
            return GuiDependencyDiagnosis(checked=False)

        missing_required: list[str] = []
        missing_recommended: list[str] = []

        for package_name, library_name, level in QT_RUNTIME_LIBS:
            if ctypes.util.find_library(library_name):
                continue
            if level == "required":
                missing_required.append(package_name)
            else:
                missing_recommended.append(package_name)

        if not missing_required and not missing_recommended:
            message = pick(
                lang,
                "No se detectaron dependencias Qt/X11 faltantes para Ubuntu.",
                "No common missing Qt/X11 runtime libraries were detected for Ubuntu.",
            )
        else:
            message = pick(
                lang,
                "Si la GUI falla al cargar el plugin `xcb`, instala estas bibliotecas del sistema: "
                f"{', '.join(missing_required + missing_recommended)}.",
                "If the GUI fails to load the `xcb` plugin, install these system libraries: "
                f"{', '.join(missing_required + missing_recommended)}.",
            )

        return GuiDependencyDiagnosis(
            checked=True,
            missing_required=missing_required,
            missing_recommended=missing_recommended,
            message=message,
        )

    def _build_recommendations(
        self,
        tools: OrderedDict[str, ToolDiagnosis],
        pdk: PdkDiagnosis,
        python_env: PythonEnvDiagnosis,
        gui_dependencies: GuiDependencyDiagnosis,
        lang: str,
    ) -> list[str]:
        recommendations: list[str] = []

        if any(tool.status == "missing" for tool in tools.values()):
            recommendations.append(
                pick(
                    lang,
                    "Instala las herramientas EDA base con el bootstrap de Ubuntu o ajusta rutas manuales en Preferences.",
                    "Install the base EDA tools with the Ubuntu bootstrap or adjust custom paths in Preferences.",
                )
            )
        if pdk.status == "missing":
            recommendations.append(
                pick(
                    lang,
                    "Instalar paquetes del sistema no equivale a tener el PDK. Instala o apunta a una distribución `sky130A` válida.",
                    "Installing system packages is not the same as having the PDK. Install or point the app to a valid `sky130A` distribution.",
                )
            )
        elif pdk.status == "incomplete":
            recommendations.append(
                pick(
                    lang,
                    "Completa el contenido de `sky130A/libs.tech/*` o corrige `PDK_ROOT` para usar un PDK completo.",
                    "Complete `sky130A/libs.tech/*` or fix `PDK_ROOT` so the app uses a complete PDK.",
                )
            )
        elif pdk.status == "incompatible":
            recommendations.append(
                pick(
                    lang,
                    "Actualiza Magic para que cumpla la versión mínima declarada por `sky130A.tech`, o apunta la app a un PDK compatible con tu Magic instalado.",
                    "Upgrade Magic so it meets the minimum version declared by `sky130A.tech`, or point the app to a PDK compatible with your installed Magic.",
                )
            )
        if python_env.problems:
            recommendations.append(
                pick(
                    lang,
                    "Crea o repara el entorno Python XDG como usuario normal. No uses `pkexec`, `sudo` ni pip global.",
                    "Create or repair the XDG Python environment as the normal user. Do not use `pkexec`, `sudo`, or global pip.",
                )
            )
        if gui_dependencies.missing_required or gui_dependencies.missing_recommended:
            recommendations.append(
                pick(
                    lang,
                    "En Ubuntu limpio, instala también las dependencias Qt/X11 (`libxcb-cursor0`, `libxkbcommon-x11-0`, `libgl1`, etc.) para que PySide6 pueda arrancar.",
                    "On clean Ubuntu installs, also install the Qt/X11 runtime libraries (`libxcb-cursor0`, `libxkbcommon-x11-0`, `libgl1`, etc.) so PySide6 can start.",
                )
            )

        if not recommendations:
            recommendations.append(
                pick(
                    lang,
                    "El entorno base parece consistente. Haz una validación final antes de correr extracción, simulación o LVS.",
                    "The base environment looks consistent. Run a final validation before extraction, simulation, or LVS.",
                )
            )
        return recommendations

    @staticmethod
    def _overall_status(
        tools: OrderedDict[str, ToolDiagnosis],
        pdk: PdkDiagnosis,
        python_env: PythonEnvDiagnosis,
        gui_dependencies: GuiDependencyDiagnosis,
    ) -> str:
        if any(tool.status == "missing" for tool in tools.values()):
            return "error"
        if pdk.status != "present":
            return "error"
        if python_env.problems:
            return "error"
        if gui_dependencies.missing_required:
            return "warning"
        return "ok"

    @staticmethod
    def _resolve_command(candidate: str) -> tuple[str, str] | None:
        if not candidate:
            return None
        if "/" in candidate:
            path = Path(candidate).expanduser()
            if path.exists() and path.is_file() and os.access(path, os.X_OK):
                return (path.name, str(path.resolve()))
            return None
        resolved = shutil.which(candidate)
        if resolved:
            return (candidate, str(Path(resolved).resolve()))
        return None

    @staticmethod
    def _owner_name(uid: int) -> str:
        try:
            return pwd.getpwuid(uid).pw_name
        except KeyError:
            return str(uid)

    def _find_sky130a(self, settings: AppSettings) -> Path | None:
        env_pdk_root = os.environ.get("PDK_ROOT", "").strip()
        env_sky130a = os.environ.get("SKY130A", "").strip()
        manifest_roots = [Path(root).expanduser() for root in self.manifest.channel().pdk_search_roots]
        candidates = [
            Path(settings.pdk_paths.sky130a).expanduser() if settings.pdk_paths.sky130a else None,
            Path(settings.pdk_paths.pdk_root).expanduser() if settings.pdk_paths.pdk_root else None,
            Path(env_sky130a).expanduser() if env_sky130a else None,
            Path(env_pdk_root).expanduser() if env_pdk_root else None,
            *manifest_roots,
        ]

        for candidate in candidates:
            if candidate is None:
                continue
            if candidate.name == "sky130A" and candidate.exists():
                return candidate
            if candidate.exists():
                match = self._search_sky130a(candidate)
                if match is not None:
                    return match
        return None

    @staticmethod
    def _search_sky130a(root: Path) -> Path | None:
        direct = root / "sky130A"
        if direct.is_dir():
            return direct
        for pattern in ("*/sky130A", "*/*/sky130A", "**/sky130A"):
            for match in sorted(root.glob(pattern)):
                if match.is_dir():
                    return match
        return None

    @staticmethod
    def _check_python_requirements(python_bin: Path) -> bool:
        try:
            result = subprocess.run(
                [
                    str(python_bin),
                    "-c",
                    "import importlib.util as u;mods=['PySide6','pyqtgraph'];"
                    "missing=[m for m in mods if u.find_spec(m) is None];"
                    "print('OK' if not missing else 'MISSING:' + ','.join(missing))",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0 and result.stdout.strip() == "OK"

    @classmethod
    def _detect_magic_tech_requirement(cls, sky130a: Path, magic_version: str) -> tuple[str, str] | None:
        techfile = sky130a / "libs.tech" / "magic" / "sky130A.tech"
        if not techfile.is_file() or not magic_version:
            return None
        required_text = cls._read_magic_tech_required_version(techfile)
        required = cls._parse_version_tuple(required_text)
        detected = cls._parse_version_tuple(magic_version)
        if required is None or detected is None:
            return None
        if detected < required:
            return (required_text, ".".join(str(part) for part in detected))
        return None

    @staticmethod
    def _read_magic_tech_required_version(techfile: Path) -> str:
        try:
            text = techfile.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        for line in text.splitlines()[:80]:
            match = re.search(r"\bversion\s+([0-9]+(?:\.[0-9]+){1,3})\b", line, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _parse_version_tuple(text: str) -> tuple[int, ...] | None:
        revision_match = re.search(r"\bMagic\s+([0-9]+)\.([0-9]+)\s+revision\s+([0-9]+)\b", text, flags=re.IGNORECASE)
        if revision_match:
            return tuple(int(part) for part in revision_match.groups())
        match = re.search(r"\b([0-9]+(?:\.[0-9]+){1,3})\b", text)
        if not match:
            return None
        return tuple(int(part) for part in match.group(1).split("."))

    def _minimum_version(self, logical_name: str) -> str:
        """Return the manifest floor for a tool, if one is declared."""
        try:
            minimums = dict(self.manifest.channel().tool_minimum_versions)
        except (KeyError, OSError, ValueError):
            return ""
        return minimums.get(logical_name, "")

    @classmethod
    def _is_outdated(cls, version_text: str, minimum: str) -> bool:
        """Compare a detected version against a manifest floor, conservatively."""
        if not version_text or not minimum:
            return False
        detected = cls._parse_version_tuple(version_text)
        required = cls._parse_version_tuple(minimum)
        if detected is None or required is None:
            return False
        width = min(len(detected), len(required))
        return detected[:width] < required[:width]

    @staticmethod
    def _clean_version_output(output: str) -> str:
        """Pick the line that actually carries a version number.

        Tools are inconsistent here: ngspice leads with a row of asterisks and
        Magic answers an unknown flag with usage text on exit code 0.  Taking
        the first line verbatim stored things like ``Unknown option: '-version'``
        as the detected version, which also defeated the Magic/PDK compatibility
        check downstream.
        """
        rejected_prefixes = ("unknown option", "usage:", "error", "invalid option")
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped or not stripped.strip("*= -"):
                continue
            if stripped.lower().startswith(rejected_prefixes):
                return ""
            if re.search(r"\d+\.\d+|\d{2,}", stripped):
                return stripped[:180]
        return ""

    @staticmethod
    def _query_version(logical_name: str, executable: str) -> str:
        for args in TOOL_VERSION_ARGS.get(logical_name, (("--version",),)):
            try:
                result = subprocess.run(
                    [executable, *args],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=3,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            version = EnvValidator._clean_version_output(f"{result.stdout}\n{result.stderr}")
            if version:
                return version
        return ""

    @staticmethod
    def _describe_missing_candidate(candidate: str, lang: str) -> str:
        path = Path(candidate).expanduser()
        if "/" in candidate:
            if path.exists() and path.is_file() and not os.access(path, os.X_OK):
                return pick(
                    lang,
                    f"La ruta configurada existe, pero no es ejecutable: {path}",
                    f"The configured path exists, but it is not executable: {path}",
                )
            return pick(
                lang,
                f"La ruta configurada no existe: {path}",
                f"The configured path does not exist: {path}",
            )
        return pick(
            lang,
            f"El binario configurado no aparece en PATH: {candidate}",
            f"The configured command is not available in PATH: {candidate}",
        )

    @staticmethod
    def _build_tool_message(
        logical_name: str,
        found_binary: str,
        resolved_path: str,
        version: str,
        status: str,
        lang: str,
    ) -> str:
        version_suffix = f" ({version})" if version else ""
        if status == "alias":
            return pick(
                lang,
                f"{logical_name.capitalize()} no está ausente: se detectó como `{found_binary}` en {resolved_path}{version_suffix}.",
                f"{logical_name.capitalize()} is not missing: it was detected as `{found_binary}` at {resolved_path}{version_suffix}.",
            )
        return pick(
            lang,
            f"{logical_name.capitalize()} detectado como `{found_binary}` en {resolved_path}{version_suffix}.",
            f"{logical_name.capitalize()} detected as `{found_binary}` at {resolved_path}{version_suffix}.",
        )

    @staticmethod
    def _tool_status_label(status: str, lang: str) -> str:
        mapping = {
            "ok": pick(lang, "OK", "OK"),
            "alias": pick(lang, "ALIAS", "ALIAS"),
            "missing": pick(lang, "FALTA", "MISSING"),
        }
        return mapping.get(status, status.upper())

    @staticmethod
    def _pdk_status_label(status: str, lang: str) -> str:
        mapping = {
            "present": pick(lang, "PRESENTE", "PRESENT"),
            "incompatible": pick(lang, "INCOMPATIBLE", "INCOMPATIBLE"),
            "incomplete": pick(lang, "INCOMPLETO", "INCOMPLETE"),
            "missing": pick(lang, "AUSENTE", "ABSENT"),
        }
        return mapping.get(status, status.upper())

    @staticmethod
    def _python_status_label(python_env: PythonEnvDiagnosis, lang: str) -> str:
        if not python_env.problems and python_env.requirements_ok:
            return pick(lang, "OK", "OK")
        if python_env.venv_exists:
            return pick(lang, "ATENCIÓN", "ATTENTION")
        return pick(lang, "PENDIENTE", "PENDING")

    @staticmethod
    def _gui_status_label(gui_dependencies: GuiDependencyDiagnosis, lang: str) -> str:
        if gui_dependencies.missing_required:
            return pick(lang, "FALTA", "MISSING")
        if gui_dependencies.missing_recommended:
            return pick(lang, "ADVERTENCIA", "WARNING")
        return pick(lang, "OK", "OK")
