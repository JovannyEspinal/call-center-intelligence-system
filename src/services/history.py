"""Analysis History query formatting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from src.database import AnalysisRepository
from src.models import AnalysisStatus, CallAnalysis, ComplianceSeverity


@dataclass(frozen=True)
class AnalysisHistoryRow:
    """UI-ready summary of one Call Analysis."""

    analysis_id: str
    audio_hash: str
    status: AnalysisStatus
    created_at: datetime
    provider: str
    llm_model: str
    summary_prompt_version: str
    qa_prompt_version: str
    metadata_label: str
    status_reason: str | None
    report_available: bool
    weighted_score: float | None
    privacy_event_count: int
    audit_event_count: int
    comparison_candidate_ids: list[str]
    max_flag_severity: ComplianceSeverity | None = None


@dataclass(frozen=True)
class CallHistoryGroup:
    """UI-ready group of analyses for a single Call."""

    audio_hash: str
    analysis_count: int
    latest_analysis_id: str | None
    latest_status: AnalysisStatus | None
    latest_created_at: datetime | None
    analyses: list[AnalysisHistoryRow]


class AnalysisHistoryService:
    """Build Analysis History read models from persisted analysis data."""

    def __init__(self, repository: AnalysisRepository) -> None:
        self.repository = repository

    def list_history(self) -> list[CallHistoryGroup]:
        groups = []
        for entry in self.repository.list_analysis_history():
            rows = [
                self._format_analysis(analysis, entry.analyses)
                for analysis in entry.analyses
            ]
            latest = rows[0] if rows else None
            groups.append(
                CallHistoryGroup(
                    audio_hash=entry.call.audio_hash,
                    analysis_count=len(rows),
                    latest_analysis_id=latest.analysis_id if latest else None,
                    latest_status=latest.status if latest else None,
                    latest_created_at=latest.created_at if latest else None,
                    analyses=rows,
                )
            )
        return groups

    def _format_analysis(
        self,
        analysis: CallAnalysis,
        sibling_analyses: list[CallAnalysis],
    ) -> AnalysisHistoryRow:
        report = self.repository.get_report(analysis.analysis_id)
        audit_event_count = self.repository.audit_event_count(
            analysis_id=analysis.analysis_id
        )
        comparison_candidate_ids = [
            item.analysis_id
            for item in sibling_analyses
            if item.analysis_id != analysis.analysis_id
        ]

        return AnalysisHistoryRow(
            analysis_id=analysis.analysis_id,
            audio_hash=analysis.call.audio_hash,
            status=analysis.status,
            created_at=analysis.created_at,
            provider=analysis.configuration.llm_provider.value,
            llm_model=analysis.configuration.llm_model,
            summary_prompt_version=analysis.configuration.summary_prompt_version,
            qa_prompt_version=analysis.configuration.qa_prompt_version,
            metadata_label=_metadata_label(analysis),
            status_reason=analysis.status_reason,
            report_available=report is not None,
            weighted_score=(
                report.qa_result.weighted_overall_score if report is not None else None
            ),
            privacy_event_count=len(report.privacy_events) if report is not None else 0,
            audit_event_count=audit_event_count,
            comparison_candidate_ids=comparison_candidate_ids,
            max_flag_severity=(
                max_flag_severity(report.qa_result.compliance_flags)
                if report is not None
                else None
            ),
        )


def filter_history_rows(
    rows: list[AnalysisHistoryRow],
    *,
    status: AnalysisStatus | None = None,
    query: str | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
) -> list[AnalysisHistoryRow]:
    """Filter history rows by status, search text, score, and date range."""
    normalized_query = query.strip().lower() if query else None
    return [
        row
        for row in rows
        if _row_matches(
            row,
            status=status,
            query=normalized_query,
            min_score=min_score,
            max_score=max_score,
            created_from=created_from,
            created_to=created_to,
        )
    ]


def _row_matches(
    row: AnalysisHistoryRow,
    *,
    status: AnalysisStatus | None,
    query: str | None,
    min_score: float | None,
    max_score: float | None,
    created_from: date | None,
    created_to: date | None,
) -> bool:
    if status is not None and row.status is not status:
        return False
    if query is not None:
        haystack = " ".join(
            (row.analysis_id, row.audio_hash, row.metadata_label)
        ).lower()
        if query not in haystack:
            return False
    if min_score is not None or max_score is not None:
        if row.weighted_score is None:
            return False
        if min_score is not None and row.weighted_score < min_score:
            return False
        if max_score is not None and row.weighted_score > max_score:
            return False
    if created_from is not None and row.created_at.date() < created_from:
        return False
    if created_to is not None and row.created_at.date() > created_to:
        return False
    return True


def max_flag_severity(flags) -> ComplianceSeverity | None:
    """Highest compliance severity among flags, or None when there are none."""
    if not flags:
        return None
    severity_order = list(ComplianceSeverity)
    return max(flags, key=lambda flag: severity_order.index(flag.severity)).severity


def _metadata_label(analysis: CallAnalysis) -> str:
    parts = [
        value
        for value in (
            analysis.metadata.department,
            analysis.metadata.caller_id,
            analysis.metadata.filename,
        )
        if value
    ]
    return " | ".join(parts) if parts else "No metadata"
