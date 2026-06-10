"""Structured sentiment trajectory contract tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models import (
    CallPhase,
    CallSummary,
    ResolutionStatus,
    SentimentPoint,
    SentimentTrend,
)


def summary_with_points(points: list[SentimentPoint]) -> CallSummary:
    return CallSummary(
        call_purpose="Customer called about a billing issue.",
        key_discussion_points=[
            "Billing mismatch",
            "Refund timeline",
            "Confirmation email",
        ],
        resolution_status=ResolutionStatus.RESOLVED,
        customer_sentiment_trajectory="Frustrated -> Reassured",
        sentiment_points=points,
    )


def point(phase: CallPhase, score: int) -> SentimentPoint:
    return SentimentPoint(
        phase=phase,
        score=score,
        observation=f"Customer sentiment during the {phase.value} of the call.",
    )


def test_summary_without_sentiment_points_has_unknown_trend() -> None:
    summary = summary_with_points([])

    assert summary.sentiment_points == []
    assert summary.sentiment_trend is SentimentTrend.UNKNOWN


def test_sentiment_points_must_cover_each_phase_once_in_order() -> None:
    with pytest.raises(ValidationError, match="one sentiment point per call phase"):
        summary_with_points([point(CallPhase.OPENING, 2)])

    with pytest.raises(ValidationError, match="one sentiment point per call phase"):
        summary_with_points(
            [
                point(CallPhase.OPENING, 2),
                point(CallPhase.OPENING, 3),
                point(CallPhase.CLOSING, 4),
            ]
        )

    with pytest.raises(ValidationError, match="call order"):
        summary_with_points(
            [
                point(CallPhase.CLOSING, 4),
                point(CallPhase.MIDDLE, 3),
                point(CallPhase.OPENING, 2),
            ]
        )


def test_sentiment_trend_improving_when_closing_exceeds_opening() -> None:
    summary = summary_with_points(
        [
            point(CallPhase.OPENING, 2),
            point(CallPhase.MIDDLE, 3),
            point(CallPhase.CLOSING, 4),
        ]
    )

    assert summary.sentiment_trend is SentimentTrend.IMPROVING


def test_sentiment_trend_declining_when_closing_below_opening() -> None:
    summary = summary_with_points(
        [
            point(CallPhase.OPENING, 4),
            point(CallPhase.MIDDLE, 3),
            point(CallPhase.CLOSING, 2),
        ]
    )

    assert summary.sentiment_trend is SentimentTrend.DECLINING


def test_sentiment_trend_stable_when_opening_and_closing_match() -> None:
    summary = summary_with_points(
        [
            point(CallPhase.OPENING, 3),
            point(CallPhase.MIDDLE, 2),
            point(CallPhase.CLOSING, 3),
        ]
    )

    assert summary.sentiment_trend is SentimentTrend.STABLE


def test_sentiment_point_score_bounds() -> None:
    with pytest.raises(ValidationError):
        point(CallPhase.OPENING, 0)
    with pytest.raises(ValidationError):
        point(CallPhase.OPENING, 6)


def test_mock_analysis_client_populates_sentiment_points() -> None:
    from src.models import RedactedTranscript, SpeakerRole, TranscriptSegment
    from src.services import MockAnalysisClient

    transcript = RedactedTranscript(
        full_text="Agent: I can help.",
        segments=[
            TranscriptSegment(
                speaker_role=SpeakerRole.AGENT,
                start_seconds=0,
                end_seconds=2,
                text="I can help.",
                confidence=0.9,
            )
        ],
    )

    summary = MockAnalysisClient().generate_summary(transcript)

    assert [item.phase for item in summary.sentiment_points] == [
        CallPhase.OPENING,
        CallPhase.MIDDLE,
        CallPhase.CLOSING,
    ]
    assert summary.sentiment_trend is SentimentTrend.IMPROVING
