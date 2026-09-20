"""Tests for raw-file parsing and waveform analysis."""

from __future__ import annotations

import math
import struct
import tempfile
import unittest
from pathlib import Path

from app.core.ngspice_raw_parser import NgspiceRawParser
from app.core.spice_tools import analyze_signal, compute_spectrum


def _write_raw(path: Path, names: list[str], rows: list[list[float]], flags: str = "real") -> None:
    header = [
        "Title: test",
        "Date: now",
        "Plotname: Transient Analysis",
        f"Flags: {flags}",
        f"No. Variables: {len(names)}",
        f"No. Points: {len(rows)}",
        "Variables:",
    ]
    for index, name in enumerate(names):
        header.append(f"\t{index}\t{name}\t{'time' if index == 0 else 'voltage'}")
    header.append("Binary:")
    payload = bytearray()
    for row in rows:
        payload += struct.pack(f"<{len(row)}d", *row)
    path.write_bytes("\n".join(header).encode() + b"\n" + bytes(payload))


class NgspiceRawParserTest(unittest.TestCase):
    def test_real_traces_are_parsed_per_variable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = Path(tmpdir) / "out.raw"
            rows = [[i * 1e-9, float(i), float(-i)] for i in range(64)]
            _write_raw(raw, ["time", "v(a)", "v(b)"], rows)

            signals = NgspiceRawParser.load_signals(raw)

        self.assertEqual(set(signals), {"time", "v(a)", "v(b)"})
        x_values, a_values = signals["v(a)"]
        self.assertEqual(len(x_values), 64)
        self.assertAlmostEqual(x_values[10], 10e-9)
        self.assertAlmostEqual(a_values[10], 10.0)
        self.assertAlmostEqual(signals["v(b)"][1][10], -10.0)

    def test_complex_traces_expand_to_magnitude_and_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = Path(tmpdir) / "ac.raw"
            # frequency (real, imag), then one variable with real=3, imag=4
            rows = [[float(i + 1), 0.0, 3.0, 4.0] for i in range(8)]
            _write_raw(raw, ["frequency", "v(out)"], rows, flags="complex")

            signals = NgspiceRawParser.load_signals(raw)

        self.assertIn("mag(v(out))", signals)
        self.assertIn("phase(v(out))", signals)
        # |3+4j| = 5 -> 20*log10(5)
        self.assertAlmostEqual(signals["mag(v(out))"][1][0], 20.0 * math.log10(5.0), places=9)
        self.assertAlmostEqual(signals["phase(v(out))"][1][0], math.degrees(math.atan2(4.0, 3.0)), places=9)

    def test_truncated_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = Path(tmpdir) / "short.raw"
            _write_raw(raw, ["time", "v(a)"], [[0.0, 0.0]])
            data = raw.read_bytes()
            raw.write_bytes(data[:-4])

            with self.assertRaises(ValueError):
                NgspiceRawParser.load_signals(raw)


class SpectrumTest(unittest.TestCase):
    @staticmethod
    def _tone(frequency: float, points: int = 8192, dt: float = 2e-9):
        x = [i * dt for i in range(points)]
        y = [math.sin(2.0 * math.pi * frequency * t) for t in x]
        return x, y

    def test_dominant_frequency_is_recovered(self) -> None:
        x, y = self._tone(2.4e6)

        spectrum = compute_spectrum(x, y)

        self.assertIsNotNone(spectrum.dominant_frequency_hz)
        self.assertLess(abs(spectrum.dominant_frequency_hz - 2.4e6) / 2.4e6, 0.01)

    def test_resolution_is_finer_than_the_old_512_sample_cap(self) -> None:
        """The FFT keeps far more of the trace than the quadratic DFT could."""
        x, y = self._tone(2.4e6)

        spectrum = compute_spectrum(x, y)

        self.assertGreater(len(spectrum.frequencies), 512)
        self.assertEqual(len(spectrum.frequencies), len(spectrum.magnitudes))

    def test_short_traces_return_empty_spectra(self) -> None:
        spectrum = compute_spectrum([0.0, 1.0], [0.0, 1.0])

        self.assertEqual(spectrum.frequencies, [])
        self.assertIsNone(spectrum.dominant_frequency_hz)

    def test_flat_time_axis_is_rejected(self) -> None:
        spectrum = compute_spectrum([0.0] * 32, [1.0] * 32)

        self.assertEqual(spectrum.frequencies, [])


class AnalyzeSignalTest(unittest.TestCase):
    def test_metrics_match_closed_form_values_for_a_sine(self) -> None:
        # An exact number of cycles in the window, so RMS has a closed form.
        points, dt = 4096, 2e-9
        frequency = 16.0 / (points * dt)
        x = [i * dt for i in range(points)]
        y = [math.sin(2.0 * math.pi * frequency * t) for t in x]

        metrics, _spectrum = analyze_signal(x, y, x_label="time")

        self.assertAlmostEqual(metrics.rms, 1.0 / math.sqrt(2.0), places=3)
        self.assertAlmostEqual(metrics.peak_to_peak, 2.0, places=3)
        self.assertAlmostEqual(metrics.amplitude, 1.0, places=3)
        self.assertLess(abs(metrics.frequency_hz - frequency) / frequency, 0.01)

    def test_phase_against_a_shifted_reference(self) -> None:
        points, dt = 4096, 2e-9
        frequency = 16.0 / (points * dt)
        shift = 0.6
        x = [i * dt for i in range(points)]
        y = [math.sin(2.0 * math.pi * frequency * t) for t in x]
        reference = [math.sin(2.0 * math.pi * frequency * t - shift) for t in x]

        metrics, _spectrum = analyze_signal(x, y, x_label="time", reference=(x, reference))

        self.assertIsNotNone(metrics.phase_deg)
        # A partial final cycle leaks a little into the neighbouring bins.
        self.assertAlmostEqual(metrics.phase_deg, math.degrees(shift), delta=0.5)

    def test_two_samples_are_not_enough(self) -> None:
        with self.assertRaises(ValueError):
            analyze_signal([0.0, 1.0], [0.0])


if __name__ == "__main__":
    unittest.main()
