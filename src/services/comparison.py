"""Analysis Result Comparison between two analyses of the same call."""

from __future__ import annotations

from dataclasses import dataclass

from src.database import AnalysisRepository
from src.models import (
    AnalysisStatus,
    CallAnalysis,
    CallReport,
    QADimension,
    SentimentTrend,
)

CONFIGURATION_COMPARISON_EXCLUDED_FIELDS = {"created_at"}


class AnalysisComparisonError(ValueError):
    """Raised when two analyses cannot be compared."""


@dataclass(frozen=True)
class ConfigurationDifference:
    """One Analysis Configuration field that differs between two analyses."""

    field: str
    base_value: str
    other_value: str


@dataclass(frozen=True)
class DimensionDelta:
    """Score movement for one QA dimension between two call reports."""

    dimension: QADimension
    base_score: int
    other_score: int
    delta: int


@dataclass(frozen=True)
class ReportComparison:
    """Reviewer-relevant output differences between two call reports."""

    base_weighted_score: float
    other_weighted_score: float
    weighted_score_delta: float
    dimension_deltas: list[DimensionDelta]
    flags_added: list[str]
    flags_removed: list[str]
    resolution_status_changed: bool
    base_resolution_status: str
    other_resolution_status: str
    sentiment_trend_changed: bool
    base_sentiment_trend: SentimentTrend
    other_sentiment_trend: SentimentTrend
    privacy_event_count_delta: int


@dataclass(frozen=True)
class AnalysisComparison:
    """Structured comparison of two analyses for the same call."""

    audio_hash: str
    base_analysis_id: str
    other_analysis_id: str
    base_status: AnalysisStatus
    other_status: AnalysisStatus
    configuration_differences: list[ConfigurationDifference]
    report_comparison: ReportComparison | None


class AnalysisComparisonService:
    """Explain why two analyses of the same call produced different results."""

    def __init__(self, repository: AnalysisRepository) -> None:
        self.repository = repository

    def compare(
        self,
        base_analysis_id: str,
        other_analysis_id: str,
    ) -> AnalysisComparison:
        if base_analysis_id == other_analysis_id:
            raise AnalysisComparisonError(
                "comparison requires two different analysis IDs"
            )
        base = self._require_analysis(base_analysis_id)
        other = self._require_analysis(other_analysis_id)
        if base.call.audio_hash != other.call.audio_hash:
            raise AnalysisComparisonError(
                "comparison requires two analyses of the same call"
            )

        base_report = self.repository.get_report(base_analysis_id)
        other_report = self.repository.get_report(other_analysis_id)
        report_comparison = (
            compare_reports(base_report, other_report)
            if base_report is not None and other_report is not None
            else None
        )
        return AnalysisComparison(
            audio_hash=base.call.audio_hash,
            base_analysis_id=base_analysis_id,
            other_analysis_id=other_analysis_id,
            base_status=base.status,
            other_status=other.status,
            configuration_differences=compare_configurations(base, other),
            report_comparison=report_comparison,
        )

    def _require_analysis(self, analysis_id: str) -> CallAnalysis:
        analysis = self.repository.get_analysis(analysis_id)
        if analysis is None:
            raise AnalysisComparisonError(f"analysis {analysis_id!r} not found")
        return analysis


def compare_configurations(
    base: CallAnalysis,
    other: CallAnalysis,
) -> list[ConfigurationDifference]:
    base_config = base.configuration.model_dump(mode="json")
    other_config = other.configuration.model_dump(mode="json")
    return [
        ConfigurationDifference(
            field=field,
            base_value=str(base_config[field]),
            other_value=str(other_config[field]),
        )
        for field in base_config
        if field not in CONFIGURATION_COMPARISON_EXCLUDED_FIELDS
        and base_config[field] != other_config[field]
    ]


def compare_reports(base: CallReport, other: CallReport) -> ReportComparison:
    base_scores = {item.dimension: item.score for item in base.qa_result.dimensions}
    other_scores = {item.dimension: item.score for item in other.qa_result.dimensions}
    dimension_deltas = [
        DimensionDelta(
            dimension=dimension,
            base_score=base_scores[dimension],
            other_score=other_scores[dimension],
            delta=other_scores[dimension] - base_scores[dimension],
        )
        for dimension in QADimension
    ]
    base_flag_titles = [flag.title for flag in base.qa_result.compliance_flags]
    other_flag_titles = [flag.title for flag in other.qa_result.compliance_flags]
    base_score = base.qa_result.weighted_overall_score
    other_score = other.qa_result.weighted_overall_score
    return ReportComparison(
        base_weighted_score=base_score,
        other_weighted_score=other_score,
        weighted_score_delta=round(other_score - base_score, 2),
        dimension_deltas=dimension_deltas,
        flags_added=[
            title for title in other_flag_titles if title not in base_flag_titles
        ],
        flags_removed=[
            title for title in base_flag_titles if title not in other_flag_titles
        ],
        resolution_status_changed=(
            base.summary.resolution_status is not other.summary.resolution_status
        ),
        base_resolution_status=base.summary.resolution_status.value,
        other_resolution_status=other.summary.resolution_status.value,
        sentiment_trend_changed=(
            base.summary.sentiment_trend is not other.summary.sentiment_trend
        ),
        base_sentiment_trend=base.summary.sentiment_trend,
        other_sentiment_trend=other.summary.sentiment_trend,
        privacy_event_count_delta=len(other.privacy_events) - len(base.privacy_events),
    )
