"""Analysis History filtering tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

from src.models import AnalysisStatus
from src.services import AnalysisHistoryRow, filter_history_rows

BASE_TIME = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def history_row(
    analysis_id: str,
    *,
    status: AnalysisStatus = AnalysisStatus.COMPLETED,
    metadata_label: str = "billing",
    weighted_score: float | None = 3.5,
    created_at: datetime = BASE_TIME,
) -> AnalysisHistoryRow:
    return AnalysisHistoryRow(
        analysis_id=analysis_id,
        audio_hash="a" * 64,
        status=status,
        created_at=created_at,
        provider="mock",
        llm_model="mock",
        summary_prompt_version="v2",
        qa_prompt_version="v1",
        metadata_label=metadata_label,
        status_reason=None,
        report_available=weighted_score is not None,
        weighted_score=weighted_score,
        privacy_event_count=0,
        audit_event_count=1,
        comparison_candidate_ids=[],
    )


ROWS = [
    history_row("analysis-1", metadata_label="billing | alice"),
    history_row(
        "analysis-2",
        status=AnalysisStatus.FAILED,
        metadata_label="support | bob",
        weighted_score=None,
    ),
    history_row(
        "analysis-3",
        status=AnalysisStatus.SUPERVISOR_REVIEW,
        metadata_label="billing | carol",
        weighted_score=2.1,
    ),
]


def test_no_filters_returns_all_rows() -> None:
    assert filter_history_rows(ROWS) == ROWS


def test_filter_by_status() -> None:
    filtered = filter_history_rows(ROWS, status=AnalysisStatus.FAILED)

    assert [row.analysis_id for row in filtered] == ["analysis-2"]


def test_filter_by_query_matches_metadata_case_insensitively() -> None:
    filtered = filter_history_rows(ROWS, query="BILLING")

    assert [row.analysis_id for row in filtered] == ["analysis-1", "analysis-3"]


def test_filter_by_query_matches_analysis_id() -> None:
    filtered = filter_history_rows(ROWS, query="analysis-2")

    assert [row.analysis_id for row in filtered] == ["analysis-2"]


def test_filter_by_score_range_excludes_rows_without_scores() -> None:
    filtered = filter_history_rows(ROWS, min_score=3.0)
    assert [row.analysis_id for row in filtered] == ["analysis-1"]

    filtered = filter_history_rows(ROWS, max_score=3.0)
    assert [row.analysis_id for row in filtered] == ["analysis-3"]


def test_filter_by_date_range() -> None:
    rows = [
        history_row("june-1", created_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC)),
        history_row("june-5", created_at=datetime(2026, 6, 5, 9, 0, tzinfo=UTC)),
        history_row("june-9", created_at=datetime(2026, 6, 9, 9, 0, tzinfo=UTC)),
    ]

    filtered = filter_history_rows(rows, created_from=date(2026, 6, 5))
    assert [row.analysis_id for row in filtered] == ["june-5", "june-9"]

    filtered = filter_history_rows(rows, created_to=date(2026, 6, 5))
    assert [row.analysis_id for row in filtered] == ["june-1", "june-5"]

    filtered = filter_history_rows(
        rows,
        created_from=date(2026, 6, 2),
        created_to=date(2026, 6, 8),
    )
    assert [row.analysis_id for row in filtered] == ["june-5"]


def test_filters_combine() -> None:
    filtered = filter_history_rows(
        ROWS,
        status=AnalysisStatus.SUPERVISOR_REVIEW,
        query="billing",
        min_score=1.0,
        max_score=3.0,
    )

    assert [row.analysis_id for row in filtered] == ["analysis-3"]
