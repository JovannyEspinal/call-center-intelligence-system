"""Call summary contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from src.models.enums import CallPhase, ResolutionStatus, SentimentTrend


class ActionItem(BaseModel):
    """Concrete follow-up commitment from a call."""

    model_config = ConfigDict(frozen=True)

    description: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    deadline: str | None = None


class SentimentPoint(BaseModel):
    """Scored customer sentiment observation for one phase of a call."""

    model_config = ConfigDict(frozen=True)

    phase: CallPhase
    score: int = Field(ge=1, le=5)
    observation: str = Field(min_length=1)


class CallSummary(BaseModel):
    """Factual, non-evaluative description of a call."""

    model_config = ConfigDict(frozen=True)

    call_purpose: str = Field(min_length=1)
    key_discussion_points: list[str] = Field(min_length=3, max_length=7)
    action_items: list[ActionItem] = Field(default_factory=list)
    resolution_status: ResolutionStatus
    customer_sentiment_trajectory: str = Field(min_length=1)
    sentiment_points: list[SentimentPoint] = Field(default_factory=list)
    named_entities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_sentiment_points(self) -> CallSummary:
        if not self.sentiment_points:
            return self
        phases = [item.phase for item in self.sentiment_points]
        if sorted(phases, key=list(CallPhase).index) != list(CallPhase):
            raise ValueError(
                "sentiment points require exactly one sentiment point per call phase"
            )
        if phases != list(CallPhase):
            raise ValueError("sentiment points must appear in call order")
        return self

    @computed_field
    @property
    def sentiment_trend(self) -> SentimentTrend:
        """Deterministic trajectory direction from opening vs closing scores."""
        if not self.sentiment_points:
            return SentimentTrend.UNKNOWN
        delta = self.sentiment_points[-1].score - self.sentiment_points[0].score
        if delta >= 1:
            return SentimentTrend.IMPROVING
        if delta <= -1:
            return SentimentTrend.DECLINING
        return SentimentTrend.STABLE


def describe_sentiment_trajectory(summary: CallSummary) -> str:
    """Render the customer sentiment trajectory, preferring scored points."""
    if not summary.sentiment_points:
        return summary.customer_sentiment_trajectory
    points = " -> ".join(
        f"{point.phase.value} {point.score}/5" for point in summary.sentiment_points
    )
    return f"{points} ({summary.sentiment_trend.value})"
