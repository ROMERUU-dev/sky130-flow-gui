"""Tests for comparing two runs."""

from __future__ import annotations

import math
import unittest

from app.core.run_compare import compare_runs, compare_signal


def _sine(points: int, dt: float, amplitude: float = 1.0, frequency: float = 2e6):
    x = [index * dt for index in range(points)]
    y = [amplitude * math.sin(2.0 * math.pi * frequency * t) for t in x]
    return (x, y)


class CompareSignalTest(unittest.TestCase):
    def test_identical_signals_have_no_delta(self) -> None:
        signal = _sine(500, 2e-9)

        delta = compare_signal(signal, signal, "v(out)")

        self.assertAlmostEqual(delta.max_abs_delta, 0.0, places=12)
        self.assertAlmostEqual(delta.rms_delta, 0.0, places=12)

    def test_different_timesteps_are_resampled_not_penalised(self) -> None:
        """A finer timestep must not look like a difference in the signal."""
        coarse = _sine(300, 3.1e-9)
        fine = _sine(900, 1.0e-9)

        delta = compare_signal(fine, coarse, "v(out)")

        # Interpolation error only; nowhere near the signal's own swing.
        self.assertLess(delta.relative, 0.02)

    def test_an_amplitude_change_is_measured(self) -> None:
        delta = compare_signal(_sine(500, 2e-9, amplitude=1.1), _sine(500, 2e-9), "v(out)")

        self.assertAlmostEqual(delta.max_abs_delta, 0.1, places=2)
        self.assertGreater(delta.relative, 0.04)

    def test_only_the_overlapping_window_is_compared(self) -> None:
        long_run = _sine(1000, 2e-9)
        short_run = _sine(200, 2e-9)

        delta = compare_signal(long_run, short_run, "v(out)")

        self.assertLessEqual(delta.overlap_end, short_run[0][-1] + 1e-18)
        self.assertGreater(delta.samples, 1)

    def test_a_descending_reference_axis_is_handled(self) -> None:
        """numpy.interp needs an increasing axis; a sweep may be stored backwards."""
        x, y = _sine(400, 2e-9)
        reversed_reference = (list(reversed(x)), list(reversed(y)))

        delta = compare_signal((x, y), reversed_reference, "v(out)")

        self.assertAlmostEqual(delta.max_abs_delta, 0.0, places=9)

    def test_runs_that_do_not_overlap_return_nothing(self) -> None:
        early = ([0.0, 1e-9, 2e-9], [0.0, 1.0, 0.0])
        late = ([9e-9, 10e-9, 11e-9], [0.0, 1.0, 0.0])

        self.assertIsNone(compare_signal(early, late, "v(out)"))

    def test_a_single_sample_returns_nothing(self) -> None:
        self.assertIsNone(compare_signal(([0.0], [1.0]), _sine(10, 1e-9), "v(out)"))


class CompareRunsTest(unittest.TestCase):
    def test_shared_and_exclusive_signals_are_separated(self) -> None:
        current = {"v(a)": _sine(300, 2e-9), "v(only_now)": _sine(300, 2e-9)}
        reference = {"v(a)": _sine(300, 2e-9), "v(only_before)": _sine(300, 2e-9)}

        comparison = compare_runs(current, reference)

        self.assertEqual(comparison.shared_names, ("v(a)",))
        self.assertEqual(comparison.only_in_current, ("v(only_now)",))
        self.assertEqual(comparison.only_in_reference, ("v(only_before)",))

    def test_the_independent_variable_is_not_compared(self) -> None:
        """The parser re-exposes it plotted against its own sample index."""
        axis = ([float(i) for i in range(300)], [i * 2e-9 for i in range(300)])
        current = {"time": axis, "v(a)": _sine(300, 2e-9)}
        reference = {"time": axis, "v(a)": _sine(300, 2e-9)}

        comparison = compare_runs(current, reference)

        self.assertNotIn("time", comparison.shared_names)
        self.assertIn("v(a)", comparison.shared_names)

    def test_results_are_ordered_by_relative_movement(self) -> None:
        current = {"small": _sine(300, 2e-9, amplitude=1.01), "big": _sine(300, 2e-9, amplitude=2.0)}
        reference = {"small": _sine(300, 2e-9), "big": _sine(300, 2e-9)}

        comparison = compare_runs(current, reference)

        self.assertEqual(comparison.deltas[0].name, "big")
        self.assertEqual(comparison.worst().name, "big")

    def test_identical_runs_are_reported_as_identical(self) -> None:
        signals = {"v(a)": _sine(300, 2e-9)}

        self.assertTrue(compare_runs(signals, dict(signals)).identical())

    def test_an_empty_side_is_handled(self) -> None:
        comparison = compare_runs({}, {"v(a)": _sine(10, 1e-9)})

        self.assertEqual(comparison.deltas, ())
        self.assertEqual(comparison.only_in_reference, ("v(a)",))
        self.assertIsNone(comparison.worst())

    def test_relative_is_zero_for_a_flat_reference(self) -> None:
        flat = ([0.0, 1e-9, 2e-9], [1.0, 1.0, 1.0])
        current = ([0.0, 1e-9, 2e-9], [1.0, 1.5, 1.0])

        delta = compare_signal(current, flat, "v(a)")

        self.assertEqual(delta.reference_span, 0.0)
        self.assertEqual(delta.relative, 0.0)


if __name__ == "__main__":
    unittest.main()
