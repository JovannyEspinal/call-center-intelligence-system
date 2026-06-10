"""Call report persistence."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.database.schema import CallAnalysisRow, CallReportRow
from src.models import CallReport


class CallReportRepository:
    """Persist and retrieve redacted call reports."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save_report(self, report: CallReport) -> CallReport:
        analysis_row = self.session.get(CallAnalysisRow, report.analysis_id)
        if analysis_row is None:
            raise ValueError("cannot save report before its call analysis")

        row = self.session.get(CallReportRow, report.analysis_id)
        if row is None:
            row = CallReportRow(
                analysis_id=report.analysis_id,
                status=report.status.value,
                weighted_score=report.qa_result.weighted_overall_score,
                report_json=report.model_dump_json(),
                created_at=report.created_at,
            )
            self.session.add(row)
        else:
            row.status = report.status.value
            row.weighted_score = report.qa_result.weighted_overall_score
            row.report_json = report.model_dump_json()
            row.created_at = report.created_at
        self.session.flush()
        return report

    def get_report(self, analysis_id: str) -> CallReport | None:
        row = self.session.get(CallReportRow, analysis_id)
        if row is None:
            return None
        return CallReport.model_validate_json(row.report_json)
