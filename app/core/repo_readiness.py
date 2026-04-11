"""Local repository readiness checks for Tiny Tapeout-style submissions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class ReadinessCheck:
    """A single local submission-readiness check."""

    title: str
    status: str
    detail: str
    path: Path | None = None


class RepoReadinessChecker:
    """Validate a project tree before committing or pushing to GitHub."""

    def check(self, project_root: str | Path) -> list[ReadinessCheck]:
        root = Path(project_root).expanduser().resolve()
        checks: list[ReadinessCheck] = []
        checks.append(self._check_root(root))
        checks.extend(self._check_template_files(root))
        info = self._read_info_yaml(root)
        checks.extend(self._check_info_yaml(root, info))
        checks.extend(self._check_submission_artifacts(root, info))
        checks.extend(self._check_outputs(root))
        checks.extend(self._check_git_hygiene(root))
        return checks

    def _check_root(self, root: Path) -> ReadinessCheck:
        if root.is_dir():
            return ReadinessCheck("Proyecto", "ok", f"Raiz encontrada: {root}", root)
        return ReadinessCheck("Proyecto", "error", f"No existe la carpeta del proyecto: {root}", root)

    def _check_template_files(self, root: Path) -> list[ReadinessCheck]:
        required = [
            ("README.md", "README"),
            ("info.yaml", "Metadata Tiny Tapeout"),
            ("docs/info.md", "Documentacion publica"),
            ("src/project.v", "Wrapper HDL del template"),
            ("test", "Carpeta de tests"),
        ]
        checks = []
        for relative, title in required:
            path = root / relative
            if path.exists():
                checks.append(ReadinessCheck(title, "ok", f"Existe {relative}", path))
            else:
                checks.append(ReadinessCheck(title, "error", f"Falta {relative}", path))
        return checks

    def _read_info_yaml(self, root: Path) -> dict[str, object]:
        path = root / "info.yaml"
        if not path.is_file():
            return {}
        try:
            return self._parse_info_yaml(path.read_text())
        except OSError:
            return {}

    def _parse_info_yaml(self, text: str) -> dict[str, object]:
        data: dict[str, object] = {"source_files": []}
        section = ""
        in_source_files = False
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            stripped = line.strip()
            if not raw_line.startswith(" ") and stripped.endswith(":"):
                section = stripped[:-1]
                in_source_files = False
                continue
            if not raw_line.startswith(" ") and ":" in stripped:
                key, value = stripped.split(":", 1)
                data[key.strip()] = self._clean_yaml_scalar(value)
                section = ""
                in_source_files = False
                continue
            if section == "project" and stripped == "source_files:":
                in_source_files = True
                continue
            if section == "project" and in_source_files and stripped.startswith("- "):
                source_files = data.setdefault("source_files", [])
                if isinstance(source_files, list):
                    source_files.append(self._clean_yaml_scalar(stripped[2:]))
                continue
            if section == "project" and ":" in stripped:
                key, value = stripped.split(":", 1)
                data[f"project.{key.strip()}"] = self._clean_yaml_scalar(value)
                in_source_files = False
        return data

    @staticmethod
    def _clean_yaml_scalar(value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
            return cleaned[1:-1]
        return cleaned

    def _check_info_yaml(self, root: Path, info: dict[str, object]) -> list[ReadinessCheck]:
        path = root / "info.yaml"
        if not path.is_file():
            return [ReadinessCheck("info.yaml", "error", "Falta info.yaml", path)]

        required_fields = [
            "yaml_version",
            "project.title",
            "project.author",
            "project.description",
            "project.top_module",
            "project.source_files",
            "project.tiles",
            "project.analog_pins",
            "project.uses_3v3",
        ]
        checks: list[ReadinessCheck] = []
        for field in required_fields:
            value = info.get(field)
            if field == "project.source_files":
                value = info.get("source_files")
            if value:
                checks.append(ReadinessCheck(f"info.yaml:{field}", "ok", f"{field} definido", path))
            else:
                checks.append(ReadinessCheck(f"info.yaml:{field}", "error", f"Falta {field}", path))

        yaml_version = str(info.get("yaml_version", ""))
        if yaml_version == "6":
            checks.append(ReadinessCheck("info.yaml version", "ok", "yaml_version es 6", path))
        else:
            checks.append(ReadinessCheck("info.yaml version", "warning", f"yaml_version esperado: 6; actual: {yaml_version or '-'}", path))

        top_module = str(info.get("project.top_module", ""))
        if top_module.startswith("tt_um_"):
            checks.append(ReadinessCheck("Top module", "ok", f"Top module Tiny Tapeout: {top_module}", path))
        else:
            checks.append(ReadinessCheck("Top module", "warning", f"El top_module no empieza con tt_um_: {top_module or '-'}", path))

        tiles = str(info.get("project.tiles", ""))
        if tiles in {"1x2", "2x2"}:
            checks.append(ReadinessCheck("Tiles", "ok", f"Tiles valido: {tiles}", path))
        else:
            checks.append(ReadinessCheck("Tiles", "warning", f"Tiles esperado 1x2 o 2x2; actual: {tiles or '-'}", path))

        analog_pins = str(info.get("project.analog_pins", ""))
        if analog_pins.isdigit() and 0 <= int(analog_pins) <= 6:
            checks.append(ReadinessCheck("Analog pins", "ok", f"analog_pins={analog_pins}", path))
        else:
            checks.append(ReadinessCheck("Analog pins", "error", f"analog_pins debe estar entre 0 y 6; actual: {analog_pins or '-'}", path))

        return checks

    def _check_submission_artifacts(self, root: Path, info: dict[str, object]) -> list[ReadinessCheck]:
        checks: list[ReadinessCheck] = []
        source_files = info.get("source_files", [])
        if isinstance(source_files, list) and source_files:
            for source_file in source_files:
                source_path = root / "src" / str(source_file)
                if source_path.is_file():
                    checks.append(ReadinessCheck("Source file", "ok", f"Existe src/{source_file}", source_path))
                else:
                    checks.append(ReadinessCheck("Source file", "error", f"Falta src/{source_file}", source_path))
        else:
            checks.append(ReadinessCheck("Source files", "error", "info.yaml no lista source_files", root / "info.yaml"))

        gds_files = sorted((root / "gds").glob("*.gds")) if (root / "gds").is_dir() else []
        if gds_files:
            checks.append(ReadinessCheck("GDS", "ok", f"GDS encontrado: {gds_files[0].name}", gds_files[0]))
        else:
            checks.append(ReadinessCheck("GDS", "warning", "No hay GDS en gds/. Para analog/custom normalmente debe existir antes de submission.", root / "gds"))

        lef_files = sorted((root / "lef").glob("*.lef")) if (root / "lef").is_dir() else []
        if lef_files:
            checks.append(ReadinessCheck("LEF", "ok", f"LEF encontrado: {lef_files[0].name}", lef_files[0]))
        else:
            checks.append(ReadinessCheck("LEF", "warning", "No hay LEF en lef/. Puede ser necesario para el flujo final.", root / "lef"))
        return checks

    def _check_outputs(self, root: Path) -> list[ReadinessCheck]:
        checks: list[ReadinessCheck] = []
        extraction = root / "runs" / "extraction"
        extracted = sorted(extraction.glob("*_extracted.spice")) if extraction.is_dir() else []
        checks.append(
            ReadinessCheck(
                "Extraccion Magic",
                "ok" if extracted else "warning",
                f"Netlist extraido: {extracted[-1].name}" if extracted else "No se encontro *_extracted.spice en runs/extraction.",
                extracted[-1] if extracted else extraction,
            )
        )

        checks.append(self._check_report_folder(root / "runs" / "lvs", "LVS", ("match", "clean", "success", "netlists match")))
        checks.append(self._check_report_folder(root / "runs" / "antenna", "Antena", ("pass", "clean", "success", "violations: 0")))
        return checks

    def _check_report_folder(self, folder: Path, title: str, pass_tokens: tuple[str, ...]) -> ReadinessCheck:
        reports = []
        if folder.is_dir():
            for pattern in ("*.log", "*.rpt", "*.report", "*.txt"):
                reports.extend(folder.rglob(pattern))
        if not reports:
            return ReadinessCheck(title, "warning", f"No hay reportes en {folder}", folder)
        latest = max(reports, key=lambda path: path.stat().st_mtime)
        try:
            text = latest.read_text(errors="ignore").lower()
        except OSError:
            text = ""
        if any(token in text for token in pass_tokens) and "error" not in text and "fail" not in text:
            return ReadinessCheck(title, "ok", f"Reporte parece OK: {latest.name}", latest)
        return ReadinessCheck(title, "warning", f"Revisar reporte manualmente: {latest.name}", latest)

    def _check_git_hygiene(self, root: Path) -> list[ReadinessCheck]:
        checks: list[ReadinessCheck] = []
        gitignore = root / ".gitignore"
        if gitignore.is_file():
            text = gitignore.read_text(errors="ignore")
            if "runs/" in text:
                checks.append(ReadinessCheck(".gitignore", "ok", "runs/ esta ignorado", gitignore))
            else:
                checks.append(ReadinessCheck(".gitignore", "warning", "Conviene ignorar runs/ antes de hacer push", gitignore))
        else:
            checks.append(ReadinessCheck(".gitignore", "warning", "Falta .gitignore", gitignore))

        risky = self._find_risky_paths(root)
        if risky:
            checks.append(ReadinessCheck("Rutas locales", "warning", f"Posibles rutas locales en {len(risky)} archivo(s)", risky[0]))
        else:
            checks.append(ReadinessCheck("Rutas locales", "ok", "No se detectaron rutas absolutas obvias", root))

        if (root / ".git").exists():
            checks.append(ReadinessCheck("Git", "ok", "Repositorio git inicializado", root / ".git"))
        else:
            checks.append(ReadinessCheck("Git", "warning", "Repositorio git no inicializado todavia", root))
        return checks

    def _find_risky_paths(self, root: Path) -> list[Path]:
        risky: list[Path] = []
        skip_dirs = {".git", "runs", "__pycache__"}
        pattern = re.compile(r"(/home/|/tmp/|/Users/|C:\\\\)")
        for path in root.rglob("*"):
            if any(part in skip_dirs for part in path.parts):
                continue
            if not path.is_file() or path.stat().st_size > 1_000_000:
                continue
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                continue
            if pattern.search(text):
                risky.append(path)
        return risky
