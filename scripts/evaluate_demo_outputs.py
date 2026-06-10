"""Deterministic demo evaluation checks over persisted call reports."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import AnalysisStatus, CallReport, SpeakerRole  # noqa: E402
from src.models.redaction import contains_raw_sensitive_value  # noqa: E402


@dataclass(frozen=True)
class EvalCheck:
    """One deterministic evaluation result."""

    name: str
    passed: bool
    detail: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic evaluation checks on persisted call reports."
    )
    parser.add_argument(
        "--database",
        default="data/calls.db",
        help="SQLite database path. Defaults to data/calls.db.",
    )
    parser.add_argument(
        "--analysis-id",
        default=None,
        help="Specific analysis ID to evaluate. Defaults to the latest report.",
    )
    parser.add_argument(
        "--min-segments",
        type=int,
        default=5,
        help="Minimum redacted transcript segment count.",
    )
    parser.add_argument(
        "--max-unknown-speaker-ratio",
        type=float,
        default=0.05,
        help="Maximum allowed ratio of unknown speaker segments.",
    )
    args = parser.parse_args()

    try:
        report = load_report(Path(args.database), analysis_id=args.analysis_id)
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(f"Evaluation failed to load report: {exc}", file=sys.stderr)
        return 2

    checks = evaluate_report(
        report,
        min_segments=args.min_segments,
        max_unknown_speaker_ratio=args.max_unknown_speaker_ratio,
    )
    print(format_eval_summary(report.analysis_id, checks))
    return 0 if all(check.passed for check in checks) else 1


def load_report(database_path: Path, *, analysis_id: str | None = None) -> CallReport:
    """Load a call report from SQLite."""
    if not database_path.exists():
        raise FileNotFoundError(f"database does not exist: {database_path}")

    with sqlite3.connect(database_path) as connection:
        if analysis_id:
            row = connection.execute(
                "SELECT report_json FROM call_reports WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT report_json FROM call_reports ORDER BY created_at DESC LIMIT 1"
            ).fetchone()

    if row is None:
        raise ValueError("no persisted call report found")
    return CallReport.model_validate_json(row[0])


def evaluate_report(
    report: CallReport,
    *,
    min_segments: int,
    max_unknown_speaker_ratio: float,
    extra_report_text_surfaces: list[str] | None = None,
) -> list[EvalCheck]:
    """Evaluate objective safety, routing, and completeness properties."""
    segments = report.redacted_transcript.segments
    unknown_count = sum(
        1 for segment in segments if segment.speaker_role is SpeakerRole.UNKNOWN
    )
    unknown_ratio = unknown_count / len(segments) if segments else 1.0
    report_text = "\n".join(
        collect_report_text_surfaces(report)
        + list(extra_report_text_surfaces or [])
    )
    report_text_has_sensitive_value = contains_raw_sensitive_value(report_text)

    checks = [
        EvalCheck(
            name="terminal_status",
            passed=report.status
            in {AnalysisStatus.COMPLETED, AnalysisStatus.SUPERVISOR_REVIEW},
            detail=f"status={report.status.value}",
        ),
        EvalCheck(
            name="report_text_has_no_raw_sensitive_values",
            passed=not report_text_has_sensitive_value,
            detail="raw sensitive pattern detected"
            if report_text_has_sensitive_value
            else "no raw sensitive patterns detected",
        ),
        EvalCheck(
            name="redacted_transcript_has_segments",
            passed=len(segments) >= min_segments,
            detail=f"segments={len(segments)}, min={min_segments}",
        ),
        EvalCheck(
            name="unknown_speaker_ratio_under_threshold",
            passed=unknown_ratio <= max_unknown_speaker_ratio,
            detail=(
                f"unknown={unknown_count}/{len(segments)} "
                f"({unknown_ratio:.2%}), max={max_unknown_speaker_ratio:.2%}"
            ),
        ),
        EvalCheck(
            name="summary_is_complete",
            passed=summary_is_complete(report),
            detail=summary_detail(report),
        ),
        EvalCheck(
            name="qa_is_complete",
            passed=len(report.qa_result.dimensions) == 5
            and 1 <= report.qa_result.weighted_overall_score <= 5,
            detail=(
                f"dimensions={len(report.qa_result.dimensions)}, "
                f"weighted_score={report.qa_result.weighted_overall_score}"
            ),
        ),
        EvalCheck(
            name="privacy_events_have_redacted_context",
            passed=privacy_events_have_redacted_context(report),
            detail=f"privacy_events={len(report.privacy_events)}",
        ),
    ]
    return checks


def collect_report_text_surfaces(report: CallReport) -> list[str]:
    """Collect report-facing prose where raw customer data must never appear."""
    surfaces = [
        report.redacted_transcript.full_text,
        report.summary.call_purpose,
        report.summary.customer_sentiment_trajectory,
    ]
    surfaces.extend(report.summary.key_discussion_points)
    surfaces.extend(report.summary.named_entities)
    for action_item in report.summary.action_items:
        surfaces.extend(
            value
            for value in (
                action_item.description,
                action_item.owner,
                action_item.deadline,
            )
            if value
        )
    for segment in report.redacted_transcript.segments:
        surfaces.append(segment.text)
    for dimension in report.qa_result.dimensions:
        surfaces.append(dimension.justification)
        surfaces.extend(evidence.excerpt for evidence in dimension.evidence)
    for flag in report.qa_result.compliance_flags:
        surfaces.extend([flag.title, flag.description])
        surfaces.extend(evidence.excerpt for evidence in flag.evidence)
    surfaces.extend(event.context_excerpt for event in report.privacy_events)
    surfaces.extend(
        value
        for value in (
            report.metadata.filename,
            report.metadata.caller_id,
            report.metadata.department,
        )
        if value
    )
    return surfaces


def summary_is_complete(report: CallReport) -> bool:
    summary = report.summary
    return bool(
        summary.call_purpose
        and summary.key_discussion_points
        and summary.customer_sentiment_trajectory
        and summary.resolution_status
    )


def summary_detail(report: CallReport) -> str:
    summary = report.summary
    return (
        f"purpose={bool(summary.call_purpose)}, "
        f"points={len(summary.key_discussion_points)}, "
        f"resolution={summary.resolution_status.value}"
    )


def privacy_events_have_redacted_context(report: CallReport) -> bool:
    return all(
        not contains_raw_sensitive_value(event.context_excerpt)
        for event in report.privacy_events
    )


def format_eval_summary(analysis_id: str, checks: list[EvalCheck]) -> str:
    """Format eval output for humans and CI logs."""
    passed_count = sum(1 for check in checks if check.passed)
    lines = [
        f"Analysis ID: {analysis_id}",
        f"Checks passed: {passed_count}/{len(checks)}",
    ]
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"- {status} {check.name}: {check.detail}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
