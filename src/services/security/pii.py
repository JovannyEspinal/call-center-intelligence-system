"""PII redaction services."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.models import PrivacyDataType, PrivacyEvent, SpeakerRole


class PIIRedactionResult(BaseModel):
    """Result of redacting sensitive values from text."""

    model_config = ConfigDict(frozen=True)

    redacted_text: str
    privacy_events: list[PrivacyEvent] = Field(default_factory=list)


class PIIRedactor(Protocol):
    """Contract implemented by PII redaction engines."""

    def redact_text(
        self,
        text: str,
        *,
        speaker_role: SpeakerRole | None = None,
        start_seconds: float | None = None,
        end_seconds: float | None = None,
    ) -> PIIRedactionResult:
        """Redact sensitive values from a text string."""


@dataclass(frozen=True)
class _PIIPattern:
    data_type: PrivacyDataType
    placeholder: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class _PIIMatch:
    data_type: PrivacyDataType
    placeholder: str
    start: int
    end: int


class RegexPIIRedactor:
    """Deterministic regex redactor for common call-center PII formats."""

    _patterns: tuple[_PIIPattern, ...] = (
        _PIIPattern(
            PrivacyDataType.SSN,
            "[REDACTED_SSN]",
            re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        ),
        _PIIPattern(
            PrivacyDataType.CREDIT_CARD,
            "[REDACTED_CREDIT_CARD]",
            re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
        ),
        _PIIPattern(
            PrivacyDataType.EMAIL,
            "[REDACTED_EMAIL]",
            re.compile(
                r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
                re.IGNORECASE,
            ),
        ),
        _PIIPattern(
            PrivacyDataType.EMAIL,
            "[REDACTED_EMAIL]",
            re.compile(
                r"\b[A-Z0-9._%+-]+\s+(?:at|\[at\]|\(at\))\s+"
                r"[A-Z0-9.-]+\.[A-Z]{2,}\b",
                re.IGNORECASE,
            ),
        ),
        _PIIPattern(
            PrivacyDataType.PHONE,
            "[REDACTED_PHONE]",
            re.compile(r"\b(?:\+?1[ -.]?)?(?:\(?\d{3}\)?[ -.])\d{3}[ -.]\d{4}\b"),
        ),
        _PIIPattern(
            PrivacyDataType.DATE_OF_BIRTH,
            "[REDACTED_DOB]",
            re.compile(
                r"\b(?:january|february|march|april|may|june|july|august|"
                r"september|october|november|december)\s+\d{1,2},\s+\d{4}\b",
                re.IGNORECASE,
            ),
        ),
        _PIIPattern(
            PrivacyDataType.ADDRESS,
            "[REDACTED_ADDRESS]",
            re.compile(
                r"\b\d{2,6},?\s+(?:[A-Z0-9]+\s+){0,3}"
                r"(?:street|st\.?|avenue|ave\.?|road|rd\.?|drive|dr\.?|"
                r"lane|ln\.?|boulevard|blvd\.?)\b"
                r"(?:,?\s+(?:apartment|apt\.?|unit|suite)\s+[A-Z0-9]+)?"
                r"(?:,?\s+[A-Z][a-z]+){0,4}"
                r"(?:,?\s+\d{4,5})?",
                re.IGNORECASE,
            ),
        ),
        _PIIPattern(
            PrivacyDataType.ACCOUNT_NUMBER,
            "[REDACTED_ACCOUNT_NUMBER]",
            re.compile(
                r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine)"
                r"(?:[, -]+(?:zero|one|two|three|four|five|six|seven|eight|nine))"
                r"{4,}\b",
                re.IGNORECASE,
            ),
        ),
        _PIIPattern(
            PrivacyDataType.ACCOUNT_NUMBER,
            "[REDACTED_ACCOUNT_NUMBER]",
            re.compile(
                r"\b(?:account number|card number).{0,100}?"
                r"\b(?:\d[,\s-]*){10}\b",
                re.IGNORECASE,
            ),
        ),
        _PIIPattern(
            PrivacyDataType.PHONE,
            "[REDACTED_PHONE]",
            re.compile(r"\b\d{10}\b"),
        ),
        _PIIPattern(
            PrivacyDataType.SECURITY_NUMBER,
            "[REDACTED_SECURITY_NUMBER]",
            re.compile(r"(?<![$\w])\d{4,10}\b"),
        ),
        _PIIPattern(
            PrivacyDataType.VERIFICATION_CODE,
            "[REDACTED_VERIFICATION_CODE]",
            re.compile(
                r"\b(?:code|reference number)\s+(?:is\s+)?"
                r"(?:[A-Z]\s+for\s+[A-Z]+,\s*)?"
                r"[A-Z0-9][A-Z0-9, -]{3,}\b",
                re.IGNORECASE,
            ),
        ),
    )

    def redact_text(
        self,
        text: str,
        *,
        speaker_role: SpeakerRole | None = None,
        start_seconds: float | None = None,
        end_seconds: float | None = None,
    ) -> PIIRedactionResult:
        """Redact sensitive values after collecting every match first."""
        matches = self._collect_matches(text)
        redacted_text = self._replace_right_to_left(text, matches)
        privacy_events = [
            PrivacyEvent(
                data_type=match.data_type,
                placeholder=match.placeholder,
                context_excerpt=self._redacted_context(redacted_text, match, matches),
                speaker_role=speaker_role,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
            )
            for match in matches
        ]
        return PIIRedactionResult(
            redacted_text=redacted_text,
            privacy_events=privacy_events,
        )

    def _collect_matches(self, text: str) -> list[_PIIMatch]:
        matches: list[_PIIMatch] = []
        occupied_ranges: list[range] = []
        for pii_pattern in self._patterns:
            for match in pii_pattern.pattern.finditer(text):
                match_range = range(match.start(), match.end())
                if self._overlaps_existing_range(match_range, occupied_ranges):
                    continue
                matches.append(
                    _PIIMatch(
                        data_type=pii_pattern.data_type,
                        placeholder=pii_pattern.placeholder,
                        start=match.start(),
                        end=match.end(),
                    )
                )
                occupied_ranges.append(match_range)
        return sorted(matches, key=lambda item: item.start)

    @staticmethod
    def _replace_right_to_left(text: str, matches: list[_PIIMatch]) -> str:
        redacted_text = text
        for match in sorted(matches, key=lambda item: item.start, reverse=True):
            redacted_text = (
                redacted_text[: match.start]
                + match.placeholder
                + redacted_text[match.end :]
            )
        return redacted_text

    def _redacted_context(
        self,
        redacted_text: str,
        match: _PIIMatch,
        matches: list[_PIIMatch],
    ) -> str:
        placeholder_index = self._redacted_match_start(match, matches)
        if placeholder_index < 0:
            return match.placeholder

        context_start = max(0, placeholder_index - 40)
        context_end = min(
            len(redacted_text),
            placeholder_index + len(match.placeholder) + 40,
        )
        return redacted_text[context_start:context_end].strip()

    @staticmethod
    def _redacted_match_start(match: _PIIMatch, matches: list[_PIIMatch]) -> int:
        offset = sum(
            len(previous.placeholder) - (previous.end - previous.start)
            for previous in matches
            if previous.start < match.start
        )
        return match.start + offset

    @staticmethod
    def _overlaps_existing_range(
        candidate: range,
        occupied_ranges: list[range],
    ) -> bool:
        candidate_start = candidate.start
        candidate_end = candidate.stop
        return any(
            candidate_start < occupied.stop and candidate_end > occupied.start
            for occupied in occupied_ranges
        )
