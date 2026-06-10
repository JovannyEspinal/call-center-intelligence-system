"""Audit event contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeAlias
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.enums import AuditAction
from src.models.redaction import contains_raw_sensitive_value

AuditDetailValue: TypeAlias = str | int | float | bool


class AuditEvent(BaseModel):
    """Immutable business-significant event during a call analysis."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    analysis_id: str = Field(min_length=1)
    action: AuditAction
    details: dict[str, AuditDetailValue] = Field(default_factory=dict)
    reviewer_id: str | None = None
    session_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_no_raw_sensitive_values(self) -> AuditEvent:
        values_to_check = [
            str(value) for value in [self.reviewer_id, self.session_id] if value
        ]
        values_to_check.extend(
            str(value) for value in self.details.values() if isinstance(value, str)
        )
        if any(contains_raw_sensitive_value(value) for value in values_to_check):
            raise ValueError("audit events must not contain raw sensitive values")
        return self
