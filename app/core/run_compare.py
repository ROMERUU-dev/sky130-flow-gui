"""Compare the signals of two runs.

Two runs rarely land on the same time points: a different timestep, a longer
sweep, or a post-layout netlist with extra parasitics all shift the sample
grid. Comparing sample-by-sample would report differences that are only an
artefact of that, so the reference is resampled onto the axis of the run being
inspected before anything is subtracted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy

Signals = dict[str, tuple[list[float], list[float]]]


@dataclass(frozen=True)
class SignalDelta:
    """How far one signal moved between two runs."""

    name: str
    max_abs_delta: float
    rms_delta: float
    reference_span: float
    overlap_start: float
    overlap_end: float
    samples: int

    @property
    def relative(self) -> float:
        """Largest deviation as a fraction of the reference's own swing."""
        if self.reference_span <= 0:
            return 0.0
        return self.max_abs_delta / self.reference_span

    def describe(self) -> str:
        return f"{self.name}: Δmax {self.max_abs_delta:.4g}, RMS {self.rms_delta:.4g} ({self.relative * 100:.2f}%)"


@dataclass(frozen=True)
class RunComparison:
    """Outcome of comparing a run against a reference run."""

    deltas: tuple[SignalDelta, ...] = ()
    only_in_current: tuple[str, ...] = ()
    only_in_reference: tuple[str, ...] = ()

    @property
    def shared_names(self) -> tuple[str, ...]:
        return tuple(delta.name for delta in self.deltas)

    def worst(self) -> SignalDelta | None:
        """The signal that moved most, relative to its own swing."""
        if not self.deltas:
            return None
        return max(self.deltas, key=lambda delta: delta.relative)

    def identical(self, tolerance: float = 1e-12) -> bool:
        return all(delta.max_abs_delta <= tolerance for delta in self.deltas)


def _is_index_axis(x_values: list[float]) -> bool:
    """True when the X values are a plain 0,1,2,... index.

    The raw parser re-exposes the independent variable as a trace plotted
    against its own sample index. Comparing that against another run measures
    nothing but the sample count.
    """
    if len(x_values) < 2:
        return False
    axis = numpy.asarray(x_values, dtype=float)
    return bool(numpy.array_equal(axis, numpy.arange(axis.size, dtype=float)))


def _comparable(name: str, signals: Signals) -> bool:
    """Skip the independent variable, which is an axis rather than a trace."""
    x_values, y_values = signals[name]
    if len(x_values) < 2 or len(y_values) < 2:
        return False
    return not _is_index_axis(x_values)


def compare_signal(
    current: tuple[list[float], list[float]],
    reference: tuple[list[float], list[float]],
    name: str,
) -> SignalDelta | None:
    """Resample the reference onto the current axis and measure the gap."""
    current_x = numpy.asarray(current[0], dtype=float)
    current_y = numpy.asarray(current[1], dtype=float)
    reference_x = numpy.asarray(reference[0], dtype=float)
    reference_y = numpy.asarray(reference[1], dtype=float)

    if current_x.size < 2 or reference_x.size < 2:
        return None

    # Only the region both runs actually cover can be compared.
    start = max(float(current_x.min()), float(reference_x.min()))
    end = min(float(current_x.max()), float(reference_x.max()))
    if not (end > start):
        return None

    window = (current_x >= start) & (current_x <= end)
    axis = current_x[window]
    if axis.size < 2:
        return None

    # numpy.interp needs an increasing axis; a sweep may be stored descending.
    order = numpy.argsort(reference_x)
    resampled = numpy.interp(axis, reference_x[order], reference_y[order])
    delta = current_y[window] - resampled

    span = float(reference_y.max() - reference_y.min())
    return SignalDelta(
        name=name,
        max_abs_delta=float(numpy.abs(delta).max()),
        rms_delta=float(numpy.sqrt(numpy.mean(delta * delta))),
        reference_span=span,
        overlap_start=start,
        overlap_end=end,
        samples=int(axis.size),
    )


def compare_runs(current: Signals, reference: Signals) -> RunComparison:
    """Compare every signal the two runs have in common."""
    if not current or not reference:
        return RunComparison(
            only_in_current=tuple(sorted(current or {})),
            only_in_reference=tuple(sorted(reference or {})),
        )

    shared = sorted(set(current) & set(reference))
    deltas = []
    for name in shared:
        if not (_comparable(name, current) and _comparable(name, reference)):
            continue
        delta = compare_signal(current[name], reference[name], name)
        if delta is not None:
            deltas.append(delta)

    deltas.sort(key=lambda item: item.relative, reverse=True)
    return RunComparison(
        deltas=tuple(deltas),
        only_in_current=tuple(sorted(set(current) - set(reference))),
        only_in_reference=tuple(sorted(set(reference) - set(current))),
    )
