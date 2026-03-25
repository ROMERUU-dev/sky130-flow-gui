"""Parsing, EM estimation, and export helpers for the EM sizing tab."""

from __future__ import annotations

import csv
from dataclasses import asdict
import json
import math
import re
from pathlib import Path

from app.models.em_models import (
    AnalysisBundle,
    BranchAnalysis,
    BranchMetrics,
    BranchWaveform,
    EmProfile,
    MetalRule,
    ParsedWaveformFile,
    ViaRule,
)

COMMENT_PREFIXES = ("#", ";", "*", "//")
POWER_TOKENS = ("vdd", "vss", "gnd", "supply", "rail", "vpwr", "vgnd")
OUTPUT_TOKENS = ("out", "output", "pad", "io")


class EmService:
    """EM sizing service for ngspice branch current waveforms."""

    def __init__(self, profiles_path: Path | None = None) -> None:
        self.profiles_path = profiles_path or Path(__file__).resolve().parents[1] / "data" / "sky130_em_profiles.json"
        self._profiles = self._load_profiles()

    def list_profiles(self) -> list[str]:
        return sorted(self._profiles)

    def get_profile(self, name: str) -> EmProfile:
        if name not in self._profiles:
            raise ValueError(f"Unknown EM profile: {name}")
        return self._profiles[name]

    def parse_waveform_file(self, path: str | Path, probe_map_path: str | Path | None = None) -> ParsedWaveformFile:
        source_path = Path(path).expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Waveform file not found: {source_path}")

        raw_lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines()
        filtered_lines = [line.strip() for line in raw_lines if self._is_data_line(line)]
        if not filtered_lines:
            raise ValueError("No waveform data found in file.")

        delimiter = "," if any("," in line for line in filtered_lines[:3]) else "whitespace"
        rows = [self._split_line(line, delimiter) for line in filtered_lines]
        rows = [row for row in rows if row]
        if not rows:
            raise ValueError("No parseable waveform rows found in file.")

        probe_map = self._load_probe_map(probe_map_path)
        if probe_map:
            return self._parse_with_probe_map(source_path, rows, delimiter, probe_map)

        header_row = rows[0]
        has_header = self._row_looks_like_header(header_row)
        data_rows = rows[1:] if has_header else rows
        if not data_rows:
            raise ValueError("The waveform file contains a header but no numeric samples.")

        column_count = max(len(row) for row in data_rows)
        if column_count < 2:
            raise ValueError("Expected time plus at least one current column.")

        if has_header:
            headers = self._normalize_headers(header_row, column_count)
        else:
            headers = ["time"] + [f"branch_{index}" for index in range(1, column_count)]

        times: list[float] = []
        branch_samples: list[list[float]] = [[] for _ in range(column_count - 1)]
        for row_index, row in enumerate(data_rows, start=1 if has_header else 0):
            if len(row) < column_count:
                raise ValueError(f"Row {row_index + 1} has {len(row)} columns, expected {column_count}.")
            try:
                time_value = self._to_float(row[0])
            except ValueError as exc:
                raise ValueError(f"Invalid time value on row {row_index + 1}: {row[0]!r}") from exc
            times.append(time_value)

            for column_index in range(1, column_count):
                try:
                    branch_samples[column_index - 1].append(self._to_float(row[column_index]))
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid current value on row {row_index + 1}, column {column_index + 1}: {row[column_index]!r}"
                    ) from exc

        branches = [
            BranchWaveform(
                name=headers[index + 1],
                samples_a=samples,
                source_name=headers[index + 1],
                header_inferred=not has_header,
            )
            for index, samples in enumerate(branch_samples)
        ]
        return ParsedWaveformFile(
            source_path=source_path,
            time_values_s=times,
            branches=branches,
            had_header=has_header,
            detected_delimiter=delimiter,
            warnings=[],
        )

    def analyze(
        self,
        parsed: ParsedWaveformFile,
        profile_name: str,
        metric_mode: str,
        target_metal: str,
        via_type: str | None,
        margin_factor: float,
        manual_types: dict[str, str] | None = None,
    ) -> AnalysisBundle:
        profile = self.get_profile(profile_name)
        if target_metal not in profile.metals:
            raise ValueError(f"Unknown target metal: {target_metal}")
        if margin_factor <= 0:
            raise ValueError("Margin factor must be greater than zero.")

        metal_rule = profile.metals[target_metal]
        resolved_via_type = via_type if via_type and via_type != "auto" else metal_rule.default_via
        if resolved_via_type not in profile.vias:
            raise ValueError(f"Unknown via type: {resolved_via_type}")
        via_rule = profile.vias[resolved_via_type]

        branches: list[BranchAnalysis] = []
        for branch in parsed.branches:
            branch_type = (manual_types or {}).get(branch.name, self.classify_branch(branch.name))
            metrics = self.compute_metrics(branch.samples_a)
            metric_used, selected_metric = self.select_design_metric(metric_mode, branch_type, metrics)
            design_current_a = selected_metric * margin_factor
            width_required_um = self.calculate_required_width_um(design_current_a, metal_rule)
            width_final_um = self.round_up_to_grid(max(width_required_um, metal_rule.minimum_width_um), metal_rule.routing_grid_um)
            vias_required = self.calculate_via_count(design_current_a, via_rule)
            via_rows, via_cols = self.compact_array(vias_required)
            warnings = self.build_warnings(
                branch_name=branch.name,
                branch_type=branch_type,
                target_metal=target_metal,
                metrics=metrics,
                metric_mode=metric_mode,
                metric_used=metric_used,
                margin_factor=margin_factor,
                width_required_um=width_required_um,
                width_final_um=width_final_um,
                min_width_um=metal_rule.minimum_width_um,
                vias_required=vias_required,
                header_inferred=branch.header_inferred,
            )
            status = self._status_from_warnings(warnings)
            branches.append(
                BranchAnalysis(
                    branch_name=branch.name,
                    branch_type=branch_type,
                    metrics=metrics,
                    metric_mode_requested=metric_mode,
                    metric_used=metric_used,
                    selected_metric_a=selected_metric,
                    margin_factor=margin_factor,
                    design_current_a=design_current_a,
                    target_metal=target_metal,
                    via_type=resolved_via_type,
                    width_required_um=width_required_um,
                    width_final_um=width_final_um,
                    vias_required=vias_required,
                    via_rows=via_rows,
                    via_cols=via_cols,
                    status=status,
                    warnings=warnings,
                    source_name=branch.source_name,
                    source_file=str(parsed.source_path),
                )
            )

        general_warnings = [
            "Estimated EM rules only. This tab is not official foundry EM signoff.",
            profile.safety_note,
            profile.notes,
        ]
        general_warnings.extend(parsed.warnings)
        return AnalysisBundle(
            source_path=parsed.source_path,
            profile_name=profile.name,
            target_metal=target_metal,
            via_type=resolved_via_type,
            requested_metric_mode=metric_mode,
            margin_factor=margin_factor,
            branches=branches,
            general_warnings=general_warnings,
        )

    @staticmethod
    def compute_metrics(samples_a: list[float]) -> BranchMetrics:
        if not samples_a:
            raise ValueError("Cannot compute current metrics from an empty waveform.")
        count = len(samples_a)
        average_a = sum(samples_a) / count
        rms_a = math.sqrt(sum(sample * sample for sample in samples_a) / count)
        peak_abs_a = max(abs(sample) for sample in samples_a)
        return BranchMetrics(average_a=average_a, rms_a=rms_a, peak_abs_a=peak_abs_a)

    @staticmethod
    def classify_branch(name: str) -> str:
        lowered = name.lower()
        if any(token in lowered for token in POWER_TOKENS):
            return "power"
        if any(token in lowered for token in OUTPUT_TOKENS):
            return "output"
        return "signal"

    @staticmethod
    def select_design_metric(metric_mode: str, branch_type: str, metrics: BranchMetrics) -> tuple[str, float]:
        if metric_mode == "average":
            return "average", abs(metrics.average_a)
        if metric_mode == "rms":
            return "rms", metrics.rms_a
        if metric_mode == "peak":
            return "peak", metrics.peak_abs_a
        if metric_mode != "auto":
            raise ValueError(f"Unsupported metric mode: {metric_mode}")

        average_abs_a = abs(metrics.average_a)
        if branch_type == "power":
            avg_with_margin = average_abs_a * 1.25
            if metrics.rms_a >= avg_with_margin:
                return "rms", metrics.rms_a
            return "average", avg_with_margin
        if branch_type == "output":
            conservative_output = max(metrics.rms_a, 0.5 * metrics.peak_abs_a)
            if conservative_output == metrics.rms_a:
                return "rms", conservative_output
            return "peak", conservative_output
        return "rms", metrics.rms_a

    @staticmethod
    def calculate_required_width_um(design_current_a: float, metal_rule: MetalRule) -> float:
        design_current_ma = abs(design_current_a) * 1_000.0
        required_area_um2 = design_current_ma / metal_rule.allowed_current_density_ma_per_um2
        return required_area_um2 / metal_rule.thickness_um

    @staticmethod
    def calculate_via_count(design_current_a: float, via_rule: ViaRule) -> int:
        design_current_ma = abs(design_current_a) * 1_000.0
        return max(1, math.ceil(design_current_ma / via_rule.allowed_current_ma))

    @staticmethod
    def round_up_to_grid(value_um: float, grid_um: float) -> float:
        if grid_um <= 0:
            raise ValueError("Routing grid must be greater than zero.")
        steps = math.ceil(value_um / grid_um)
        return steps * grid_um

    @staticmethod
    def compact_array(via_count: int) -> tuple[int, int]:
        cols = math.ceil(math.sqrt(via_count))
        rows = math.ceil(via_count / cols)
        return rows, cols

    def export_csv(self, bundle: AnalysisBundle, destination: str | Path) -> Path:
        path = Path(destination)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "branch",
                    "type",
                    "i_avg_a",
                    "i_rms_a",
                    "i_peak_a",
                    "metric_used",
                    "i_design_a",
                    "metal",
                    "width_required_um",
                    "width_final_um",
                    "vias_required",
                    "via_array",
                    "status",
                    "warnings",
                ]
            )
            for branch in bundle.branches:
                writer.writerow(
                    [
                        branch.branch_name,
                        branch.branch_type,
                        branch.metrics.average_a,
                        branch.metrics.rms_a,
                        branch.metrics.peak_abs_a,
                        branch.metric_used,
                        branch.design_current_a,
                        branch.target_metal,
                        branch.width_required_um,
                        branch.width_final_um,
                        branch.vias_required,
                        f"{branch.via_rows}x{branch.via_cols}",
                        branch.status,
                        " | ".join(branch.warnings),
                    ]
                )
        return path

    def export_json(self, bundle: AnalysisBundle, destination: str | Path) -> Path:
        path = Path(destination)
        payload = asdict(bundle)
        payload["source_path"] = str(bundle.source_path)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def export_text_report(self, bundle: AnalysisBundle, destination: str | Path) -> Path:
        path = Path(destination)
        lines = [
            "EM Sizing Report",
            f"Source file: {bundle.source_path}",
            f"Profile: {bundle.profile_name}",
            f"Target metal: {bundle.target_metal}",
            f"Via type: {bundle.via_type}",
            f"Requested metric mode: {bundle.requested_metric_mode}",
            f"Margin factor: {bundle.margin_factor:.3f}",
            "",
            "Assumptions:",
        ]
        lines.extend(f"- {warning}" for warning in bundle.general_warnings)
        lines.append("")
        for branch in bundle.branches:
            lines.extend(
                [
                    f"Branch: {branch.branch_name}",
                    f"  Type: {branch.branch_type}",
                    f"  I_avg: {branch.metrics.average_a:.6g} A",
                    f"  I_rms: {branch.metrics.rms_a:.6g} A",
                    f"  I_peak: {branch.metrics.peak_abs_a:.6g} A",
                    f"  Metric used: {branch.metric_used}",
                    f"  I_design: {branch.design_current_a:.6g} A",
                    f"  Metal: {branch.target_metal}",
                    f"  Width required: {branch.width_required_um:.6g} um",
                    f"  Width final: {branch.width_final_um:.6g} um",
                    f"  Via recommendation: {branch.vias_required} total as {branch.via_rows}x{branch.via_cols}",
                    f"  Status: {branch.status}",
                ]
            )
            if branch.warnings:
                lines.append("  Warnings:")
                lines.extend(f"    - {warning}" for warning in branch.warnings)
            lines.append("")
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return path

    def _load_profiles(self) -> dict[str, EmProfile]:
        payload = json.loads(self.profiles_path.read_text(encoding="utf-8"))
        profiles: dict[str, EmProfile] = {}
        for name, raw_profile in payload.get("profiles", {}).items():
            metals = {
                metal_name: MetalRule(name=metal_name, **metal_data)
                for metal_name, metal_data in raw_profile.get("metals", {}).items()
            }
            vias = {
                via_name: ViaRule(name=via_name, **via_data)
                for via_name, via_data in raw_profile.get("vias", {}).items()
            }
            profiles[name] = EmProfile(
                name=name,
                notes=raw_profile.get("notes", ""),
                safety_note=raw_profile.get("safety_note", ""),
                metals=metals,
                vias=vias,
            )
        if not profiles:
            raise ValueError("No EM profiles are defined.")
        return profiles

    @staticmethod
    def _is_data_line(line: str) -> bool:
        stripped = line.strip()
        return bool(stripped) and not any(stripped.startswith(prefix) for prefix in COMMENT_PREFIXES)

    @staticmethod
    def _split_line(line: str, delimiter: str) -> list[str]:
        if delimiter == ",":
            return [cell.strip() for cell in line.split(",")]
        return re.split(r"\s+", line.strip())

    def _parse_with_probe_map(self, source_path: Path, rows: list[list[str]], delimiter: str, probe_map: dict) -> ParsedWaveformFile:
        probes = probe_map.get("probes", [])
        if not probes:
            raise ValueError("Probe map does not contain any probes.")

        warnings: list[str] = list(probe_map.get("warnings", []))
        numeric_rows: list[list[float]] = []
        start_index = 0
        if rows and self._row_looks_like_header(rows[0]):
            start_index = 1
        for row_index, row in enumerate(rows[start_index:], start=start_index + 1):
            try:
                numeric_rows.append([self._to_float(token) for token in row])
            except ValueError as exc:
                raise ValueError(f"Invalid numeric row in EM file at line {row_index}.") from exc

        expected_currents = len(probes)
        time_values: list[float] = []
        branch_samples: list[list[float]] = [[] for _ in range(expected_currents)]

        for row in numeric_rows:
            normalized_row, row_warnings = self._normalize_em_row(row, expected_currents)
            warnings.extend(row_warnings)
            time_values.append(normalized_row[0])
            for column_index in range(expected_currents):
                branch_samples[column_index].append(normalized_row[column_index + 1])

        branches = []
        for index, probe in enumerate(probes):
            base_name = probe.get("original_net") or probe.get("probe_name") or f"probe_{index + 1}"
            branch_name = f"{base_name} (manual)" if probe.get("mode") == "internal_manual" else base_name
            if probe.get("mode") == "output_driver_load":
                warnings.append(f"Output net {branch_name} instrumented using driver/load split.")
            if probe.get("mode") == "internal_manual":
                warnings.append(f"Manual instrumentation used for {base_name}; interpretation depends on selected branch.")
            warnings.extend(probe.get("warnings", []))
            branches.append(
                BranchWaveform(
                    name=branch_name,
                    samples_a=branch_samples[index],
                    source_name=str(probe.get("probe_name", branch_name)),
                    header_inferred=False,
                )
            )

        return ParsedWaveformFile(
            source_path=source_path,
            time_values_s=time_values,
            branches=branches,
            had_header=False,
            detected_delimiter=delimiter,
            warnings=sorted(set(warnings)),
        )

    @staticmethod
    def _normalize_em_row(row: list[float], expected_currents: int) -> tuple[list[float], list[str]]:
        warnings: list[str] = []
        expected_clean = expected_currents + 1
        expected_pair_with_time = 2 * (expected_currents + 1)
        expected_pair_without_time = 2 * expected_currents

        if len(row) == expected_clean:
            return row[:expected_clean], warnings
        if len(row) == expected_pair_with_time:
            warnings.append("Duplicated time columns detected and ignored during EM parsing.")
            return [row[1]] + [row[2 * index + 1] for index in range(1, expected_currents + 1)], warnings
        if len(row) == expected_pair_without_time:
            warnings.append("Duplicated time columns detected and ignored during EM parsing.")
            return [row[0]] + [row[2 * index + 1] for index in range(expected_currents)], warnings

        raise ValueError(
            f"Parsed current column count does not match the probe map. Expected {expected_currents} current columns for this EM dataset."
        )

    @staticmethod
    def _load_probe_map(probe_map_path: str | Path | None) -> dict | None:
        if probe_map_path is None:
            return None
        path = Path(probe_map_path).expanduser().resolve()
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _row_looks_like_header(row: list[str]) -> bool:
        for cell in row:
            try:
                EmService._to_float(cell)
            except ValueError:
                return True
        return False

    @staticmethod
    def _normalize_headers(header_row: list[str], column_count: int) -> list[str]:
        headers = list(header_row[:column_count])
        while len(headers) < column_count:
            headers.append(f"branch_{len(headers)}")
        if not headers[0]:
            headers[0] = "time"
        for index in range(1, len(headers)):
            if not headers[index]:
                headers[index] = f"branch_{index}"
        return headers

    @staticmethod
    def _to_float(token: str) -> float:
        cleaned = token.strip()
        if cleaned.lower().startswith("i(") and cleaned.endswith(")"):
            raise ValueError("Branch label is not numeric")
        return float(cleaned)

    @staticmethod
    def build_warnings(
        *,
        branch_name: str,
        branch_type: str,
        target_metal: str,
        metrics: BranchMetrics,
        metric_mode: str,
        metric_used: str,
        margin_factor: float,
        width_required_um: float,
        width_final_um: float,
        min_width_um: float,
        vias_required: int,
        header_inferred: bool,
    ) -> list[str]:
        warnings = ["Estimated EM sizing only; verify against official signoff data."]
        average_abs_a = abs(metrics.average_a)
        peak_to_avg = math.inf if average_abs_a == 0 and metrics.peak_abs_a > 0 else 0.0
        if average_abs_a > 0:
            peak_to_avg = metrics.peak_abs_a / average_abs_a

        if peak_to_avg >= 5.0:
            warnings.append("High peak/average ratio; current is strongly pulsed.")
        if metrics.rms_a > 0 and metrics.peak_abs_a / metrics.rms_a >= 2.0:
            warnings.append("Peak current is much larger than RMS current.")
        if margin_factor < 1.10:
            warnings.append("Margin factor is low for a conservative routing estimate.")
        if width_required_um < min_width_um or math.isclose(width_final_um, min_width_um, rel_tol=0.0, abs_tol=1e-9):
            warnings.append("Final width is constrained by minimum DRC width.")
        if vias_required == 1:
            warnings.append("Single via recommendation; consider extra vias for robustness if area allows.")
        if header_inferred:
            warnings.append("Branch label was inferred because the file had no header.")
        if branch_type == "signal" and metric_mode == "auto" and peak_to_avg >= 3.0:
            warnings.append("Auto metric used RMS on a peaky signal branch; review peak events manually.")
        if branch_type == "signal" and branch_name.lower().startswith("branch_"):
            warnings.append("Branch classification may be uncertain due to generic branch naming.")
        if metric_used == "peak":
            warnings.append("Peak-based sizing can be pessimistic for sustained routing area.")
        if branch_type == "power" and target_metal in {"li1", "met1"}:
            warnings.append("Power net is routed on a low metal layer. Consider met3/met4.")
        return warnings

    @staticmethod
    def _status_from_warnings(warnings: list[str]) -> str:
        if len(warnings) >= 5:
            return "review"
        if len(warnings) >= 3:
            return "caution"
        return "ok"
