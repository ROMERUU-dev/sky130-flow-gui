"""Estimate how far a simulation has got.

ngspice prints its percentage only when it is attached to a terminal; in batch
mode, which is how the app runs it, there is nothing to parse. It does write
the raw file as it goes, though, and the header states how many variables each
point carries — so the file's own growth measures the run.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

BYTES_PER_VALUE = 8
HEADER_MARKER = b"Binary:\n"
MAX_HEADER_BYTES = 64 * 1024

_SUFFIXES = {
    "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3,
    "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18,
}


def parse_spice_number(text: str) -> float | None:
    """Read a SPICE quantity such as `10p`, `2.5meg` or `1e-9`."""
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return None
    match = re.fullmatch(r"([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)\s*([a-z]*)", cleaned)
    if not match:
        return None
    value = float(match.group(1))
    suffix = match.group(2)
    if not suffix:
        return value
    # `meg` has to be tested before `m`, and trailing unit letters are ignored.
    for name in ("meg", "t", "g", "k", "m", "u", "n", "p", "f", "a"):
        if suffix.startswith(name):
            return value * _SUFFIXES[name]
    return value


def _estimate_tran(parts: list[str]) -> int | None:
    if len(parts) < 3:
        return None
    step = parse_spice_number(parts[1])
    stop = parse_spice_number(parts[2])
    start = parse_spice_number(parts[3]) if len(parts) > 3 else 0.0
    if not step or not stop or step <= 0:
        return None
    span = stop - (start or 0.0)
    if span <= 0:
        return None
    return max(1, round(span / step) + 1)


def _estimate_ac(parts: list[str]) -> int | None:
    if len(parts) < 5:
        return None
    mode = parts[1]
    count = parse_spice_number(parts[2])
    first = parse_spice_number(parts[3])
    last = parse_spice_number(parts[4])
    if not count or not first or not last or last <= first:
        return None
    if mode.startswith("lin"):
        return max(1, round(count))
    decades = math.log10(last / first)
    spans = decades if mode.startswith("dec") else decades / math.log10(2.0)
    return max(1, round(count * spans) + 1)


def _estimate_dc(parts: list[str]) -> int | None:
    if len(parts) < 5:
        return None
    start = parse_spice_number(parts[2])
    stop = parse_spice_number(parts[3])
    step = parse_spice_number(parts[4])
    if start is None or stop is None or not step or step == 0:
        return None
    return max(1, round(abs(stop - start) / abs(step)) + 1)


def estimate_points(netlist_text: str) -> int | None:
    """Estimate the number of points the analysis will produce.

    ngspice varies its timestep, so for a transient this is an estimate rather
    than a count. It is close enough to drive a progress bar, and the fraction
    it feeds is clamped before it is shown.
    """
    if not netlist_text:
        return None
    handlers = {".tran": _estimate_tran, ".ac": _estimate_ac, ".dc": _estimate_dc}
    for raw_line in netlist_text.splitlines():
        line = raw_line.strip().lower()
        for directive, handler in handlers.items():
            if line.startswith(directive):
                estimate = handler(line.split())
                if estimate is not None:
                    return estimate
    return None


@dataclass
class RawLayout:
    """What the raw header says about the shape of the data."""

    header_bytes: int
    variables: int
    complex_values: bool = False

    @property
    def bytes_per_point(self) -> int:
        multiplier = 2 if self.complex_values else 1
        return self.variables * BYTES_PER_VALUE * multiplier


def read_raw_layout(raw_path: Path | str) -> RawLayout | None:
    """Read the header ngspice writes before it starts emitting points."""
    path = Path(raw_path)
    try:
        with path.open("rb") as handle:
            head = handle.read(MAX_HEADER_BYTES)
    except OSError:
        return None
    marker = head.find(HEADER_MARKER)
    if marker == -1:
        return None
    text = head[:marker].decode("utf-8", errors="replace")
    variables = 0
    complex_values = False
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("no. variables:"):
            try:
                variables = int(stripped.split(":", 1)[1])
            except ValueError:
                return None
        elif stripped.startswith("flags:"):
            complex_values = "complex" in stripped
    if variables < 1:
        return None
    return RawLayout(
        header_bytes=marker + len(HEADER_MARKER),
        variables=variables,
        complex_values=complex_values,
    )


class RawProgress:
    """Track a run's progress from the size of the raw file it is writing."""

    def __init__(self, raw_path: Path | str, expected_points: int | None) -> None:
        self.raw_path = Path(raw_path)
        self.expected_points = expected_points if (expected_points or 0) > 0 else None
        self._layout: RawLayout | None = None

    @property
    def measurable(self) -> bool:
        """Progress is only a percentage when the point count is known."""
        return self.expected_points is not None

    def points_written(self) -> int | None:
        """How many complete points the file holds so far."""
        if self._layout is None:
            self._layout = read_raw_layout(self.raw_path)
        if self._layout is None or self._layout.bytes_per_point <= 0:
            return None
        try:
            size = self.raw_path.stat().st_size
        except OSError:
            return None
        payload = max(0, size - self._layout.header_bytes)
        return payload // self._layout.bytes_per_point

    def fraction(self) -> float | None:
        """Completion between 0 and 1, or None while it cannot be measured."""
        if self.expected_points is None:
            return None
        written = self.points_written()
        if written is None:
            return None
        return min(1.0, max(0.0, written / self.expected_points))
