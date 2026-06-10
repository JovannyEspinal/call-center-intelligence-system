"""Audio intake contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.models.configuration import AnalysisMetadata
from src.models.enums import AudioFormat
from src.models.injection import PromptInjectionResult
from src.models.privacy import PrivacyEvent


class RawAnalysisMetadata(BaseModel):
    """Untrusted user-provided metadata before intake sanitization.

    The uploaded filename lives on AudioInput so there is one source of truth.
    """

    model_config = ConfigDict(frozen=True)

    caller_id: str | None = None
    department: str | None = None


class AudioInput(BaseModel):
    """Raw audio payload submitted for analysis."""

    model_config = ConfigDict(frozen=True)

    audio_bytes: bytes = Field(min_length=1)
    filename: str = Field(min_length=1)
    metadata: RawAnalysisMetadata = Field(default_factory=RawAnalysisMetadata)


class AudioProperties(BaseModel):
    """Validated audio container properties."""

    model_config = ConfigDict(frozen=True)

    duration_seconds: float | None = Field(default=None, gt=0)
    sample_rate_hz: int | None = Field(default=None, gt=0)
    channels: int | None = Field(default=None, gt=0)


class IntakeResult(BaseModel):
    """Validated audio and sanitized metadata for downstream processing."""

    model_config = ConfigDict(frozen=True)

    audio_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    detected_format: AudioFormat
    file_size_bytes: int = Field(gt=0)
    properties: AudioProperties
    temp_audio_path: str
    metadata: AnalysisMetadata
    privacy_events: list[PrivacyEvent] = Field(default_factory=list)
    metadata_injection_result: PromptInjectionResult
