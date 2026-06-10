"""Transcription cache persistence."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.database.repositories.calls import CallRepository
from src.database.repositories.common import as_utc
from src.database.schema import TranscriptionCacheRow
from src.models import (
    TRANSCRIPTION_CACHE_VERSION,
    PrivacyEvent,
    RedactedTranscript,
    TranscriptionCacheEntry,
)


class TranscriptionCacheRepository:
    """Persist reusable redacted transcripts keyed by audio hash."""

    def __init__(self, session: Session, calls: CallRepository) -> None:
        self.session = session
        self.calls = calls

    def save_transcription_cache_entry(
        self,
        entry: TranscriptionCacheEntry,
    ) -> TranscriptionCacheEntry:
        self.calls.get_or_create_call(entry.audio_hash)
        row = self.session.get(TranscriptionCacheRow, entry.audio_hash)
        if row is None:
            row = TranscriptionCacheRow(
                audio_hash=entry.audio_hash,
                redacted_transcript_json=entry.redacted_transcript.model_dump_json(),
                privacy_events_json=_privacy_events_json(entry.privacy_events),
                cache_version=entry.cache_version,
                created_at=entry.created_at,
            )
            self.session.add(row)
        else:
            row.redacted_transcript_json = entry.redacted_transcript.model_dump_json()
            row.privacy_events_json = _privacy_events_json(entry.privacy_events)
            row.cache_version = entry.cache_version
            row.created_at = entry.created_at
        self.session.flush()
        return entry

    def get_transcription_cache_entry(
        self,
        audio_hash: str,
        *,
        expected_cache_version: str = TRANSCRIPTION_CACHE_VERSION,
    ) -> TranscriptionCacheEntry | None:
        row = self.session.get(TranscriptionCacheRow, audio_hash)
        if row is None:
            return None
        if row.cache_version != expected_cache_version:
            return None
        return TranscriptionCacheEntry(
            audio_hash=row.audio_hash,
            redacted_transcript=RedactedTranscript.model_validate_json(
                row.redacted_transcript_json
            ),
            privacy_events=[
                PrivacyEvent.model_validate(item)
                for item in _load_privacy_events_json(row.privacy_events_json)
            ],
            cache_version=row.cache_version,
            created_at=as_utc(row.created_at),
        )


def _privacy_events_json(privacy_events: list[PrivacyEvent]) -> str:
    return "[" + ",".join(event.model_dump_json() for event in privacy_events) + "]"


def _load_privacy_events_json(value: str) -> list[dict]:
    import json

    return json.loads(value or "[]")
