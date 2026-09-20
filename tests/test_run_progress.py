"""Tests for estimating how far a simulation has got."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from app.core.run_progress import (
    RawProgress,
    estimate_points,
    parse_spice_number,
    read_raw_layout,
)


def _write_raw(path: Path, variables: int, points: int, flags: str = "real") -> None:
    header = [
        "Title: test",
        "Date: now",
        "Plotname: Transient Analysis",
        f"Flags: {flags}",
        f"No. Variables: {variables}",
        "No. Points: 0",
        "Variables:",
    ]
    for index in range(variables):
        header.append(f"\t{index}\tv{index}\tvoltage")
    header.append("Binary:")
    values_per_point = variables * (2 if flags == "complex" else 1)
    payload = bytearray()
    for _ in range(points):
        payload += struct.pack(f"<{values_per_point}d", *([0.0] * values_per_point))
    path.write_bytes("\n".join(header).encode() + b"\n" + bytes(payload))


class ParseSpiceNumberTest(unittest.TestCase):
    def test_engineering_suffixes(self) -> None:
        self.assertEqual(parse_spice_number("10p"), 1e-11)
        self.assertEqual(parse_spice_number("1n"), 1e-9)
        self.assertEqual(parse_spice_number("2.5k"), 2500.0)

    def test_meg_is_not_read_as_milli(self) -> None:
        """`m` is milli and `meg` is mega; testing `m` first would be wrong."""
        self.assertEqual(parse_spice_number("1meg"), 1e6)
        self.assertEqual(parse_spice_number("1m"), 1e-3)

    def test_scientific_notation(self) -> None:
        self.assertEqual(parse_spice_number("1e-9"), 1e-9)
        self.assertEqual(parse_spice_number("-2.5E3"), -2500.0)

    def test_trailing_units_are_ignored(self) -> None:
        self.assertAlmostEqual(parse_spice_number("10ns"), 1e-8)
        self.assertAlmostEqual(parse_spice_number("5uF"), 5e-6)

    def test_nonsense_returns_nothing(self) -> None:
        self.assertIsNone(parse_spice_number(""))
        self.assertIsNone(parse_spice_number("abc"))
        self.assertIsNone(parse_spice_number(None))


class EstimatePointsTest(unittest.TestCase):
    def test_transient(self) -> None:
        self.assertEqual(estimate_points(".tran 2n 4u"), 2001)

    def test_transient_with_a_start_time(self) -> None:
        self.assertEqual(estimate_points(".tran 1n 10u 2u"), 8001)

    def test_ac_decade_sweep(self) -> None:
        self.assertEqual(estimate_points(".ac dec 20 1k 1meg"), 61)

    def test_ac_linear_sweep(self) -> None:
        self.assertEqual(estimate_points(".ac lin 500 1k 1meg"), 500)

    def test_dc_sweep(self) -> None:
        self.assertEqual(estimate_points(".dc v1 0 1.8 0.01"), 181)

    def test_an_operating_point_cannot_be_measured(self) -> None:
        self.assertIsNone(estimate_points(".op"))

    def test_the_directive_is_found_inside_a_full_netlist(self) -> None:
        netlist = "* title\nV1 in 0 1\nR1 in 0 1k\n.tran 1n 5u\n.save all\n.end\n"

        self.assertEqual(estimate_points(netlist), 5001)

    def test_malformed_directives_are_ignored(self) -> None:
        self.assertIsNone(estimate_points(".tran"))
        self.assertIsNone(estimate_points(".tran 0 5u"))
        self.assertIsNone(estimate_points(".tran 1n 0"))
        self.assertIsNone(estimate_points(""))


class RawLayoutTest(unittest.TestCase):
    def test_the_header_reports_the_point_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "out.raw"
            _write_raw(raw, variables=6, points=10)

            layout = read_raw_layout(raw)

            self.assertEqual(layout.variables, 6)
            self.assertEqual(layout.bytes_per_point, 48)
            self.assertFalse(layout.complex_values)

    def test_complex_data_is_twice_the_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "ac.raw"
            _write_raw(raw, variables=4, points=5, flags="complex")

            self.assertEqual(read_raw_layout(raw).bytes_per_point, 64)

    def test_a_header_that_has_not_been_written_yet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "partial.raw"
            raw.write_bytes(b"Title: test\nNo. Variables: 4\n")

            self.assertIsNone(read_raw_layout(raw))

    def test_a_missing_file(self) -> None:
        self.assertIsNone(read_raw_layout("/nonexistent/out.raw"))


class RawProgressTest(unittest.TestCase):
    def test_progress_tracks_the_points_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "out.raw"
            _write_raw(raw, variables=4, points=250)

            progress = RawProgress(raw, expected_points=1000)

            self.assertTrue(progress.measurable)
            self.assertEqual(progress.points_written(), 250)
            self.assertAlmostEqual(progress.fraction(), 0.25)

    def test_an_overrun_is_clamped_to_one(self) -> None:
        """ngspice varies its timestep, so it can exceed the estimate."""
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "out.raw"
            _write_raw(raw, variables=4, points=1500)

            self.assertEqual(RawProgress(raw, expected_points=1000).fraction(), 1.0)

    def test_nothing_is_measurable_without_an_estimate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "out.raw"
            _write_raw(raw, variables=4, points=10)

            progress = RawProgress(raw, expected_points=None)

            self.assertFalse(progress.measurable)
            self.assertIsNone(progress.fraction())

    def test_a_file_that_does_not_exist_yet(self) -> None:
        progress = RawProgress("/nonexistent/out.raw", expected_points=100)

        self.assertIsNone(progress.points_written())
        self.assertIsNone(progress.fraction())

    def test_a_zero_estimate_is_treated_as_unmeasurable(self) -> None:
        self.assertFalse(RawProgress("/x.raw", expected_points=0).measurable)

    def test_an_empty_payload_reads_as_zero_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "out.raw"
            _write_raw(raw, variables=4, points=0)

            self.assertEqual(RawProgress(raw, expected_points=100).fraction(), 0.0)


if __name__ == "__main__":
    unittest.main()
