"""Audit event persistence."""

from __future__ import annotations

import json

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from src.database.repositories.common import as_utc
from src.database.schema import AuditEventRow
from src.models import AuditEvent


class AuditEventRepository:
    """Append and query immutable audit events."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        existing = self.session.get(AuditEventRow, event.event_id)
        if existing is not None:
            raise ValueError("audit event already exists")

        self.session.add(
            AuditEventRow(
                event_id=event.event_id,
                analysis_id=event.analysis_id,
                action=event.action.value,
                details_json=json.dumps(event.details),
                reviewer_id=event.reviewer_id,
                session_id=event.session_id,
                created_at=event.created_at,
            )
        )
        self.session.flush()
        return event

    def recent_audit_events(
        self,
        *,
        limit: int = 20,
        analysis_id: str | None = None,
    ) -> list[AuditEvent]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")

        statement: Select[tuple[AuditEventRow]] = select(AuditEventRow)
        if analysis_id is not None:
            statement = statement.where(AuditEventRow.analysis_id == analysis_id)
        rows = self.session.scalars(
            statement.order_by(AuditEventRow.created_at.desc()).limit(limit)
        ).all()
        return [self._audit_event_from_row(row) for row in rows]

    def audit_event_count(self, *, analysis_id: str | None = None) -> int:
        statement = select(func.count()).select_from(AuditEventRow)
        if analysis_id is not None:
            statement = statement.where(AuditEventRow.analysis_id == analysis_id)
        return int(self.session.scalar(statement) or 0)

    @staticmethod
    def _audit_event_from_row(row: AuditEventRow) -> AuditEvent:
        return AuditEvent(
            event_id=row.event_id,
            analysis_id=row.analysis_id,
            action=row.action,
            details=json.loads(row.details_json),
            reviewer_id=row.reviewer_id,
            session_id=row.session_id,
            created_at=as_utc(row.created_at),
        )
