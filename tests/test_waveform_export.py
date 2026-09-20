"""Tests for CSV export of parsed waveforms."""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
from pathlib import Path

from app.core.waveform_export import build_csv, write_csv


class BuildCsvTest(unittest.TestCase):
    def setUp(self) -> None:
        x = [0.0, 1e-9, 2e-9]
        self.signals = {
            "v(a)": (x, [0.0, 0.5, 1.0]),
            "v(b)": (x, [1.0, 0.5, 0.0]),
            "v(other)": ([0.0, 5e-9], [3.0, 4.0]),
        }

    def _rows(self, text: str) -> list[list[str]]:
        return list(csv.reader(io.StringIO(text)))

    def test_traces_on_a_shared_axis_get_one_x_column(self) -> None:
        rows = self._rows(build_csv(self.signals, ["v(a)", "v(b)"], x_label="time"))

        self.assertEqual(rows[0], ["time", "v(a)", "v(b)"])
        self.assertEqual(len(rows), 4)
        self.assertEqual(float(rows[2][0]), 1e-9)
        self.assertEqual(float(rows[2][1]), 0.5)
        self.assertEqual(float(rows[2][2]), 0.5)

    def test_mismatched_axes_keep_their_own_x_column(self) -> None:
        """Nothing is resampled or truncated behind the user's back."""
        rows = self._rows(build_csv(self.signals, ["v(a)", "v(other)"], x_label="time"))

        self.assertEqual(rows[0], ["time[v(a)]", "v(a)", "time[v(other)]", "v(other)"])
        # The shorter trace leaves blanks rather than inventing values.
        self.assertEqual(rows[3][2], "")
        self.assertEqual(rows[3][3], "")

    def test_full_double_precision_is_preserved(self) -> None:
        signals = {"v(a)": ([0.0], [0.1 + 0.2])}

        rows = self._rows(build_csv(signals, ["v(a)"]))

        self.assertEqual(float(rows[1][1]), 0.1 + 0.2)

    def test_unknown_names_are_ignored_and_empty_selection_raises(self) -> None:
        rows = self._rows(build_csv(self.signals, ["nope", "v(a)"], x_label="time"))
        self.assertEqual(rows[0], ["time", "v(a)"])

        with self.assertRaises(ValueError):
            build_csv(self.signals, ["nope"])

    def test_write_csv_creates_missing_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "nested" / "run" / "trace.csv"

            written = write_csv(target, self.signals, ["v(a)"], x_label="time")

            self.assertTrue(written.is_file())
            self.assertIn("v(a)", written.read_text(encoding="utf-8").splitlines()[0])


if __name__ == "__main__":
    unittest.main()
