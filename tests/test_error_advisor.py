"""Tests for turning tool output into actionable advice."""

from __future__ import annotations

import unittest

from app.core.error_advisor import (
    ACTION_CHECK_PDK,
    ACTION_INSTALL_MAGIC,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    analyze,
    format_advice,
    has_blocking_errors,
)

NGSPICE_UNKNOWN_SUBCKT = """
Circuit: * test
Error: unknown subckt: x1 a b sky130_fd_pr__nfet_01v8
    in line no. 2 from file /tmp/design.spice
    Simulation interrupted due to error!
"""


class NgspiceRulesTest(unittest.TestCase):
    def test_unknown_subckt_names_the_subcircuit_not_the_instance(self) -> None:
        """ngspice prints the whole line; the subcircuit is its last token."""
        advices = analyze(NGSPICE_UNKNOWN_SUBCKT, tool="ngspice")

        subckt = next(a for a in advices if a.rule_id == "ngspice.unknown_subckt")
        self.assertIn("sky130_fd_pr__nfet_01v8", subckt.detail)
        self.assertNotIn("(x1)", subckt.detail)
        self.assertEqual(subckt.action, ACTION_CHECK_PDK)
        self.assertTrue(subckt.blocking)

    def test_a_failing_run_is_blocking_even_with_exit_code_zero(self) -> None:
        self.assertTrue(has_blocking_errors(analyze(NGSPICE_UNKNOWN_SUBCKT, tool="ngspice")))

    def test_singular_matrix_suggests_a_dc_path(self) -> None:
        advices = analyze("Error: singular matrix: check nodes", tool="ngspice")

        self.assertEqual(advices[0].rule_id, "ngspice.singular_matrix")
        self.assertIn("tierra", advices[0].suggestion.lower())

    def test_convergence_failure_is_recognised(self) -> None:
        text = "doAnalyses: TRAN;iteration limit reached step too small"

        self.assertEqual(analyze(text, tool="ngspice")[0].rule_id, "ngspice.no_convergence")

    def test_a_missing_include_is_recognised(self) -> None:
        text = "Error: could not find include file /wrong/path/sky130.lib.spice"

        advices = analyze(text, tool="ngspice")

        self.assertEqual(advices[0].rule_id, "ngspice.missing_include")
        self.assertIn("sky130.lib.spice", advices[0].detail)

    def test_a_missing_vector_is_only_a_warning(self) -> None:
        advices = analyze("Error: no such vector v(nope)", tool="ngspice")

        vector = next(a for a in advices if a.rule_id == "ngspice.no_such_vector")
        self.assertEqual(vector.severity, SEVERITY_WARNING)
        self.assertFalse(vector.blocking)

    def test_a_clean_log_produces_nothing(self) -> None:
        text = "Circuit: rc\nNo compatibility mode selected\nTotal analysis time: 0.01\n"

        self.assertEqual(analyze(text, tool="ngspice"), [])
        self.assertFalse(has_blocking_errors([]))


class OtherToolRulesTest(unittest.TestCase):
    def test_magic_version_mismatch_points_at_the_installer(self) -> None:
        text = "tech file sky130A.tech requires version 8.3.411, version mismatch"

        advices = analyze(text, tool="magic")

        self.assertEqual(advices[0].action, ACTION_INSTALL_MAGIC)
        self.assertIn("8.3.105", advices[0].suggestion)

    def test_netgen_mismatch_is_recognised(self) -> None:
        advices = analyze("Final result: Netlists do not match.", tool="netgen")

        self.assertEqual(advices[0].rule_id, "netgen.mismatch")

    def test_yosys_missing_module(self) -> None:
        advices = analyze("ERROR: Module `\\my_top' not found!", tool="yosys")

        self.assertEqual(advices[0].rule_id, "yosys.no_such_module")

    def test_openroad_error_code(self) -> None:
        advices = analyze("[ERROR GRT-0043] No routing tracks", tool="openroad")

        self.assertEqual(advices[0].rule_id, "openroad.error")

    def test_general_rules_apply_to_every_tool(self) -> None:
        for tool in ("ngspice", "magic", "yosys"):
            with self.subTest(tool=tool):
                advices = analyze("bash: /out/x: Permission denied", tool=tool)
                self.assertTrue(any(a.rule_id == "general.permission_denied" for a in advices))

    def test_rules_for_other_tools_are_not_applied(self) -> None:
        advices = analyze("Netlists do not match.", tool="ngspice")

        self.assertFalse(any(a.rule_id == "netgen.mismatch" for a in advices))


class OrderingAndFormattingTest(unittest.TestCase):
    def test_blocking_advice_sorts_first(self) -> None:
        text = "Error: no such vector v(x)\nError: singular matrix\n"

        advices = analyze(text, tool="ngspice")

        self.assertEqual(advices[0].severity, SEVERITY_ERROR)

    def test_each_rule_reports_once(self) -> None:
        text = "singular matrix\nsingular matrix\nsingular matrix\n"

        self.assertEqual(len(analyze(text, tool="ngspice")), 1)

    def test_the_number_of_findings_is_capped(self) -> None:
        text = NGSPICE_UNKNOWN_SUBCKT + "\nsingular matrix\nno such vector v(a)\npermission denied\n"

        self.assertLessEqual(len(analyze(text, tool="ngspice", limit=2)), 2)

    def test_formatting_includes_cause_and_remedy(self) -> None:
        rendered = format_advice(analyze(NGSPICE_UNKNOWN_SUBCKT, tool="ngspice"))

        self.assertIn("Subcircuito no definido", rendered)
        self.assertIn("→", rendered)

    def test_empty_input_is_handled(self) -> None:
        self.assertEqual(analyze(""), [])
        self.assertEqual(format_advice([]), "")


if __name__ == "__main__":
    unittest.main()
