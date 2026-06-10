"""Call report contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.configuration import AnalysisConfiguration, AnalysisMetadata
from src.models.enums import AnalysisStatus, ComplianceSeverity
from src.models.evidence import RedactedTranscript, SecurityEvidence
from src.models.privacy import PrivacyEvent
from src.models.scoring import QAScoreResult
from src.models.summary import CallSummary


class Call(BaseModel):
    """Source audio identity for the system."""

    model_config = ConfigDict(frozen=True)

    audio_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class CallAnalysis(BaseModel):
    """Pipeline run and resulting state for a call."""

    model_config = ConfigDict(frozen=True)

    analysis_id: str = Field(min_length=1)
    call: Call
    status: AnalysisStatus
    configuration: AnalysisConfiguration
    metadata: AnalysisMetadata = Field(default_factory=AnalysisMetadata)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status_reason: str | None = None


class CallReport(BaseModel):
    """Assembled artifact generated from a successful call analysis."""

    model_config = ConfigDict(frozen=True)

    analysis_id: str = Field(min_length=1)
    status: AnalysisStatus
    configuration: AnalysisConfiguration
    metadata: AnalysisMetadata = Field(default_factory=AnalysisMetadata)
    redacted_transcript: RedactedTranscript
    summary: CallSummary
    qa_result: QAScoreResult
    privacy_events: list[PrivacyEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_report_status(self) -> CallReport:
        if self.status not in {
            AnalysisStatus.COMPLETED,
            AnalysisStatus.SUPERVISOR_REVIEW,
        }:
            raise ValueError("call reports only exist for successful analyses")
        has_critical_flag = any(
            flag.severity is ComplianceSeverity.CRITICAL
            for flag in self.qa_result.compliance_flags
        )
        if has_critical_flag and self.status is not AnalysisStatus.SUPERVISOR_REVIEW:
            raise ValueError("critical compliance flags require supervisor review")
        return self


class BlockedAnalysisRecord(BaseModel):
    """Record of a call analysis that stopped for safety."""

    model_config = ConfigDict(frozen=True)

    analysis_id: str = Field(min_length=1)
    status: AnalysisStatus = AnalysisStatus.BLOCKED
    configuration: AnalysisConfiguration
    security_evidence: list[SecurityEvidence] = Field(min_length=1)
    privacy_events: list[PrivacyEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_blocked_status(self) -> BlockedAnalysisRecord:
        if self.status is not AnalysisStatus.BLOCKED:
            raise ValueError("blocked analysis records must have blocked status")
        return self
