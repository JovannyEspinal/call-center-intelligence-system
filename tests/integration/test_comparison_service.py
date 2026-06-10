"""Analysis Result Comparison service tests."""

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
    AnalysisConfiguration,
    AnalysisMetadata,
    AnalysisStatus,
    Call,
    CallAnalysis,
    CallReport,
    CallSummary,
    ComplianceFlag,
    ComplianceSeverity,
    LLMProvider,
    QADimension,
    QADimensionScore,
    QAScoreResult,
    RedactedTranscript,
    ResolutionStatus,
    SpeakerRole,
    TranscriptEvidence,
    TranscriptSegment,
)
from src.services import AnalysisComparisonError, AnalysisComparisonService

CALL_HASH = "a" * 64
OTHER_CALL_HASH = "b" * 64
BASE_TIME = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def session_factory(tmp_path: Path):
    engine = create_sqlite_engine(tmp_path / "comparison.db")
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
        full_text="Agent: I can help.",
        segments=[
            TranscriptSegment(
                speaker_role=SpeakerRole.AGENT,
                start_seconds=0,
                end_seconds=2,
                text="I can help.",
                confidence=0.94,
            )
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
        resolution_status=ResolutionStatus.RESOLVED,
        customer_sentiment_trajectory="Frustrated -> Reassured",
    )


def qa_result(
    *,
    empathy_score: int = 5,
    flag_titles: tuple[str, ...] = (),
    flag_severity: ComplianceSeverity = ComplianceSeverity.HIGH,
) -> QAScoreResult:
    scores = {
        QADimension.PROFESSIONALISM: 4,
        QADimension.EMPATHY: empathy_score,
        QADimension.PROBLEM_RESOLUTION: 3,
        QADimension.COMPLIANCE: 2,
        QADimension.COMMUNICATION_CLARITY: 4,
    }
    return QAScoreResult(
        dimensions=[
            QADimensionScore(
                dimension=dimension,
                score=score,
                justification=f"{dimension.value} justification",
                evidence=[evidence()],
            )
            for dimension, score in scores.items()
        ],
        compliance_flags=[
            ComplianceFlag(
                title=title,
                description=f"{title} description",
                severity=flag_severity,
                evidence=[evidence()],
            )
            for title in flag_titles
        ],
    )


def analysis(
    analysis_id: str,
    *,
    audio_hash: str = CALL_HASH,
    status: AnalysisStatus = AnalysisStatus.COMPLETED,
    provider: LLMProvider = LLMProvider.MOCK,
    llm_model: str = "mock",
    created_at: datetime = BASE_TIME,
) -> CallAnalysis:
    return CallAnalysis(
        analysis_id=analysis_id,
        call=Call(audio_hash=audio_hash),
        status=status,
        configuration=AnalysisConfiguration(
            llm_provider=provider,
            llm_model=llm_model,
        ),
        metadata=AnalysisMetadata(department="billing"),
        created_at=created_at,
    )


def report(
    analysis_id: str,
    *,
    qa: QAScoreResult | None = None,
    status: AnalysisStatus = AnalysisStatus.COMPLETED,
) -> CallReport:
    return CallReport(
        analysis_id=analysis_id,
        status=status,
        configuration=AnalysisConfiguration(),
        redacted_transcript=redacted_transcript(),
        summary=summary(),
        qa_result=qa if qa is not None else qa_result(),
    )


def test_compare_reports_includes_config_and_score_differences(
    session_factory,
) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.save_analysis(analysis("base", provider=LLMProvider.MOCK))
        repository.save_report(report("base", qa=qa_result(empathy_score=5)))
        repository.save_analysis(
            analysis(
                "other",
                provider=LLMProvider.OPENAI,
                llm_model="gpt-4o-mini",
                created_at=BASE_TIME + timedelta(minutes=5),
            )
        )
        repository.save_report(
            report(
                "other",
                qa=qa_result(empathy_score=3, flag_titles=("Verification skipped",)),
            )
        )
        session.commit()

    with session_factory() as session:
        repository = AnalysisRepository(session)
        comparison = AnalysisComparisonService(repository).compare("base", "other")

    assert comparison.audio_hash == CALL_HASH
    assert comparison.base_analysis_id == "base"
    assert comparison.other_analysis_id == "other"
    assert comparison.base_status is AnalysisStatus.COMPLETED
    assert comparison.other_status is AnalysisStatus.COMPLETED

    config_fields = {item.field: item for item in comparison.configuration_differences}
    assert config_fields["llm_provider"].base_value == "mock"
    assert config_fields["llm_provider"].other_value == "openai"
    assert config_fields["llm_model"].other_value == "gpt-4o-mini"
    assert "created_at" not in config_fields

    result = comparison.report_comparison
    assert result is not None
    assert result.base_weighted_score == 3.5
    assert result.other_weighted_score == 3.1
    assert result.weighted_score_delta == -0.4

    dimension_deltas = {item.dimension: item for item in result.dimension_deltas}
    empathy = dimension_deltas[QADimension.EMPATHY]
    assert empathy.base_score == 5
    assert empathy.other_score == 3
    assert empathy.delta == -2
    assert dimension_deltas[QADimension.PROFESSIONALISM].delta == 0

    assert result.flags_added == ["Verification skipped"]
    assert result.flags_removed == []
    assert result.resolution_status_changed is False
    assert result.privacy_event_count_delta == 0


def test_compare_without_other_report_returns_status_only(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.save_analysis(analysis("base"))
        repository.save_report(report("base"))
        repository.save_analysis(
            analysis(
                "other",
                status=AnalysisStatus.FAILED,
                created_at=BASE_TIME + timedelta(minutes=5),
            )
        )
        session.commit()

    with session_factory() as session:
        repository = AnalysisRepository(session)
        comparison = AnalysisComparisonService(repository).compare("base", "other")

    assert comparison.other_status is AnalysisStatus.FAILED
    assert comparison.report_comparison is None


def test_compare_rejects_analyses_of_different_calls(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.save_analysis(analysis("base"))
        repository.save_analysis(analysis("other", audio_hash=OTHER_CALL_HASH))
        session.commit()

    with session_factory() as session:
        repository = AnalysisRepository(session)
        with pytest.raises(AnalysisComparisonError, match="same call"):
            AnalysisComparisonService(repository).compare("base", "other")


def test_compare_rejects_unknown_or_identical_analysis_ids(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.save_analysis(analysis("base"))
        session.commit()

    with session_factory() as session:
        repository = AnalysisRepository(session)
        service = AnalysisComparisonService(repository)
        with pytest.raises(AnalysisComparisonError, match="not found"):
            service.compare("base", "missing")
        with pytest.raises(AnalysisComparisonError, match="different"):
            service.compare("base", "base")
