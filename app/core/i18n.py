"""Small UI language helpers."""

from __future__ import annotations


def pick(language: str, es: str, en: str) -> str:
    """Return a Spanish or English string based on the saved UI language."""
    return en if language.lower().startswith("en") else es
