from __future__ import annotations

from datetime import UTC, datetime

from scripts.evaluate_demo_outputs import evaluate_report, format_eval_summary
from src.models import (
    ActionItem,
    AnalysisConfiguration,
    AnalysisStatus,
    CallReport,
    CallSummary,
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


def report_with_segments(
    segments: list[TranscriptSegment],
    *,
    privacy_events: list[PrivacyEvent] | None = None,
) -> CallReport:
    return CallReport(
        analysis_id="analysis-eval",
        status=AnalysisStatus.COMPLETED,
        configuration=AnalysisConfiguration(),
        redacted_transcript=RedactedTranscript(
            full_text=" ".join(segment.text for segment in segments),
            segments=segments,
        ),
        summary=CallSummary(
            call_purpose="Customer called about a billing issue.",
            key_discussion_points=[
                "Customer described the issue.",
                "Agent acknowledged the issue.",
                "Agent offered next steps.",
            ],
            action_items=[ActionItem(description="Follow up", owner="agent")],
            resolution_status=ResolutionStatus.RESOLVED,
            customer_sentiment_trajectory="Concerned -> Reassured",
        ),
        qa_result=QAScoreResult(
            dimensions=[
                QADimensionScore(
                    dimension=dimension,
                    score=4,
                    justification=f"{dimension.value} was acceptable.",
                    evidence=[
                        TranscriptEvidence(
                            speaker_role=SpeakerRole.AGENT,
                            start_seconds=0,
                            end_seconds=2,
                            excerpt="Hello, I can help.",
                            supports_agent_accountability=True,
                        )
                    ],
                )
                for dimension in QADimension
            ]
        ),
        privacy_events=privacy_events or [],
        created_at=datetime.now(UTC),
    )


def segment(index: int, role: SpeakerRole) -> TranscriptSegment:
    return TranscriptSegment(
        speaker_role=role,
        start_seconds=float(index),
        end_seconds=float(index + 1),
        text=f"Segment {index} text.",
    )


def test_evaluate_report_passes_complete_redacted_report() -> None:
    report = report_with_segments(
        [
            segment(0, SpeakerRole.AGENT),
            segment(1, SpeakerRole.CUSTOMER),
            segment(2, SpeakerRole.AGENT),
            segment(3, SpeakerRole.CUSTOMER),
            segment(4, SpeakerRole.AGENT),
        ],
        privacy_events=[
            PrivacyEvent(
                data_type=PrivacyDataType.PHONE,
                placeholder="[REDACTED_PHONE]",
                context_excerpt="Phone [REDACTED_PHONE]",
            )
        ],
    )

    checks = evaluate_report(
        report,
        min_segments=5,
        max_unknown_speaker_ratio=0.05,
    )

    assert all(check.passed for check in checks)
    assert "Checks passed: 7/7" in format_eval_summary(report.analysis_id, checks)


def test_evaluate_report_fails_raw_sensitive_values_and_unknown_ratio() -> None:
    report = report_with_segments(
        [
            segment(0, SpeakerRole.UNKNOWN),
            segment(1, SpeakerRole.UNKNOWN),
            segment(2, SpeakerRole.AGENT),
        ]
    )

    checks = evaluate_report(
        report,
        min_segments=5,
        max_unknown_speaker_ratio=0.05,
        extra_report_text_surfaces=["customer@example.com"],
    )
    by_name = {check.name: check for check in checks}

    assert not by_name["report_text_has_no_raw_sensitive_values"].passed
    assert not by_name["redacted_transcript_has_segments"].passed
    assert not by_name["unknown_speaker_ratio_under_threshold"].passed
