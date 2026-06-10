"""Pipeline Observability trend analytics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.database import AnalysisRepository
from src.models import AnalysisStatus, CallAnalysis


@dataclass(frozen=True)
class DailyTrendRow:
    """Aggregated pipeline outcomes for one UTC day."""

    day: date
    total: int
    completed: int
    supervisor_review: int
    blocked: int
    failed: int
    success_rate: float
    average_score: float | None
    compliance_flag_count: int


class PipelineAnalyticsService:
    """Build time-series read models from persisted analysis history."""

    def __init__(self, repository: AnalysisRepository) -> None:
        self.repository = repository

    def daily_trends(self) -> list[DailyTrendRow]:
        analyses: list[CallAnalysis] = [
            analysis
            for entry in self.repository.list_analysis_history()
            for analysis in entry.analyses
        ]
        by_day: dict[date, list[CallAnalysis]] = {}
        for analysis in analyses:
            by_day.setdefault(analysis.created_at.date(), []).append(analysis)
        return [
            self._aggregate_day(day, day_analyses)
            for day, day_analyses in sorted(by_day.items())
        ]

    def _aggregate_day(
        self,
        day: date,
        analyses: list[CallAnalysis],
    ) -> DailyTrendRow:
        status_counts = {
            status: sum(1 for analysis in analyses if analysis.status is status)
            for status in AnalysisStatus
        }
        scores: list[float] = []
        compliance_flag_count = 0
        for analysis in analyses:
            report = self.repository.get_report(analysis.analysis_id)
            if report is None:
                continue
            scores.append(report.qa_result.weighted_overall_score)
            compliance_flag_count += len(report.qa_result.compliance_flags)

        total = len(analyses)
        success_count = (
            status_counts[AnalysisStatus.COMPLETED]
            + status_counts[AnalysisStatus.SUPERVISOR_REVIEW]
        )
        return DailyTrendRow(
            day=day,
            total=total,
            completed=status_counts[AnalysisStatus.COMPLETED],
            supervisor_review=status_counts[AnalysisStatus.SUPERVISOR_REVIEW],
            blocked=status_counts[AnalysisStatus.BLOCKED],
            failed=status_counts[AnalysisStatus.FAILED],
            success_rate=round(success_count / total * 100, 1) if total else 0.0,
            average_score=round(sum(scores) / len(scores), 2) if scores else None,
            compliance_flag_count=compliance_flag_count,
        )
