"""Pipeline trend analytics tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
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
    AnalysisStatus,
    Call,
    CallAnalysis,
    CallReport,
    CallSummary,
    ComplianceFlag,
    ComplianceSeverity,
    QADimension,
    QADimensionScore,
    QAScoreResult,
    RedactedTranscript,
    ResolutionStatus,
    SpeakerRole,
    TranscriptEvidence,
    TranscriptSegment,
)
from src.services import PipelineAnalyticsService

DAY_ONE = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
DAY_TWO = DAY_ONE + timedelta(days=1)


@pytest.fixture
def session_factory(tmp_path: Path):
    engine = create_sqlite_engine(tmp_path / "analytics.db")
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


def report(
    analysis_id: str,
    *,
    score: int,
    flag_count: int = 0,
) -> CallReport:
    return CallReport(
        analysis_id=analysis_id,
        status=AnalysisStatus.COMPLETED,
        configuration=AnalysisConfiguration(),
        redacted_transcript=RedactedTranscript(
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
        ),
        summary=CallSummary(
            call_purpose="Customer called about a billing issue.",
            key_discussion_points=["Billing", "Refund", "Email"],
            resolution_status=ResolutionStatus.RESOLVED,
            customer_sentiment_trajectory="Frustrated -> Reassured",
        ),
        qa_result=QAScoreResult(
            dimensions=[
                QADimensionScore(
                    dimension=dimension,
                    score=score,
                    justification=f"{dimension.value} justification",
                    evidence=[evidence()],
                )
                for dimension in QADimension
            ],
            compliance_flags=[
                ComplianceFlag(
                    title=f"Flag {index}",
                    description="Flag description",
                    severity=ComplianceSeverity.MEDIUM,
                    evidence=[evidence()],
                )
                for index in range(flag_count)
            ],
        ),
    )


def analysis(
    analysis_id: str,
    *,
    audio_hash: str,
    status: AnalysisStatus,
    created_at: datetime,
) -> CallAnalysis:
    return CallAnalysis(
        analysis_id=analysis_id,
        call=Call(audio_hash=audio_hash),
        status=status,
        configuration=AnalysisConfiguration(),
        created_at=created_at,
    )


def test_daily_trends_aggregates_by_utc_day(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.save_analysis(
            analysis(
                "day1-completed",
                audio_hash="a" * 64,
                status=AnalysisStatus.COMPLETED,
                created_at=DAY_ONE,
            )
        )
        repository.save_report(report("day1-completed", score=4, flag_count=1))
        repository.save_analysis(
            analysis(
                "day1-failed",
                audio_hash="b" * 64,
                status=AnalysisStatus.FAILED,
                created_at=DAY_ONE + timedelta(hours=2),
            )
        )
        repository.save_analysis(
            analysis(
                "day2-completed",
                audio_hash="c" * 64,
                status=AnalysisStatus.COMPLETED,
                created_at=DAY_TWO,
            )
        )
        repository.save_report(report("day2-completed", score=2))
        session.commit()

    with session_factory() as session:
        repository = AnalysisRepository(session)
        trends = PipelineAnalyticsService(repository).daily_trends()

    assert [row.day for row in trends] == [date(2026, 6, 1), date(2026, 6, 2)]

    day_one = trends[0]
    assert day_one.total == 2
    assert day_one.completed == 1
    assert day_one.failed == 1
    assert day_one.blocked == 0
    assert day_one.supervisor_review == 0
    assert day_one.success_rate == 50.0
    assert day_one.average_score == 4.0
    assert day_one.compliance_flag_count == 1

    day_two = trends[1]
    assert day_two.total == 1
    assert day_two.success_rate == 100.0
    assert day_two.average_score == 2.0
    assert day_two.compliance_flag_count == 0


def test_daily_trends_empty_history(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        trends = PipelineAnalyticsService(repository).daily_trends()

    assert trends == []
