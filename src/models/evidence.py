"""Evidence and redacted transcript contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.enums import SpeakerRole
from src.models.redaction import contains_raw_sensitive_value
from src.models.time_ranges import validate_timestamp_range


class TranscriptEvidence(BaseModel):
    """Redacted transcript excerpt supporting an analysis claim."""

    model_config = ConfigDict(frozen=True)

    speaker_role: SpeakerRole
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    excerpt: str = Field(min_length=1)
    supports_agent_accountability: bool = False

    @model_validator(mode="after")
    def validate_evidence(self) -> TranscriptEvidence:
        validate_timestamp_range(self.start_seconds, self.end_seconds, required=True)
        if contains_raw_sensitive_value(self.excerpt):
            raise ValueError("transcript evidence must be redacted")
        if (
            self.supports_agent_accountability
            and self.speaker_role is SpeakerRole.UNKNOWN
        ):
            raise ValueError(
                "unknown speaker evidence cannot support agent accountability"
            )
        return self


class SecurityEvidence(BaseModel):
    """Redacted excerpt explaining why a call analysis was blocked."""

    model_config = ConfigDict(frozen=True)

    matched_pattern: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    speaker_role: SpeakerRole | None = None
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_security_evidence(self) -> SecurityEvidence:
        validate_timestamp_range(self.start_seconds, self.end_seconds, required=False)
        if contains_raw_sensitive_value(self.excerpt):
            raise ValueError("security evidence must be redacted")
        return self


class TranscriptSegment(BaseModel):
    """One redacted transcript segment."""

    model_config = ConfigDict(frozen=True)

    speaker_role: SpeakerRole
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_segment(self) -> TranscriptSegment:
        validate_timestamp_range(self.start_seconds, self.end_seconds, required=True)
        if contains_raw_sensitive_value(self.text):
            raise ValueError("transcript segment must be redacted")
        return self


class RedactedTranscript(BaseModel):
    """Privacy-safe transcript used for analysis, display, reports, and history."""

    model_config = ConfigDict(frozen=True)

    full_text: str = Field(min_length=1)
    segments: list[TranscriptSegment] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_redacted_transcript(self) -> RedactedTranscript:
        if contains_raw_sensitive_value(self.full_text):
            raise ValueError("redacted transcript cannot contain raw sensitive values")
        return self
