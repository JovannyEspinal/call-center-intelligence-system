"""Audit trail services."""

from __future__ import annotations

from typing import Protocol

from src.models import AuditAction, AuditDetailValue, AuditEvent


class AuditSink(Protocol):
    """Append-only audit event sink."""

    def append(
        self,
        *,
        analysis_id: str,
        action: AuditAction,
        details: dict[str, AuditDetailValue] | None = None,
        reviewer_id: str | None = None,
        session_id: str | None = None,
    ) -> AuditEvent:
        """Append a business-significant audit event."""

    def recent(self, *, limit: int = 20) -> list[AuditEvent]:
        """Return recent audit events, newest first."""


class InMemoryAuditSink:
    """Append-only in-memory audit sink for tests and graph wiring."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(
        self,
        *,
        analysis_id: str,
        action: AuditAction,
        details: dict[str, AuditDetailValue] | None = None,
        reviewer_id: str | None = None,
        session_id: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            analysis_id=analysis_id,
            action=action,
            details=details or {},
            reviewer_id=reviewer_id,
            session_id=session_id,
        )
        self._events.append(event)
        return event

    def recent(self, *, limit: int = 20) -> list[AuditEvent]:
        if limit < 1:
            raise ValueError("limit must be greater than zero")
        return list(reversed(self._events[-limit:]))
