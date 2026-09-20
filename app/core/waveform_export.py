"""Export parsed waveforms as CSV.

The viewer could already save a picture of a plot, which is no use when the
numbers have to go into a report, a spreadsheet or another tool.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path


def build_csv(
    signals: dict[str, tuple[list[float], list[float]]],
    names: list[str],
    x_label: str = "x",
) -> str:
    """Render the named traces as CSV text.

    Traces that share an X axis are written as one table with a single X
    column. When they do not line up, each trace gets its own X column so
    nothing is silently resampled or truncated.
    """
    selected = [name for name in names if name in signals]
    if not selected:
        raise ValueError("No signals were selected for export")

    columns: list[tuple[str, list[float]]] = []
    reference_x = signals[selected[0]][0]
    shared = all(
        len(signals[name][0]) == len(reference_x)
        and _axes_match(signals[name][0], reference_x)
        for name in selected
    )

    if shared:
        columns.append((x_label, list(reference_x)))
        for name in selected:
            columns.append((name, list(signals[name][1])))
    else:
        for name in selected:
            x_values, y_values = signals[name]
            columns.append((f"{x_label}[{name}]", list(x_values)))
            columns.append((name, list(y_values)))

    depth = max(len(values) for _header, values in columns)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([header for header, _values in columns])
    for row_index in range(depth):
        writer.writerow(
            [
                _format(values[row_index]) if row_index < len(values) else ""
                for _header, values in columns
            ]
        )
    return buffer.getvalue()


def write_csv(
    path: str | Path,
    signals: dict[str, tuple[list[float], list[float]]],
    names: list[str],
    x_label: str = "x",
) -> Path:
    """Write the named traces to ``path`` and return the resolved path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_csv(signals, names, x_label=x_label), encoding="utf-8")
    return target


def _axes_match(candidate: list[float], reference: list[float]) -> bool:
    """Compare two X axes by their endpoints, which is enough for one run."""
    if not candidate or not reference:
        return candidate == reference
    return candidate[0] == reference[0] and candidate[-1] == reference[-1]


def _format(value: float) -> str:
    """Keep full double precision without printing noise for round numbers."""
    return repr(float(value))
