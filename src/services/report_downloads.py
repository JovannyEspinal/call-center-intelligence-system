"""Generate temporary downloads from persisted Call Reports."""

from __future__ import annotations

import json
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from textwrap import shorten
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.database import AnalysisRepository
from src.models import (
    QA_DIMENSION_WEIGHTS,
    AuditAction,
    AuditEvent,
    CallReport,
    PrivacyEvent,
    describe_sentiment_trajectory,
)

INK = colors.HexColor("#1C1B17")
PETROL_DARK = colors.HexColor("#07332D")
PETROL = colors.HexColor("#0B4F44")
TEAL = colors.HexColor("#0E7560")
PAPER = colors.HexColor("#F4F1EA")
PAPER_TEXT = colors.HexColor("#F4F0E6")
HEADER_SUBTLE = colors.HexColor("#9ECBBD")
MUTED = colors.HexColor("#5A5A52")
BORDER = colors.HexColor("#D8D4C8")
BAR_TRACK = colors.HexColor("#E7E3D8")
AMBER = colors.HexColor("#B45309")
ORANGE_RED = colors.HexColor("#C2410C")
CRITICAL_RED = colors.HexColor("#B91C1C")
SLATE = colors.HexColor("#6B7280")

SEVERITY_COLORS = {
    "low": SLATE,
    "medium": AMBER,
    "high": ORANGE_RED,
    "critical": CRITICAL_RED,
}


class ReportDownloadError(ValueError):
    """Raised when a requested report download cannot be generated."""


@dataclass(frozen=True)
class JsonReportDownload:
    """Temporary JSON report download payload."""

    analysis_id: str
    filename: str
    content: str


@dataclass(frozen=True)
class PdfReportDownload:
    """Temporary PDF report download artifact."""

    analysis_id: str
    filename: str
    path: Path


class ReportDownloadService:
    """Generate reviewer downloads from persisted redacted Call Reports."""

    def __init__(self, repository: AnalysisRepository) -> None:
        self.repository = repository

    def generate_json_download(
        self,
        analysis_id: str,
        *,
        reviewer_id: str | None = None,
        session_id: str | None = None,
    ) -> JsonReportDownload:
        report = self._get_report_or_raise(analysis_id)
        self._record_download_if_identified(
            analysis_id,
            reviewer_id=reviewer_id,
            session_id=session_id,
            report_format="json",
        )
        return JsonReportDownload(
            analysis_id=analysis_id,
            filename=f"{analysis_id}-call-report.json",
            content=json.dumps(
                report.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            ),
        )

    def generate_pdf_download(
        self,
        analysis_id: str,
        *,
        output_dir: str | Path | None = None,
        reviewer_id: str | None = None,
        session_id: str | None = None,
    ) -> PdfReportDownload:
        report = self._get_report_or_raise(analysis_id)
        output_path = _pdf_output_path(analysis_id, output_dir=output_dir)
        _write_pdf(report, output_path)
        self._record_download_if_identified(
            analysis_id,
            reviewer_id=reviewer_id,
            session_id=session_id,
            report_format="pdf",
        )
        return PdfReportDownload(
            analysis_id=analysis_id,
            filename=output_path.name,
            path=output_path,
        )

    def _get_report_or_raise(self, analysis_id: str) -> CallReport:
        report = self.repository.get_report(analysis_id)
        if report is None:
            raise ReportDownloadError("call report does not exist for analysis")
        return report

    def _record_download_if_identified(
        self,
        analysis_id: str,
        *,
        reviewer_id: str | None,
        session_id: str | None,
        report_format: str,
    ) -> None:
        if reviewer_id is None and session_id is None:
            return
        self.repository.append_audit_event(
            AuditEvent(
                analysis_id=analysis_id,
                action=AuditAction.REPORT_DOWNLOADED,
                reviewer_id=reviewer_id,
                session_id=session_id,
                details={"format": report_format},
            )
        )
        self.repository.commit()


def _pdf_output_path(analysis_id: str, *, output_dir: str | Path | None) -> Path:
    if output_dir is None:
        output_root = Path(tempfile.mkdtemp(prefix="call-report-"))
    else:
        output_root = Path(output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
    return output_root / f"{analysis_id}-call-report.pdf"


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="SectionTitle",
            parent=styles["Heading2"],
            fontSize=12,
            spaceBefore=18,
            spaceAfter=8,
            textColor=PETROL,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Body",
            parent=styles["Normal"],
            fontSize=9,
            leading=12.5,
            textColor=INK,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Muted",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=MUTED,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableHeader",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.white,
            fontName="Helvetica-Bold",
        )
    )
    styles.add(
        ParagraphStyle(
            name="Cell",
            parent=styles["Normal"],
            fontSize=8,
            leading=10.5,
            textColor=INK,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CellBold",
            parent=styles["Cell"],
            fontName="Helvetica-Bold",
        )
    )
    styles.add(
        ParagraphStyle(
            name="Evidence",
            parent=styles["Cell"],
            fontName="Helvetica-Oblique",
            textColor=MUTED,
            spaceBefore=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SeverityChip",
            parent=styles["Cell"],
            fontName="Helvetica-Bold",
            textColor=colors.white,
            alignment=1,
        )
    )
    styles.add(
        ParagraphStyle(
            name="KpiValue",
            parent=styles["Normal"],
            fontSize=15,
            leading=18,
            fontName="Helvetica-Bold",
            textColor=PETROL_DARK,
            alignment=1,
        )
    )
    styles.add(
        ParagraphStyle(
            name="KpiLabel",
            parent=styles["Normal"],
            fontSize=6.5,
            leading=9,
            fontName="Helvetica-Bold",
            textColor=MUTED,
            alignment=1,
        )
    )
    return styles


def _page_decorator(report: CallReport):
    """Draw the branded header band and confidentiality footer on each page."""

    def draw(canvas, doc) -> None:
        width, height = letter
        margin = 0.65 * inch
        band_height = 0.95 * inch
        canvas.saveState()
        canvas.setFillColor(PETROL_DARK)
        canvas.rect(0, height - band_height, width, band_height, stroke=0, fill=1)
        canvas.setFillColor(TEAL)
        canvas.rect(0, height - band_height - 3, width, 3, stroke=0, fill=1)
        canvas.setFillColor(PAPER_TEXT)
        canvas.setFont("Helvetica-Bold", 17)
        canvas.drawString(margin, height - 0.5 * inch, "Call Report")
        canvas.setFillColor(HEADER_SUBTLE)
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(
            margin,
            height - 0.7 * inch,
            "Call Center Intelligence - Redacted QA & Compliance Review",
        )
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(
            width - margin,
            height - 0.5 * inch,
            f"Analysis {report.analysis_id}",
        )
        canvas.drawRightString(
            width - margin,
            height - 0.7 * inch,
            report.created_at.isoformat(timespec="seconds"),
        )
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.6)
        canvas.line(margin, 0.55 * inch, width - margin, 0.55 * inch)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(
            margin,
            0.4 * inch,
            "Confidential - privacy-redacted call report. "
            "Sensitive values are replaced with placeholders.",
        )
        canvas.drawRightString(width - margin, 0.4 * inch, f"Page {doc.page}")
        canvas.restoreState()

    return draw


def _write_pdf(report: CallReport, output_path: Path) -> None:
    styles = _build_styles()
    story = [
        _kpi_strip(report, styles),
        Spacer(1, 14),
        Paragraph("Analysis Details", styles["SectionTitle"]),
        _key_value_table(
            [
                ("Analysis ID", report.analysis_id),
                ("Created", report.created_at.isoformat(timespec="seconds")),
                ("LLM Model", report.configuration.llm_model),
                ("Transcription Model", report.configuration.transcription_model),
                (
                    "Prompt Versions",
                    f"summary {report.configuration.summary_prompt_version} / "
                    f"qa {report.configuration.qa_prompt_version} / "
                    f"rubric {report.configuration.rubric_version}",
                ),
            ],
            styles,
        ),
        Paragraph("Summary", styles["SectionTitle"]),
        Paragraph(_pdf_text(report.summary.call_purpose), styles["Body"]),
        Spacer(1, 4),
        ListFlowable(
            [
                ListItem(Paragraph(_pdf_text(point), styles["Body"]))
                for point in report.summary.key_discussion_points
            ],
            bulletType="bullet",
            leftIndent=18,
        ),
        Spacer(1, 6),
        Paragraph(
            _pdf_text(f"Resolution: {report.summary.resolution_status.value.title()}"),
            styles["Body"],
        ),
        Paragraph(
            _pdf_text(
                f"Customer Sentiment: {describe_sentiment_trajectory(report.summary)}"
            ),
            styles["Body"],
        ),
        Paragraph("Action Items", styles["SectionTitle"]),
        _action_items_flowable(report, styles),
        Paragraph("QA Scorecard", styles["SectionTitle"]),
        Paragraph(
            _pdf_text(
                "Scores are evidence-backed and weighted deterministically "
                "by the global QA rubric. "
                f"Weighted QA Score: {report.qa_result.weighted_overall_score} / 5."
            ),
            styles["Muted"],
        ),
        Spacer(1, 6),
        _qa_score_table(report, styles),
        Paragraph("Compliance Flags", styles["SectionTitle"]),
    ]

    if report.qa_result.compliance_flags:
        for flag in report.qa_result.compliance_flags:
            story.append(_compliance_flag_table(flag, styles))
            story.append(Spacer(1, 6))
    else:
        story.append(Paragraph("No compliance flags were raised.", styles["Body"]))

    story.extend([Paragraph("Privacy Events", styles["SectionTitle"])])
    if report.privacy_events:
        unique_privacy_events = _unique_privacy_events(report)
        story.append(
            Paragraph(
                _pdf_text(
                    "Sensitive values were redacted before LLM analysis. "
                    f"{len(unique_privacy_events)} unique privacy events were "
                    "recorded."
                ),
                styles["Muted"],
            )
        )
        story.append(Spacer(1, 6))
        story.append(_privacy_event_summary_table(report, styles))
        story.append(Spacer(1, 8))
        story.append(_privacy_event_detail_table(report, styles))
    else:
        story.append(Paragraph("None", styles["Body"]))

    decorator = _page_decorator(report)
    SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        pageCompression=0,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=1.3 * inch,
        bottomMargin=0.85 * inch,
    ).build(story, onFirstPage=decorator, onLaterPages=decorator)


def _kpi_strip(report: CallReport, styles) -> Table:
    kpis = [
        (f"{report.qa_result.weighted_overall_score}", "Weighted QA Score"),
        (report.status.value.replace("_", " ").title(), "Status"),
        (report.summary.resolution_status.value.title(), "Resolution"),
        (report.summary.sentiment_trend.value.title(), "Sentiment Trend"),
        (str(len(report.qa_result.compliance_flags)), "Compliance Flags"),
    ]
    table = Table(
        [
            [
                [
                    Paragraph(_pdf_text(value), styles["KpiValue"]),
                    Paragraph(_pdf_text(label.upper()), styles["KpiLabel"]),
                ]
                for value, label in kpis
            ]
        ],
        colWidths=[1.31 * inch] * len(kpis),
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.75, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def _action_items_flowable(report: CallReport, styles):
    if not report.summary.action_items:
        return Paragraph("No action items were recorded.", styles["Body"])
    rows = [
        [
            Paragraph("Description", styles["TableHeader"]),
            Paragraph("Owner", styles["TableHeader"]),
            Paragraph("Deadline", styles["TableHeader"]),
        ]
    ]
    rows.extend(
        [
            Paragraph(_pdf_text(item.description), styles["Cell"]),
            Paragraph(_pdf_text(item.owner.title()), styles["Cell"]),
            Paragraph(_pdf_text(item.deadline or "-"), styles["Cell"]),
        ]
        for item in report.summary.action_items
    )
    table = Table(
        rows,
        colWidths=[4.2 * inch, 1.2 * inch, 1.15 * inch],
        hAlign="LEFT",
    )
    table.setStyle(_table_style(header=True))
    return table


def _evidence_line(item) -> str:
    time_range = _format_time_range(item.start_seconds, item.end_seconds)
    excerpt = _brief(item.excerpt, width=160)
    return f'Evidence [{item.speaker_role.value} {time_range}]: "{excerpt}"'


def _score_bar(score: int) -> Drawing:
    bar_width, bar_height = 70, 7
    drawing = Drawing(bar_width, bar_height)
    drawing.add(
        Rect(0, 0, bar_width, bar_height, fillColor=BAR_TRACK, strokeColor=None)
    )
    drawing.add(
        Rect(
            0,
            0,
            bar_width * score / 5,
            bar_height,
            fillColor=_score_color(score),
            strokeColor=None,
        )
    )
    return drawing


def _score_color(score: int):
    if score >= 4:
        return TEAL
    if score == 3:
        return AMBER
    return ORANGE_RED


def _key_value_table(
    rows: list[tuple[str, object]],
    styles,
) -> Table:
    table = Table(
        [
            [
                Paragraph(_pdf_text(label), styles["CellBold"]),
                Paragraph(_pdf_text(value), styles["Cell"]),
            ]
            for label, value in rows
        ],
        colWidths=[1.55 * inch, 5.0 * inch],
        hAlign="LEFT",
    )
    table.setStyle(_table_style())
    return table


def _qa_score_table(report: CallReport, styles) -> Table:
    rows = [
        [
            Paragraph("Dimension", styles["TableHeader"]),
            Paragraph("Score", styles["TableHeader"]),
            Paragraph("", styles["TableHeader"]),
            Paragraph("Weight", styles["TableHeader"]),
            Paragraph("Justification & Evidence", styles["TableHeader"]),
        ]
    ]
    rows.extend(
        [
            Paragraph(
                _pdf_text(_display_data_type(dimension.dimension.value)),
                styles["CellBold"],
            ),
            Paragraph(_pdf_text(f"{dimension.score}/5"), styles["CellBold"]),
            _score_bar(dimension.score),
            Paragraph(
                _pdf_text(f"{round(QA_DIMENSION_WEIGHTS[dimension.dimension] * 100)}%"),
                styles["Cell"],
            ),
            [
                Paragraph(_pdf_text(dimension.justification), styles["Cell"]),
                *(
                    Paragraph(
                        _pdf_text(_evidence_line(item)),
                        styles["Evidence"],
                    )
                    for item in dimension.evidence
                ),
            ],
        ]
        for dimension in report.qa_result.dimensions
    )
    table = Table(
        rows,
        colWidths=[1.25 * inch, 0.5 * inch, 1.05 * inch, 0.55 * inch, 3.2 * inch],
        hAlign="LEFT",
    )
    table.setStyle(_table_style(header=True))
    return table


def _compliance_flag_table(flag, styles) -> Table:
    severity_color = SEVERITY_COLORS.get(flag.severity.value, SLATE)
    rows = [
        [
            Paragraph(_pdf_text(flag.severity.value.upper()), styles["SeverityChip"]),
            Paragraph(_pdf_text(flag.title), styles["CellBold"]),
            Paragraph(_pdf_text(flag.description), styles["Cell"]),
        ]
    ]
    rows.extend(
        [
            Paragraph("", styles["Cell"]),
            Paragraph("Evidence", styles["Evidence"]),
            Paragraph(
                _pdf_text(
                    f"[{item.speaker_role.value} "
                    f"{_format_time_range(item.start_seconds, item.end_seconds)}] "
                    f'"{_brief(item.excerpt)}"'
                ),
                styles["Evidence"],
            ),
        ]
        for item in flag.evidence
    )
    table = Table(
        rows,
        colWidths=[0.85 * inch, 1.7 * inch, 4.0 * inch],
        hAlign="LEFT",
    )
    style_commands = _table_style().getCommands() + [
        ("BACKGROUND", (0, 0), (0, 0), severity_color),
        ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
    ]
    table.setStyle(TableStyle(style_commands))
    return table


def _privacy_event_summary_table(report: CallReport, styles) -> Table:
    counts: dict[str, int] = {}
    for event in _unique_privacy_events(report):
        counts[event.data_type.value] = counts.get(event.data_type.value, 0) + 1

    rows = [
        [
            Paragraph("Data Type", styles["TableHeader"]),
            Paragraph("Count", styles["TableHeader"]),
        ]
    ]
    rows.extend(
        [
            Paragraph(_pdf_text(_display_data_type(data_type)), styles["CellBold"]),
            Paragraph(_pdf_text(count), styles["Cell"]),
        ]
        for data_type, count in sorted(counts.items())
    )
    table = Table(rows, colWidths=[2.1 * inch, 0.75 * inch], hAlign="LEFT")
    table.setStyle(_table_style(header=True))
    return table


def _privacy_event_detail_table(report: CallReport, styles) -> Table:
    privacy_events = _unique_privacy_events(report)
    rows = [
        [
            Paragraph("Type", styles["TableHeader"]),
            Paragraph("Time", styles["TableHeader"]),
            Paragraph("Context", styles["TableHeader"]),
        ]
    ]
    rows.extend(
        [
            Paragraph(
                _pdf_text(_display_data_type(event.data_type.value)),
                styles["CellBold"],
            ),
            Paragraph(_pdf_text(_event_time_range(report, event)), styles["Cell"]),
            Paragraph(_pdf_text(_event_context(report, event)), styles["Cell"]),
        ]
        for event in privacy_events[:25]
    )
    if len(privacy_events) > 25:
        rows.append(
            [
                Paragraph("More", styles["CellBold"]),
                Paragraph("", styles["Cell"]),
                Paragraph(
                    _pdf_text(
                        f"{len(privacy_events) - 25} additional privacy "
                        "events omitted from this compact PDF view. See JSON report "
                        "for full detail."
                    ),
                    styles["Cell"],
                ),
            ]
        )

    table = Table(
        rows,
        colWidths=[1.15 * inch, 1.55 * inch, 3.85 * inch],
        hAlign="LEFT",
    )
    table.setStyle(_table_style(header=True))
    return table


def _event_time_range(report: CallReport, event: PrivacyEvent) -> str:
    if event.start_seconds is None or event.end_seconds is None:
        inferred_range = _infer_event_time_range(report, event)
        return inferred_range or "N/A"
    return _format_time_range(event.start_seconds, event.end_seconds)


def _infer_event_time_range(report: CallReport, event: PrivacyEvent) -> str | None:
    best_segment = _best_privacy_event_segment(report, event) or _best_context_segment(
        report,
        event,
    )
    if best_segment is None:
        return None
    return _format_time_range(best_segment.start_seconds, best_segment.end_seconds)


def _event_context(report: CallReport, event: PrivacyEvent) -> str:
    best_segment = _best_privacy_event_segment(report, event)
    if best_segment is not None:
        return best_segment.text
    full_text_context = _full_text_event_context(report, event)
    if full_text_context is not None:
        return full_text_context
    return _brief(event.context_excerpt, width=120)


def _best_privacy_event_segment(report: CallReport, event: PrivacyEvent):
    candidates = [
        segment
        for segment in report.redacted_transcript.segments
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


def _best_context_segment(report: CallReport, event: PrivacyEvent):
    if not report.redacted_transcript.segments:
        return None
    context_tokens = _token_set(
        _full_text_event_context(report, event) or event.context_excerpt
    )
    if not context_tokens:
        return None
    best_segment = max(
        report.redacted_transcript.segments,
        key=lambda segment: len(context_tokens & _token_set(segment.text)),
    )
    if not context_tokens & _token_set(best_segment.text):
        return None
    return best_segment


def _full_text_event_context(report: CallReport, event: PrivacyEvent) -> str | None:
    full_text = report.redacted_transcript.full_text
    placeholder_indexes = _placeholder_indexes(full_text, event.placeholder)
    if not placeholder_indexes:
        return None

    context_tokens = _token_set(event.context_excerpt)
    best_context = max(
        (_sentence_window(full_text, index) for index in placeholder_indexes),
        key=lambda context: len(context_tokens & _token_set(context)),
    )
    return best_context or None


def _placeholder_indexes(value: str, placeholder: str) -> list[int]:
    indexes: list[int] = []
    start = 0
    while True:
        index = value.find(placeholder, start)
        if index < 0:
            return indexes
        indexes.append(index)
        start = index + len(placeholder)


def _sentence_window(value: str, placeholder_index: int) -> str:
    start = _previous_sentence_boundary(value, placeholder_index)
    end = _next_sentence_boundary(
        value,
        placeholder_index,
        include_following_sentence=True,
    )
    return value[start:end].strip()


def _previous_sentence_boundary(value: str, index: int) -> int:
    boundary = max(value.rfind(".", 0, index), value.rfind("?", 0, index))
    if boundary < 0:
        return 0
    if not value[boundary + 1 : index].strip():
        previous_boundary = max(
            value.rfind(".", 0, boundary),
            value.rfind("?", 0, boundary),
        )
        return 0 if previous_boundary < 0 else previous_boundary + 1
    return boundary + 1


def _next_sentence_boundary(
    value: str,
    index: int,
    *,
    include_following_sentence: bool,
) -> int:
    boundary = _first_boundary_after(value, index)
    if boundary is None:
        return len(value)
    if not include_following_sentence:
        return boundary + 1
    next_boundary = _first_boundary_after(value, boundary + 1)
    return (next_boundary + 1) if next_boundary is not None else boundary + 1


def _first_boundary_after(value: str, index: int) -> int | None:
    boundaries = [
        boundary
        for boundary in (value.find(".", index), value.find("?", index))
        if boundary >= 0
    ]
    return min(boundaries) if boundaries else None


def _format_time_range(start_seconds: float, end_seconds: float) -> str:
    start = math.floor(start_seconds)
    end = math.ceil(end_seconds)
    return f"{_format_timestamp(start)}-{_format_timestamp(end)}"


def _format_timestamp(seconds: int) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining_seconds = seconds % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes:02d}:{remaining_seconds:02d}"


def _unique_privacy_events(report: CallReport) -> list[PrivacyEvent]:
    seen: set[tuple[str, str, str]] = set()
    unique_events: list[PrivacyEvent] = []
    for event in report.privacy_events:
        key = (
            event.data_type.value,
            _event_time_range(report, event),
            _normalized_context(_event_context(report, event)),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_events.append(event)
    return sorted(unique_events, key=lambda event: _event_sort_key(report, event))


def _event_sort_key(report: CallReport, event: PrivacyEvent) -> tuple[float, str]:
    if event.start_seconds is not None:
        return (event.start_seconds, event.data_type.value)
    best_segment = _best_privacy_event_segment(report, event) or _best_context_segment(
        report,
        event,
    )
    if best_segment is not None:
        return (best_segment.start_seconds, event.data_type.value)
    return (float("inf"), event.data_type.value)


def _normalized_context(value: str) -> str:
    return " ".join(value.split()).lower()


def _display_data_type(value: str) -> str:
    return value.replace("_", " ").title()


def _token_set(value: str) -> set[str]:
    return {
        token.strip(".,:;!?()[]'\"").lower()
        for token in value.split()
        if token.strip(".,:;!?()[]'\"")
    }


def _table_style(*, header: bool = False) -> TableStyle:
    commands = [
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        (
            "ROWBACKGROUNDS",
            (0, 1 if header else 0),
            (-1, -1),
            [colors.white, colors.HexColor("#f9fafb")],
        ),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")))
    return TableStyle(commands)


def _brief(value: str, *, width: int = 180) -> str:
    return shorten(value, width=width, placeholder="...")


def _pdf_text(value: object) -> str:
    return escape(str(value))
