"""Helpers for locating layout working directories and top cells."""

from __future__ import annotations

from pathlib import Path


def resolve_layout_dir(project_root: Path) -> Path:
    mag_dir = project_root / "mag"
    return mag_dir if mag_dir.exists() and mag_dir.is_dir() else project_root


def infer_top_cell(layout_dir: Path) -> str:
    candidates = sorted(path.stem for path in layout_dir.glob("tt_um_*.mag"))
    if candidates:
        return candidates[0]

    def is_user_layout(path: Path) -> bool:
        stem = path.stem
        if stem.startswith("sky130_fd_"):
            return False
        if stem in {"expand", "TOP"}:
            return False
        return True

    generic_candidates = sorted(path.stem for path in layout_dir.glob("*.mag") if is_user_layout(path))
    return generic_candidates[0] if generic_candidates else ""
