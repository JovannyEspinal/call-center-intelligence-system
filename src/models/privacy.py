"""Privacy event contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.enums import PrivacyDataType, SpeakerRole
from src.models.redaction import contains_raw_sensitive_value
from src.models.time_ranges import validate_timestamp_range


class PrivacyEvent(BaseModel):
    """Sensitive information occurrence that required redaction."""

    model_config = ConfigDict(frozen=True)

    data_type: PrivacyDataType
    placeholder: str = Field(pattern=r"^\[REDACTED_[A-Z_]+\]$")
    context_excerpt: str = Field(min_length=1)
    speaker_role: SpeakerRole | None = None
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_privacy_event(self) -> PrivacyEvent:
        validate_timestamp_range(self.start_seconds, self.end_seconds, required=False)
        if contains_raw_sensitive_value(self.context_excerpt):
            raise ValueError("privacy event context must be redacted")
        return self
