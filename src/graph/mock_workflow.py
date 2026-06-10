"""LangGraph workflow with mocked transcription and injectable analysis client."""

from __future__ import annotations

import hashlib
from pathlib import Path

from langgraph.graph import END, StateGraph

from src.agents import (
    IntakeSecurityBlocked,
    IntakeValidationError,
    validate_audio_input,
)
from src.database import AnalysisRepository
from src.graph.state import PipelineState
from src.models import (
    TRANSCRIPTION_CACHE_VERSION,
    AnalysisConfiguration,
    AnalysisMetadata,
    AnalysisStatus,
    AuditAction,
    BlockedAnalysisRecord,
    Call,
    CallAnalysis,
    ComplianceSeverity,
    RedactedTranscript,
    SecurityEvidence,
    SpeakerRole,
    TranscriptionCacheEntry,
    TranscriptSegment,
)
from src.models.reports import CallReport
from src.services import (
    AnalysisLLMClient,
    AuditSink,
    InMemoryAuditSink,
    MockAnalysisClient,
    MockTranscriptionClient,
    TranscriptionClient,
)
from src.services.security import RegexPIIRedactor, RegexPromptInjectionDetector


def build_mock_workflow(
    audit_sink: AuditSink | None = None,
    *,
    analysis_client: AnalysisLLMClient | None = None,
    transcription_client: TranscriptionClient | None = None,
    repository: AnalysisRepository | None = None,
    temp_dir: str | Path | None = None,
):
    """Build the analysis graph with replaceable expensive dependencies."""
    sink = audit_sink or InMemoryAuditSink()
    llm_client = analysis_client or MockAnalysisClient()
    stt_client = transcription_client or MockTranscriptionClient()
    graph = StateGraph(PipelineState)
    graph.add_node("start_analysis", lambda state: start_analysis(state, sink))
    graph.add_node("intake", lambda state: intake(state, sink, temp_dir=temp_dir))
    graph.add_node(
        "transcribe_audio",
        lambda state: transcribe_audio(state, sink, stt_client),
    )
    graph.add_node(
        "load_transcription_cache",
        lambda state: load_transcription_cache(state, sink, repository),
    )
    graph.add_node("detect_injection", detect_injection)
    graph.add_node("redact_pii", lambda state: redact_pii(state, sink))
    graph.add_node(
        "save_transcription_cache",
        lambda state: save_transcription_cache(state, repository),
    )
    graph.add_node(
        "generate_summary",
        lambda state: generate_summary(state, sink, llm_client),
    )
    graph.add_node("score_qa", lambda state: score_qa(state, sink, llm_client))
    graph.add_node("build_report", lambda state: build_report(state, sink))
    graph.add_node("blocked", lambda state: blocked(state, sink))
    graph.add_node("failed", lambda state: failed(state, sink))
    graph.add_node("persist_result", lambda state: persist_result(state, repository))
    graph.add_node("finalize_result", finalize_result)

    graph.set_entry_point("start_analysis")
    graph.add_edge("start_analysis", "intake")
    graph.add_conditional_edges(
        "intake",
        route_after_intake,
        {
            "continue": "load_transcription_cache",
            "blocked": "blocked",
            "failed": "failed",
        },
    )
    graph.add_conditional_edges(
        "load_transcription_cache",
        route_after_cache_lookup,
        {"cached": "generate_summary", "miss": "transcribe_audio"},
    )
    graph.add_conditional_edges(
        "transcribe_audio",
        route_after_transcription,
        {"continue": "detect_injection", "failed": "failed"},
    )
    graph.add_conditional_edges(
        "detect_injection",
        route_after_injection_detection,
        {"continue": "redact_pii", "blocked": "blocked"},
    )
    graph.add_edge("redact_pii", "save_transcription_cache")
    graph.add_edge("save_transcription_cache", "generate_summary")
    graph.add_conditional_edges(
        "generate_summary",
        route_after_analysis_client,
        {"continue": "score_qa", "failed": "failed"},
    )
    graph.add_conditional_edges(
        "score_qa",
        route_after_analysis_client,
        {"continue": "build_report", "failed": "failed"},
    )
    graph.add_edge("build_report", "persist_result")
    graph.add_edge("blocked", "persist_result")
    graph.add_edge("failed", "persist_result")
    graph.add_edge("persist_result", "finalize_result")
    graph.add_edge("finalize_result", END)
    return graph.compile()


def start_analysis(state: PipelineState, audit_sink: AuditSink) -> PipelineState:
    event = audit_sink.append(
        analysis_id=state["analysis_id"],
        action=AuditAction.ANALYSIS_STARTED,
    )
    return {
        "metadata": state.get("metadata", AnalysisMetadata()),
        "configuration": state.get("configuration", AnalysisConfiguration()),
        "audit_events": [*state.get("audit_events", []), event],
    }


def intake(
    state: PipelineState,
    audit_sink: AuditSink,
    *,
    temp_dir: str | Path | None = None,
) -> PipelineState:
    audio_input = state.get("audio_input")
    if audio_input is None:
        return {"status": AnalysisStatus.FAILED, "error": "audio_input is required"}

    try:
        result = validate_audio_input(audio_input, temp_dir=temp_dir)
    except IntakeSecurityBlocked as exc:
        return {
            "audio_hash": hashlib.sha256(audio_input.audio_bytes).hexdigest(),
            "status": AnalysisStatus.BLOCKED,
            "error": str(exc),
            "metadata": exc.metadata,
            "privacy_events": [
                *state.get("privacy_events", []),
                *exc.privacy_events,
            ],
            "injection_result": exc.injection_result,
        }
    except IntakeValidationError as exc:
        return {
            "audio_hash": hashlib.sha256(audio_input.audio_bytes).hexdigest(),
            "status": AnalysisStatus.FAILED,
            "error": str(exc),
        }

    event = audit_sink.append(
        analysis_id=state["analysis_id"],
        action=AuditAction.INTAKE_COMPLETED,
        details={
            "detected_format": result.detected_format.value,
            "file_size_bytes": result.file_size_bytes,
        },
    )
    return {
        "audio_hash": result.audio_hash,
        "detected_format": result.detected_format,
        "file_size_bytes": result.file_size_bytes,
        "audio_properties": result.properties,
        "temp_audio_path": result.temp_audio_path,
        "intake_result": result,
        "metadata": result.metadata,
        "privacy_events": [
            *state.get("privacy_events", []),
            *result.privacy_events,
        ],
        "audit_events": [*state.get("audit_events", []), event],
    }


def transcribe_audio(
    state: PipelineState,
    audit_sink: AuditSink,
    transcription_client: TranscriptionClient,
) -> PipelineState:
    if state.get("raw_transcript_text"):
        transcript_text = state["raw_transcript_text"] or ""
        raw_segments = state.get("raw_transcript_segments")
        event = audit_sink.append(
            analysis_id=state["analysis_id"],
            action=AuditAction.TRANSCRIPTION_COMPLETED,
            details={"transcription_source": "state_override"},
        )
        return {
            "raw_transcript_text": transcript_text,
            "raw_transcript_segments": raw_segments,
            "audit_events": [*state.get("audit_events", []), event],
        }

    try:
        result = transcription_client.transcribe(state["temp_audio_path"] or "")
    except Exception as exc:
        return {
            "status": AnalysisStatus.FAILED,
            "error": f"transcription failed: {exc}",
        }

    event = audit_sink.append(
        analysis_id=state["analysis_id"],
        action=AuditAction.TRANSCRIPTION_COMPLETED,
        details={"transcription_model": result.model_name},
    )
    return {
        "raw_transcript_text": result.full_text,
        "raw_transcript_segments": result.segments,
        "audit_events": [*state.get("audit_events", []), event],
    }


def load_transcription_cache(
    state: PipelineState,
    audit_sink: AuditSink,
    repository: AnalysisRepository | None,
) -> PipelineState:
    if repository is None or state.get("raw_transcript_text"):
        return {"transcription_cache_hit": False}

    cache_entry = repository.get_transcription_cache_entry(
        state["audio_hash"],
        expected_cache_version=transcription_cache_version_for_state(state),
    )
    if cache_entry is None:
        return {"transcription_cache_hit": False}

    event = audit_sink.append(
        analysis_id=state["analysis_id"],
        action=AuditAction.TRANSCRIPTION_CACHE_USED,
    )
    return {
        "transcription_cache_hit": True,
        "redacted_transcript": cache_entry.redacted_transcript,
        "privacy_events": [
            *state.get("privacy_events", []),
            *cache_entry.privacy_events,
        ],
        "audit_events": [*state.get("audit_events", []), event],
    }


def detect_injection(state: PipelineState) -> PipelineState:
    detector = RegexPromptInjectionDetector()
    result = detector.scan_text(state["raw_transcript_text"] or "")
    return {"injection_result": result}


def redact_pii(state: PipelineState, audit_sink: AuditSink) -> PipelineState:
    redactor = RegexPIIRedactor()
    redaction = redactor.redact_text(state["raw_transcript_text"] or "")
    raw_segments = state.get("raw_transcript_segments")
    if raw_segments:
        segment_redactions = [
            redactor.redact_text(
                segment.text,
                speaker_role=segment.speaker_role,
                start_seconds=segment.start_seconds,
                end_seconds=segment.end_seconds,
            )
            for segment in raw_segments
        ]
        segments = [
            TranscriptSegment(
                speaker_role=segment.speaker_role,
                start_seconds=segment.start_seconds,
                end_seconds=segment.end_seconds,
                text=segment_redaction.redacted_text,
                confidence=segment.confidence,
            )
            for segment, segment_redaction in zip(
                raw_segments,
                segment_redactions,
                strict=True,
            )
        ]
    else:
        segments = [
            TranscriptSegment(
                speaker_role=SpeakerRole.UNKNOWN,
                start_seconds=0,
                end_seconds=10,
                text=redaction.redacted_text,
                confidence=1.0,
            )
        ]

    transcript = RedactedTranscript(
        full_text=redaction.redacted_text,
        segments=segments,
    )
    privacy_events = _timestamp_privacy_events(redaction.privacy_events, transcript)
    event = audit_sink.append(
        analysis_id=state["analysis_id"],
        action=AuditAction.PII_REDACTION_COMPLETED,
        details={"privacy_event_count": len(privacy_events)},
    )
    return {
        "redacted_transcript": transcript,
        "transcript_privacy_events": privacy_events,
        "privacy_events": [
            *state.get("privacy_events", []),
            *privacy_events,
        ],
        "audit_events": [*state.get("audit_events", []), event],
    }


def _timestamp_privacy_events(
    privacy_events,
    transcript: RedactedTranscript,
):
    return [
        event.model_copy(update=context)
        if (context := _infer_privacy_event_context(event, transcript))
        else event
        for event in privacy_events
    ]


def _infer_privacy_event_context(event, transcript: RedactedTranscript):
    best_segment = _best_privacy_event_segment(event, transcript)
    if best_segment is None:
        return {"context_excerpt": event.context_excerpt}
    return {
        "context_excerpt": best_segment.text,
        "speaker_role": best_segment.speaker_role,
        "start_seconds": best_segment.start_seconds,
        "end_seconds": best_segment.end_seconds,
    }


def _best_privacy_event_segment(event, transcript: RedactedTranscript):
    candidates = [
        segment
        for segment in transcript.segments
        if event.placeholder in segment.text
    ]
    if not candidates:
        return None

    context_tokens = _token_set(event.context_excerpt)
    best_segment = max(
        candidates,
        key=lambda segment: len(context_tokens & _token_set(segment.text)),
    )
    if not context_tokens & _token_set(best_segment.text):
        return None
    return best_segment


def _token_set(value: str) -> set[str]:
    return {
        token.strip(".,:;!?()[]'\"").lower()
        for token in value.split()
        if token.strip(".,:;!?()[]'\"")
    }


def save_transcription_cache(
    state: PipelineState,
    repository: AnalysisRepository | None,
) -> PipelineState:
    if repository is None:
        return {}
    repository.save_transcription_cache_entry(
        TranscriptionCacheEntry(
            audio_hash=state["audio_hash"],
            redacted_transcript=state["redacted_transcript"],
            privacy_events=state.get("transcript_privacy_events", []),
            cache_version=transcription_cache_version_for_state(state),
        )
    )
    return {}


def transcription_cache_version_for_state(state: PipelineState) -> str:
    """Scope reusable transcripts to redaction and transcription processing."""
    configuration = state["configuration"]
    return f"{TRANSCRIPTION_CACHE_VERSION}:{configuration.transcription_model}"


def generate_summary(
    state: PipelineState,
    audit_sink: AuditSink,
    analysis_client: AnalysisLLMClient,
) -> PipelineState:
    try:
        summary = analysis_client.generate_summary(state["redacted_transcript"])
    except Exception as exc:
        return {
            "status": AnalysisStatus.FAILED,
            "error": f"summary generation failed: {exc}",
        }
    event = audit_sink.append(
        analysis_id=state["analysis_id"],
        action=AuditAction.SUMMARY_COMPLETED,
    )
    return {
        "summary": summary,
        "audit_events": [*state.get("audit_events", []), event],
    }


def score_qa(
    state: PipelineState,
    audit_sink: AuditSink,
    analysis_client: AnalysisLLMClient,
) -> PipelineState:
    try:
        qa_result = analysis_client.score_qa(
            state["redacted_transcript"],
            state["summary"],
        )
    except Exception as exc:
        return {
            "status": AnalysisStatus.FAILED,
            "error": f"qa scoring failed: {exc}",
        }
    event = audit_sink.append(
        analysis_id=state["analysis_id"],
        action=AuditAction.QA_COMPLETED,
    )
    return {
        "qa_result": qa_result,
        "audit_events": [*state.get("audit_events", []), event],
    }


def build_report(state: PipelineState, audit_sink: AuditSink) -> PipelineState:
    status = (
        AnalysisStatus.SUPERVISOR_REVIEW
        if any(
            flag.severity is ComplianceSeverity.CRITICAL
            for flag in state["qa_result"].compliance_flags
        )
        else AnalysisStatus.COMPLETED
    )
    audit_events = list(state.get("audit_events", []))
    if status is AnalysisStatus.SUPERVISOR_REVIEW:
        audit_events.append(
            audit_sink.append(
                analysis_id=state["analysis_id"],
                action=AuditAction.SUPERVISOR_REVIEW_REQUIRED,
            )
        )

    report = CallReport(
        analysis_id=state["analysis_id"],
        status=status,
        configuration=state["configuration"],
        metadata=state["metadata"],
        redacted_transcript=state["redacted_transcript"],
        summary=state["summary"],
        qa_result=state["qa_result"],
        privacy_events=state.get("privacy_events", []),
    )
    audit_events.append(
        audit_sink.append(
            analysis_id=state["analysis_id"], action=AuditAction.REPORT_CREATED
        )
    )
    return {"status": status, "report": report, "audit_events": audit_events}


def blocked(state: PipelineState, audit_sink: AuditSink) -> PipelineState:
    injection_result = state["injection_result"]
    redactor = RegexPIIRedactor()
    security_evidence = [
        SecurityEvidence(
            matched_pattern=match.pattern_name,
            excerpt=redactor.redact_text(match.excerpt).redacted_text,
        )
        for match in injection_result.matches
    ]
    raw_transcript_text = state.get("raw_transcript_text")
    transcript_privacy_events = (
        redactor.redact_text(raw_transcript_text).privacy_events
        if raw_transcript_text
        else []
    )
    blocked_record = BlockedAnalysisRecord(
        analysis_id=state["analysis_id"],
        configuration=state["configuration"],
        security_evidence=security_evidence,
        privacy_events=[
            *state.get("privacy_events", []),
            *transcript_privacy_events,
        ],
    )
    event = audit_sink.append(
        analysis_id=state["analysis_id"],
        action=AuditAction.PROMPT_INJECTION_BLOCKED,
        details={"matched_pattern_count": len(injection_result.matches)},
    )
    return {
        "status": AnalysisStatus.BLOCKED,
        "blocked_record": blocked_record,
        "audit_events": [*state.get("audit_events", []), event],
    }


def failed(state: PipelineState, audit_sink: AuditSink) -> PipelineState:
    event = audit_sink.append(
        analysis_id=state["analysis_id"],
        action=AuditAction.ANALYSIS_FAILED,
        details={"error": state.get("error", "analysis failed")},
    )
    return {
        "status": AnalysisStatus.FAILED,
        "audit_events": [*state.get("audit_events", []), event],
    }


def persist_result(
    state: PipelineState,
    repository: AnalysisRepository | None,
) -> PipelineState:
    if repository is None:
        return {"persisted": False, "persistence_skipped_reason": "repository missing"}

    audio_hash = state.get("audio_hash")
    if audio_hash is None:
        for event in state.get("audit_events", []):
            repository.append_audit_event(event)
        repository.commit()
        return {
            "persisted": False,
            "persistence_skipped_reason": "audio_hash missing",
        }

    analysis = CallAnalysis(
        analysis_id=state["analysis_id"],
        call=Call(audio_hash=audio_hash),
        status=state["status"],
        configuration=state["configuration"],
        metadata=state["metadata"],
        status_reason=state.get("error"),
    )
    repository.save_analysis(analysis)
    if "report" in state:
        repository.save_report(state["report"])
    for event in state.get("audit_events", []):
        repository.append_audit_event(event)
    repository.commit()
    return {"persisted": True}


def finalize_result(state: PipelineState) -> PipelineState:
    updates: PipelineState = {
        "audio_input": None,
        "intake_result": None,
        "raw_transcript_text": None,
        "raw_transcript_segments": None,
    }
    temp_audio_path = state.get("temp_audio_path")
    if temp_audio_path is None:
        updates["temp_audio_path"] = None
        return updates

    try:
        Path(temp_audio_path).unlink(missing_ok=True)
    except OSError as exc:
        updates["cleanup_error"] = str(exc)
    updates["temp_audio_path"] = None
    return updates


def route_after_intake(state: PipelineState) -> str:
    if state.get("status") is AnalysisStatus.FAILED:
        return "failed"
    if state.get("status") is AnalysisStatus.BLOCKED:
        return "blocked"
    return "continue"


def route_after_cache_lookup(state: PipelineState) -> str:
    return "cached" if state.get("transcription_cache_hit") else "miss"


def route_after_transcription(state: PipelineState) -> str:
    return "failed" if state.get("status") is AnalysisStatus.FAILED else "continue"


def route_after_injection_detection(state: PipelineState) -> str:
    result = state["injection_result"]
    return "blocked" if result.injection_detected else "continue"


def route_after_analysis_client(state: PipelineState) -> str:
    return "failed" if state.get("status") is AnalysisStatus.FAILED else "continue"
