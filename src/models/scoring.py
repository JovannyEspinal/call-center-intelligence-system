"""QA scoring and compliance contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from src.models.enums import (
    QA_DIMENSION_WEIGHTS,
    ComplianceSeverity,
    QADimension,
)
from src.models.evidence import TranscriptEvidence


class ComplianceFlag(BaseModel):
    """Specific policy or regulatory concern with supporting evidence."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: ComplianceSeverity
    evidence: list[TranscriptEvidence] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_compliance_evidence(self) -> ComplianceFlag:
        for item in self.evidence:
            if not item.supports_agent_accountability:
                raise ValueError(
                    "compliance flag evidence must support agent accountability"
                )
        return self


class QADimensionScore(BaseModel):
    """Evidence-backed score for one QA dimension."""

    model_config = ConfigDict(frozen=True)

    dimension: QADimension
    score: int = Field(ge=1, le=5)
    justification: str = Field(min_length=1)
    evidence: list[TranscriptEvidence] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_qa_evidence(self) -> QADimensionScore:
        for item in self.evidence:
            if not item.supports_agent_accountability:
                raise ValueError(
                    "qa dimension evidence must support agent accountability"
                )
        return self


class QAScoreResult(BaseModel):
    """Complete deterministic QA score result."""

    model_config = ConfigDict(frozen=True)

    dimensions: list[QADimensionScore]
    compliance_flags: list[ComplianceFlag] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dimensions(self) -> QAScoreResult:
        seen = [score.dimension for score in self.dimensions]
        expected = set(QADimension)
        if set(seen) != expected:
            missing = sorted(dimension.value for dimension in expected - set(seen))
            extra = sorted(dimension.value for dimension in set(seen) - expected)
            raise ValueError(
                "qa result must include exactly one score for each dimension; "
                f"missing={missing}, extra={extra}"
            )
        if len(seen) != len(set(seen)):
            raise ValueError("qa result cannot include duplicate dimensions")
        return self

    @computed_field
    @property
    def weighted_overall_score(self) -> float:
        """Deterministic weighted score rounded to two decimal places."""
        by_dimension = {score.dimension: score.score for score in self.dimensions}
        weighted_score = sum(
            by_dimension[dimension] * weight
            for dimension, weight in QA_DIMENSION_WEIGHTS.items()
        )
        return round(weighted_score, 2)
