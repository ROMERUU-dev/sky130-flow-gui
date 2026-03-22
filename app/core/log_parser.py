"""Simple heuristics to extract pass/fail and highlight errors from tool logs."""

from __future__ import annotations

import re

ERROR_PATTERNS = [
    re.compile(r"\berror\b", re.IGNORECASE),
    re.compile(r"\bfatal\b", re.IGNORECASE),
    re.compile(r"segmentation fault", re.IGNORECASE),
]


class LogParser:
    """Parses logs for common statuses and issues."""

    @staticmethod
    def has_errors(text: str) -> bool:
        return any(p.search(text) for p in ERROR_PATTERNS)

    @staticmethod
    def lvs_summary(text: str) -> str:
        lowered = text.lower()
        if "lvs completed" in lowered and "netlists match uniquely" in lowered:
            return "LVS passed"
        if "mismatch" in lowered or "property errors" in lowered:
            return "LVS failed"
        return "LVS status unknown"

    @staticmethod
    def antenna_summary(text: str) -> str:
        lowered = text.lower()
        if "violation" in lowered:
            return "Antenna violations found"
        if "0 violations" in lowered or "no violations" in lowered:
            return "Antenna check passed"
        return "Antenna status unknown"

    @staticmethod
    def extract_key_errors(text: str, limit: int = 15) -> list[str]:
        lines = [line.strip() for line in text.splitlines()]
        bad = [ln for ln in lines if any(p.search(ln) for p in ERROR_PATTERNS)]
        return bad[:limit]
