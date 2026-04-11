"""Environment and path validation helpers."""

from __future__ import annotations

import ctypes.util
import os
import pwd
import re
import shutil
import subprocess
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from app.core.dependency_manifest import DependencyManifest
from app.core.i18n import pick
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
    "magic": (("-dnull", "-noconsole", "-version"), ("-version",), ("--version",)),
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
    """Validate configured executables, PDK paths, and local Python environment."""

    def __init__(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.manifest = DependencyManifest()

    def diagnose(self, settings: AppSettings, lang: str = "en") -> EnvironmentDiagnosis:
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
                item=pick(lang, "Python: .venv", "Python: .venv"),
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

            message = self._build_tool_message(
                logical_name=logical_name,
                found_binary=found_binary,
                resolved_path=resolved_path,
                version=version,
                status=status,
                lang=lang,
            )
            return ToolDiagnosis(
                logical_name=logical_name,
                configured_value=configured_value,
                found_binary=found_binary,
                resolved_path=resolved_path,
                version=version,
                status=status,
                message=message,
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
            klayout_antenna_deck=str(sky130a / "libs.tech" / "klayout" / "drc" / "sky130A_ant.rb"),
        )

    def _detect_python_environment(self, lang: str) -> PythonEnvDiagnosis:
        app_root = self.repo_root
        venv_path = app_root / ".venv"
        requirements = app_root / "requirements.txt"
        repo_writable = os.access(app_root, os.W_OK)
        venv_exists = venv_path.exists()
        problems: list[str] = []
        venv_owner = ""
        venv_writable = False
        requirements_ok = False
        python_bin = str(venv_path / "bin" / "python")

        if venv_exists:
            stat_result = venv_path.stat()
            venv_owner = self._owner_name(stat_result.st_uid)
            venv_writable = os.access(venv_path, os.W_OK)
            current_uid = os.getuid()
            if stat_result.st_uid != current_uid and current_uid != 0:
                problems.append(
                    pick(
                        lang,
                        f"El entorno virtual existe, pero pertenece a {venv_owner}. Esto puede ocurrir si se mezcló pkexec con operaciones del usuario.",
                        f"The virtual environment exists, but it belongs to {venv_owner}. This can happen when pkexec is mixed with user-owned operations.",
                    )
                )
            if not venv_writable:
                problems.append(
                    pick(
                        lang,
                        f"No se puede modificar `.venv` en {venv_path} porque el usuario actual no tiene permisos de escritura.",
                        f"`.venv` at {venv_path} is not writable by the current user.",
                    )
                )
            if Path(python_bin).exists():
                requirements_ok = self._check_python_requirements(Path(python_bin))
                if not requirements_ok:
                    problems.append(
                        pick(
                            lang,
                            "El entorno virtual existe, pero faltan dependencias Python (`PySide6`, `pyqtgraph`) o no se pudieron validar.",
                            "The virtual environment exists, but Python dependencies (`PySide6`, `pyqtgraph`) are missing or could not be validated.",
                        )
                    )
            else:
                problems.append(
                    pick(
                        lang,
                        "El entorno virtual existe, pero no contiene `.venv/bin/python`.",
                        "The virtual environment exists, but `.venv/bin/python` is missing.",
                    )
                )
        else:
            if not repo_writable:
                problems.append(
                    pick(
                        lang,
                        f"No se puede preparar `.venv` en esta ruta porque el usuario actual no tiene permisos de escritura sobre {app_root}.",
                        f"`.venv` cannot be prepared here because the current user does not have write permission in {app_root}.",
                    )
                )
            else:
                problems.append(
                    pick(
                        lang,
                        f"No existe `.venv` en {venv_path}.",
                        f"`.venv` does not exist at {venv_path}.",
                    )
                )

        if not requirements.exists():
            problems.append(
                pick(
                    lang,
                    f"No se encontró `requirements.txt` en {requirements}.",
                    f"`requirements.txt` was not found at {requirements}.",
                )
            )

        if not problems and requirements_ok:
            message = pick(
                lang,
                f"Entorno Python listo en {venv_path}.",
                f"Python environment is ready at {venv_path}.",
            )
        else:
            message = " ".join(problems)

        return PythonEnvDiagnosis(
            app_root=str(app_root),
            venv_path=str(venv_path),
            venv_exists=venv_exists,
            venv_owner=venv_owner,
            venv_writable=venv_writable,
            repo_writable=repo_writable,
            requirements_ok=requirements_ok,
            python_bin=python_bin,
            problems=problems,
            message=message,
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
                    "Prepara `.venv` como usuario normal. No mezcles `pkexec` o `sudo` con la creación del entorno Python dentro del repo.",
                    "Prepare `.venv` as the normal user. Do not mix `pkexec` or `sudo` with Python environment creation inside the repo.",
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
            output = (result.stdout or result.stderr).strip()
            if output:
                return output.splitlines()[0][:180]
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
