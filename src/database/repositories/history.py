"""Analysis history queries."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.repositories.analyses import CallAnalysisRepository
from src.database.repositories.common import CallHistoryEntry
from src.database.schema import CallRow
from src.models import Call


class AnalysisHistoryRepository:
    """Query analysis history grouped by call."""

    def __init__(self, session: Session, analyses: CallAnalysisRepository) -> None:
        self.session = session
        self.analyses = analyses

    def list_analysis_history(self) -> list[CallHistoryEntry]:
        call_rows = self.session.scalars(
            select(CallRow).order_by(CallRow.created_at.desc())
        ).all()
        return [
            CallHistoryEntry(
                call=Call(audio_hash=row.audio_hash),
                analyses=self.analyses.list_analyses_for_call(row.audio_hash),
            )
            for row in call_rows
        ]
