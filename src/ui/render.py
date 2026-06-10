"""Dark-console HTML renderers and CSS for the dashboard UI.

All text interpolated into HTML is escaped; renderers accept primitives so
they stay testable without domain imports.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

FORCE_DARK_JS = """
() => {
    const url = new URL(window.location);
    if (url.searchParams.get('__theme') !== 'dark') {
        url.searchParams.set('__theme', 'dark');
        window.location.href = url.href;
    }
}
"""

DASHBOARD_CSS = """
:root, .dark {
    --ccs-bg: #0b0f0e;
    --ccs-card: #111615;
    --ccs-card-2: #161c1b;
    --ccs-border: #232b29;
    --ccs-text: #e8ebea;
    --ccs-muted: #8b9491;
    --ccs-teal: #14b8a6;
    --ccs-teal-soft: rgba(20, 184, 166, 0.14);
    --ccs-green: #34d399;
    --ccs-amber: #fbbf24;
    --ccs-orange: #fb923c;
    --ccs-red: #f87171;
    --ccs-purple: #c4b5fd;
    --body-background-fill: var(--ccs-bg);
    --background-fill-primary: var(--ccs-card);
    --background-fill-secondary: var(--ccs-card-2);
    --block-background-fill: var(--ccs-card);
    --border-color-primary: var(--ccs-border);
    --block-border-color: var(--ccs-border);
    --body-text-color: var(--ccs-text);
    --block-label-text-color: var(--ccs-muted);
    --block-title-text-color: var(--ccs-text);
}
body, .gradio-container {
    background: var(--ccs-bg) !important;
    color: var(--ccs-text);
}
.gradio-container {max-width: 1480px !important; margin: 0 auto !important;}
footer {display: none !important;}

/* ---- app bar ---- */
.app-bar {
    display: flex; align-items: center; gap: 14px;
    padding: 14px 4px 12px;
    border-bottom: 1px solid var(--ccs-border);
    margin-bottom: 2px;
}
.app-bar .logo {
    width: 38px; height: 38px; border-radius: 10px;
    background: var(--ccs-teal);
    display: flex; align-items: center; justify-content: center;
    font-size: 19px; color: #06302b;
}
.app-bar .title {font-size: 1.25rem; font-weight: 700; color: var(--ccs-text);}
.app-bar .tagline {color: var(--ccs-muted); font-size: 0.88rem; margin-left: 6px;}

/* ---- cards & sections ---- */
.ccs-card, .gradio-container .block {border-radius: 12px;}
.section-header {
    display: flex; align-items: center; gap: 10px;
    margin: 4px 0 2px; color: var(--ccs-text);
    font-weight: 600; font-size: 1rem;
}
.section-header .step {
    width: 24px; height: 24px; border-radius: 50%;
    border: 1.5px solid var(--ccs-teal); color: var(--ccs-teal);
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 0.8rem; font-weight: 700;
}
.section-header .hint {color: var(--ccs-muted); font-weight: 400; font-size: 0.85rem;}
.upload-note {color: var(--ccs-muted); font-size: 0.78rem; margin-top: -4px;}

/* ---- chips ---- */
.chip {
    display: inline-flex; align-items: center;
    padding: 3px 12px; border-radius: 999px;
    font-size: 0.76rem; font-weight: 600; letter-spacing: 0.01em;
    border: 1px solid transparent; white-space: nowrap;
}
.chip-status-completed {
    background: rgba(52,211,153,.12);
    color: var(--ccs-green);
    border-color: rgba(52,211,153,.35);
}
.chip-status-supervisor_review {
    background: rgba(196,181,253,.12);
    color: var(--ccs-purple);
    border-color: rgba(196,181,253,.35);
}
.chip-status-blocked {
    background: rgba(251,146,60,.12);
    color: var(--ccs-orange);
    border-color: rgba(251,146,60,.35);
}
.chip-status-failed {
    background: rgba(248,113,113,.12);
    color: var(--ccs-red);
    border-color: rgba(248,113,113,.35);
}
.chip-severity-critical {
    background: rgba(248,113,113,.16);
    color: #fca5a5;
    border-color: rgba(248,113,113,.4);
}
.chip-severity-high {
    background: rgba(248,113,113,.12);
    color: var(--ccs-red);
    border-color: rgba(248,113,113,.35);
}
.chip-severity-medium {
    background: rgba(251,191,36,.12);
    color: var(--ccs-amber);
    border-color: rgba(251,191,36,.35);
}
.chip-severity-low {
    background: rgba(251,191,36,.07);
    color: #fde68a;
    border-color: rgba(251,191,36,.2);
}
.chip-good {
    background: rgba(52,211,153,.12);
    color: var(--ccs-green);
    border-color: rgba(52,211,153,.35);
}
.chip-warn {
    background: rgba(251,191,36,.12);
    color: var(--ccs-amber);
    border-color: rgba(251,191,36,.35);
}
.chip-bad {
    background: rgba(248,113,113,.12);
    color: var(--ccs-red);
    border-color: rgba(248,113,113,.35);
}
.chip-muted {
    background: rgba(139,148,145,.12);
    color: var(--ccs-muted);
    border-color: rgba(139,148,145,.3);
}

/* ---- KPI cards ---- */
.kpi-grid {
    display: grid; gap: 12px;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
}
.kpi-card {
    background: var(--ccs-card-2);
    border: 1px solid var(--ccs-border);
    border-radius: 12px; padding: 14px 16px;
    display: flex; flex-direction: column; gap: 3px;
}
.kpi-card .kpi-label {color: var(--ccs-muted); font-size: 0.78rem; font-weight: 600;}
.kpi-card .kpi-value {
    font-size: 1.7rem;
    font-weight: 700;
    color: var(--ccs-text);
    line-height: 1.2;
}
.kpi-card .kpi-sub {font-size: 0.76rem; color: var(--ccs-muted);}
.kpi-card.tone-good .kpi-value {color: var(--ccs-green);}
.kpi-card.tone-warn .kpi-value {color: var(--ccs-amber);}
.kpi-card.tone-bad .kpi-value {color: var(--ccs-red);}

/* ---- summary card ---- */
.summary-card {
    background: var(--ccs-card-2);
    border: 1px solid var(--ccs-border);
    border-radius: 12px; padding: 18px 20px;
}
.summary-card .card-head {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    margin-bottom: 14px;
}
.summary-card .card-title {
    font-weight: 700;
    font-size: 1.02rem;
    color: var(--ccs-text);
}
.summary-card .card-meta {
    margin-left: auto;
    color: var(--ccs-muted);
    font-size: 0.8rem;
}
.summary-kpis {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    border: 1px solid var(--ccs-border); border-radius: 10px; overflow: hidden;
    margin-bottom: 14px;
}
.summary-kpis .skpi {
    padding: 12px 16px; border-right: 1px solid var(--ccs-border);
    background: var(--ccs-card);
}
.summary-kpis .skpi:last-child {border-right: none;}
.summary-kpis .skpi-label {
    color: var(--ccs-muted);
    font-size: 0.76rem;
    font-weight: 600;
}
.summary-kpis .skpi-value {font-size: 1.35rem; font-weight: 700; margin: 2px 0;}
.summary-kpis .skpi-sub {font-size: 0.74rem; color: var(--ccs-muted);}
.skpi-value.tone-good {color: var(--ccs-green);}
.skpi-value.tone-warn {color: var(--ccs-amber);}
.skpi-value.tone-bad {color: var(--ccs-red);}
.skpi-value.tone-low {color: #fde68a;}
.ai-summary-label {
    color: var(--ccs-muted); font-size: 0.8rem; font-weight: 700;
    margin-bottom: 6px;
}
.summary-card .purpose {color: var(--ccs-text); font-size: 0.92rem; line-height: 1.55;}
.summary-card ul {margin: 8px 0 12px 2px; padding-left: 18px;}
.summary-card li {color: var(--ccs-text); font-size: 0.88rem; line-height: 1.55;}
.insight-chips {display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px;}
.sentiment-detail {color: var(--ccs-muted); font-size: 0.8rem; margin-top: 10px;}

/* ---- table wrapper ---- */
.table-wrap {
    overflow-x: auto;
    border: 1px solid var(--ccs-border);
    border-radius: 12px;
    background: var(--ccs-card-2);
    padding: 2px 10px;
}

/* ---- inline tables (flags, health) ---- */
.ccs-table {width: 100%; border-collapse: collapse; font-size: 0.85rem;}
.ccs-table th {
    text-align: left; color: var(--ccs-muted); font-weight: 600;
    font-size: 0.78rem; padding: 8px 12px;
    border-bottom: 1px solid var(--ccs-border);
}
.ccs-table td {
    padding: 10px 12px; color: var(--ccs-text);
    border-bottom: 1px solid var(--ccs-border); vertical-align: top;
}
.ccs-table tr:last-child td {border-bottom: none;}
.empty-note {color: var(--ccs-muted); font-size: 0.86rem; padding: 8px 2px;}

/* ---- trend bar ---- */
.trend-bar {
    display: inline-block; width: 90px; height: 6px;
    background: rgba(139,148,145,.18); border-radius: 999px;
    vertical-align: middle; overflow: hidden;
}
.trend-bar .fill {height: 100%; background: var(--ccs-green); border-radius: 999px;}

/* ---- system health ---- */
.health-card {
    background: var(--ccs-card-2); border: 1px solid var(--ccs-border);
    border-radius: 12px; padding: 14px 16px;
}
.health-card .card-title {font-weight: 700; margin-bottom: 8px; color: var(--ccs-text);}
.health-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 9px 2px; border-bottom: 1px solid var(--ccs-border);
    font-size: 0.86rem; color: var(--ccs-text);
}
.health-row:last-child {border-bottom: none;}
.health-state-good {color: var(--ccs-green); font-weight: 600; font-size: 0.8rem;}
.health-state-muted {color: var(--ccs-muted); font-weight: 600; font-size: 0.8rem;}
.health-state-warn {color: var(--ccs-amber); font-weight: 600; font-size: 0.8rem;}

/* ---- gradio component restyling ---- */
.gradio-container .tabs > .tab-nav {
    border-bottom: 1px solid var(--ccs-border) !important;
}
.gradio-container .tab-nav button {
    color: var(--ccs-muted) !important;
    font-weight: 600;
}
.gradio-container .tab-nav button.selected {
    color: var(--ccs-teal) !important;
    border-bottom: 2px solid var(--ccs-teal) !important;
}
.gradio-container button.primary {
    background: var(--ccs-teal) !important;
    color: #06302b !important; font-weight: 700;
    border: none !important;
}
.gradio-container button.secondary {
    background: var(--ccs-card-2) !important;
    color: var(--ccs-text) !important;
    border: 1px solid var(--ccs-border) !important;
}
.gradio-container label span[data-testid="block-info"],
.gradio-container .block-label, .gradio-container label > span {
    background: transparent !important;
    color: var(--ccs-muted) !important;
    font-weight: 600 !important;
}
.gradio-container .audio-container, .gradio-container [data-testid="waveform"] {
    border: 1.5px dashed var(--ccs-border) !important; border-radius: 12px;
}
.gradio-container table {background: transparent !important;}
.gradio-container thead {background: var(--ccs-card-2) !important;}
.gradio-container .accordion {border: 1px solid var(--ccs-border) !important;}
"""


def _esc(value: object) -> str:
    return escape(str(value))


def chip(label: str, kind: str) -> str:
    """Render a pill chip; `kind` selects the palette class."""
    return f'<span class="chip chip-{_esc(kind)}">{_esc(label)}</span>'


def render_status_chip(status: str) -> str:
    normalized = status.strip().lower()
    if not normalized:
        return ""
    return chip(normalized.replace("_", " ").title(), f"status-{normalized}")


def score_quality(score: float) -> tuple[str, str]:
    """Qualitative label and tone for a 0-5 weighted QA score."""
    if score >= 4.5:
        return ("Excellent", "good")
    if score >= 3.5:
        return ("Good", "good")
    if score >= 2.5:
        return ("Fair", "warn")
    return ("Needs Review", "bad")


def risk_label(severity: str | None) -> tuple[str, str]:
    """Reviewer-facing risk label and tone from the max flag severity."""
    if severity is None:
        return ("None", "good")
    tones = {"critical": "bad", "high": "bad", "medium": "warn", "low": "low"}
    return (severity.title(), tones.get(severity, "muted"))


def render_score_cell(score: float | None) -> str:
    if score is None:
        return "—"
    label, tone = score_quality(score)
    return (
        f'<div><span class="skpi-value tone-{tone}" style="font-size:1rem">'
        f"{_esc(score)}</span>"
        f'<span style="color:var(--ccs-muted);font-size:.75rem"> /5</span><br>'
        f'<span class="skpi-sub" style="color:var(--ccs-muted)">{label}</span></div>'
    )


def render_app_bar() -> str:
    return (
        '<div class="app-bar">'
        '<div class="logo">&#9776;</div>'
        '<span class="title">Call Center Intelligence</span>'
        '<span class="tagline">Privacy-safe call analysis &middot; '
        "Evidence-backed QA scoring &middot; Compliance review</span>"
        "</div>"
    )


def render_section_header(step: int, title: str, hint: str | None = None) -> str:
    hint_html = f'<span class="hint">{_esc(hint)}</span>' if hint else ""
    return (
        '<div class="section-header">'
        f'<span class="step">{step}</span>'
        f"<span>{_esc(title)}</span>{hint_html}"
        "</div>"
    )


def render_kpi_cards(cards: list[dict]) -> str:
    rendered = []
    for card in cards:
        tone = card.get("tone")
        tone_class = f" tone-{tone}" if tone else ""
        sub = card.get("sub")
        sub_html = f'<span class="kpi-sub">{_esc(sub)}</span>' if sub else ""
        rendered.append(
            f'<div class="kpi-card{tone_class}">'
            f'<span class="kpi-label">{_esc(card["label"])}</span>'
            f'<span class="kpi-value">{_esc(card["value"])}</span>'
            f"{sub_html}</div>"
        )
    return f'<div class="kpi-grid">{"".join(rendered)}</div>'


def render_summary_card(
    *,
    status: str,
    created_at: str,
    weighted_score: float,
    resolution: str,
    risk_severity: str | None,
    sentiment_trend: str,
    purpose: str,
    discussion_points: list[str],
    insight_chips: list[tuple[str, str]],
    sentiment_detail: str | None,
) -> str:
    score_label, score_tone = score_quality(weighted_score)
    risk_text, risk_tone = risk_label(risk_severity)
    sentiment_tones = {
        "improving": "good",
        "stable": "warn",
        "declining": "bad",
        "unknown": "muted",
    }
    sentiment_tone = sentiment_tones.get(sentiment_trend, "muted")
    points = "".join(f"<li>{_esc(point)}</li>" for point in discussion_points)
    chips_html = "".join(chip(label, tone) for label, tone in insight_chips)
    sentiment_html = (
        f'<div class="sentiment-detail">Sentiment trajectory: '
        f"{_esc(sentiment_detail)}</div>"
        if sentiment_detail
        else ""
    )
    return (
        '<div class="summary-card">'
        '<div class="card-head">'
        '<span class="card-title">Analysis Summary</span>'
        f"{render_status_chip(status)}"
        f'<span class="card-meta">{_esc(created_at)}</span>'
        "</div>"
        '<div class="summary-kpis">'
        '<div class="skpi"><div class="skpi-label">QA Score</div>'
        f'<div class="skpi-value tone-{score_tone}">{_esc(weighted_score)}'
        '<span style="font-size:.85rem;color:var(--ccs-muted)"> /5</span></div>'
        f'<div class="skpi-sub">{score_label}</div></div>'
        '<div class="skpi"><div class="skpi-label">Call Outcome</div>'
        f'<div class="skpi-value">{_esc(resolution.title())}</div>'
        '<div class="skpi-sub">Resolution status</div></div>'
        '<div class="skpi"><div class="skpi-label">Risk Level</div>'
        f'<div class="skpi-value tone-{risk_tone}">{risk_text}</div>'
        '<div class="skpi-sub">From compliance flags</div></div>'
        '<div class="skpi"><div class="skpi-label">Sentiment</div>'
        f'<div class="skpi-value tone-{sentiment_tone}">'
        f"{_esc(sentiment_trend.title())}</div>"
        '<div class="skpi-sub">Customer trajectory</div></div>'
        "</div>"
        '<div class="ai-summary-label">AI SUMMARY</div>'
        f'<div class="purpose">{_esc(purpose)}</div>'
        f"<ul>{points}</ul>"
        f'<div class="insight-chips">{chips_html}</div>'
        f"{sentiment_html}"
        "</div>"
    )


def render_empty_summary_card() -> str:
    return (
        '<div class="summary-card">'
        '<div class="card-head"><span class="card-title">Analysis Summary</span>'
        "</div>"
        '<div class="empty-note">Upload a call and run an analysis to see the '
        "QA scorecard, compliance flags, and redacted transcript here.</div>"
        "</div>"
    )


def render_message_card(
    status: str,
    message: str,
    detail_lines: list[str] | None = None,
) -> str:
    details = "".join(
        f'<div class="empty-note">{_esc(line)}</div>' for line in detail_lines or []
    )
    return (
        '<div class="summary-card">'
        '<div class="card-head"><span class="card-title">Analysis Summary</span>'
        f"{render_status_chip(status)}</div>"
        f'<div class="purpose">{_esc(message)}</div>'
        f"{details}"
        "</div>"
    )


def render_flags_table(flags: list[dict]) -> str:
    if not flags:
        return (
            '<div class="empty-note">No compliance flags were raised for this '
            "analysis.</div>"
        )
    rendered_rows = []
    for flag in flags:
        severity = flag["severity"]
        timestamp = flag.get("timestamp") or "—"
        rendered_rows.append(
            "<tr>"
            f"<td>{chip(severity.title(), f'severity-{severity}')}</td>"
            f"<td>{_esc(flag['title'])}</td>"
            f"<td>{_esc(flag['description'])}</td>"
            f'<td style="white-space:nowrap">{_esc(timestamp)}</td>'
            "</tr>"
        )
    rows = "".join(rendered_rows)
    return (
        '<table class="ccs-table">'
        "<thead><tr><th>Severity</th><th>Title</th><th>Description</th>"
        "<th>Timestamp</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def render_trend_bar(success_rate: float) -> str:
    clamped = max(0.0, min(100.0, success_rate))
    return (
        f'{clamped:.1f}% <span class="trend-bar">'
        f'<span class="fill" style="width:{clamped:.0f}%"></span></span>'
    )


AUDIT_ACTION_TONES = {
    "report_created": "good",
    "qa_completed": "good",
    "summary_completed": "good",
    "analysis_started": "muted",
    "intake_completed": "muted",
    "transcription_completed": "muted",
    "transcription_cache_used": "muted",
    "pii_redaction_completed": "muted",
    "report_downloaded": "muted",
    "supervisor_review_required": "status-supervisor_review",
    "prompt_injection_blocked": "status-blocked",
    "analysis_failed": "status-failed",
}


def render_audit_action_chip(action: str) -> str:
    tone = AUDIT_ACTION_TONES.get(action, "muted")
    return chip(action.replace("_", " ").title(), tone)


def render_table_html(
    headers: list[str],
    rows: list[list[str]],
    html_columns: set[int] | None = None,
    empty_message: str = "No data yet.",
) -> str:
    """Render a styled table; cells in html_columns are pre-rendered HTML."""
    if not rows:
        return f'<div class="empty-note">{_esc(empty_message)}</div>'
    allowed = html_columns or set()
    head = "".join(f"<th>{_esc(header)}</th>" for header in headers)
    body = "".join(
        "<tr>"
        + "".join(
            f"<td>{cell if index in allowed else _esc(cell)}</td>"
            for index, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    return (
        '<div class="table-wrap"><table class="ccs-table">'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )


def render_system_health(checks: list[tuple[str, str, str]]) -> str:
    rows = "".join(
        f'<div class="health-row"><span>{_esc(name)}</span>'
        f'<span class="health-state-{_esc(tone)}">{_esc(state)}</span></div>'
        for name, state, tone in checks
    )
    return (
        '<div class="health-card">'
        '<div class="card-title">System Status</div>'
        f"{rows}</div>"
    )
