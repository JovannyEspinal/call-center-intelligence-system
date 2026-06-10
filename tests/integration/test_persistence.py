from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from src.database import (
    AnalysisRepository,
    create_session_factory,
    create_sqlite_engine,
    init_database,
)
from src.database.schema import CallReportRow, CallRow, TranscriptionCacheRow
from src.models import (
    ActionItem,
    AnalysisConfiguration,
    AnalysisMetadata,
    AnalysisStatus,
    AuditAction,
    AuditEvent,
    Call,
    CallAnalysis,
    CallReport,
    CallSummary,
    ComplianceFlag,
    ComplianceSeverity,
    PrivacyDataType,
    PrivacyEvent,
    QADimension,
    QADimensionScore,
    QAScoreResult,
    RedactedTranscript,
    ResolutionStatus,
    SpeakerRole,
    TranscriptEvidence,
    TranscriptionCacheEntry,
    TranscriptSegment,
)

VALID_AUDIO_HASH = "a" * 64


@pytest.fixture
def session_factory(tmp_path: Path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    init_database(engine)
    return create_session_factory(engine)


def evidence() -> TranscriptEvidence:
    return TranscriptEvidence(
        speaker_role=SpeakerRole.AGENT,
        start_seconds=1,
        end_seconds=3,
        excerpt="I can help resolve this billing issue.",
        supports_agent_accountability=True,
    )


def all_dimension_scores() -> list[QADimensionScore]:
    return [
        QADimensionScore(
            dimension=dimension,
            score=score,
            justification=f"{dimension.value} justification",
            evidence=[evidence()],
        )
        for dimension, score in (
            (QADimension.PROFESSIONALISM, 4),
            (QADimension.EMPATHY, 5),
            (QADimension.PROBLEM_RESOLUTION, 3),
            (QADimension.COMPLIANCE, 2),
            (QADimension.COMMUNICATION_CLARITY, 4),
        )
    ]


def redacted_transcript() -> RedactedTranscript:
    return RedactedTranscript(
        full_text="Agent: I can help. Customer: My card is [REDACTED_CREDIT_CARD].",
        segments=[
            TranscriptSegment(
                speaker_role=SpeakerRole.AGENT,
                start_seconds=0,
                end_seconds=2,
                text="I can help.",
                confidence=0.94,
            ),
            TranscriptSegment(
                speaker_role=SpeakerRole.CUSTOMER,
                start_seconds=2,
                end_seconds=5,
                text="My card is [REDACTED_CREDIT_CARD].",
                confidence=0.91,
            ),
        ],
    )


def summary() -> CallSummary:
    return CallSummary(
        call_purpose="Customer called about a billing issue.",
        key_discussion_points=[
            "Billing mismatch",
            "Refund timeline",
            "Confirmation email",
        ],
        action_items=[
            ActionItem(description="Email refund confirmation", owner="agent")
        ],
        resolution_status=ResolutionStatus.RESOLVED,
        customer_sentiment_trajectory="Frustrated -> Reassured",
    )


def qa_result() -> QAScoreResult:
    return QAScoreResult(
        dimensions=all_dimension_scores(),
        compliance_flags=[
            ComplianceFlag(
                title="Identity verification skipped",
                description="Agent accessed account data before verification.",
                severity=ComplianceSeverity.HIGH,
                evidence=[evidence()],
            )
        ],
    )


def analysis(
    analysis_id: str,
    *,
    status: AnalysisStatus = AnalysisStatus.COMPLETED,
    status_reason: str | None = None,
) -> CallAnalysis:
    return CallAnalysis(
        analysis_id=analysis_id,
        call=Call(audio_hash=VALID_AUDIO_HASH),
        status=status,
        configuration=AnalysisConfiguration(),
        metadata=AnalysisMetadata(department="billing"),
        status_reason=status_reason,
    )


def report(analysis_id: str) -> CallReport:
    return CallReport(
        analysis_id=analysis_id,
        status=AnalysisStatus.COMPLETED,
        configuration=AnalysisConfiguration(),
        metadata=AnalysisMetadata(
            filename="[REDACTED_EMAIL]",
            caller_id="[REDACTED_PHONE]",
            department="billing",
        ),
        redacted_transcript=redacted_transcript(),
        summary=summary(),
        qa_result=qa_result(),
        privacy_events=[
            PrivacyEvent(
                data_type=PrivacyDataType.CREDIT_CARD,
                placeholder="[REDACTED_CREDIT_CARD]",
                context_excerpt="Customer said [REDACTED_CREDIT_CARD].",
                speaker_role=SpeakerRole.CUSTOMER,
            )
        ],
    )


def test_same_call_can_have_multiple_analyses(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.save_analysis(analysis("analysis-1"))
        repository.save_analysis(
            analysis(
                "analysis-2",
                status=AnalysisStatus.SUPERVISOR_REVIEW,
                status_reason="Critical compliance flag",
            )
        )
        session.commit()

    with session_factory() as session:
        repository = AnalysisRepository(session)

        call_count = session.scalar(
            select(CallRow).where(CallRow.audio_hash == VALID_AUDIO_HASH)
        )
        history = repository.list_analysis_history()
        analysis_count = repository.analysis_count_for_call(VALID_AUDIO_HASH)

    assert call_count is not None
    assert len(history) == 1
    assert history[0].call.audio_hash == VALID_AUDIO_HASH
    assert [item.analysis_id for item in history[0].analyses] == [
        "analysis-2",
        "analysis-1",
    ]
    assert analysis_count == 2


def test_get_or_create_call_is_idempotent(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.get_or_create_call(VALID_AUDIO_HASH)
        repository.get_or_create_call(VALID_AUDIO_HASH)
        session.commit()

        assert session.scalar(
            select(CallRow).where(CallRow.audio_hash == VALID_AUDIO_HASH)
        )
        assert session.query(CallRow).count() == 1


def test_report_round_trips_as_valid_redacted_json(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.save_analysis(analysis("analysis-1"))
        saved_report = repository.save_report(report("analysis-1"))
        session.commit()

    with session_factory() as session:
        repository = AnalysisRepository(session)
        loaded_report = repository.get_report("analysis-1")
        report_json = session.scalar(
            select(CallReportRow.report_json).where(
                CallReportRow.analysis_id == "analysis-1"
            )
        )

    assert loaded_report == saved_report
    assert loaded_report is not None
    assert loaded_report.qa_result.weighted_overall_score == 3.5
    assert report_json is not None
    assert "4111 1111 1111 1111" not in report_json
    assert "customer@example.com" not in report_json


def test_report_requires_existing_analysis(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)

        with pytest.raises(ValueError, match="before its call analysis"):
            repository.save_report(report("missing-analysis"))


def test_audit_events_are_appended_and_read_newest_first(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.append_audit_event(
            AuditEvent(
                analysis_id="analysis-1",
                action=AuditAction.ANALYSIS_STARTED,
            )
        )
        completed = repository.append_audit_event(
            AuditEvent(
                analysis_id="analysis-1",
                action=AuditAction.INTAKE_COMPLETED,
                details={"detected_format": "wav", "file_size_bytes": 100},
            )
        )
        session.commit()

    with session_factory() as session:
        repository = AnalysisRepository(session)
        recent = repository.recent_audit_events(limit=2, analysis_id="analysis-1")

    assert [event.action for event in recent] == [
        AuditAction.INTAKE_COMPLETED,
        AuditAction.ANALYSIS_STARTED,
    ]
    assert recent[0] == completed


def test_duplicate_audit_event_id_is_rejected(session_factory) -> None:
    event = AuditEvent(
        event_id="event-1",
        analysis_id="analysis-1",
        action=AuditAction.ANALYSIS_STARTED,
    )

    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.append_audit_event(event)

        with pytest.raises(ValueError, match="already exists"):
            repository.append_audit_event(event)


def test_transcription_cache_reuse_does_not_replace_analysis_history(
    session_factory,
) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.save_transcription_cache_entry(
            TranscriptionCacheEntry(
                audio_hash=VALID_AUDIO_HASH,
                redacted_transcript=redacted_transcript(),
            )
        )
        repository.save_analysis(analysis("analysis-1"))
        repository.save_analysis(analysis("analysis-2"))
        repository.append_audit_event(
            AuditEvent(
                analysis_id="analysis-2",
                action=AuditAction.TRANSCRIPTION_CACHE_USED,
            )
        )
        session.commit()

    with session_factory() as session:
        repository = AnalysisRepository(session)
        cache_entry = repository.get_transcription_cache_entry(VALID_AUDIO_HASH)
        analyses = repository.list_analyses_for_call(VALID_AUDIO_HASH)
        audit_events = repository.recent_audit_events(analysis_id="analysis-2")

    assert cache_entry is not None
    assert cache_entry.redacted_transcript == redacted_transcript()
    assert [item.analysis_id for item in analyses] == ["analysis-2", "analysis-1"]
    assert [event.action for event in audit_events] == [
        AuditAction.TRANSCRIPTION_CACHE_USED
    ]


def test_transcription_cache_ignores_stale_cache_version(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.save_transcription_cache_entry(
            TranscriptionCacheEntry(
                audio_hash=VALID_AUDIO_HASH,
                redacted_transcript=redacted_transcript(),
            )
        )
        row = session.get(TranscriptionCacheRow, VALID_AUDIO_HASH)
        row.cache_version = "legacy"
        session.commit()

    with session_factory() as session:
        repository = AnalysisRepository(session)

        assert repository.get_transcription_cache_entry(VALID_AUDIO_HASH) is None


def test_failed_and_blocked_analyses_do_not_require_reports(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.save_analysis(
            analysis(
                "analysis-failed",
                status=AnalysisStatus.FAILED,
                status_reason="unsupported audio format",
            )
        )
        repository.save_analysis(
            analysis(
                "analysis-blocked",
                status=AnalysisStatus.BLOCKED,
                status_reason="prompt injection detected",
            )
        )
        session.commit()

    with session_factory() as session:
        repository = AnalysisRepository(session)
        analyses = repository.list_analyses_for_call(VALID_AUDIO_HASH)

    assert {item.status for item in analyses} == {
        AnalysisStatus.FAILED,
        AnalysisStatus.BLOCKED,
    }
    assert repository.get_report("analysis-failed") is None
    assert repository.get_report("analysis-blocked") is None
