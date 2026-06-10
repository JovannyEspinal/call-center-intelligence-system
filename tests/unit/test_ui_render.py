"""Dashboard HTML renderer tests."""

from __future__ import annotations

from src.ui.render import (
    chip,
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
    render_trend_bar,
    risk_label,
    score_quality,
)


def test_chip_escapes_content_and_sets_kind_class() -> None:
    rendered = chip("<b>High</b>", "severity-high")

    assert 'class="chip chip-severity-high"' in rendered
    assert "&lt;b&gt;High&lt;/b&gt;" in rendered


def test_status_chip_maps_statuses() -> None:
    assert "chip-status-completed" in render_status_chip("completed")
    assert "Supervisor Review" in render_status_chip("supervisor_review")
    assert "chip-status-blocked" in render_status_chip("blocked")
    assert render_status_chip("") == ""


def test_score_quality_thresholds() -> None:
    assert score_quality(4.6) == ("Excellent", "good")
    assert score_quality(4.0) == ("Good", "good")
    assert score_quality(2.8) == ("Fair", "warn")
    assert score_quality(1.9) == ("Needs Review", "bad")


def test_risk_label_from_severity() -> None:
    assert risk_label("critical") == ("Critical", "bad")
    assert risk_label("high") == ("High", "bad")
    assert risk_label("medium") == ("Medium", "warn")
    assert risk_label("low") == ("Low", "low")
    assert risk_label(None) == ("None", "good")


def test_render_score_cell_includes_quality_label() -> None:
    rendered = render_score_cell(4.0)

    assert "4.0" in rendered
    assert "/5" in rendered
    assert "Good" in rendered
    assert render_score_cell(None) == "—"


def test_render_summary_card_contains_kpis_and_chips() -> None:
    rendered = render_summary_card(
        status="completed",
        created_at="2026-06-10T12:00:00",
        weighted_score=4.0,
        resolution="resolved",
        risk_severity="high",
        sentiment_trend="improving",
        purpose="Customer called about a billing issue.",
        discussion_points=["Billing mismatch", "Refund timeline"],
        insight_chips=[("Issue Resolved", "good"), ("High Risk Flag", "bad")],
        sentiment_detail="opening 2/5 -> closing 4/5",
    )

    assert "Analysis Summary" in rendered
    assert "QA Score" in rendered
    assert "4.0" in rendered
    assert "Resolved" in rendered
    assert "Risk Level" in rendered
    assert "High" in rendered
    assert "Improving" in rendered
    assert "Customer called about a billing issue." in rendered
    assert "Issue Resolved" in rendered


def test_render_summary_card_escapes_untrusted_text() -> None:
    rendered = render_summary_card(
        status="completed",
        created_at="2026-06-10T12:00:00",
        weighted_score=4.0,
        resolution="resolved",
        risk_severity=None,
        sentiment_trend="unknown",
        purpose="<script>alert(1)</script>",
        discussion_points=["<img src=x>"],
        insight_chips=[],
        sentiment_detail=None,
    )

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<img" not in rendered


def test_render_flags_table_rows_and_empty_state() -> None:
    rendered = render_flags_table(
        [
            {
                "severity": "high",
                "title": "Payment disclosure incomplete",
                "description": "Agent did not disclose terms.",
                "timestamp": "00:07:42",
            }
        ]
    )

    assert "chip-severity-high" in rendered
    assert "Payment disclosure incomplete" in rendered
    assert "00:07:42" in rendered

    assert "No compliance flags" in render_flags_table([])


def test_render_kpi_cards_renders_value_label_and_sub() -> None:
    rendered = render_kpi_cards(
        [
            {"value": "12", "label": "Total Analyses", "sub": "all time"},
            {"value": "96.3%", "label": "Success Rate", "sub": None, "tone": "good"},
        ]
    )

    assert 'class="kpi-grid"' in rendered
    assert "Total Analyses" in rendered
    assert "96.3%" in rendered
    assert "all time" in rendered


def test_render_trend_bar_width_tracks_rate() -> None:
    rendered = render_trend_bar(75.0)

    assert "width:75" in rendered.replace(" ", "")


def test_render_audit_action_chip_tones() -> None:
    assert "chip" in render_audit_action_chip("report_created")
    assert "Analysis Failed" in render_audit_action_chip("analysis_failed")


def test_render_system_health_lists_checks() -> None:
    rendered = render_system_health(
        [
            ("Database", "Operational", "good"),
            ("LangSmith Tracing", "Disabled", "muted"),
        ]
    )

    assert "System Status" in rendered
    assert "Database" in rendered
    assert "Operational" in rendered


def test_message_and_empty_cards() -> None:
    assert "Upload a call" in render_empty_summary_card()
    blocked = render_message_card(
        "blocked",
        "Analysis blocked for prompt-injection risk.",
        ["pattern: ignore instructions"],
    )
    assert "chip-status-blocked" in blocked
    assert "prompt-injection" in blocked


def test_app_bar_and_section_header() -> None:
    bar = render_app_bar()
    assert "Call Center Intelligence" in bar
    assert "app-bar" in bar

    header = render_section_header(1, "Input", "Upload call audio")
    assert "1" in header and "Input" in header and "Upload call audio" in header
