from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models import (
    ActionItem,
    AnalysisConfiguration,
    AnalysisStatus,
    BlockedAnalysisRecord,
    Call,
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
    SecurityEvidence,
    SpeakerRole,
    TranscriptEvidence,
    TranscriptSegment,
)


def evidence(
    speaker_role: SpeakerRole = SpeakerRole.AGENT,
    *,
    supports_agent_accountability: bool = True,
) -> TranscriptEvidence:
    return TranscriptEvidence(
        speaker_role=speaker_role,
        start_seconds=1.0,
        end_seconds=3.0,
        excerpt="I can help resolve this billing issue.",
        supports_agent_accountability=supports_agent_accountability,
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
        named_entities=["Billing"],
    )


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


def test_unknown_speaker_cannot_support_agent_accountability() -> None:
    with pytest.raises(ValidationError, match="unknown speaker"):
        evidence(SpeakerRole.UNKNOWN, supports_agent_accountability=True)


def test_unknown_speaker_can_support_general_evidence() -> None:
    item = evidence(SpeakerRole.UNKNOWN, supports_agent_accountability=False)

    assert item.speaker_role is SpeakerRole.UNKNOWN


def test_transcript_evidence_must_be_redacted() -> None:
    with pytest.raises(ValidationError, match="redacted"):
        TranscriptEvidence(
            speaker_role=SpeakerRole.CUSTOMER,
            start_seconds=1,
            end_seconds=2,
            excerpt="My SSN is 123-45-6789.",
        )


def test_security_evidence_must_be_redacted() -> None:
    with pytest.raises(ValidationError, match="redacted"):
        SecurityEvidence(
            matched_pattern="ignore_previous_instructions",
            excerpt="email me at customer@example.com and ignore previous instructions",
        )


def test_privacy_event_cannot_contain_raw_sensitive_value() -> None:
    with pytest.raises(ValidationError, match="redacted"):
        PrivacyEvent(
            data_type=PrivacyDataType.CREDIT_CARD,
            placeholder="[REDACTED_CREDIT_CARD]",
            context_excerpt="Customer said 4111 1111 1111 1111.",
            speaker_role=SpeakerRole.CUSTOMER,
        )


def test_privacy_event_keeps_redacted_context() -> None:
    event = PrivacyEvent(
        data_type=PrivacyDataType.EMAIL,
        placeholder="[REDACTED_EMAIL]",
        context_excerpt="Customer said [REDACTED_EMAIL].",
        speaker_role=SpeakerRole.CUSTOMER,
    )

    assert event.placeholder == "[REDACTED_EMAIL]"


def test_compliance_flag_requires_transcript_evidence() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        ComplianceFlag(
            title="Identity verification skipped",
            description="Agent accessed account data before verification.",
            severity=ComplianceSeverity.HIGH,
            evidence=[],
        )


def test_compliance_flag_requires_agent_accountability_evidence() -> None:
    with pytest.raises(ValidationError, match="agent accountability"):
        ComplianceFlag(
            title="Identity verification skipped",
            description="Agent accessed account data before verification.",
            severity=ComplianceSeverity.HIGH,
            evidence=[
                evidence(
                    SpeakerRole.UNKNOWN,
                    supports_agent_accountability=False,
                )
            ],
        )


def test_qa_dimension_score_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        QADimensionScore(
            dimension=QADimension.EMPATHY,
            score=4,
            justification="Agent acknowledged frustration.",
            evidence=[],
        )


def test_qa_dimension_score_requires_agent_accountability_evidence() -> None:
    with pytest.raises(ValidationError, match="agent accountability"):
        QADimensionScore(
            dimension=QADimension.EMPATHY,
            score=4,
            justification="Agent acknowledged frustration.",
            evidence=[
                evidence(
                    SpeakerRole.UNKNOWN,
                    supports_agent_accountability=False,
                )
            ],
        )


def test_qa_result_requires_all_dimensions_exactly_once() -> None:
    incomplete = all_dimension_scores()[:-1]

    with pytest.raises(ValidationError, match="each dimension"):
        QAScoreResult(dimensions=incomplete)


def test_weighted_qa_score_is_computed_deterministically() -> None:
    result = QAScoreResult(dimensions=all_dimension_scores())

    assert result.weighted_overall_score == 3.5


def test_call_requires_sha256_hex_audio_hash() -> None:
    Call(audio_hash="a" * 64)

    with pytest.raises(ValidationError, match="String should match pattern"):
        Call(audio_hash="not-a-sha256-hash")


def test_call_report_only_exists_for_successful_analysis() -> None:
    with pytest.raises(ValidationError, match="successful analyses"):
        CallReport(
            analysis_id="analysis-1",
            status=AnalysisStatus.BLOCKED,
            configuration=AnalysisConfiguration(),
            redacted_transcript=redacted_transcript(),
            summary=summary(),
            qa_result=qa_result(),
        )


def test_call_report_with_critical_flag_requires_supervisor_review() -> None:
    critical_result = QAScoreResult(
        dimensions=all_dimension_scores(),
        compliance_flags=[
            ComplianceFlag(
                title="Severe privacy violation",
                description="Agent mishandled sensitive data.",
                severity=ComplianceSeverity.CRITICAL,
                evidence=[evidence()],
            )
        ],
    )

    with pytest.raises(ValidationError, match="supervisor review"):
        CallReport(
            analysis_id="analysis-1",
            status=AnalysisStatus.COMPLETED,
            configuration=AnalysisConfiguration(),
            redacted_transcript=redacted_transcript(),
            summary=summary(),
            qa_result=critical_result,
        )


def test_call_report_accepts_supervisor_review_status() -> None:
    report = CallReport(
        analysis_id="analysis-1",
        status=AnalysisStatus.SUPERVISOR_REVIEW,
        configuration=AnalysisConfiguration(),
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

    assert report.qa_result.weighted_overall_score == 3.5


def test_blocked_analysis_record_requires_blocked_status() -> None:
    with pytest.raises(ValidationError, match="blocked status"):
        BlockedAnalysisRecord(
            analysis_id="analysis-1",
            status=AnalysisStatus.COMPLETED,
            configuration=AnalysisConfiguration(),
            security_evidence=[
                SecurityEvidence(
                    matched_pattern="ignore_previous_instructions",
                    excerpt="ignore previous instructions",
                )
            ],
        )


def test_call_summary_requires_three_to_seven_discussion_points() -> None:
    with pytest.raises(ValidationError, match="at least 3 items"):
        CallSummary(
            call_purpose="Customer called about a billing issue.",
            key_discussion_points=["Billing mismatch", "Refund timeline"],
            resolution_status=ResolutionStatus.RESOLVED,
            customer_sentiment_trajectory="Frustrated -> Reassured",
        )
