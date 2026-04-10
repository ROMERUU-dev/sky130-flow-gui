"""Setup assistant helpers for Ubuntu bootstrap and environment detection."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys

from app.core.dependency_manifest import DependencyManifest
from app.core.env_validator import EnvValidator, REQUIRED_PDK_SUBDIRS
from app.core.settings_manager import AppSettings


@dataclass(frozen=True)
class PdkCandidate:
    """Reusable SKY130A candidate discovered on disk."""

    sky130a_path: str
    root_path: str
    status: str
    source: str
    detail: str


@dataclass(frozen=True)
class PdkInstallPreflight:
    """Precheck summary for managed PDK installation."""

    target_root: str
    target_sky130a: str
    install_mode: str
    minimum_free_bytes: int
    free_bytes: int
    enough_space: bool
    existing_status: str
    selected_candidate: str
    selected_candidate_status: str
    message: str


@dataclass(frozen=True)
class PdkInstallResult:
    """Outcome of a managed PDK installation attempt."""

    ok: bool
    changed: bool
    target_sky130a: str
    source_sky130a: str
    message: str


@dataclass(frozen=True)
class PdkSourceBuildPreflight:
    """Precheck summary for building the PDK from sources."""

    build_root: str
    target_sky130a: str
    minimum_free_bytes: int
    free_bytes: int
    enough_space: bool
    target_available: bool
    missing_commands: tuple[str, ...]
    has_required_commands: bool
    has_pinned_source: bool
    reusable_candidate_available: bool
    ready: bool
    message: str


@dataclass(frozen=True)
class PdkBundlePreflight:
    """Precheck summary for downloading and installing a TT-style PDK bundle."""

    enabled: bool
    bundle_name: str
    bundle_version: str
    install_root: str
    target_sky130a: str
    cache_root: str
    asset_url: str
    asset_filename: str
    asset_sha256: str
    minimum_free_bytes: int
    free_bytes: int
    enough_space: bool
    target_available: bool
    target_status: str
    ready: bool
    message: str


class SetupManager:
    """Detect common installations and provide installer entrypoints."""

    def __init__(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.manifest = DependencyManifest()
        self.validator = EnvValidator()

    def installer_script(self) -> Path:
        return self.repo_root / "scripts" / "install_vlsi_env_ubuntu.sh"

    def pdk_source_build_script(self) -> Path:
        return self.repo_root / "scripts" / "build_sky130_pdk_from_sources.sh"

    def pdk_bundle_install_script(self) -> Path:
        return self.repo_root / "scripts" / "install_tt_pdk_bundle.py"

    def installer_command(self) -> list[str]:
        return ["pkexec", "/bin/bash", str(self.installer_script()), self.manifest.default_channel()]

    def pdk_source_build_command(self) -> list[str]:
        return ["/bin/bash", str(self.pdk_source_build_script()), self.manifest.default_channel()]

    def pdk_bundle_install_command(self) -> list[str]:
        return [sys.executable, str(self.pdk_bundle_install_script()), self.manifest.default_channel()]

    def bootstrap_packages(self, channel: str | None = None) -> tuple[str, ...]:
        return self.manifest.channel(channel).apt_packages

    def supported_channels(self) -> tuple[str, ...]:
        return self.manifest.channel_names()

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

    def detect_reusable_pdk_candidates(self) -> list[PdkCandidate]:
        roots = self._candidate_pdk_roots()
        seen: set[Path] = set()
        candidates: list[PdkCandidate] = []

        for root, source in roots:
            if not root.exists():
                continue
            if root.name == "sky130A" and root.is_dir():
                sky130a_paths = [root]
            else:
                sky130a_paths = self._find_all_sky130a_under(root)

            for sky130a in sky130a_paths:
                resolved = sky130a.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                missing = [relative for relative in REQUIRED_PDK_SUBDIRS.values() if not resolved.joinpath(relative).exists()]
                status = "present" if not missing else "incomplete"
                detail = (
                    "ready to adopt"
                    if status == "present"
                    else f"missing: {', '.join(missing)}"
                )
                candidates.append(
                    PdkCandidate(
                        sky130a_path=str(resolved),
                        root_path=str(resolved.parent),
                        status=status,
                        source=source,
                        detail=detail,
                    )
                )

        candidates.sort(key=lambda item: (0 if item.status == "present" else 1, item.sky130a_path))
        return candidates

    def apply_pdk_candidate(self, settings: AppSettings, sky130a_path: str) -> bool:
        candidate_path = Path(sky130a_path).expanduser().resolve()
        if not candidate_path.exists():
            return False
        mapping = self._build_pdk_mapping(candidate_path)
        changed = False
        for key, value in mapping.items():
            if getattr(settings.pdk_paths, key) != value:
                setattr(settings.pdk_paths, key, value)
                changed = True
        return changed

    def pdk_install_preflight(self, settings: AppSettings) -> PdkInstallPreflight:
        policy = self.manifest.channel()
        target_root = Path(policy.pdk_managed_root).expanduser()
        target_sky130a = target_root / "sky130A"
        usage_root = target_root if target_root.exists() else target_root.parent if target_root.parent.exists() else Path.home()
        free_bytes = shutil.disk_usage(usage_root).free
        minimum_free_bytes = policy.pdk_minimum_free_gb * 1024 * 1024 * 1024
        enough_space = free_bytes >= minimum_free_bytes
        existing_status = self._classify_sky130a_path(target_sky130a)

        selected_candidate = ""
        selected_candidate_status = "missing"
        for candidate in self.detect_reusable_pdk_candidates():
            if Path(candidate.sky130a_path).resolve() == target_sky130a.resolve():
                continue
            if candidate.status == "present":
                selected_candidate = candidate.sky130a_path
                selected_candidate_status = candidate.status
                break

        message_parts = [
            f"target={target_sky130a}",
            f"mode={policy.pdk_managed_install_mode}",
            f"free_gb={free_bytes / (1024 ** 3):.1f}",
        ]
        if not enough_space:
            message_parts.append(f"requires_at_least={policy.pdk_minimum_free_gb}GB")
        if existing_status != "missing":
            message_parts.append(f"existing={existing_status}")
        if selected_candidate:
            message_parts.append(f"candidate={selected_candidate}")

        return PdkInstallPreflight(
            target_root=str(target_root),
            target_sky130a=str(target_sky130a),
            install_mode=policy.pdk_managed_install_mode,
            minimum_free_bytes=minimum_free_bytes,
            free_bytes=free_bytes,
            enough_space=enough_space,
            existing_status=existing_status,
            selected_candidate=selected_candidate,
            selected_candidate_status=selected_candidate_status,
            message="; ".join(message_parts),
        )

    def install_managed_pdk(self, settings: AppSettings, source_sky130a: str | None = None) -> PdkInstallResult:
        preflight = self.pdk_install_preflight(settings)
        target_path = Path(preflight.target_sky130a).expanduser()
        source_path = Path(source_sky130a or preflight.selected_candidate).expanduser() if (source_sky130a or preflight.selected_candidate) else None

        if not preflight.enough_space:
            return PdkInstallResult(
                ok=False,
                changed=False,
                target_sky130a=str(target_path),
                source_sky130a=str(source_path or ""),
                message=f"Not enough free space for managed PDK target at {target_path}.",
            )
        if source_path is None or not source_path.exists():
            return PdkInstallResult(
                ok=False,
                changed=False,
                target_sky130a=str(target_path),
                source_sky130a=str(source_path or ""),
                message="No reusable PDK candidate is available to install.",
            )
        if preflight.install_mode != "symlink":
            return PdkInstallResult(
                ok=False,
                changed=False,
                target_sky130a=str(target_path),
                source_sky130a=str(source_path),
                message=f"Unsupported managed PDK install mode: {preflight.install_mode}",
            )

        if os.path.lexists(target_path):
            try:
                if target_path.resolve() == source_path.resolve():
                    self.apply_pdk_candidate(settings, str(target_path))
                    return PdkInstallResult(
                        ok=True,
                        changed=False,
                        target_sky130a=str(target_path),
                        source_sky130a=str(source_path),
                        message="Managed PDK target already points to the selected candidate.",
                    )
            except OSError:
                pass
            return PdkInstallResult(
                ok=False,
                changed=False,
                target_sky130a=str(target_path),
                source_sky130a=str(source_path),
                message=f"Managed PDK target already exists at {target_path}.",
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.symlink_to(source_path.resolve(), target_is_directory=True)
        self.apply_pdk_candidate(settings, str(target_path))
        return PdkInstallResult(
            ok=True,
            changed=True,
            target_sky130a=str(target_path),
            source_sky130a=str(source_path.resolve()),
            message=f"Managed PDK installed at {target_path} -> {source_path.resolve()}",
        )

    def pdk_source_build_preflight(self, settings: AppSettings) -> PdkSourceBuildPreflight:
        policy = self.manifest.channel()
        build_root = Path(policy.pdk_source_build_root).expanduser()
        target_sky130a = Path(policy.pdk_managed_root).expanduser() / "sky130A"
        usage_root = build_root if build_root.exists() else build_root.parent if build_root.parent.exists() else Path.home()
        free_bytes = shutil.disk_usage(usage_root).free
        minimum_free_bytes = policy.pdk_source_build_minimum_free_gb * 1024 * 1024 * 1024
        enough_space = free_bytes >= minimum_free_bytes
        target_available = not os.path.lexists(target_sky130a)
        missing_commands = tuple(
            command for command in policy.pdk_source_build_required_commands if shutil.which(command) is None
        )
        has_required_commands = not missing_commands
        has_pinned_source = bool(policy.pdk_source_build_open_pdks_repo and policy.pdk_source_build_open_pdks_ref)
        reusable_candidate_available = any(candidate.status == "present" for candidate in self.detect_reusable_pdk_candidates())
        ready = enough_space and target_available and has_required_commands and has_pinned_source and not reusable_candidate_available
        message_parts = [
            f"build_root={build_root}",
            f"target={target_sky130a}",
            f"free_gb={free_bytes / (1024 ** 3):.1f}",
        ]
        if not enough_space:
            message_parts.append(f"requires_at_least={policy.pdk_source_build_minimum_free_gb}GB")
        if not target_available:
            message_parts.append("target_already_exists")
        if missing_commands:
            message_parts.append(f"missing_commands={','.join(missing_commands)}")
        if not has_pinned_source:
            message_parts.append("missing_pinned_source")
        if reusable_candidate_available:
            message_parts.append("reusable_candidate_detected")
        return PdkSourceBuildPreflight(
            build_root=str(build_root),
            target_sky130a=str(target_sky130a),
            minimum_free_bytes=minimum_free_bytes,
            free_bytes=free_bytes,
            enough_space=enough_space,
            target_available=target_available,
            missing_commands=missing_commands,
            has_required_commands=has_required_commands,
            has_pinned_source=has_pinned_source,
            reusable_candidate_available=reusable_candidate_available,
            ready=ready,
            message="; ".join(message_parts),
        )

    def pdk_bundle_preflight(self, settings: AppSettings) -> PdkBundlePreflight:
        policy = self.manifest.channel()
        install_root = Path(policy.pdk_bundle_install_root).expanduser()
        target_sky130a = install_root / "sky130A"
        cache_root = Path(policy.pdk_bundle_cache_root).expanduser()
        usage_root = install_root if install_root.exists() else install_root.parent if install_root.parent.exists() else Path.home()
        free_bytes = shutil.disk_usage(usage_root).free
        minimum_free_bytes = policy.pdk_bundle_minimum_free_gb * 1024 * 1024 * 1024
        enough_space = free_bytes >= minimum_free_bytes
        target_status = self._classify_sky130a_path(target_sky130a)
        target_available = not os.path.lexists(target_sky130a)
        has_asset = bool(policy.pdk_bundle_enabled and policy.pdk_bundle_asset_url and policy.pdk_bundle_asset_filename)
        ready = has_asset and enough_space and target_available

        message_parts = [
            f"bundle={policy.pdk_bundle_name}",
            f"install_root={install_root}",
            f"target={target_sky130a}",
            f"cache_root={cache_root}",
            f"free_gb={free_bytes / (1024 ** 3):.1f}",
        ]
        if policy.pdk_bundle_version:
            message_parts.append(f"version={policy.pdk_bundle_version}")
        if not policy.pdk_bundle_enabled:
            message_parts.append("bundle_disabled")
        if not policy.pdk_bundle_asset_url:
            message_parts.append("missing_asset_url")
        if not policy.pdk_bundle_asset_filename:
            message_parts.append("missing_asset_filename")
        if not enough_space:
            message_parts.append(f"requires_at_least={policy.pdk_bundle_minimum_free_gb}GB")
        if not target_available:
            message_parts.append(f"target_status={target_status}")

        return PdkBundlePreflight(
            enabled=policy.pdk_bundle_enabled,
            bundle_name=policy.pdk_bundle_name,
            bundle_version=policy.pdk_bundle_version,
            install_root=str(install_root),
            target_sky130a=str(target_sky130a),
            cache_root=str(cache_root),
            asset_url=policy.pdk_bundle_asset_url,
            asset_filename=policy.pdk_bundle_asset_filename,
            asset_sha256=policy.pdk_bundle_asset_sha256,
            minimum_free_bytes=minimum_free_bytes,
            free_bytes=free_bytes,
            enough_space=enough_space,
            target_available=target_available,
            target_status=target_status,
            ready=ready,
            message="; ".join(message_parts),
        )

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

    def _candidate_pdk_roots(self) -> list[tuple[Path, str]]:
        policy = self.manifest.channel()
        roots: list[tuple[Path, str]] = []
        configured_roots = [
            (Path(path).expanduser(), "manifest")
            for path in policy.pdk_search_roots
        ]
        roots.extend(configured_roots)
        for env_var in ("SKY130A", "PDK_ROOT"):
            raw = os.environ.get(env_var, "").strip()
            if raw:
                roots.append((Path(raw).expanduser(), f"env:{env_var}"))
        return roots

    @staticmethod
    def _find_all_sky130a_under(root: Path) -> list[Path]:
        matches: list[Path] = []
        direct = root / "sky130A"
        if direct.is_dir():
            matches.append(direct)
        for pattern in ("*/sky130A", "*/*/sky130A", "**/sky130A"):
            for match in sorted(root.glob(pattern)):
                if match.is_dir():
                    matches.append(match)
        return matches

    @staticmethod
    def _classify_sky130a_path(sky130a: Path) -> str:
        if not sky130a.exists():
            return "missing"
        missing = [relative for relative in REQUIRED_PDK_SUBDIRS.values() if not sky130a.joinpath(relative).exists()]
        return "present" if not missing else "incomplete"
