"""Shared repository helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.models import Call, CallAnalysis


@dataclass(frozen=True)
class CallHistoryEntry:
    """A call and its analyses for the Analysis History view."""

    call: Call
    analyses: list[CallAnalysis]


def as_utc(value: datetime) -> datetime:
    """Normalize SQLite-loaded datetimes back to UTC-aware values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
