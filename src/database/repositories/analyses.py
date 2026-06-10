"""Call analysis persistence."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.database.repositories.calls import CallRepository
from src.database.repositories.common import as_utc
from src.database.schema import CallAnalysisRow
from src.models import AnalysisConfiguration, AnalysisMetadata, Call, CallAnalysis


class CallAnalysisRepository:
    """Persist and query pipeline executions for calls."""

    def __init__(self, session: Session, calls: CallRepository) -> None:
        self.session = session
        self.calls = calls

    def save_analysis(self, analysis: CallAnalysis) -> CallAnalysis:
        self.calls.get_or_create_call(analysis.call.audio_hash)
        row = self.session.get(CallAnalysisRow, analysis.analysis_id)
        if row is None:
            row = CallAnalysisRow(
                analysis_id=analysis.analysis_id,
                audio_hash=analysis.call.audio_hash,
                status=analysis.status.value,
                configuration_json=analysis.configuration.model_dump_json(),
                metadata_json=analysis.metadata.model_dump_json(),
                status_reason=analysis.status_reason,
                created_at=analysis.created_at,
            )
            self.session.add(row)
        else:
            row.status = analysis.status.value
            row.configuration_json = analysis.configuration.model_dump_json()
            row.metadata_json = analysis.metadata.model_dump_json()
            row.status_reason = analysis.status_reason
            row.created_at = analysis.created_at
        self.session.flush()
        return analysis

    def get_analysis(self, analysis_id: str) -> CallAnalysis | None:
        row = self.session.get(CallAnalysisRow, analysis_id)
        if row is None:
            return None
        return self.analysis_from_row(row)

    def analysis_count_for_call(self, audio_hash: str) -> int:
        count = self.session.scalar(
            select(func.count())
            .select_from(CallAnalysisRow)
            .where(CallAnalysisRow.audio_hash == audio_hash)
        )
        return int(count or 0)

    def list_analyses_for_call(self, audio_hash: str) -> list[CallAnalysis]:
        rows = self.session.scalars(
            select(CallAnalysisRow)
            .where(CallAnalysisRow.audio_hash == audio_hash)
            .order_by(CallAnalysisRow.created_at.desc())
        ).all()
        return [self.analysis_from_row(row) for row in rows]

    @staticmethod
    def analysis_from_row(row: CallAnalysisRow) -> CallAnalysis:
        return CallAnalysis(
            analysis_id=row.analysis_id,
            call=Call(audio_hash=row.audio_hash),
            status=row.status,
            configuration=AnalysisConfiguration.model_validate_json(
                row.configuration_json
            ),
            metadata=AnalysisMetadata.model_validate_json(row.metadata_json),
            created_at=as_utc(row.created_at),
            status_reason=row.status_reason,
        )
