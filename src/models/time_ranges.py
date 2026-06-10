"""Shared validation helpers for timestamp ranges."""

from __future__ import annotations


def validate_timestamp_range(
    start_seconds: float | None,
    end_seconds: float | None,
    *,
    required: bool,
) -> None:
    """Validate an optional or required timestamp range."""
    if required and (start_seconds is None or end_seconds is None):
        raise ValueError("start_seconds and end_seconds are required")
    if start_seconds is None or end_seconds is None:
        return
    if end_seconds <= start_seconds:
        raise ValueError("end_seconds must be greater than start_seconds")
