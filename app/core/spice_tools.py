"""Helpers for temporary simulation netlists and basic waveform analysis."""

from __future__ import annotations

import cmath
import math
import re
from dataclasses import dataclass


ANALYSIS_DIRECTIVES = (".tran", ".ac", ".dc", ".save", ".plot", ".print", ".four")
DEVICE_NODE_COUNTS = {
    "r": 2,
    "c": 2,
    "l": 2,
    "d": 2,
    "v": 2,
    "i": 2,
    "e": 4,
    "g": 4,
    "f": 2,
    "h": 2,
    "q": 3,
    "j": 3,
    "m": 4,
    "t": 4,
}
PHASE_EPSILON = 1e-12


@dataclass(frozen=True)
class SpectrumData:
    frequencies: list[float]
    magnitudes: list[float]
    dominant_frequency_hz: float | None


@dataclass(frozen=True)
class SignalMetrics:
    x_label: str
    minimum: float
    maximum: float
    mean: float
    rms: float
    peak_to_peak: float
    amplitude: float
    frequency_hz: float | None
    period_s: float | None
    phase_deg: float | None


def extract_candidate_points(netlist_text: str) -> list[str]:
    """Return a best-effort list of node names found in the netlist."""
    found: set[str] = set()

    for raw_line in netlist_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("*") or line.startswith(";") or line.startswith("."):
            continue

        tokens = line.split()
        if len(tokens) < 3:
            continue

        prefix = tokens[0][0].lower()
        count = DEVICE_NODE_COUNTS.get(prefix)
        if prefix == "x":
            stop = len(tokens)
            for idx, token in enumerate(tokens[1:], start=1):
                if "=" in token:
                    stop = idx
                    break
            candidate_tokens = tokens[1 : max(1, stop - 1)]
        elif count:
            candidate_tokens = tokens[1 : 1 + count]
        else:
            candidate_tokens = []

        for token in candidate_tokens:
            normalized = token.strip("(),")
            if _is_valid_node_name(normalized):
                found.add(normalized)

    return sorted(found)


def build_generated_netlist(
    source_text: str,
    analysis_type: str,
    analysis_params: dict[str, str],
    save_points: list[str],
    extra_directives: str,
) -> str:
    """Inject generated analysis directives into a temporary simulation netlist."""
    cleaned_lines: list[str] = []
    inserted = False

    for line in source_text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith(ANALYSIS_DIRECTIVES):
            continue
        if not inserted and stripped == ".end":
            cleaned_lines.extend(_generated_directives(analysis_type, analysis_params, save_points, extra_directives))
            inserted = True
        cleaned_lines.append(line)

    if not inserted:
        cleaned_lines.extend(_generated_directives(analysis_type, analysis_params, save_points, extra_directives))
        cleaned_lines.append(".end")

    return "\n".join(cleaned_lines).rstrip() + "\n"


def analyze_signal(
    x_values: list[float],
    y_values: list[float],
    x_label: str = "time",
    reference: tuple[list[float], list[float]] | None = None,
) -> tuple[SignalMetrics, SpectrumData]:
    """Compute practical time-domain metrics and a simple frequency spectrum."""
    if len(x_values) < 2 or len(y_values) < 2:
        raise ValueError("Not enough samples to analyze the signal")

    count = min(len(x_values), len(y_values))
    x = [float(value) for value in x_values[:count]]
    y = [float(value) for value in y_values[:count]]

    y_min = min(y)
    y_max = max(y)
    mean = sum(y) / len(y)
    rms = math.sqrt(sum(value * value for value in y) / len(y))
    peak_to_peak = y_max - y_min
    amplitude = peak_to_peak / 2.0

    is_time_domain = x_label.lower() == "time"
    frequency = _estimate_frequency_zero_crossings(x, y, mean) if is_time_domain else None
    spectrum = compute_spectrum(x, y) if is_time_domain else SpectrumData([], [], None)
    if is_time_domain and frequency is None:
        frequency = spectrum.dominant_frequency_hz

    period = (1.0 / frequency) if frequency and frequency > 0 else None
    phase = None
    if is_time_domain and reference and frequency and frequency > 0:
        phase = _estimate_phase(y, reference[1], x, frequency)

    metrics = SignalMetrics(
        x_label=x_label,
        minimum=y_min,
        maximum=y_max,
        mean=mean,
        rms=rms,
        peak_to_peak=peak_to_peak,
        amplitude=amplitude,
        frequency_hz=frequency,
        period_s=period,
        phase_deg=phase,
    )
    return metrics, spectrum


def compute_spectrum(x_values: list[float], y_values: list[float], max_samples: int = 512) -> SpectrumData:
    """Compute a lightweight DFT for display and dominant-frequency detection."""
    count = min(len(x_values), len(y_values))
    if count < 4:
        return SpectrumData([], [], None)

    x = [float(value) for value in x_values[:count]]
    y = [float(value) for value in y_values[:count]]
    step = max(1, math.ceil(count / max_samples))
    sampled_x = x[::step]
    sampled_y = y[::step]
    if len(sampled_x) < 4:
        return SpectrumData([], [], None)

    trimmed_length = _largest_power_of_two(len(sampled_y))
    sampled_x = sampled_x[:trimmed_length]
    sampled_y = sampled_y[:trimmed_length]
    if trimmed_length < 4:
        return SpectrumData([], [], None)

    mean = sum(sampled_y) / trimmed_length
    centered = [value - mean for value in sampled_y]
    dt = (sampled_x[-1] - sampled_x[0]) / max(trimmed_length - 1, 1)
    if dt <= 0:
        return SpectrumData([], [], None)

    frequencies: list[float] = []
    magnitudes: list[float] = []
    dominant_frequency = None
    dominant_magnitude = -1.0

    half = trimmed_length // 2
    for index in range(1, half):
        coeff = 0j
        for sample_index, sample in enumerate(centered):
            angle = -2.0 * math.pi * index * sample_index / trimmed_length
            coeff += sample * cmath.exp(1j * angle)

        magnitude = abs(coeff) / trimmed_length
        frequency = index / (trimmed_length * dt)
        frequencies.append(frequency)
        magnitudes.append(magnitude)

        if magnitude > dominant_magnitude:
            dominant_magnitude = magnitude
            dominant_frequency = frequency

    return SpectrumData(frequencies, magnitudes, dominant_frequency)


def normalize_save_point(point: str) -> str:
    """Convert a node name into a .save-compatible ngspice expression."""
    cleaned = point.strip()
    if not cleaned:
        return ""
    if "(" in cleaned and ")" in cleaned:
        return cleaned
    return f"v({cleaned})"


def format_value(value: float | None, unit: str = "", precision: int = 5) -> str:
    """Pretty-print measurements with compact engineering prefixes."""
    if value is None or math.isnan(value) or math.isinf(value):
        return "N/A"
    magnitude = abs(value)
    prefixes = [
        (1e9, "G"),
        (1e6, "M"),
        (1e3, "k"),
        (1.0, ""),
        (1e-3, "m"),
        (1e-6, "u"),
        (1e-9, "n"),
        (1e-12, "p"),
    ]
    for factor, prefix in prefixes:
        if magnitude >= factor or factor == 1e-12:
            scaled = value / factor
            return f"{scaled:.{precision}g} {prefix}{unit}".strip()
    return f"{value:.{precision}g} {unit}".strip()


def _generated_directives(
    analysis_type: str,
    analysis_params: dict[str, str],
    save_points: list[str],
    extra_directives: str,
) -> list[str]:
    directives = [
        "",
        "* Generated by SKY130 Flow GUI simulation editor",
        ".option filetype=binary",
    ]

    filtered_points = [normalize_save_point(point) for point in save_points if normalize_save_point(point)]
    save_mode = analysis_params.get("save_mode", "All signals")
    if save_mode == "Selected probes only" and filtered_points:
        directives.append(".save " + " ".join(filtered_points))
    else:
        directives.append(".save all")

    temperature = analysis_params.get("temp_c", "").strip()
    if temperature:
        directives.append(f".temp {temperature}")

    if analysis_type == "AC":
        sweep = analysis_params.get("ac_sweep", "dec")
        points = analysis_params.get("ac_points", "20")
        start = analysis_params.get("ac_start", "1")
        stop = analysis_params.get("ac_stop", "1e9")
        directives.append(f".ac {sweep} {points} {start} {stop}")
    elif analysis_type == "DC":
        source = analysis_params.get("dc_source", "V1")
        start = analysis_params.get("dc_start", "0")
        stop = analysis_params.get("dc_stop", "1.8")
        step = analysis_params.get("dc_step", "0.01")
        directives.append(f".dc {source} {start} {stop} {step}")
    elif analysis_type == "Operating Point":
        directives.append(".op")
    else:
        step = analysis_params.get("tran_step", "1n")
        stop = analysis_params.get("tran_stop", "1u")
        start = analysis_params.get("tran_start", "").strip()
        use_uic = analysis_params.get("tran_uic", "").strip()
        if start:
            directive = f".tran {step} {stop} {start}"
        else:
            directive = f".tran {step} {stop}"
        if use_uic:
            directive += " uic"
        directives.append(directive)

    extra = extra_directives.strip()
    if extra:
        directives.extend(extra.splitlines())

    return directives


def _estimate_frequency_zero_crossings(x_values: list[float], y_values: list[float], mean: float) -> float | None:
    crossings: list[float] = []
    for index in range(1, len(y_values)):
        prev = y_values[index - 1] - mean
        curr = y_values[index] - mean
        if prev <= 0 < curr:
            x0 = x_values[index - 1]
            x1 = x_values[index]
            denom = curr - prev
            if denom == 0:
                crossings.append(x1)
            else:
                ratio = (-prev) / denom
                crossings.append(x0 + ratio * (x1 - x0))

    if len(crossings) < 2:
        return None

    periods = [curr - prev for prev, curr in zip(crossings, crossings[1:]) if curr > prev]
    if len(periods) < 2:
        return None

    avg_period = sum(periods) / len(periods)
    return (1.0 / avg_period) if avg_period > 0 else None


def _estimate_phase(
    y_values: list[float],
    ref_values: list[float],
    x_values: list[float],
    frequency_hz: float,
) -> float | None:
    count = min(len(y_values), len(ref_values), len(x_values))
    if count < 4:
        return None

    dt = (x_values[count - 1] - x_values[0]) / max(count - 1, 1)
    if dt <= 0:
        return None

    cycles = frequency_hz * count * dt
    if cycles <= 0:
        return None

    index = max(1, round(cycles))
    signal_coeff = 0j
    ref_coeff = 0j
    signal_mean = sum(y_values[:count]) / count
    ref_mean = sum(ref_values[:count]) / count
    for sample_index in range(count):
        angle = -2.0 * math.pi * index * sample_index / count
        factor = cmath.exp(1j * angle)
        signal_coeff += (y_values[sample_index] - signal_mean) * factor
        ref_coeff += (ref_values[sample_index] - ref_mean) * factor

    if abs(signal_coeff) < PHASE_EPSILON or abs(ref_coeff) < PHASE_EPSILON:
        return None

    phase = math.degrees(cmath.phase(signal_coeff) - cmath.phase(ref_coeff))
    while phase <= -180.0:
        phase += 360.0
    while phase > 180.0:
        phase -= 360.0
    return phase


def _largest_power_of_two(value: int) -> int:
    power = 1
    while power * 2 <= value:
        power *= 2
    return power


def _is_valid_node_name(token: str) -> bool:
    return bool(token) and token not in {"0", "gnd"} and re.fullmatch(r"[A-Za-z0-9_:/#$.+-]+", token) is not None


def apply_model_corner(source_text: str, corner: str) -> str:
    """Rewrite a SKY130 .lib corner selector when present."""
    target_corner = corner.strip().lower()
    if target_corner not in {"tt", "ss", "ff", "sf", "fs"}:
        return source_text

    updated_lines: list[str] = []
    for line in source_text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith(".lib ") and "sky130.lib.spice" in lowered:
            parts = stripped.split()
            if len(parts) >= 3:
                parts[-1] = target_corner
                indent = line[: len(line) - len(line.lstrip())]
                updated_lines.append(indent + " ".join(parts))
                continue
        updated_lines.append(line)
    return "\n".join(updated_lines)
