"""Helpers for resolving packaged branding assets."""

from __future__ import annotations

import warnings
from pathlib import Path


RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources"
PNG_LOGO_CANDIDATES = (
    RESOURCE_DIR / "squirrel-logo.png",
    RESOURCE_DIR / "squirrel_logo.png",
    RESOURCE_DIR / "sky130-flow-gui.png",
)
SVG_LOGO_CANDIDATES = (
    RESOURCE_DIR / "ardilla_silueta_blanca_suave.svg",
    RESOURCE_DIR / "squirrel-logo.svg",
    RESOURCE_DIR / "squirrel_logo.svg",
    RESOURCE_DIR / "sky130-flow-gui.svg",
)


def resolve_branding_logo() -> tuple[str, Path | None]:
    """Resolve the preferred branding asset inside the packaged app tree."""
    for candidate in PNG_LOGO_CANDIDATES:
        if candidate.is_file():
            return ("png", candidate)
    for candidate in SVG_LOGO_CANDIDATES:
        if candidate.is_file():
            return ("svg", candidate)
    warnings.warn(
        f"No branding logo asset was found under {RESOURCE_DIR}. Splash will use the vector fallback.",
        RuntimeWarning,
        stacklevel=2,
    )
    return ("fallback", None)
