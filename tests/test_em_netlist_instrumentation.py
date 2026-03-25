"""Tests for EM netlist instrumentation."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.services.em_netlist_instrumentation import (
    ensure_em_workspace,
    inspect_internal_net_candidates,
    instrument_netlist_for_em,
    instrument_netlist_text_for_em,
    normalize_em_current_file,
    preview_manual_instrumentation,
    write_manual_instrumented_netlist,
    write_em_probe_map,
)


class EmNetlistInstrumentationTest(unittest.TestCase):
    def test_instrument_simple_netlist(self) -> None:
        source = "\n".join(
            [
                "V1 vpwr 0 1.8",
                "R1 vpwr out 1k",
                ".tran 1n 5n",
                ".end",
            ]
        )
        instrumented, metadata = instrument_netlist_text_for_em(
            source,
            {
                "project_mode": "custom_sky130",
                "wrdata_output": "/tmp/em_currents.txt",
            },
        )
        self.assertIn("R1 vpwr__em out 1k", instrumented)
        self.assertIn("VPROBE_vpwr vpwr vpwr__em 0", instrumented)
        self.assertIn("wrdata /tmp/em_currents.txt time i(VPROBE_vpwr)", instrumented)
        self.assertEqual(metadata["probes"][0]["original_net"], "vpwr")

    def test_original_file_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.spice"
            output_path = Path(temp_dir) / "source__emprobe.spice"
            original = "V1 vpwr 0 1.8\nR1 vpwr out 1k\n.tran 1n 5n\n.end\n"
            source_path.write_text(original, encoding="utf-8")
            instrument_netlist_for_em(
                str(source_path),
                str(output_path),
                {"project_mode": "custom_sky130", "wrdata_output": str(Path(temp_dir) / "currents.txt")},
            )
            self.assertEqual(source_path.read_text(encoding="utf-8"), original)
            self.assertTrue(output_path.exists())

    def test_does_not_touch_subckt_body(self) -> None:
        source = "\n".join(
            [
                ".subckt child in out vpwr vgnd",
                "RCORE vpwr out 1k",
                ".ends",
                "V1 vpwr 0 1.8",
                "X1 sig out vpwr vgnd child",
                ".tran 1n 5n",
                ".end",
            ]
        )
        instrumented, _ = instrument_netlist_text_for_em(
            source,
            {
                "project_mode": "custom_sky130",
                "wrdata_output": "/tmp/em_currents.txt",
            },
        )
        self.assertIn("RCORE vpwr out 1k", instrumented)
        self.assertIn("X1 sig out vpwr__em vgnd__em child", instrumented)

    def test_tiny_tapeout_mode_instruments_named_io_nets(self) -> None:
        source = "\n".join(
            [
                "V1 vpwr 0 1.8",
                "X1 clk ui_in[0] uo_out[0] ua[0] vpwr vgnd tt_block",
                ".tran 1n 5n",
                ".end",
            ]
        )
        instrumented, metadata = instrument_netlist_text_for_em(
            source,
            {
                "project_mode": "tiny_tapeout",
                "wrdata_output": "/tmp/em_currents.txt",
            },
        )
        probe_nets = {item["original_net"] for item in metadata["probes"]}
        self.assertTrue({"vpwr", "clk", "ui_in[0]", "vgnd"}.issubset(probe_nets))
        self.assertNotIn("uo_out[0]", probe_nets)
        self.assertNotIn("ua[0]", probe_nets)
        self.assertIn("X1 clk__em ui_in[0]__em uo_out[0] ua[0] vpwr__em vgnd__em tt_block", instrumented)

    def test_output_net_driver_load_split_rewrites_only_driver_side(self) -> None:
        source = "\n".join(
            [
                "X17 p1 VGND VNB VPB VPWR uio_out[5] sky130_fd_sc_hd__bufbuf_16",
                "C20 uio_out[5] GND 10p",
                ".tran 1n 5n",
                ".end",
            ]
        )
        instrumented, metadata = instrument_netlist_text_for_em(
            source,
            {
                "project_mode": "tiny_tapeout",
                "wrdata_output": "/tmp/em_currents.txt",
            },
        )
        self.assertIn("uio_out[5]__drv sky130_fd_sc_hd__bufbuf_16", instrumented)
        self.assertIn("C20 uio_out[5] GND__em 10p", instrumented)
        self.assertIn("VPROBE_uio_out_5 uio_out[5] uio_out[5]__drv 0", instrumented)
        output_probe = next(item for item in metadata["probes"] if item["original_net"] == "uio_out[5]")
        self.assertEqual(output_probe["mode"], "output_driver_load")
        self.assertEqual(output_probe["moved_statements"], ["X17"])

    def test_output_net_without_explicit_load_is_skipped(self) -> None:
        source = "\n".join(
            [
                "X17 p1 VGND VNB VPB VPWR uio_out[5] sky130_fd_sc_hd__bufbuf_16",
                ".tran 1n 5n",
                ".end",
            ]
        )
        instrumented, metadata = instrument_netlist_text_for_em(
            source,
            {
                "project_mode": "tiny_tapeout",
                "wrdata_output": "/tmp/em_currents.txt",
            },
        )
        self.assertNotIn("VPROBE_uio_out_5", instrumented)
        self.assertTrue(metadata["warnings"])

    def test_detects_internal_candidate_net(self) -> None:
        source = "\n".join(
            [
                "X5 a p1 vpwr vgnd cell_a",
                "X7 p1 y vpwr vgnd cell_b",
                "C20 p1 0 10p",
                ".end",
            ]
        )
        candidates = inspect_internal_net_candidates(source)
        p1 = next(item for item in candidates if item["net_name"] == "p1")
        self.assertEqual(len(p1["connected_elements"]), 3)
        self.assertEqual({item["instance_name"] for item in p1["connected_elements"]}, {"X5", "X7", "C20"})

    def test_preview_manual_instrumentation_moves_selected_drivers_only(self) -> None:
        source = "\n".join(
            [
                "X5 a p1 vpwr vgnd cell_a",
                "X7 p1 y vpwr vgnd cell_b",
                "C20 p1 0 10p",
                ".end",
            ]
        )
        preview = preview_manual_instrumentation(source, "p1", ["X5", "X7"], "/tmp/manual_currents.txt")
        instrumented = preview["instrumented_text"]
        self.assertIn("X5 a p1__manual_drv vpwr vgnd cell_a", instrumented)
        self.assertIn("X7 p1__manual_drv y vpwr vgnd cell_b", instrumented)
        self.assertIn("C20 p1 0 10p", instrumented)
        self.assertIn("VPROBE_p1_manual p1 p1__manual_drv 0", instrumented)

    def test_write_manual_instrumented_netlist_keeps_original_file_untouched(self) -> None:
        source = "X5 a p1 vpwr vgnd cell_a\nC20 p1 0 10p\n.end\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            netlist_path = Path(temp_dir) / "manual.spice"
            map_path = Path(temp_dir) / "manual_map.json"
            metadata = write_manual_instrumented_netlist(
                source_text=source,
                output_netlist_path=netlist_path,
                probe_map_path=map_path,
                net_name="p1",
                moved_statements=["X5"],
                wrdata_output=Path(temp_dir) / "manual_currents.txt",
            )
            written = netlist_path.read_text(encoding="utf-8")
            self.assertEqual(source, "X5 a p1 vpwr vgnd cell_a\nC20 p1 0 10p\n.end\n")
            self.assertIn("p1__manual_drv", written)
            self.assertEqual(metadata["probes"][0]["mode"], "internal_manual")

    def test_ensure_em_workspace_creates_expected_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_em_workspace(temp_dir)
            self.assertTrue(paths["netlists"].exists())
            self.assertTrue(paths["inputs"].exists())
            self.assertTrue(paths["reports"].exists())

    def test_normalize_em_current_file_removes_duplicate_time_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "raw.txt"
            normalized_path = Path(temp_dir) / "normalized.txt"
            map_path = Path(temp_dir) / "map.json"
            raw_path.write_text("0 0 0 1e-3\n1e-9 1e-9 1e-9 1.1e-3\n", encoding="utf-8")
            write_em_probe_map(
                map_path,
                {
                    "probes": [
                        {
                            "probe_name": "VPROBE_vpwr",
                            "original_net": "vpwr",
                            "node_inserted": "vpwr__em",
                            "current_expr": "i(VPROBE_vpwr)",
                        }
                    ]
                },
            )
            result = normalize_em_current_file(raw_path, normalized_path, map_path)
            normalized_text = normalized_path.read_text(encoding="utf-8")
            self.assertIn("time,vpwr", normalized_text)
            self.assertEqual(result["probe_count"], 1)
            self.assertTrue(result["warnings"])

    @unittest.skipIf(shutil.which("ngspice") is None, "ngspice not available")
    def test_ngspice_runs_instrumented_netlist_without_syntax_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.spice"
            output_path = Path(temp_dir) / "source__emprobe.spice"
            currents_path = Path(temp_dir) / "currents.txt"
            source_path.write_text(
                "\n".join(
                    [
                        "V1 vpwr 0 1.8",
                        "R1 vpwr out 1k",
                        "C1 out 0 1p",
                        ".tran 1n 5n",
                        ".end",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            instrument_netlist_for_em(
                str(source_path),
                str(output_path),
                {"project_mode": "custom_sky130", "wrdata_output": str(currents_path)},
            )
            result = subprocess.run(
                ["ngspice", "-b", str(output_path)],
                capture_output=True,
                text=True,
                check=False,
                cwd=temp_dir,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertTrue(currents_path.exists())


if __name__ == "__main__":
    unittest.main()
