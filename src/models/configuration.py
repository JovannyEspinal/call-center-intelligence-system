"""Analysis configuration and metadata contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.enums import LLMProvider
from src.models.redaction import contains_raw_sensitive_value


class AnalysisConfiguration(BaseModel):
    """Captured conditions under which a call analysis was produced."""

    model_config = ConfigDict(frozen=True)

    llm_provider: LLMProvider = LLMProvider.MOCK
    llm_model: str = "mock"
    transcription_model: str = "mock"
    summary_prompt_version: str = "v2"
    qa_prompt_version: str = "v1"
    rubric_version: str = "v1"
    pii_redaction_version: str = "v1"
    injection_detector_version: str = "v1"
    scoring_formula_version: str = "v1"
    app_version: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnalysisMetadata(BaseModel):
    """Optional user-provided context associated with a call analysis."""

    model_config = ConfigDict(frozen=True)

    filename: str | None = None
    caller_id: str | None = None
    department: str | None = None

    @model_validator(mode="after")
    def validate_metadata(self) -> AnalysisMetadata:
        for value in (self.filename, self.caller_id, self.department):
            if value and contains_raw_sensitive_value(value):
                raise ValueError("analysis metadata must be redacted before storage")
        return self
