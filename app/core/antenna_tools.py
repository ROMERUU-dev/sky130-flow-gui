"""Locate an antenna rule deck, or fall back to Magic's built-in check.

The app assumed every PDK ships a KLayout antenna deck at a fixed filename
(`sky130A_ant.rb`). sky130A does not ship one at all: its KLayout DRC deck
contains no antenna rules, and the antenna check for this PDK lives in Magic's
techfile instead. Leaving the field blank made a supported flow look broken.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Names seen across sky130/gf180 style PDKs, most specific first.
DECK_CANDIDATES = (
    "drc/sky130A_ant.rb",
    "drc/sky130A_antenna.lydrc",
    "drc/antenna.lydrc",
    "drc/antenna.rb",
    "antenna.lydrc",
    "antenna.rb",
)

MAGIC_ANTENNA_MARKER = "antenna"


@dataclass(frozen=True)
class AntennaSupport:
    """What this PDK can actually do for antenna checks."""

    klayout_deck: str = ""
    magic_tech: str = ""
    magic_available: bool = False

    @property
    def has_klayout_deck(self) -> bool:
        return bool(self.klayout_deck)

    @property
    def preferred_engine(self) -> str:
        """`klayout` when a deck exists, `magic` when only the techfile does."""
        if self.has_klayout_deck:
            return "klayout"
        if self.magic_available:
            return "magic"
        return "none"


def find_klayout_antenna_deck(sky130a: Path | str) -> str:
    """Return the first antenna deck that exists under a PDK, or an empty string."""
    root = Path(sky130a).expanduser()
    klayout_root = root / "libs.tech" / "klayout"
    for relative in DECK_CANDIDATES:
        candidate = klayout_root / relative
        if candidate.is_file():
            return str(candidate)
    # Anything whose name mentions antennas counts, whatever the PDK called it.
    if klayout_root.is_dir():
        for candidate in sorted(klayout_root.rglob("*antenna*")):
            if candidate.is_file() and candidate.suffix in {".rb", ".lydrc", ".drc"}:
                return str(candidate)
    return ""


def magic_tech_has_antenna_rules(sky130a: Path | str) -> tuple[str, bool]:
    """Report whether the PDK's Magic techfile carries antenna rules."""
    techfile = Path(sky130a).expanduser() / "libs.tech" / "magic" / "sky130A.tech"
    if not techfile.is_file():
        return ("", False)
    try:
        text = techfile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return (str(techfile), False)
    return (str(techfile), MAGIC_ANTENNA_MARKER in text.lower())


def detect_antenna_support(sky130a: Path | str) -> AntennaSupport:
    """Work out which antenna engines this PDK supports."""
    if not sky130a:
        return AntennaSupport()
    deck = find_klayout_antenna_deck(sky130a)
    tech, available = magic_tech_has_antenna_rules(sky130a)
    return AntennaSupport(klayout_deck=deck, magic_tech=tech, magic_available=available)


def build_magic_antenna_script(layout: Path | str, report_path: Path | str, top_cell: str = "") -> str:
    """Write the Tcl that drives `antennacheck` over one layout."""
    layout_path = Path(layout)
    cell = top_cell or layout_path.stem
    name = layout_path.name
    lines = [
        "drc off",
        f"load {name}" if layout_path.suffix in {".mag", ""} else f"gds read {layout_path}",
    ]
    if layout_path.suffix not in {".mag", ""}:
        lines.append(f"load {cell}")
    lines += [
        "select top cell",
        "extract do local",
        f"feedback save {report_path}",
        "antennacheck",
        f"feedback save {report_path}",
        "quit -noprompt",
    ]
    return "\n".join(lines) + "\n"
