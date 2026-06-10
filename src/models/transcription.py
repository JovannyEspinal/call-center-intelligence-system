"""Transcription stage and cache contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.enums import SpeakerRole
from src.models.evidence import RedactedTranscript
from src.models.privacy import PrivacyEvent
from src.models.time_ranges import validate_timestamp_range

TRANSCRIPTION_CACHE_VERSION = "redaction-v5-speaker-v3"


class RawTranscriptSegment(BaseModel):
    """One unredacted transcript segment returned by a transcription adapter."""

    model_config = ConfigDict(frozen=True)

    speaker_role: SpeakerRole = SpeakerRole.UNKNOWN
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_segment(self) -> RawTranscriptSegment:
        validate_timestamp_range(self.start_seconds, self.end_seconds, required=True)
        return self


class TranscriptionResult(BaseModel):
    """Raw transcription output before security scanning and PII redaction."""

    model_config = ConfigDict(frozen=True)

    full_text: str = Field(min_length=1)
    segments: list[RawTranscriptSegment] = Field(min_length=1)
    model_name: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_full_text_matches_segments(self) -> TranscriptionResult:
        segment_text = " ".join(segment.text for segment in self.segments).strip()
        if self.full_text.strip() != segment_text:
            raise ValueError("full_text must match joined transcript segment text")
        return self


class TranscriptionCacheEntry(BaseModel):
    """Reusable redacted transcript result for a call audio hash."""

    model_config = ConfigDict(frozen=True)

    audio_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    redacted_transcript: RedactedTranscript
    privacy_events: list[PrivacyEvent] = Field(default_factory=list)
    cache_version: str = TRANSCRIPTION_CACHE_VERSION
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
