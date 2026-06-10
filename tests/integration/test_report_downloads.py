from __future__ import annotations

import json
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
    TranscriptSegment,
)
from src.services import ReportDownloadError, ReportDownloadService
from src.services.report_downloads import (
    _event_context,
    _event_time_range,
    _unique_privacy_events,
)

VALID_AUDIO_HASH = "c" * 64


@pytest.fixture
def session_factory(tmp_path: Path):
    engine = create_sqlite_engine(tmp_path / "reports.db")
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


def summary() -> CallSummary:
    return CallSummary(
        call_purpose="Customer called about a <billing> & refund issue.",
        key_discussion_points=[
            "Billing mismatch",
            "Refund <timeline> & confirmation",
            "Confirmation email",
        ],
        action_items=[
            ActionItem(description="Email refund confirmation", owner="agent")
        ],
        resolution_status=ResolutionStatus.RESOLVED,
        customer_sentiment_trajectory="Frustrated -> Reassured",
    )


def call_report() -> CallReport:
    return CallReport(
        analysis_id="analysis-report",
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
                data_type=PrivacyDataType.PHONE,
                placeholder="[REDACTED_PHONE]",
                context_excerpt="Customer said [REDACTED_PHONE].",
                speaker_role=SpeakerRole.CUSTOMER,
            )
        ],
    )


def report_with_duplicate_privacy_events() -> CallReport:
    return call_report().model_copy(
        update={
            "privacy_events": [
                PrivacyEvent(
                    data_type=PrivacyDataType.PHONE,
                    placeholder="[REDACTED_PHONE]",
                    context_excerpt="Customer said [REDACTED_PHONE].",
                    speaker_role=SpeakerRole.CUSTOMER,
                ),
                PrivacyEvent(
                    data_type=PrivacyDataType.PHONE,
                    placeholder="[REDACTED_PHONE]",
                    context_excerpt="Customer said [REDACTED_PHONE].",
                    speaker_role=SpeakerRole.CUSTOMER,
                ),
            ]
        },
    )


def seed_report(repository: AnalysisRepository) -> None:
    repository.save_analysis(
        CallAnalysis(
            analysis_id="analysis-report",
            call=Call(audio_hash=VALID_AUDIO_HASH),
            status=AnalysisStatus.COMPLETED,
            configuration=AnalysisConfiguration(),
            metadata=AnalysisMetadata(department="billing"),
        )
    )
    repository.save_report(call_report())
    repository.commit()


def test_json_download_returns_pretty_redacted_report(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        seed_report(repository)

    with session_factory() as session:
        repository = AnalysisRepository(session)
        download = ReportDownloadService(repository).generate_json_download(
            "analysis-report",
            reviewer_id="reviewer-1",
        )

    payload = json.loads(download.content)
    assert download.filename == "analysis-report-call-report.json"
    assert payload["analysis_id"] == "analysis-report"
    assert payload["qa_result"]["weighted_overall_score"] == 3.5
    assert "[REDACTED_PHONE]" in download.content
    assert "555-123-4567" not in download.content
    assert "customer@example.com" not in download.content

    with session_factory() as session:
        repository = AnalysisRepository(session)
        audit_events = repository.recent_audit_events(analysis_id="analysis-report")

    assert audit_events[0].action is AuditAction.REPORT_DOWNLOADED
    assert audit_events[0].reviewer_id == "reviewer-1"
    assert audit_events[0].details == {"format": "json"}


def test_json_download_without_identity_does_not_record_audit_event(
    session_factory,
) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        seed_report(repository)
        download = ReportDownloadService(repository).generate_json_download(
            "analysis-report"
        )

    with session_factory() as session:
        repository = AnalysisRepository(session)
        audit_events = repository.recent_audit_events(analysis_id="analysis-report")

    assert download.analysis_id == "analysis-report"
    assert audit_events == []


def test_pdf_download_writes_temporary_redacted_pdf(
    tmp_path: Path,
    session_factory,
) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        seed_report(repository)
        download = ReportDownloadService(repository).generate_pdf_download(
            "analysis-report",
            output_dir=tmp_path,
            session_id="session-1",
        )

    pdf_bytes = download.path.read_bytes()
    assert download.filename == "analysis-report-call-report.pdf"
    assert download.path.exists()
    assert pdf_bytes.startswith(b"%PDF")
    assert b"00:02-00:05" in pdf_bytes
    assert b"[REDACTED_PHONE]" in pdf_bytes
    assert b"555-123-4567" not in pdf_bytes
    assert b"customer@example.com" not in pdf_bytes

    with session_factory() as session:
        repository = AnalysisRepository(session)
        audit_events = repository.recent_audit_events(analysis_id="analysis-report")

    assert audit_events[0].action is AuditAction.REPORT_DOWNLOADED
    assert audit_events[0].session_id == "session-1"
    assert audit_events[0].details == {"format": "pdf"}


def test_pdf_privacy_events_are_deduplicated_for_counts_and_details() -> None:
    report = report_with_duplicate_privacy_events()

    unique_events = _unique_privacy_events(report)

    assert len(report.privacy_events) == 2
    assert len(unique_events) == 1


def test_pdf_privacy_event_context_uses_full_transcript_segment() -> None:
    report = call_report()

    assert _event_context(report, report.privacy_events[0]) == (
        "My phone is [REDACTED_PHONE]."
    )


def test_pdf_privacy_event_context_uses_full_text_when_segments_split_entity() -> None:
    report = call_report().model_copy(
        update={
            "redacted_transcript": RedactedTranscript(
                full_text=(
                    "What is your date of birth and physical address? "
                    "[REDACTED_DOB]. My address is [REDACTED_ADDRESS]."
                ),
                segments=[
                    TranscriptSegment(
                        speaker_role=SpeakerRole.AGENT,
                        start_seconds=0,
                        end_seconds=1,
                        text="What is your date of birth and physical address?",
                    ),
                    TranscriptSegment(
                        speaker_role=SpeakerRole.CUSTOMER,
                        start_seconds=1,
                        end_seconds=2,
                        text="June 26,",
                    ),
                    TranscriptSegment(
                        speaker_role=SpeakerRole.CUSTOMER,
                        start_seconds=2,
                        end_seconds=3,
                        text="[REDACTED_SECURITY_NUMBER].",
                    ),
                ],
            ),
            "privacy_events": [
                PrivacyEvent(
                    data_type=PrivacyDataType.DATE_OF_BIRTH,
                    placeholder="[REDACTED_DOB]",
                    context_excerpt=(
                        "our date of birth and physical address? "
                        "[REDACTED_DOB]. My address is"
                    ),
                )
            ],
        }
    )

    assert _event_context(report, report.privacy_events[0]) == (
        "What is your date of birth and physical address? "
        "[REDACTED_DOB]. My address is [REDACTED_ADDRESS]."
    )
    assert _event_time_range(report, report.privacy_events[0]) == "00:00-00:01"


def test_pdf_privacy_events_are_sorted_by_timestamp() -> None:
    report = call_report().model_copy(
        update={
            "privacy_events": [
                PrivacyEvent(
                    data_type=PrivacyDataType.EMAIL,
                    placeholder="[REDACTED_EMAIL]",
                    context_excerpt="Later [REDACTED_EMAIL].",
                    start_seconds=8,
                    end_seconds=9,
                ),
                PrivacyEvent(
                    data_type=PrivacyDataType.PHONE,
                    placeholder="[REDACTED_PHONE]",
                    context_excerpt="Earlier [REDACTED_PHONE].",
                    start_seconds=2,
                    end_seconds=5,
                ),
            ]
        }
    )

    unique_events = _unique_privacy_events(report)

    assert [event.data_type for event in unique_events] == [
        PrivacyDataType.PHONE,
        PrivacyDataType.EMAIL,
    ]


def test_pdf_privacy_event_intro_uses_unique_count(
    tmp_path: Path,
    session_factory,
) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.save_analysis(
            CallAnalysis(
                analysis_id="analysis-report",
                call=Call(audio_hash=VALID_AUDIO_HASH),
                status=AnalysisStatus.COMPLETED,
                configuration=AnalysisConfiguration(),
            )
        )
        repository.save_report(report_with_duplicate_privacy_events())
        repository.commit()
        download = ReportDownloadService(repository).generate_pdf_download(
            "analysis-report",
            output_dir=tmp_path,
        )

    pdf_bytes = download.path.read_bytes()
    assert b"1 unique privacy events were recorded." in pdf_bytes
    assert b"2 unique privacy events were recorded." not in pdf_bytes


def test_pdf_includes_reviewer_intelligence_sections(
    tmp_path: Path,
    session_factory,
) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)
        seed_report(repository)
        download = ReportDownloadService(repository).generate_pdf_download(
            "analysis-report",
            output_dir=tmp_path,
        )

    pdf_bytes = download.path.read_bytes()
    # KPI strip and section structure
    assert b"Weighted QA Score" in pdf_bytes
    assert b"QA Scorecard" in pdf_bytes
    assert b"Action Items" in pdf_bytes
    # Summary intelligence
    assert b"Email refund confirmation" in pdf_bytes
    # reportlab splits text runs at the escaped ">" in "->"
    assert b"Customer Sentiment: Frustrated" in pdf_bytes
    assert b"Reassured" in pdf_bytes
    assert b"Resolved" in pdf_bytes
    # Scorecard shows rubric weights and accountability evidence
    assert b"30%" in pdf_bytes
    assert b"I can help resolve this billing issue." in pdf_bytes
    # Severity-coded compliance flag
    assert b"HIGH" in pdf_bytes
    # Page furniture
    assert b"Confidential" in pdf_bytes


def test_pdf_renders_structured_sentiment_points(
    tmp_path: Path,
    session_factory,
) -> None:
    from src.models import CallPhase, SentimentPoint

    scored_summary = summary().model_copy(
        update={
            "sentiment_points": [
                SentimentPoint(
                    phase=CallPhase.OPENING,
                    score=2,
                    observation="Customer opened frustrated.",
                ),
                SentimentPoint(
                    phase=CallPhase.MIDDLE,
                    score=3,
                    observation="Customer engaged with the agent.",
                ),
                SentimentPoint(
                    phase=CallPhase.CLOSING,
                    score=4,
                    observation="Customer reassured by the resolution.",
                ),
            ]
        }
    )
    with session_factory() as session:
        repository = AnalysisRepository(session)
        repository.save_analysis(
            CallAnalysis(
                analysis_id="analysis-report",
                call=Call(audio_hash=VALID_AUDIO_HASH),
                status=AnalysisStatus.COMPLETED,
                configuration=AnalysisConfiguration(),
            )
        )
        repository.save_report(
            call_report().model_copy(update={"summary": scored_summary})
        )
        repository.commit()
        download = ReportDownloadService(repository).generate_pdf_download(
            "analysis-report",
            output_dir=tmp_path,
        )

    pdf_bytes = download.path.read_bytes()
    assert b"opening 2/5" in pdf_bytes
    assert b"closing 4/5" in pdf_bytes
    assert b"improving" in pdf_bytes


def test_report_download_fails_for_missing_report(session_factory) -> None:
    with session_factory() as session:
        repository = AnalysisRepository(session)

        with pytest.raises(ReportDownloadError, match="does not exist"):
            ReportDownloadService(repository).generate_json_download("missing")
