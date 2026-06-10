from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.database import (
    AnalysisRepository,
    create_session_factory,
    create_sqlite_engine,
    init_database,
)
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
    LLMProvider,
    PrivacyDataType,
    PrivacyEvent,
    QADimension,
    QADimensionScore,
    QAScoreResult,
    RedactedTranscript,
    ResolutionStatus,
    SpeakerRole,
    TranscriptEvidence,
    TranscriptSegment,
)
from src.services import AnalysisHistoryService

CALL_A_HASH = "a" * 64
CALL_B_HASH = "b" * 64
BASE_TIME = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)


@pytest.fixture
def session_factory(tmp_path: Path):
    engine = create_sqlite_engine(tmp_path / "history.db")
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


def redacted_transcript() -> RedactedTranscript:
    return RedactedTranscript(
        full_text="Agent: I can help. Customer: My phone is [REDACTED_PHONE].",
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
                text="My phone is [REDACTED_PHONE].",
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
        dimensions=[
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
        ],
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
    audio_hash: str,
    *,
    status: AnalysisStatus,
    created_at: datetime,
    status_reason: str | None = None,
    provider: LLMProvider = LLMProvider.MOCK,
) -> CallAnalysis:
    return CallAnalysis(
        analysis_id=analysis_id,
        call=Call(audio_hash=audio_hash),
        status=status,
        configuration=AnalysisConfiguration(
            llm_provider=provider,
            llm_model=f"{provider.value}-model",
            summary_prompt_version="summary-v1",
            qa_prompt_version="qa-v1",
        ),
        metadata=AnalysisMetadata(
            filename="[REDACTED_EMAIL]",
            department="billing",
        ),
        created_at=created_at,
        status_reason=status_reason,
    )


def report(
    analysis_id: str,
    *,
    status: AnalysisStatus = AnalysisStatus.COMPLETED,
) -> CallReport:
    return CallReport(
        analysis_id=analysis_id,
        status=status,
        configuration=AnalysisConfiguration(),
        metadata=AnalysisMetadata(
            filename="[REDACTED_EMAIL]",
            department="billing",
        ),
        redacted_transcript=redacted_transcript(),
        summary=summary(),
        qa_result=qa_result(),
        privacy_events=[
            PrivacyEvent(
                data_type=PrivacyDataType.PHONE,
                placeholder="[REDACTED_PHONE]",
                context_excerpt="Customer said [REDACTED_PHONE].",
                speaker_role=SpeakerRole.CUSTOMER,
            )
        ],
    )


def seed_history(repository: AnalysisRepository) -> None:
    repository.save_analysis(
        analysis(
            "analysis-a-old",
            CALL_A_HASH,
            status=AnalysisStatus.COMPLETED,
            created_at=BASE_TIME,
        )
    )
    repository.save_report(report("analysis-a-old"))
    repository.append_audit_event(
        AuditEvent(
            analysis_id="analysis-a-old",
            action=AuditAction.ANALYSIS_STARTED,
            created_at=BASE_TIME,
        )
    )
    repository.append_audit_event(
        AuditEvent(
            analysis_id="analysis-a-old",
            action=AuditAction.REPORT_CREATED,
            created_at=BASE_TIME + timedelta(seconds=1),
        )
    )

    repository.save_analysis(
        analysis(
            "analysis-a-new",
            CALL_A_HASH,
            status=AnalysisStatus.FAILED,
            created_at=BASE_TIME + timedelta(minutes=10),
            status_reason="unsupported audio format",
            provider=LLMProvider.OPENAI,
        )
    )
    repository.append_audit_event(
        AuditEvent(
            analysis_id="analysis-a-new",
            action=AuditAction.ANALYSIS_FAILED,
            created_at=BASE_TIME + timedelta(minutes=10),
        )
    )
    for offset in range(21):
        repository.append_audit_event(
            AuditEvent(
                analysis_id="analysis-a-new",
                action=AuditAction.ANALYSIS_FAILED,
                created_at=BASE_TIME + timedelta(minutes=11, seconds=offset),
            )
        )

    repository.save_analysis(
        analysis(
            "analysis-b",
            CALL_B_HASH,
            status=AnalysisStatus.COMPLETED,
            created_at=BASE_TIME + timedelta(minutes=5),
        )
    )
    repository.save_report(report("analysis-b"))


def test_analysis_history_service_groups_and_formats_rows(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        seed_history(repository)
        session.commit()

    with session_factory() as session:
        repository = AnalysisRepository(session)
        history = AnalysisHistoryService(repository).list_history()

    assert [group.audio_hash for group in history] == [CALL_B_HASH, CALL_A_HASH]

    call_a = history[1]
    assert call_a.analysis_count == 2
    assert call_a.latest_analysis_id == "analysis-a-new"
    assert call_a.latest_status is AnalysisStatus.FAILED

    newest = call_a.analyses[0]
    assert newest.analysis_id == "analysis-a-new"
    assert newest.status is AnalysisStatus.FAILED
    assert newest.provider == "openai"
    assert newest.llm_model == "openai-model"
    assert newest.summary_prompt_version == "summary-v1"
    assert newest.qa_prompt_version == "qa-v1"
    assert newest.metadata_label == "billing | [REDACTED_EMAIL]"
    assert newest.status_reason == "unsupported audio format"
    assert newest.report_available is False
    assert newest.weighted_score is None
    assert newest.privacy_event_count == 0
    assert newest.audit_event_count == 22
    assert newest.comparison_candidate_ids == ["analysis-a-old"]

    older = call_a.analyses[1]
    assert older.report_available is True
    assert older.weighted_score == 3.5
    assert older.privacy_event_count == 1
    assert older.audit_event_count == 2
    assert older.comparison_candidate_ids == ["analysis-a-new"]


def test_analysis_history_service_handles_empty_history(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        history = AnalysisHistoryService(repository).list_history()

    assert history == []
