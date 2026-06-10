"""Gradio application wiring for the Call Center Intelligence System."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

from src.database import (
    AnalysisRepository,
    create_session_factory,
    create_sqlite_engine,
    init_database,
)
from src.graph import build_mock_workflow
from src.models import (
    AnalysisConfiguration,
    AnalysisStatus,
    AudioInput,
    CallSummary,
    LLMProvider,
    RawAnalysisMetadata,
    RedactedTranscript,
    describe_sentiment_trajectory,
)
from src.services import (
    AnalysisComparisonError,
    AnalysisComparisonService,
    AnalysisHistoryRow,
    AnalysisHistoryService,
    AnalysisLLMClient,
    FasterWhisperTranscriptionClient,
    MockAnalysisClient,
    MockTranscriptionClient,
    OpenAIAnalysisClient,
    OpenAIDiarizedTranscriptionClient,
    PipelineAnalyticsService,
    ReportDownloadError,
    ReportDownloadService,
    TranscriptionClient,
    filter_history_rows,
    max_flag_severity,
)
from src.ui.render import (
    DASHBOARD_CSS,
    FORCE_DARK_JS,
    render_app_bar,
    render_audit_action_chip,
    render_empty_summary_card,
    render_flags_table,
    render_kpi_cards,
    render_message_card,
    render_score_cell,
    render_section_header,
    render_status_chip,
    render_summary_card,
    render_system_health,
    render_table_html,
    render_trend_bar,
    risk_label,
    score_quality,
)

HISTORY_ANALYSIS_ID_INDEX = 1
HISTORY_REPORT_AVAILABLE_INDEX = 6


@dataclass(frozen=True)
class AppSettings:
    """Runtime configuration loaded from environment variables."""

    database_url: str = "sqlite:///data/calls.db"
    analysis_backend: str = "mock"
    openai_model: str = "gpt-4o-mini"
    transcription_backend: str = "mock"
    openai_transcription_model: str = "gpt-4o-transcribe-diarize"
    openai_diarized_chunk_seconds: int = 180
    whisper_model: str = "base"
    whisper_device: str = "auto"
    whisper_compute_type: str = "int8"
    server_name: str = "0.0.0.0"
    server_port: int = 7860


@dataclass(frozen=True)
class AppRuntime:
    """Initialized app dependencies shared by UI event handlers."""

    settings: AppSettings
    session_factory: sessionmaker
    analysis_clients: dict[tuple[str, bool], AnalysisLLMClient] = field(
        default_factory=dict
    )
    transcription_clients: dict[str, TranscriptionClient] = field(default_factory=dict)


def load_app_settings() -> AppSettings:
    """Load app settings from `.env` and process environment variables."""
    load_dotenv()
    return AppSettings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/calls.db"),
        analysis_backend=os.getenv(
            "ANALYSIS_BACKEND",
            os.getenv("LLM_PROVIDER", "mock"),
        ).lower(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        transcription_backend=os.getenv("TRANSCRIPTION_BACKEND", "mock").lower(),
        openai_transcription_model=os.getenv(
            "OPENAI_TRANSCRIPTION_MODEL",
            "gpt-4o-transcribe-diarize",
        ),
        openai_diarized_chunk_seconds=int(
            os.getenv("OPENAI_DIARIZED_CHUNK_SECONDS", "180")
        ),
        whisper_model=os.getenv(
            "WHISPER_MODEL",
            os.getenv("WHISPER_MODEL_SIZE", "base"),
        ),
        whisper_device=os.getenv("WHISPER_DEVICE", "auto"),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
    )


def create_app_runtime(settings: AppSettings | None = None) -> AppRuntime:
    """Initialize SQLite persistence and return app runtime dependencies."""
    resolved_settings = settings or load_app_settings()
    database_path = sqlite_path_from_database_url(resolved_settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_sqlite_engine(database_path)
    init_database(engine)
    return AppRuntime(
        settings=resolved_settings,
        session_factory=create_session_factory(engine),
    )


def sqlite_path_from_database_url(database_url: str) -> Path:
    """Resolve the supported SQLite URL format into a filesystem path."""
    if database_url.startswith("sqlite:///"):
        return Path(database_url.removeprefix("sqlite:///"))
    return Path(database_url)


def build_analysis_client(
    settings: AppSettings,
    *,
    backend: str | None = None,
    force_critical_compliance: bool = False,
) -> AnalysisLLMClient:
    """Build the selected structured analysis client."""
    selected_backend = (backend or settings.analysis_backend).lower()
    if selected_backend == "mock":
        return MockAnalysisClient(
            force_critical_compliance=force_critical_compliance,
        )
    if selected_backend == "openai":
        return OpenAIAnalysisClient(model=settings.openai_model)
    raise ValueError(f"unsupported analysis backend: {selected_backend}")


def get_analysis_client(
    runtime: AppRuntime,
    *,
    backend: str | None = None,
    force_critical_compliance: bool = False,
) -> AnalysisLLMClient:
    """Return a cached analysis client for the selected backend/mode."""
    selected_backend = (backend or runtime.settings.analysis_backend).lower()
    cache_key = (selected_backend, force_critical_compliance)
    if cache_key not in runtime.analysis_clients:
        runtime.analysis_clients[cache_key] = build_analysis_client(
            runtime.settings,
            backend=selected_backend,
            force_critical_compliance=force_critical_compliance,
        )
    return runtime.analysis_clients[cache_key]


def build_transcription_client(
    settings: AppSettings,
    *,
    backend: str | None = None,
) -> TranscriptionClient:
    """Build the selected speech-to-text client."""
    selected_backend = (backend or settings.transcription_backend).lower()
    if selected_backend == "mock":
        return MockTranscriptionClient()
    if selected_backend == "faster_whisper":
        return FasterWhisperTranscriptionClient(
            model_name=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    if selected_backend == "openai_diarized":
        return OpenAIDiarizedTranscriptionClient(
            model_name=settings.openai_transcription_model,
            chunk_seconds=settings.openai_diarized_chunk_seconds,
        )
    raise ValueError(f"unsupported transcription backend: {selected_backend}")


def get_transcription_client(
    runtime: AppRuntime,
    *,
    backend: str | None = None,
) -> TranscriptionClient:
    """Return a cached transcription client so real models are loaded once."""
    selected_backend = (backend or runtime.settings.transcription_backend).lower()
    if selected_backend not in runtime.transcription_clients:
        runtime.transcription_clients[selected_backend] = build_transcription_client(
            runtime.settings,
            backend=selected_backend,
        )
    return runtime.transcription_clients[selected_backend]


def _invoke_analysis(
    runtime: AppRuntime,
    *,
    audio_file: str | Path,
    caller_id: str | None,
    department: str | None,
    analysis_backend: str | None = None,
    transcription_backend: str | None = None,
    mock_compliance_mode: str | None = None,
) -> dict:
    """Build inputs and run the analysis graph, returning the raw result."""
    audio_path = Path(audio_file)
    audio_input = AudioInput(
        audio_bytes=audio_path.read_bytes(),
        filename=audio_path.name,
        metadata=RawAnalysisMetadata(
            caller_id=_blank_to_none(caller_id),
            department=_blank_to_none(department),
        ),
    )
    selected_analysis_backend = (
        analysis_backend or runtime.settings.analysis_backend
    ).lower()
    selected_transcription_backend = (
        transcription_backend or runtime.settings.transcription_backend
    ).lower()
    configuration = AnalysisConfiguration(
        llm_provider=LLMProvider(selected_analysis_backend),
        llm_model=(
            runtime.settings.openai_model
            if selected_analysis_backend == "openai"
            else "mock"
        ),
        transcription_model=(
            runtime.settings.whisper_model
            if selected_transcription_backend == "faster_whisper"
            else runtime.settings.openai_transcription_model
            if selected_transcription_backend == "openai_diarized"
            else "mock"
        ),
    )
    analysis_client = get_analysis_client(
        runtime,
        backend=selected_analysis_backend,
        force_critical_compliance=mock_compliance_mode == "critical",
    )
    transcription_client = get_transcription_client(
        runtime,
        backend=selected_transcription_backend,
    )

    with runtime.session_factory() as session:
        repository = AnalysisRepository(session)
        workflow = build_mock_workflow(
            analysis_client=analysis_client,
            transcription_client=transcription_client,
            repository=repository,
        )
        return workflow.invoke(
            {
                "analysis_id": f"analysis-{uuid4()}",
                "audio_input": audio_input,
                "configuration": configuration,
            }
        )


def analyze_uploaded_call(
    runtime: AppRuntime,
    *,
    audio_file: str | Path | None,
    caller_id: str | None,
    department: str | None,
    analysis_backend: str | None = None,
    transcription_backend: str | None = None,
    mock_compliance_mode: str | None = None,
) -> tuple[str, str, str, str, list[list[str]]]:
    """Run the analysis graph from UI inputs and return display-ready outputs."""
    if audio_file is None:
        return (
            "Failed",
            "Upload an audio file before running analysis.",
            "",
            "",
            [],
        )

    try:
        result = _invoke_analysis(
            runtime,
            audio_file=audio_file,
            caller_id=caller_id,
            department=department,
            analysis_backend=analysis_backend,
            transcription_backend=transcription_backend,
            mock_compliance_mode=mock_compliance_mode,
        )
    except Exception as exc:
        return ("Failed", f"Analysis could not start: {exc}", "", "", [])

    return format_analysis_result(result)


def analyze_call_dashboard(
    runtime: AppRuntime,
    *,
    audio_file: str | Path | None,
    caller_id: str | None,
    department: str | None,
    analysis_backend: str | None = None,
    transcription_backend: str | None = None,
    mock_compliance_mode: str | None = None,
) -> tuple[str, str, str, str]:
    """Run analysis and render dashboard outputs (summary card, flags, etc.)."""
    if audio_file is None:
        return (
            render_message_card(
                "failed", "Upload an audio file before running analysis."
            ),
            render_flags_table([]),
            "",
            "",
        )
    try:
        result = _invoke_analysis(
            runtime,
            audio_file=audio_file,
            caller_id=caller_id,
            department=department,
            analysis_backend=analysis_backend,
            transcription_backend=transcription_backend,
            mock_compliance_mode=mock_compliance_mode,
        )
    except Exception as exc:
        return (
            render_message_card("failed", f"Analysis could not start: {exc}"),
            render_flags_table([]),
            "",
            "",
        )
    return render_analysis_outputs(result)


def render_analysis_outputs(result: dict) -> tuple[str, str, str, str]:
    """Render a graph result as (summary card, flags table, transcript, JSON)."""
    status = result.get("status", AnalysisStatus.FAILED)
    status_label = status.value if isinstance(status, AnalysisStatus) else str(status)
    report = result.get("report")
    if report is not None:
        risk = max_flag_severity(report.qa_result.compliance_flags)
        summary_html = render_summary_card(
            status=status_label,
            created_at=report.created_at.isoformat(timespec="seconds"),
            weighted_score=report.qa_result.weighted_overall_score,
            resolution=report.summary.resolution_status.value,
            risk_severity=risk.value if risk is not None else None,
            sentiment_trend=report.summary.sentiment_trend.value,
            purpose=report.summary.call_purpose,
            discussion_points=list(report.summary.key_discussion_points),
            insight_chips=_insight_chips(report),
            sentiment_detail=(
                describe_sentiment_trajectory(report.summary)
                if report.summary.sentiment_points
                else None
            ),
        )
        flags_html = render_flags_table(
            [
                {
                    "severity": flag.severity.value,
                    "title": flag.title,
                    "description": flag.description,
                    "timestamp": _clock(flag.evidence[0].start_seconds)
                    if flag.evidence
                    else None,
                }
                for flag in report.qa_result.compliance_flags
            ]
        )
        return (
            summary_html,
            flags_html,
            format_redacted_transcript(report.redacted_transcript),
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
        )

    blocked_record = result.get("blocked_record")
    if blocked_record is not None:
        return (
            render_message_card(
                "blocked",
                "Analysis blocked for prompt-injection risk.",
                [
                    f"{item.matched_pattern}: {item.excerpt}"
                    for item in blocked_record.security_evidence
                ],
            ),
            render_flags_table([]),
            "",
            "",
        )

    error = result.get("error", "analysis failed")
    return (
        render_message_card(status_label, str(error)),
        render_flags_table([]),
        "",
        "",
    )


def _insight_chips(report) -> list[tuple[str, str]]:
    resolution_tones = {"resolved": "good", "unresolved": "warn", "escalated": "warn"}
    resolution = report.summary.resolution_status.value
    chips: list[tuple[str, str]] = [
        (resolution.title(), resolution_tones.get(resolution, "muted"))
    ]
    for flag in report.qa_result.compliance_flags:
        tone = "bad" if flag.severity.value in {"high", "critical"} else "warn"
        chips.append((flag.title, tone))
    if report.summary.action_items:
        chips.append((f"{len(report.summary.action_items)} Action Items", "muted"))
    if report.privacy_events:
        chips.append((f"{len(report.privacy_events)} Privacy Events", "muted"))
    return chips


def _clock(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def analyze_uploaded_call_and_refresh_dashboard(
    runtime: AppRuntime,
    *,
    audio_file: str | Path | None,
    caller_id: str | None,
    department: str | None,
    analysis_backend: str | None = None,
    transcription_backend: str | None = None,
    mock_compliance_mode: str | None = None,
) -> tuple[
    str,
    str,
    str,
    str,
    list[list[str]],
    list[list[str]],
    str,
    str,
    str,
    list[list[str]],
]:
    """Run analysis and return refreshed history/observability outputs."""
    analysis_outputs = analyze_uploaded_call(
        runtime,
        audio_file=audio_file,
        caller_id=caller_id,
        department=department,
        analysis_backend=analysis_backend,
        transcription_backend=transcription_backend,
        mock_compliance_mode=mock_compliance_mode,
    )
    history_rows = list_analysis_history(runtime)
    selected_analysis_id, download_message = select_history_row_for_download(
        history_rows[0] if history_rows else None
    )
    metrics, audit_rows = observability_snapshot(runtime)
    return (
        *analysis_outputs,
        history_rows,
        selected_analysis_id,
        download_message,
        metrics,
        audit_rows,
    )


def format_analysis_result(result: dict) -> tuple[str, str, str, str, list[list[str]]]:
    """Format a graph result for the Analyze Call tab."""
    status = result.get("status", AnalysisStatus.FAILED)
    status_label = status.value if isinstance(status, AnalysisStatus) else str(status)
    report = result.get("report")
    if report is not None:
        dimension_lines = [
            f"- {dimension.dimension.value}: {dimension.score}/5 "
            f"({dimension.justification})"
            for dimension in report.qa_result.dimensions
        ]
        summary = "\n".join(
            [
                f"Purpose: {report.summary.call_purpose}",
                f"Resolution: {report.summary.resolution_status.value}",
                f"Sentiment: {format_sentiment_trajectory(report.summary)}",
                f"QA Score: {report.qa_result.weighted_overall_score}",
                "",
                "Discussion Points:",
                *[f"- {point}" for point in report.summary.key_discussion_points],
                "",
                "QA Scorecard:",
                *dimension_lines,
            ]
        )
        flags = [
            [
                flag.severity.value,
                flag.title,
                flag.description,
            ]
            for flag in report.qa_result.compliance_flags
        ]
        return (
            status_label,
            summary,
            format_redacted_transcript(report.redacted_transcript),
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
            flags,
        )

    blocked_record = result.get("blocked_record")
    if blocked_record is not None:
        evidence = "\n".join(
            f"- {item.matched_pattern}: {item.excerpt}"
            for item in blocked_record.security_evidence
        )
        return (
            status_label,
            f"Analysis blocked for prompt-injection risk.\n\n{evidence}",
            "",
            "",
            [],
        )

    error = result.get("error", "analysis failed")
    return (status_label, str(error), "", "", [])


def _history_rows(
    runtime: AppRuntime,
    *,
    status: str | None = None,
    query: str | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
) -> list[AnalysisHistoryRow]:
    """Load and filter formatted history rows."""
    with runtime.session_factory() as session:
        repository = AnalysisRepository(session)
        groups = AnalysisHistoryService(repository).list_history()

    return filter_history_rows(
        [analysis for group in groups for analysis in group.analyses],
        status=AnalysisStatus(status) if status else None,
        query=query,
        min_score=min_score,
        max_score=max_score,
        created_from=created_from,
        created_to=created_to,
    )


def list_analysis_history(
    runtime: AppRuntime,
    *,
    status: str | None = None,
    query: str | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
) -> list[list[str]]:
    """Return Analysis History rows for the Gradio table, optionally filtered."""
    return [
        [
            analysis.audio_hash[:12],
            analysis.analysis_id,
            analysis.status.value,
            analysis.created_at.isoformat(timespec="seconds"),
            analysis.metadata_label,
            _format_optional_score(analysis.weighted_score),
            "yes" if analysis.report_available else "no",
            str(analysis.privacy_event_count),
            str(analysis.audit_event_count),
            ", ".join(analysis.comparison_candidate_ids),
        ]
        for analysis in _history_rows(
            runtime,
            status=status,
            query=query,
            min_score=min_score,
            max_score=max_score,
            created_from=created_from,
            created_to=created_to,
        )
    ]


HISTORY_DISPLAY_HEADERS = [
    "Call Hash",
    "Analysis ID",
    "Status",
    "Created",
    "Metadata",
    "QA Score",
    "Risk",
    "Privacy Events",
    "Audit Events",
    "Report",
    "Compare With",
]
HISTORY_DISPLAY_DATATYPES = [
    "str",
    "str",
    "html",
    "str",
    "str",
    "html",
    "html",
    "str",
    "str",
    "str",
    "str",
]
HISTORY_DISPLAY_ID_INDEX = 1
HISTORY_DISPLAY_REPORT_INDEX = 9


def history_display_rows(
    runtime: AppRuntime,
    **filters,
) -> list[list[str]]:
    """History rows with chip/score HTML cells for the dashboard table."""
    rows = []
    for analysis in _history_rows(runtime, **filters):
        risk_severity = (
            analysis.max_flag_severity.value
            if analysis.max_flag_severity is not None
            else None
        )
        risk_text, risk_tone = risk_label(risk_severity)
        rows.append(
            [
                analysis.audio_hash[:12],
                analysis.analysis_id,
                render_status_chip(analysis.status.value),
                analysis.created_at.isoformat(timespec="seconds"),
                analysis.metadata_label,
                render_score_cell(analysis.weighted_score),
                f'<span class="chip chip-{risk_tone}">{risk_text}</span>'
                if analysis.report_available
                else "—",
                str(analysis.privacy_event_count),
                str(analysis.audit_event_count),
                "yes" if analysis.report_available else "no",
                ", ".join(analysis.comparison_candidate_ids) or "—",
            ]
        )
    return rows


HISTORY_HTML_COLUMNS = {2, 5, 6}


def history_table_html(runtime: AppRuntime, **filters) -> str:
    """Full analysis-history table as styled HTML."""
    return render_table_html(
        HISTORY_DISPLAY_HEADERS,
        history_display_rows(runtime, **filters),
        html_columns=HISTORY_HTML_COLUMNS,
        empty_message="No analyses match the current filters.",
    )


def select_display_history_row(row: list[Any] | None) -> tuple[str, str]:
    """Selection handler for the dashboard history table layout."""
    if not row or len(row) <= HISTORY_DISPLAY_REPORT_INDEX:
        return ("", "Select an analysis row with an available report.")
    analysis_id = str(row[HISTORY_DISPLAY_ID_INDEX])
    report_available = str(row[HISTORY_DISPLAY_REPORT_INDEX]).lower() == "yes"
    if not analysis_id or not report_available:
        return ("", "Selected analysis does not have an available report.")
    return (analysis_id, f"Selected {analysis_id}. Generate JSON or PDF below.")


def history_stats_html(runtime: AppRuntime, **filters) -> str:
    """KPI cards summarizing the (filtered) analysis history."""
    rows = _history_rows(runtime, **filters)
    scores = [row.weighted_score for row in rows if row.weighted_score is not None]
    flagged = sum(1 for row in rows if row.max_flag_severity is not None)
    review = sum(
        1 for row in rows if row.status is AnalysisStatus.SUPERVISOR_REVIEW
    )
    average = round(sum(scores) / len(scores), 2) if scores else None
    cards = [
        {"value": str(len(rows)), "label": "Total Analyses", "sub": "matching filters"},
        {
            "value": str(flagged),
            "label": "Flagged Analyses",
            "sub": f"{flagged / len(rows) * 100:.0f}% of total" if rows else None,
            "tone": "warn" if flagged else None,
        },
        {
            "value": str(average) if average is not None else "—",
            "label": "Average QA Score",
            "sub": score_quality(average)[0] if average is not None else None,
            "tone": score_quality(average)[1] if average is not None else None,
        },
        {
            "value": str(review),
            "label": "Supervisor Review",
            "sub": "needs human attention",
            "tone": "warn" if review else None,
        },
    ]
    return render_kpi_cards(cards)


def history_filter_args(
    status_label: str | None,
    query: str | None,
    min_score: float | str | None,
    max_score: float | str | None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, str | float | date | None]:
    """Normalize raw Gradio filter inputs into history filter arguments."""
    normalized_status = _blank_to_none(status_label)
    if normalized_status is not None and normalized_status.lower().startswith("all"):
        normalized_status = None
    return {
        "status": normalized_status,
        "query": _blank_to_none(query),
        "min_score": _optional_float(min_score),
        "max_score": _optional_float(max_score),
        "created_from": _optional_date(date_from),
        "created_to": _optional_date(date_to),
    }


def compare_analyses_markdown(
    runtime: AppRuntime,
    base_analysis_id: str | None,
    other_analysis_id: str | None,
) -> str:
    """Render an Analysis Result Comparison as Markdown for the History tab."""
    base_id = _blank_to_none(base_analysis_id)
    other_id = _blank_to_none(other_analysis_id)
    if base_id is None or other_id is None:
        return "Enter two analysis IDs from the same call to compare."

    try:
        with runtime.session_factory() as session:
            repository = AnalysisRepository(session)
            comparison = AnalysisComparisonService(repository).compare(
                base_id,
                other_id,
            )
    except AnalysisComparisonError as exc:
        return f"Comparison failed: {exc}"

    lines = [
        "### Analysis Comparison",
        f"**Call** `{comparison.audio_hash[:12]}`",
        "",
        "| | Base | Other |",
        "| --- | --- | --- |",
        f"| Analysis ID | `{comparison.base_analysis_id}` "
        f"| `{comparison.other_analysis_id}` |",
        f"| Status | {comparison.base_status.value} "
        f"| {comparison.other_status.value} |",
        "",
        "**Configuration differences**",
        "",
    ]
    if comparison.configuration_differences:
        lines.extend(
            [
                "| Field | Base | Other |",
                "| --- | --- | --- |",
                *(
                    f"| {item.field} | {item.base_value} | {item.other_value} |"
                    for item in comparison.configuration_differences
                ),
            ]
        )
    else:
        lines.append("No configuration differences — same analysis conditions.")

    result = comparison.report_comparison
    lines.extend(["", "**Result comparison**", ""])
    if result is None:
        lines.append(
            "Report comparison unavailable: at least one analysis "
            "did not produce a call report."
        )
        return "\n".join(lines)

    lines.extend(
        [
            f"Weighted QA score: {result.base_weighted_score} → "
            f"{result.other_weighted_score} (Δ {result.weighted_score_delta:+})",
            "",
            "| Dimension | Base | Other | Δ |",
            "| --- | --- | --- | --- |",
            *(
                f"| {item.dimension.value} | {item.base_score} "
                f"| {item.other_score} | {item.delta:+d} |"
                for item in result.dimension_deltas
            ),
            "",
            f"Flags added: {', '.join(result.flags_added) or 'none'}",
            f"Flags removed: {', '.join(result.flags_removed) or 'none'}",
            f"Resolution status: {result.base_resolution_status} → "
            f"{result.other_resolution_status}",
            f"Sentiment trend: {result.base_sentiment_trend.value} → "
            f"{result.other_sentiment_trend.value}",
            f"Privacy events: Δ {result.privacy_event_count_delta:+d}",
        ]
    )
    return "\n".join(lines)


def daily_trends_table(runtime: AppRuntime) -> list[list[str]]:
    """Return daily pipeline trend rows for the Observability tab."""
    with runtime.session_factory() as session:
        repository = AnalysisRepository(session)
        trends = PipelineAnalyticsService(repository).daily_trends()

    return [
        [
            row.day.isoformat(),
            str(row.total),
            str(row.completed),
            str(row.supervisor_review),
            str(row.blocked),
            str(row.failed),
            f"{row.success_rate}%",
            str(row.average_score) if row.average_score is not None else "—",
            str(row.compliance_flag_count),
        ]
        for row in trends
    ]


def render_status_badge(status_label: str) -> str:
    """Render an analysis status as a colored badge."""
    normalized = status_label.strip().lower()
    if not normalized:
        return ""
    label = normalized.replace("_", " ").title()
    return f'<span class="status-badge status-{normalized}">{label}</span>'


def render_metrics_html(metrics: str) -> str:
    """Render observability metric lines as KPI cards."""
    cards = []
    for line in metrics.splitlines():
        label, _, value = line.partition(": ")
        if not value:
            continue
        cards.append(
            '<div class="kpi-card">'
            f'<span class="kpi-value">{value}</span>'
            f'<span class="kpi-label">{label}</span>'
            "</div>"
        )
    return f'<div class="kpi-grid">{"".join(cards)}</div>'


def format_sentiment_trajectory(summary: CallSummary) -> str:
    """Render the customer sentiment trajectory, preferring scored points."""
    return describe_sentiment_trajectory(summary)


def select_history_row_for_download(row: list[Any] | None) -> tuple[str, str]:
    """Return the selected analysis ID and download guidance for a history row."""
    if not row or len(row) <= HISTORY_REPORT_AVAILABLE_INDEX:
        return ("", "Select an analysis row with an available report.")

    analysis_id = str(row[HISTORY_ANALYSIS_ID_INDEX])
    report_available = str(row[HISTORY_REPORT_AVAILABLE_INDEX]).lower() == "yes"
    if not analysis_id or not report_available:
        return ("", "Selected analysis does not have an available report.")
    return (analysis_id, f"Selected {analysis_id}. Generate JSON or PDF below.")


def generate_json_report_download(
    runtime: AppRuntime,
    analysis_id: str | None,
) -> tuple[str, str | None]:
    """Generate a JSON report file for Gradio download."""
    normalized_analysis_id = _blank_to_none(analysis_id)
    if normalized_analysis_id is None:
        return ("Enter an analysis ID with an available report.", None)

    try:
        with runtime.session_factory() as session:
            repository = AnalysisRepository(session)
            download = ReportDownloadService(repository).generate_json_download(
                normalized_analysis_id,
                session_id="gradio-session",
            )
        output_path = Path(tempfile.mkdtemp(prefix="call-report-json-"))
        output_file = output_path / download.filename
        output_file.write_text(download.content, encoding="utf-8")
    except ReportDownloadError as exc:
        return (str(exc), None)
    return (f"Generated {download.filename}", str(output_file))


def generate_pdf_report_download(
    runtime: AppRuntime,
    analysis_id: str | None,
) -> tuple[str, str | None]:
    """Generate a PDF report file for Gradio download."""
    normalized_analysis_id = _blank_to_none(analysis_id)
    if normalized_analysis_id is None:
        return ("Enter an analysis ID with an available report.", None)

    try:
        with runtime.session_factory() as session:
            repository = AnalysisRepository(session)
            download = ReportDownloadService(repository).generate_pdf_download(
                normalized_analysis_id,
                session_id="gradio-session",
            )
    except ReportDownloadError as exc:
        return (str(exc), None)
    return (f"Generated {download.filename}", str(download.path))


def observability_snapshot(runtime: AppRuntime) -> tuple[str, list[list[str]]]:
    """Return dashboard metrics and recent audit events for the Observability tab."""
    with runtime.session_factory() as session:
        repository = AnalysisRepository(session)
        history = repository.list_analysis_history()
        recent_events = repository.recent_audit_events(limit=20)

        analyses = [
            analysis for call_history in history for analysis in call_history.analyses
        ]
        outcome_counts = {
            status.value: sum(1 for analysis in analyses if analysis.status is status)
            for status in AnalysisStatus
        }
        report_scores = []
        compliance_flag_count = 0
        for analysis in analyses:
            report = repository.get_report(analysis.analysis_id)
            if report is None:
                continue
            report_scores.append(report.qa_result.weighted_overall_score)
            compliance_flag_count += len(report.qa_result.compliance_flags)

    total = len(analyses)
    success_count = (
        outcome_counts[AnalysisStatus.COMPLETED.value]
        + outcome_counts[AnalysisStatus.SUPERVISOR_REVIEW.value]
    )
    success_rate = (success_count / total * 100) if total else 0
    average_score = (
        round(sum(report_scores) / len(report_scores), 2) if report_scores else None
    )
    langsmith_enabled = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"

    metrics = "\n".join(
        [
            f"Total analyses: {total}",
            f"Completed: {outcome_counts[AnalysisStatus.COMPLETED.value]}",
            "Supervisor review: "
            f"{outcome_counts[AnalysisStatus.SUPERVISOR_REVIEW.value]}",
            f"Blocked: {outcome_counts[AnalysisStatus.BLOCKED.value]}",
            f"Failed: {outcome_counts[AnalysisStatus.FAILED.value]}",
            f"Success rate: {success_rate:.1f}%",
            "Average QA score: "
            f"{average_score if average_score is not None else 'N/A'}",
            f"Compliance flags: {compliance_flag_count}",
            f"LangSmith tracing: {'enabled' if langsmith_enabled else 'disabled'}",
        ]
    )
    audit_rows = [
        [
            event.created_at.isoformat(timespec="seconds"),
            event.analysis_id,
            event.action.value,
            json.dumps(event.details, sort_keys=True),
        ]
        for event in recent_events
    ]
    return metrics, audit_rows


TRENDS_DISPLAY_HEADERS = [
    "Day",
    "Total",
    "Completed",
    "Review",
    "Blocked",
    "Failed",
    "Success Rate",
    "Avg QA Score",
    "Flags",
]
TRENDS_DISPLAY_DATATYPES = [
    "str",
    "str",
    "str",
    "str",
    "str",
    "str",
    "html",
    "str",
    "str",
]
AUDIT_DISPLAY_HEADERS = ["Created", "Analysis ID", "Action", "Details"]
AUDIT_DISPLAY_DATATYPES = ["str", "str", "html", "str"]


def observability_dashboard(runtime: AppRuntime) -> tuple[str, str, str, str]:
    """Return (KPI cards, trends table, system status, audit table) as HTML."""
    with runtime.session_factory() as session:
        repository = AnalysisRepository(session)
        trends = PipelineAnalyticsService(repository).daily_trends()
        recent_events = repository.recent_audit_events(limit=20)

    totals = {
        "total": sum(row.total for row in trends),
        "completed": sum(row.completed for row in trends),
        "review": sum(row.supervisor_review for row in trends),
        "blocked": sum(row.blocked for row in trends),
        "failed": sum(row.failed for row in trends),
        "flags": sum(row.compliance_flag_count for row in trends),
    }
    success_count = totals["completed"] + totals["review"]
    success_rate = (
        round(success_count / totals["total"] * 100, 1) if totals["total"] else 0.0
    )
    scored_days = [row for row in trends if row.average_score is not None]
    average_score = (
        round(
            sum(row.average_score * row.total for row in scored_days)
            / sum(row.total for row in scored_days),
            2,
        )
        if scored_days
        else None
    )
    kpis = render_kpi_cards(
        [
            {
                "value": str(totals["total"]),
                "label": "Total Analyses",
                "sub": "all time",
            },
            {
                "value": f"{success_rate}%",
                "label": "Success Rate",
                "sub": "completed + review",
                "tone": "good" if success_rate >= 90 else "warn",
            },
            {
                "value": str(average_score) if average_score is not None else "—",
                "label": "Avg QA Score",
                "sub": (
                    score_quality(average_score)[0]
                    if average_score is not None
                    else None
                ),
                "tone": (
                    score_quality(average_score)[1]
                    if average_score is not None
                    else None
                ),
            },
            {
                "value": str(totals["blocked"]),
                "label": "Blocked",
                "sub": "prompt injection",
                "tone": "warn" if totals["blocked"] else None,
            },
            {
                "value": str(totals["failed"]),
                "label": "Failed",
                "sub": "processing errors",
                "tone": "bad" if totals["failed"] else None,
            },
            {
                "value": str(totals["flags"]),
                "label": "Compliance Flags",
                "sub": "all analyses",
                "tone": "warn" if totals["flags"] else None,
            },
        ]
    )

    trend_rows = [
        [
            row.day.isoformat(),
            str(row.total),
            str(row.completed),
            str(row.supervisor_review),
            str(row.blocked),
            str(row.failed),
            render_trend_bar(row.success_rate),
            str(row.average_score) if row.average_score is not None else "—",
            str(row.compliance_flag_count),
        ]
        for row in reversed(trends)
    ]
    trends_table = render_table_html(
        TRENDS_DISPLAY_HEADERS,
        trend_rows,
        html_columns={6},
        empty_message="No analyses yet.",
    )

    health = render_system_health(_system_checks(runtime))
    audit_rows = [
        [
            event.created_at.isoformat(timespec="seconds"),
            event.analysis_id,
            render_audit_action_chip(event.action.value),
            json.dumps(event.details, sort_keys=True),
        ]
        for event in recent_events
    ]
    audit_table = render_table_html(
        AUDIT_DISPLAY_HEADERS,
        audit_rows,
        html_columns={2},
        empty_message="No audit events yet.",
    )
    return kpis, trends_table, health, audit_table


def _system_checks(runtime: AppRuntime) -> list[tuple[str, str, str]]:
    try:
        with runtime.session_factory() as session:
            AnalysisRepository(session).audit_event_count()
        database_state = ("Operational", "good")
    except Exception:
        database_state = ("Unreachable", "warn")
    langsmith_enabled = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
    return [
        ("Database", *database_state),
        ("Analysis Backend", runtime.settings.analysis_backend, "good"),
        ("Transcription Backend", runtime.settings.transcription_backend, "good"),
        (
            "LangSmith Tracing",
            "Enabled" if langsmith_enabled else "Disabled",
            "good" if langsmith_enabled else "muted",
        ),
    ]


def build_app_theme():
    """Build the Gradio theme for the app."""
    import gradio as gr

    return gr.themes.Base(
        primary_hue=gr.themes.colors.teal,
        neutral_hue=gr.themes.colors.zinc,
        font=[
            gr.themes.GoogleFont("Inter Tight"),
            "ui-sans-serif",
            "system-ui",
            "sans-serif",
        ],
        font_mono=[
            gr.themes.GoogleFont("IBM Plex Mono"),
            "ui-monospace",
            "monospace",
        ],
    )


def build_app(runtime: AppRuntime | None = None):
    """Build the Gradio app."""
    try:
        import gradio as gr
    except ImportError as exc:  # pragma: no cover - depends on local env
        raise RuntimeError(
            "Gradio is not installed. Run `make install` before launching the app."
        ) from exc

    app_runtime = runtime or create_app_runtime()
    initial_analysis_ids = [row.analysis_id for row in _history_rows(app_runtime)]
    initial_kpis, initial_trends, initial_health, initial_audit = (
        observability_dashboard(app_runtime)
    )
    with gr.Blocks(
        title="Call Center Intelligence",
        js=FORCE_DARK_JS,
    ) as app:
        gr.HTML(render_app_bar())

        with gr.Tab("Analyze Call"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=2, min_width=380):
                    gr.HTML(render_section_header(1, "Input", "Upload call audio"))
                    audio_file = gr.Audio(
                        label="Drag and drop audio or record",
                        sources=["upload", "microphone"],
                        type="filepath",
                    )
                    gr.HTML(
                        '<div class="upload-note">Supported formats: WAV, MP3, '
                        "FLAC, M4A &middot; Max size: 50 MB &middot; "
                        "Max duration: 60 min</div>"
                    )
                    gr.HTML(render_section_header(2, "Call context", "optional"))
                    with gr.Row():
                        caller_id = gr.Textbox(
                            label="Caller ID",
                            placeholder="e.g. ticket or CRM reference",
                        )
                        department = gr.Textbox(
                            label="Department",
                            placeholder="e.g. billing",
                        )
                    with gr.Accordion("Engine settings", open=False):
                        analysis_backend = gr.Dropdown(
                            label="Analysis Backend",
                            choices=["mock", "openai"],
                            value=app_runtime.settings.analysis_backend,
                        )
                        transcription_backend = gr.Dropdown(
                            label="Transcription Backend",
                            choices=["mock", "faster_whisper", "openai_diarized"],
                            value=app_runtime.settings.transcription_backend,
                        )
                        mock_compliance_mode = gr.Dropdown(
                            label="Mock Compliance Mode",
                            info="Use 'critical' to demo supervisor review.",
                            choices=["normal", "critical"],
                            value="normal",
                        )
                    analyze_button = gr.Button(
                        "Analyze Call", variant="primary", size="lg"
                    )

                with gr.Column(scale=3):
                    summary_output = gr.HTML(render_empty_summary_card())
                    gr.HTML(
                        '<div class="section-header" style="margin-top:10px">'
                        "<span>Compliance Flags</span></div>"
                    )
                    flags_output = gr.HTML(render_flags_table([]))

            with gr.Accordion("Redacted Transcript", open=False):
                gr.HTML(
                    '<div class="upload-note">PII removed. '
                    "Safe for internal review.</div>"
                )
                transcript_output = gr.Textbox(
                    label="Speaker- and timestamp-labeled transcript", lines=10
                )
            with gr.Accordion("Full Call Report (JSON)", open=False):
                report_output = gr.Code(label="Call Report JSON", language="json")

        with gr.Tab("Analysis History"):
            gr.HTML(render_section_header(1, "Filters", "narrow the history"))
            with gr.Row():
                status_filter = gr.Dropdown(
                    label="Status",
                    choices=[
                        "All statuses",
                        *[status.value for status in AnalysisStatus],
                    ],
                    value="All statuses",
                )
                query_filter = gr.Textbox(
                    label="Search",
                    placeholder="Analysis ID, call hash, or metadata",
                )
                min_score_filter = gr.Number(
                    label="Min QA score", minimum=0, maximum=5, value=None
                )
                max_score_filter = gr.Number(
                    label="Max QA score", minimum=0, maximum=5, value=None
                )
                date_from_filter = gr.Textbox(
                    label="From date", placeholder="YYYY-MM-DD"
                )
                date_to_filter = gr.Textbox(label="To date", placeholder="YYYY-MM-DD")
                refresh_history = gr.Button("Apply Filters", variant="primary")
            history_stats = gr.HTML(history_stats_html(app_runtime))
            history_output = gr.HTML(history_table_html(app_runtime))

            with gr.Row(equal_height=False):
                with gr.Column():
                    gr.HTML(
                        '<div class="section-header"><span>Report Actions</span>'
                        '<span class="hint">download reports for a selected '
                        "analysis</span></div>"
                    )
                    download_analysis_id = gr.Dropdown(
                        label="Analysis ID",
                        choices=initial_analysis_ids,
                        allow_custom_value=True,
                    )
                    with gr.Row():
                        json_button = gr.Button("Download JSON")
                        pdf_button = gr.Button("Download PDF")
                    download_message = gr.Textbox(label="Download Status")
                    download_file = gr.File(label="Report Download")
                with gr.Column():
                    gr.HTML(
                        '<div class="section-header"><span>Compare Analyses</span>'
                        '<span class="hint">pick two analyses of the same call'
                        "</span></div>"
                    )
                    with gr.Row():
                        compare_base_id = gr.Dropdown(
                            label="Base Analysis ID",
                            choices=initial_analysis_ids,
                            allow_custom_value=True,
                        )
                        compare_other_id = gr.Dropdown(
                            label="Other Analysis ID",
                            choices=initial_analysis_ids,
                            allow_custom_value=True,
                        )
                    compare_button = gr.Button("Compare Analyses", variant="primary")
                    comparison_output = gr.Markdown()

            def refresh_history_outputs(
                status_label: str | None,
                query: str | None,
                min_score: float | None,
                max_score: float | None,
                date_from: str | None,
                date_to: str | None,
            ):
                filters = history_filter_args(
                    status_label, query, min_score, max_score, date_from, date_to
                )
                analysis_ids = [
                    row.analysis_id for row in _history_rows(app_runtime, **filters)
                ]
                return (
                    history_stats_html(app_runtime, **filters),
                    history_table_html(app_runtime, **filters),
                    gr.update(choices=analysis_ids),
                    gr.update(choices=analysis_ids),
                    gr.update(choices=analysis_ids),
                )

            refresh_history.click(
                fn=refresh_history_outputs,
                inputs=[
                    status_filter,
                    query_filter,
                    min_score_filter,
                    max_score_filter,
                    date_from_filter,
                    date_to_filter,
                ],
                outputs=[
                    history_stats,
                    history_output,
                    compare_base_id,
                    compare_other_id,
                    download_analysis_id,
                ],
            )
            json_button.click(
                fn=lambda analysis_id: generate_json_report_download(
                    app_runtime,
                    analysis_id,
                ),
                inputs=[download_analysis_id],
                outputs=[download_message, download_file],
            )
            pdf_button.click(
                fn=lambda analysis_id: generate_pdf_report_download(
                    app_runtime,
                    analysis_id,
                ),
                inputs=[download_analysis_id],
                outputs=[download_message, download_file],
            )
            compare_button.click(
                fn=lambda base_id, other_id: compare_analyses_markdown(
                    app_runtime,
                    base_id,
                    other_id,
                ),
                inputs=[compare_base_id, compare_other_id],
                outputs=[comparison_output],
            )

        with gr.Tab("Observability"):
            with gr.Row():
                gr.HTML(
                    '<div class="section-header"><span>Observability Overview'
                    "</span></div>"
                )
                refresh_observability = gr.Button(
                    "Refresh Observability", variant="secondary", size="sm"
                )
            metrics_output = gr.HTML(initial_kpis)
            with gr.Row(equal_height=False):
                with gr.Column(scale=3):
                    gr.HTML(
                        '<div class="section-header"><span>Daily Trends</span>'
                        "</div>"
                    )
                    trends_output = gr.HTML(initial_trends)
                with gr.Column(scale=1, min_width=280):
                    health_output = gr.HTML(initial_health)
            gr.HTML(
                '<div class="section-header"><span>Recent Audit Events</span></div>'
            )
            audit_output = gr.HTML(initial_audit)

            refresh_observability.click(
                fn=lambda: observability_dashboard(app_runtime),
                outputs=[metrics_output, trends_output, health_output, audit_output],
            )

        def run_analysis(
            audio: str | None,
            caller: str | None,
            dept: str | None,
            llm_backend: str | None,
            stt_backend: str | None,
            mock_mode: str | None,
        ):
            summary, flags, transcript, report_json = analyze_call_dashboard(
                app_runtime,
                audio_file=audio,
                caller_id=caller,
                department=dept,
                analysis_backend=llm_backend,
                transcription_backend=stt_backend,
                mock_compliance_mode=mock_mode,
            )
            analysis_ids = [row.analysis_id for row in _history_rows(app_runtime)]
            kpis, trends_table, health, audit_table = observability_dashboard(
                app_runtime
            )
            return (
                summary,
                flags,
                transcript,
                report_json,
                history_stats_html(app_runtime),
                history_table_html(app_runtime),
                gr.update(choices=analysis_ids),
                gr.update(choices=analysis_ids),
                gr.update(
                    choices=analysis_ids,
                    value=analysis_ids[0] if analysis_ids else None,
                ),
                "Pick an analysis ID, then generate JSON or PDF.",
                kpis,
                trends_table,
                health,
                audit_table,
            )

        analyze_button.click(
            fn=run_analysis,
            inputs=[
                audio_file,
                caller_id,
                department,
                analysis_backend,
                transcription_backend,
                mock_compliance_mode,
            ],
            outputs=[
                summary_output,
                flags_output,
                transcript_output,
                report_output,
                history_stats,
                history_output,
                compare_base_id,
                compare_other_id,
                download_analysis_id,
                download_message,
                metrics_output,
                trends_output,
                health_output,
                audit_output,
            ],
        )

    return app


def launch_app() -> None:
    """Launch the Gradio app."""
    try:
        runtime = create_app_runtime()
        app = build_app(runtime)
    except RuntimeError as exc:
        print(exc)
        return

    app.launch(
        server_name=runtime.settings.server_name,
        server_port=runtime.settings.server_port,
        theme=build_app_theme(),
        css=DASHBOARD_CSS,
    )


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _optional_float(value: float | str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_date(value: str | None) -> date | None:
    normalized = _blank_to_none(value) if isinstance(value, str) else value
    if normalized is None:
        return None
    try:
        return date.fromisoformat(str(normalized)[:10])
    except ValueError:
        return None


def _format_optional_score(score: float | None) -> str:
    return "" if score is None else str(score)


def format_redacted_transcript(transcript: RedactedTranscript) -> str:
    """Format redacted transcript segments with roles and timestamps."""
    return "\n".join(
        (
            f"[{segment.start_seconds:.2f}-{segment.end_seconds:.2f}s] "
            f"{segment.speaker_role.value}: {segment.text}"
        )
        for segment in transcript.segments
    )
