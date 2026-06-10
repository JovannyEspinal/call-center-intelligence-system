"""Call identity persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.database.schema import CallRow
from src.models import Call


class CallRepository:
    """Persist and retrieve source call identities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_call(self, audio_hash: str) -> Call:
        row = self.session.get(CallRow, audio_hash)
        if row is None:
            row = CallRow(audio_hash=audio_hash, created_at=datetime.now(UTC))
            self.session.add(row)
            self.session.flush()
        return Call(audio_hash=row.audio_hash)
