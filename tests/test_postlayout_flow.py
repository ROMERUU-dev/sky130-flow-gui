"""Tests for post-layout project-root and Tiny Tapeout wrapper behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.project_manager import ProjectManager
from app.core.layout_tools import infer_top_cell
from app.core.spice_tools import build_generated_netlist, ensure_sky130_model_lib


class PostLayoutFlowTest(unittest.TestCase):
    def test_project_root_normalizes_mag_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "ttsky-tetrahedral-oscillator"
            mag_dir = project_root / "mag"
            mag_dir.mkdir(parents=True)

            normalized = ProjectManager.normalize_project_root(mag_dir)
            self.assertEqual(normalized, project_root.resolve())

    def test_project_root_normalizes_runs_results_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "ttsky-tetrahedral-oscillator"
            results_dir = project_root / "runs" / "results" / "260401-1234"
            results_dir.mkdir(parents=True)

            normalized = ProjectManager.normalize_project_root(results_dir)
            self.assertEqual(normalized, project_root.resolve())

    def test_tiny_tapeout_extracted_subckt_gets_startup_wrapper(self) -> None:
        source = "\n".join(
            [
                ".subckt tt_um_demo clk ena rst_n ua[0] ua[1] ui_in[0] ui_in[1]",
                "+ uio_in[0] uio_oe[0] uio_out[0] uo_out[0] uo_out[1] uo_out[2] uo_out[3] VDPWR VGND",
                "R1 uo_out[0] VGND 1k",
                ".ends",
            ]
        )

        generated = build_generated_netlist(
            source_text=source,
            analysis_type="Transient",
            analysis_params={
                "tran_step": "0.05n",
                "tran_stop": "10u",
                "tran_start": "0",
                "tran_uic": "1",
                "save_mode": "Selected probes only",
                "temp_c": "27",
            },
            save_points=["uo_out[0]", "uo_out[1]"],
            extra_directives="",
            preferred_subckt="tt_um_demo",
        )

        self.assertIn("Vclk clk 0 0", generated)
        self.assertIn("Vua_0 ua[0] 0 0", generated)
        self.assertIn("Vuio_oe_0 uio_oe[0] 0 0", generated)
        self.assertIn("CLOAD_uo_out_0 uo_out[0] 0 10f", generated)
        self.assertIn(".ic v(uo_out[0])=0.9 v(uo_out[1])=0 v(uo_out[2])=0.9 v(uo_out[3])=0", generated)
        self.assertIn("Xdut clk ena rst_n", generated)
        self.assertIn(".tran 0.05n 10u 0 uic", generated)

    def test_tiny_tapeout_wrapper_can_disable_ic_and_loads(self) -> None:
        source = "\n".join(
            [
                ".subckt tt_um_demo clk ena rst_n ua[0] ui_in[0]",
                "+ uio_in[0] uio_oe[0] uio_out[0] uo_out[0] uo_out[1] uo_out[2] uo_out[3] VDPWR VGND",
                "R1 uo_out[0] VGND 1k",
                ".ends",
            ]
        )

        generated = build_generated_netlist(
            source_text=source,
            analysis_type="Transient",
            analysis_params={
                "tran_step": "0.05n",
                "tran_stop": "10u",
                "tran_start": "0",
                "tran_uic": "1",
                "save_mode": "Selected probes only",
                "temp_c": "27",
            },
            save_points=["uo_out[0]"],
            extra_directives="",
            preferred_subckt="tt_um_demo",
            wrapper_options={
                "tiny_tapeout_initial_conditions": False,
                "tiny_tapeout_load_mode": "none",
            },
        )

        self.assertNotIn("CLOAD_uo_out_0 uo_out[0] 0 10f", generated)
        self.assertNotIn(".ic v(uo_out[0])=0.9", generated)
        self.assertIn("Xdut clk ena rst_n", generated)

    def test_tiny_tapeout_wrapper_can_emit_series_rc_loads(self) -> None:
        source = "\n".join(
            [
                ".subckt tt_um_demo clk ena rst_n ua[0] ui_in[0]",
                "+ uio_in[0] uio_oe[0] uio_out[0] uo_out[0] uo_out[1] uo_out[2] uo_out[3] VDPWR VGND",
                "R1 uo_out[0] VGND 1k",
                ".ends",
            ]
        )

        generated = build_generated_netlist(
            source_text=source,
            analysis_type="Transient",
            analysis_params={
                "tran_step": "0.05n",
                "tran_stop": "10u",
                "tran_start": "0",
                "tran_uic": "1",
                "save_mode": "Selected probes only",
                "temp_c": "27",
            },
            save_points=["uo_out[0]"],
            extra_directives="",
            preferred_subckt="tt_um_demo",
            wrapper_options={
                "tiny_tapeout_load_mode": "rc",
                "tiny_tapeout_load_cap_value": "25f",
                "tiny_tapeout_load_res_value": "2k",
            },
        )

        self.assertIn("RLOAD_uo_out_0 uo_out[0] uo_out[0]__load 2k", generated)
        self.assertIn("CLOAD_uo_out_0 uo_out[0]__load 0 25f", generated)
        self.assertNotIn("CLOAD_uo_out_0 uo_out[0] 0 25f", generated)

    def test_extracted_sky130_netlist_gets_model_lib(self) -> None:
        source = ".subckt tt_um_demo VDPWR VGND\nX1 a b sky130_fd_sc_hd__inv_1\n.ends\n"
        updated = ensure_sky130_model_lib(source, "/pdk/sky130A")
        self.assertIn(".lib /pdk/sky130A/libs.tech/ngspice/sky130.lib.spice tt", updated)

    def test_extraction_tab_prefers_tt_um_mag_as_top_cell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            layout_dir = Path(temp_dir)
            (layout_dir / "sky130_fd_sc_hd__inv_1.mag").write_text("", encoding="utf-8")
            (layout_dir / "tt_um_tetrahedral_oscillator.mag").write_text("", encoding="utf-8")
            (layout_dir / "TOP.mag").write_text("", encoding="utf-8")
            inferred = infer_top_cell(layout_dir)
            self.assertEqual(inferred, "tt_um_tetrahedral_oscillator")


if __name__ == "__main__":
    unittest.main()
