"""Prompt injection detection contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InjectionMatch(BaseModel):
    """A named prompt injection pattern match."""

    model_config = ConfigDict(frozen=True)

    pattern_name: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    excerpt: str = Field(min_length=1)


class PromptInjectionResult(BaseModel):
    """Result of scanning text for prompt injection attempts."""

    model_config = ConfigDict(frozen=True)

    injection_detected: bool
    matches: list[InjectionMatch] = Field(default_factory=list)

    @property
    def matched_pattern_names(self) -> list[str]:
        """Pattern names in first-match order without duplicates."""
        names: list[str] = []
        for match in self.matches:
            if match.pattern_name not in names:
                names.append(match.pattern_name)
        return names
