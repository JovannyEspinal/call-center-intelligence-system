from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models import AuditAction, AuditEvent
from src.services import InMemoryAuditSink


def test_audit_event_accepts_jsonish_details() -> None:
    event = AuditEvent(
        analysis_id="analysis-1",
        action=AuditAction.PII_REDACTION_COMPLETED,
        details={
            "privacy_event_count": 3,
            "duration_seconds": 1.25,
            "cache_used": False,
            "stage": "pii_redaction",
        },
    )

    assert event.details["privacy_event_count"] == 3
    assert event.details["cache_used"] is False


def test_audit_event_rejects_raw_sensitive_detail_values() -> None:
    with pytest.raises(ValidationError, match="raw sensitive"):
        AuditEvent(
            analysis_id="analysis-1",
            action=AuditAction.PII_REDACTION_COMPLETED,
            details={"raw_email": "customer@example.com"},
        )


def test_audit_event_rejects_raw_sensitive_session_identity() -> None:
    with pytest.raises(ValidationError, match="raw sensitive"):
        AuditEvent(
            analysis_id="analysis-1",
            action=AuditAction.REPORT_DOWNLOADED,
            session_id="555-123-4567",
        )


def test_in_memory_audit_sink_appends_events() -> None:
    sink = InMemoryAuditSink()

    first = sink.append(
        analysis_id="analysis-1",
        action=AuditAction.ANALYSIS_STARTED,
    )
    second = sink.append(
        analysis_id="analysis-1",
        action=AuditAction.REPORT_CREATED,
        details={"status": "completed"},
    )

    assert first.action is AuditAction.ANALYSIS_STARTED
    assert second.action is AuditAction.REPORT_CREATED
    assert sink.recent() == [second, first]


def test_in_memory_audit_sink_recent_honors_limit() -> None:
    sink = InMemoryAuditSink()
    for index in range(3):
        sink.append(
            analysis_id=f"analysis-{index}",
            action=AuditAction.ANALYSIS_STARTED,
        )

    recent = sink.recent(limit=2)

    assert [event.analysis_id for event in recent] == ["analysis-2", "analysis-1"]


def test_in_memory_audit_sink_rejects_invalid_recent_limit() -> None:
    sink = InMemoryAuditSink()

    with pytest.raises(ValueError, match="greater than zero"):
        sink.recent(limit=0)
