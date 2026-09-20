"""Tests for antenna rule discovery across engines."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.antenna_tools import (
    build_magic_antenna_script,
    detect_antenna_support,
    find_klayout_antenna_deck,
    magic_tech_has_antenna_rules,
)


def _pdk(root: Path, *, deck_name: str = "", magic_antenna: bool = False) -> Path:
    sky130a = root / "sky130A"
    (sky130a / "libs.tech" / "klayout" / "drc").mkdir(parents=True)
    (sky130a / "libs.tech" / "magic").mkdir(parents=True)
    if deck_name:
        (sky130a / "libs.tech" / "klayout" / deck_name).parent.mkdir(parents=True, exist_ok=True)
        (sky130a / "libs.tech" / "klayout" / deck_name).write_text("# deck", encoding="utf-8")
    tech = "tech\n  version 8.3.411\n"
    if magic_antenna:
        tech += "  antenna ratio 400\n"
    (sky130a / "libs.tech" / "magic" / "sky130A.tech").write_text(tech, encoding="utf-8")
    return sky130a


class DeckDiscoveryTest(unittest.TestCase):
    def test_the_conventional_filename_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sky130a = _pdk(Path(tmp), deck_name="drc/sky130A_ant.rb")

            self.assertTrue(find_klayout_antenna_deck(sky130a).endswith("sky130A_ant.rb"))

    def test_any_antenna_named_deck_counts(self) -> None:
        """Earlier versions only looked for one hardcoded filename."""
        with tempfile.TemporaryDirectory() as tmp:
            sky130a = _pdk(Path(tmp), deck_name="drc/my_antenna_rules.lydrc")

            self.assertTrue(find_klayout_antenna_deck(sky130a).endswith("my_antenna_rules.lydrc"))

    def test_a_pdk_without_a_deck_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sky130a = _pdk(Path(tmp))

            self.assertEqual(find_klayout_antenna_deck(sky130a), "")

    def test_missing_pdk_is_not_an_error(self) -> None:
        self.assertEqual(find_klayout_antenna_deck("/nonexistent/sky130A"), "")


class MagicSupportTest(unittest.TestCase):
    def test_antenna_rules_in_the_techfile_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sky130a = _pdk(Path(tmp), magic_antenna=True)

            path, available = magic_tech_has_antenna_rules(sky130a)

            self.assertTrue(path.endswith("sky130A.tech"))
            self.assertTrue(available)

    def test_a_techfile_without_antenna_rules_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sky130a = _pdk(Path(tmp))

            _path, available = magic_tech_has_antenna_rules(sky130a)

            self.assertFalse(available)


class EngineSelectionTest(unittest.TestCase):
    def test_magic_is_preferred_when_only_it_has_rules(self) -> None:
        """This is the sky130A case: no KLayout deck, rules in the techfile."""
        with tempfile.TemporaryDirectory() as tmp:
            sky130a = _pdk(Path(tmp), magic_antenna=True)

            support = detect_antenna_support(sky130a)

            self.assertFalse(support.has_klayout_deck)
            self.assertTrue(support.magic_available)
            self.assertEqual(support.preferred_engine, "magic")

    def test_a_deck_wins_when_one_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sky130a = _pdk(Path(tmp), deck_name="drc/sky130A_ant.rb", magic_antenna=True)

            self.assertEqual(detect_antenna_support(sky130a).preferred_engine, "klayout")

    def test_no_rules_at_all_reports_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sky130a = _pdk(Path(tmp))

            self.assertEqual(detect_antenna_support(sky130a).preferred_engine, "none")

    def test_an_unset_pdk_path_is_handled(self) -> None:
        self.assertEqual(detect_antenna_support("").preferred_engine, "none")


class MagicScriptTest(unittest.TestCase):
    def test_a_gds_layout_is_read_and_loaded(self) -> None:
        script = build_magic_antenna_script("/tmp/design.gds", "/tmp/report.txt", "top")

        self.assertIn("gds read /tmp/design.gds", script)
        self.assertIn("load top", script)
        self.assertIn("antennacheck", script)
        self.assertIn("feedback save /tmp/report.txt", script)
        self.assertTrue(script.rstrip().endswith("quit -noprompt"))

    def test_a_magic_layout_is_loaded_directly(self) -> None:
        script = build_magic_antenna_script("/tmp/design.mag", "/tmp/report.txt")

        self.assertIn("load design.mag", script)
        self.assertNotIn("gds read", script)

    def test_the_top_cell_defaults_to_the_file_stem(self) -> None:
        script = build_magic_antenna_script("/tmp/inverter.gds", "/tmp/r.txt")

        self.assertIn("load inverter", script)


if __name__ == "__main__":
    unittest.main()
