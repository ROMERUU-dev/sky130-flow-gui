"""Parse ngspice raw waveform files for the simulation viewer."""

from __future__ import annotations

from pathlib import Path

import numpy


class NgspiceRawParser:
    """Load real and complex ngspice binary raw files."""

    @staticmethod
    def load_signals(raw_path: str | Path) -> dict[str, tuple[list[float], list[float]]]:
        path = Path(raw_path)
        data = path.read_bytes()

        marker = b"Binary:\n"
        marker_idx = data.find(marker)
        if marker_idx == -1:
            raise ValueError(f"Unsupported ngspice raw format in {path}")

        header_text = data[:marker_idx].decode(errors="replace")
        header = NgspiceRawParser._parse_header(header_text)
        flags = str(header["flags"])
        if flags not in {"real", "complex"}:
            raise ValueError(f"Unsupported ngspice flags '{header['flags']}' in {path}")

        num_vars = header["num_variables"]
        num_points = header["num_points"]
        if num_vars < 2 or num_points < 1:
            return {}

        payload = data[marker_idx + len(marker) :]
        value_size = 8 if flags == "real" else 16
        expected_size = num_vars * num_points * value_size
        if len(payload) < expected_size:
            raise ValueError(f"Incomplete raw payload in {path}")

        signals: dict[str, tuple[list[float], list[float]]] = {}
        names = header["variables"]
        x_name = names[0]

        # A transient run easily produces a few hundred thousand points across
        # a dozen traces.  Unpacking that with struct into Python lists cost
        # seconds and a lot of memory, so the payload is read as one array and
        # sliced per variable.
        raw = numpy.frombuffer(payload, dtype="<f8", count=num_vars * num_points * (value_size // 8))

        if flags == "real":
            table = raw.reshape(num_points, num_vars)
            x_values = table[:, 0].tolist()
            for index, name in enumerate(names[1:], start=1):
                signals[name] = (x_values, table[:, index].tolist())
        else:
            table = raw.reshape(num_points, num_vars * 2)
            x_values = table[:, 0].tolist()
            for index, name in enumerate(names[1:], start=1):
                real = table[:, index * 2]
                imag = table[:, index * 2 + 1]
                magnitude = numpy.hypot(real, imag)
                decibels = 20.0 * numpy.log10(numpy.maximum(magnitude, 1e-30))
                signals[f"mag({name})"] = (x_values, decibels.tolist())
                signals[f"phase({name})"] = (x_values, numpy.degrees(numpy.arctan2(imag, real)).tolist())

        # Expose the independent variable too in case the user wants to inspect it directly.
        signals[x_name] = (list(range(len(x_values))), x_values)
        return signals

    @staticmethod
    def _parse_header(header_text: str) -> dict[str, object]:
        lines = header_text.splitlines()
        variables: list[str] = []
        num_variables = 0
        num_points = 0
        flags = ""
        in_variables = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Flags:"):
                flags = stripped.split(":", 1)[1].strip().lower()
            elif stripped.startswith("No. Variables:"):
                num_variables = int(stripped.split(":", 1)[1].strip())
            elif stripped.startswith("No. Points:"):
                num_points = int(stripped.split(":", 1)[1].strip())
            elif stripped == "Variables:":
                in_variables = True
            elif in_variables and stripped:
                parts = stripped.split()
                if len(parts) >= 3:
                    variables.append(parts[1])
                    if len(variables) >= num_variables:
                        in_variables = False

        if not variables or len(variables) != num_variables:
            raise ValueError("Could not parse ngspice variable table")

        return {
            "flags": flags,
            "num_variables": num_variables,
            "num_points": num_points,
            "variables": variables,
        }
