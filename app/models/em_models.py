"""Typed models for EM sizing analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


BranchType = str
MetricMode = str


@dataclass(frozen=True)
class MetalRule:
    """Estimated EM and geometry settings for one metal layer."""

    name: str
    thickness_um: float
    minimum_width_um: float
    routing_grid_um: float
    allowed_current_density_ma_per_um2: float
    default_via: str


@dataclass(frozen=True)
class ViaRule:
    """Estimated allowable current for one via option."""

    name: str
    allowed_current_ma: float


@dataclass(frozen=True)
class EmProfile:
    """User-selectable EM estimation profile."""

    name: str
    notes: str
    safety_note: str
    metals: dict[str, MetalRule]
    vias: dict[str, ViaRule]


@dataclass(frozen=True)
class BranchWaveform:
    """Parsed current waveform samples for one branch."""

    name: str
    samples_a: list[float]
    source_name: str
    header_inferred: bool = True


@dataclass(frozen=True)
class BranchMetrics:
    """Current metrics computed from a branch waveform."""

    average_a: float
    rms_a: float
    peak_abs_a: float


@dataclass(frozen=True)
class ParsedWaveformFile:
    """Parsed waveform file content."""

    source_path: Path
    time_values_s: list[float]
    branches: list[BranchWaveform]
    had_header: bool
    detected_delimiter: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BranchAnalysis:
    """Sizing result for one current branch."""

    branch_name: str
    branch_type: BranchType
    metrics: BranchMetrics
    metric_mode_requested: MetricMode
    metric_used: MetricMode
    selected_metric_a: float
    margin_factor: float
    design_current_a: float
    target_metal: str
    via_type: str
    width_required_um: float
    width_final_um: float
    vias_required: int
    via_rows: int
    via_cols: int
    status: str
    warnings: list[str] = field(default_factory=list)
    source_name: str = ""
    source_file: str = ""


@dataclass(frozen=True)
class AnalysisBundle:
    """Top-level analysis payload used by the UI and exports."""

    source_path: Path
    profile_name: str
    target_metal: str
    via_type: str
    requested_metric_mode: MetricMode
    margin_factor: float
    branches: list[BranchAnalysis]
    general_warnings: list[str]
