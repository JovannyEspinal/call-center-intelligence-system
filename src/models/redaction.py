"""Helpers for keeping persisted and report-facing text redacted."""

from __future__ import annotations

import re

RAW_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(
        r"\b[A-Z0-9._%+-]+\s+(?:at|\[at\]|\(at\))\s+"
        r"[A-Z0-9.-]+\.[A-Z]{2,}\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:\+?1[ -.]?)?(?:\(?\d{3}\)?[ -.])\d{3}[ -.]\d{4}\b"),
    re.compile(r"\b\d{10}\b"),
    re.compile(
        r"\b(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december)\s+\d{1,2},\s+\d{4}\b",
        re.IGNORECASE,
    ),
)


def contains_raw_sensitive_value(text: str) -> bool:
    """Return whether text appears to contain an unredacted sensitive value."""
    return any(pattern.search(text) for pattern in RAW_SENSITIVE_PATTERNS)
