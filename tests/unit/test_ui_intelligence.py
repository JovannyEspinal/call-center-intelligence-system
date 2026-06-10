"""UI helper tests for history filtering, comparison, trends, and badges."""

from __future__ import annotations

import wave
from datetime import date
from io import BytesIO
from pathlib import Path

from src.ui.app import (
    AppSettings,
    analyze_uploaded_call,
    compare_analyses_markdown,
    create_app_runtime,
    daily_trends_table,
    history_filter_args,
    list_analysis_history,
    render_metrics_html,
    render_status_badge,
)


def valid_wav_bytes(*, seconds: int = 1) -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x00\x00" * 8000 * seconds)
    return buffer.getvalue()


def runtime_with_analysis(tmp_path: Path, *, runs: int = 1):
    audio_path = tmp_path / "call.wav"
    audio_path.write_bytes(valid_wav_bytes())
    runtime = create_app_runtime(
        AppSettings(database_url=f"sqlite:///{tmp_path / 'calls.db'}")
    )
    for _ in range(runs):
        analyze_uploaded_call(
            runtime,
            audio_file=audio_path,
            caller_id=None,
            department="billing",
            analysis_backend="mock",
            transcription_backend="mock",
        )
    return runtime


def test_list_analysis_history_applies_filters(tmp_path: Path) -> None:
    runtime = runtime_with_analysis(tmp_path)

    assert len(list_analysis_history(runtime)) == 1
    assert len(list_analysis_history(runtime, status="completed")) == 1
    assert list_analysis_history(runtime, status="blocked") == []
    assert len(list_analysis_history(runtime, query="billing")) == 1
    assert list_analysis_history(runtime, query="no-such-text") == []
    assert len(list_analysis_history(runtime, min_score=3.0)) == 1
    assert list_analysis_history(runtime, min_score=4.5) == []


def test_history_filter_args_normalizes_ui_values() -> None:
    assert history_filter_args("All statuses", " ", None, None) == {
        "status": None,
        "query": None,
        "min_score": None,
        "max_score": None,
        "created_from": None,
        "created_to": None,
    }
    assert history_filter_args(
        "completed", " billing ", 1.5, 4.0, "2026-06-01", "2026-06-10"
    ) == {
        "status": "completed",
        "query": "billing",
        "min_score": 1.5,
        "max_score": 4.0,
        "created_from": date(2026, 6, 1),
        "created_to": date(2026, 6, 10),
    }


def test_compare_analyses_markdown_for_same_call(tmp_path: Path) -> None:
    runtime = runtime_with_analysis(tmp_path, runs=2)
    rows = list_analysis_history(runtime)
    base_id, other_id = rows[1][1], rows[0][1]

    rendered = compare_analyses_markdown(runtime, base_id, other_id)

    assert "Analysis Comparison" in rendered
    assert base_id in rendered
    assert other_id in rendered
    assert "No configuration differences" in rendered
    assert "0.0" in rendered  # weighted score delta


def test_compare_analyses_markdown_reports_errors(tmp_path: Path) -> None:
    runtime = runtime_with_analysis(tmp_path)

    rendered = compare_analyses_markdown(runtime, "missing-a", "missing-b")

    assert rendered.startswith("Comparison failed:")


def test_compare_analyses_markdown_requires_both_ids(tmp_path: Path) -> None:
    runtime = runtime_with_analysis(tmp_path)

    rendered = compare_analyses_markdown(runtime, "", None)

    assert rendered.startswith("Enter two analysis IDs")


def test_daily_trends_table_returns_one_row_per_day(tmp_path: Path) -> None:
    runtime = runtime_with_analysis(tmp_path)

    rows = daily_trends_table(runtime)

    assert len(rows) == 1
    day, total, completed, review, blocked, failed, rate, score, flags = rows[0]
    assert total == "1"
    assert completed == "1"
    assert rate == "100.0%"
    assert score == "4.0"
    assert flags == "0"


def test_render_status_badge_marks_each_status() -> None:
    assert 'class="status-badge status-completed"' in render_status_badge("completed")
    assert "Supervisor Review" in render_status_badge("supervisor_review")
    assert 'class="status-badge status-blocked"' in render_status_badge("blocked")
    assert 'class="status-badge status-failed"' in render_status_badge("Failed")


def test_render_metrics_html_builds_kpi_cards(tmp_path: Path) -> None:
    runtime = runtime_with_analysis(tmp_path)
    from src.ui.app import observability_snapshot

    metrics, _ = observability_snapshot(runtime)
    html = render_metrics_html(metrics)

    assert 'class="kpi-grid"' in html
    assert "Total analyses" in html
    assert ">1<" in html
