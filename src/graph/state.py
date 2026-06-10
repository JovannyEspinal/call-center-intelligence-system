"""LangGraph pipeline state contracts."""

from __future__ import annotations

from typing import TypedDict

from src.models import (
    AnalysisConfiguration,
    AnalysisMetadata,
    AnalysisStatus,
    AudioFormat,
    AudioInput,
    AudioProperties,
    AuditEvent,
    BlockedAnalysisRecord,
    CallReport,
    CallSummary,
    IntakeResult,
    PrivacyEvent,
    PromptInjectionResult,
    QAScoreResult,
    RawTranscriptSegment,
    RedactedTranscript,
)


class PipelineState(TypedDict, total=False):
    """Shared state passed through the call analysis graph."""

    analysis_id: str
    audio_input: AudioInput | None
    audio_hash: str
    detected_format: AudioFormat
    file_size_bytes: int
    audio_properties: AudioProperties
    temp_audio_path: str | None
    intake_result: IntakeResult | None
    metadata: AnalysisMetadata
    configuration: AnalysisConfiguration
    status: AnalysisStatus
    error: str

    raw_transcript_text: str | None
    raw_transcript_segments: list[RawTranscriptSegment] | None
    redacted_transcript: RedactedTranscript
    privacy_events: list[PrivacyEvent]
    transcript_privacy_events: list[PrivacyEvent]
    injection_result: PromptInjectionResult

    summary: CallSummary
    qa_result: QAScoreResult
    report: CallReport
    blocked_record: BlockedAnalysisRecord

    audit_events: list[AuditEvent]
    persisted: bool
    persistence_skipped_reason: str
    transcription_cache_hit: bool
    cleanup_error: str
