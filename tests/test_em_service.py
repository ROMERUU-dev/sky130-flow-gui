"""Focused tests for the EM sizing engine."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from app.services.em_service import EmService


class EmServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = EmService()
        self.profile = self.service.get_profile("sky130_conservative")

    def test_compute_metrics(self) -> None:
        metrics = self.service.compute_metrics([1.0, -1.0, 1.0, -1.0])
        self.assertAlmostEqual(metrics.average_a, 0.0)
        self.assertAlmostEqual(metrics.rms_a, 1.0)
        self.assertAlmostEqual(metrics.peak_abs_a, 1.0)

    def test_width_calculation(self) -> None:
        metal = self.profile.metals["met2"]
        width = self.service.calculate_required_width_um(0.002, metal)
        expected = (2.0 / metal.allowed_current_density_ma_per_um2) / metal.thickness_um
        self.assertAlmostEqual(width, expected)

    def test_via_count_calculation(self) -> None:
        via = self.profile.vias["via"]
        count = self.service.calculate_via_count(0.0031, via)
        self.assertEqual(count, 3)

    def test_rounding_behavior(self) -> None:
        self.assertAlmostEqual(self.service.round_up_to_grid(0.171, 0.005), 0.175)

    def test_auto_metric_power_branch_prefers_average_with_margin(self) -> None:
        metrics = self.service.compute_metrics([0.010, 0.010, 0.010, 0.010])
        used, value = self.service.select_design_metric("auto", "power", metrics)
        self.assertEqual(used, "average")
        self.assertAlmostEqual(value, 0.0125)

    def test_auto_metric_output_branch_uses_half_peak_when_needed(self) -> None:
        metrics = self.service.compute_metrics([0.0, 0.0, 0.0, 0.010, 0.0])
        used, value = self.service.select_design_metric("auto", "output", metrics)
        self.assertEqual(used, "peak")
        self.assertAlmostEqual(value, 0.005)

    def test_parse_whitespace_input_without_header(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "currents.txt"
            path.write_text("0 1e-3 -2e-3\n1e-9 2e-3 -3e-3\n", encoding="utf-8")
            parsed = self.service.parse_waveform_file(path)
        self.assertFalse(parsed.had_header)
        self.assertEqual(len(parsed.branches), 2)
        self.assertEqual(parsed.branches[0].name, "branch_1")
        self.assertAlmostEqual(parsed.branches[1].samples_a[1], -0.003)

    def test_parse_csv_with_header(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "currents.csv"
            path.write_text("time,i(vdd),i(out)\n0,1e-3,2e-3\n1e-9,3e-3,4e-3\n", encoding="utf-8")
            parsed = self.service.parse_waveform_file(path)
        self.assertTrue(parsed.had_header)
        self.assertEqual([branch.name for branch in parsed.branches], ["i(vdd)", "i(out)"])

    def test_parse_em_file_uses_probe_map_and_ignores_duplicate_time_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = Path(temp_dir) / "run_currents.txt"
            map_path = Path(temp_dir) / "run__emprobe_map.json"
            data_path.write_text("0 0 0 1e-3\n1e-9 1e-9 1e-9 1.2e-3\n", encoding="utf-8")
            map_path.write_text(
                '{"probes":[{"probe_name":"VPROBE_vpwr","original_net":"vpwr","node_inserted":"vpwr__em","current_expr":"i(VPROBE_vpwr)"}]}',
                encoding="utf-8",
            )
            parsed = self.service.parse_waveform_file(data_path, probe_map_path=map_path)
        self.assertEqual(len(parsed.branches), 1)
        self.assertEqual(parsed.branches[0].name, "vpwr")
        self.assertTrue(parsed.warnings)

    def test_parse_manual_em_file_labels_branch_as_manual(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = Path(temp_dir) / "run_currents_manual.txt"
            map_path = Path(temp_dir) / "run__emprobe_manual_map.json"
            data_path.write_text("time,p1\n0,1e-3\n1e-9,1.1e-3\n", encoding="utf-8")
            map_path.write_text(
                '{"probes":[{"probe_name":"VPROBE_p1_manual","original_net":"p1","node_inserted":"p1__manual_drv","current_expr":"i(VPROBE_p1_manual)","mode":"internal_manual","warnings":["User-defined instrumentation"]}]}',
                encoding="utf-8",
            )
            parsed = self.service.parse_waveform_file(data_path, probe_map_path=map_path)
        self.assertEqual(parsed.branches[0].name, "p1 (manual)")

    def test_compact_array_is_near_square(self) -> None:
        rows, cols = self.service.compact_array(5)
        self.assertEqual(rows * cols, 6)
        self.assertLessEqual(abs(rows - cols), 1)

    def test_analyze_updates_branch_source_file_per_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = Path(temp_dir) / "first.csv"
            second_path = Path(temp_dir) / "second.csv"
            content = "time,I_vdd\n0,1e-3\n1e-9,2e-3\n"
            first_path.write_text(content, encoding="utf-8")
            second_path.write_text(content, encoding="utf-8")

            first_bundle = self.service.analyze(
                parsed=self.service.parse_waveform_file(first_path),
                profile_name="sky130_conservative",
                metric_mode="auto",
                target_metal="met1",
                via_type="auto",
                margin_factor=1.25,
            )
            second_bundle = self.service.analyze(
                parsed=self.service.parse_waveform_file(second_path),
                profile_name="sky130_conservative",
                metric_mode="auto",
                target_metal="met1",
                via_type="auto",
                margin_factor=1.25,
            )

        self.assertEqual(first_bundle.branches[0].source_file, str(first_path.resolve()))
        self.assertEqual(second_bundle.branches[0].source_file, str(second_path.resolve()))


if __name__ == "__main__":
    unittest.main()
