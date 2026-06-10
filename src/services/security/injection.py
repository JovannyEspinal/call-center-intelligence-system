"""Local prompt injection detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from src.models.injection import InjectionMatch, PromptInjectionResult


class PromptInjectionDetector(Protocol):
    """Contract implemented by prompt injection detectors."""

    def scan_text(self, text: str) -> PromptInjectionResult:
        """Scan text for injection attempts."""


@dataclass(frozen=True)
class _InjectionPattern:
    name: str
    pattern: re.Pattern[str]


def _compile_pattern(pattern: str, flags: int = 0) -> re.Pattern[str]:
    return re.compile(pattern, flags | re.IGNORECASE)


class RegexPromptInjectionDetector:
    """Deterministic prompt injection detector for transcript and metadata text."""

    _patterns: tuple[_InjectionPattern, ...] = (
        _InjectionPattern(
            "ignore_previous_instructions",
            _compile_pattern(
                r"\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions?\b"
            ),
        ),
        _InjectionPattern(
            "disregard_previous_instructions",
            _compile_pattern(
                r"\bdisregard\s+(?:all\s+)?(?:previous|prior)\s+instructions?\b"
            ),
        ),
        _InjectionPattern(
            "forget_previous_context",
            _compile_pattern(
                r"\bforget\s+(?:everything|all)\s+(?:above|before|previous)\b"
            ),
        ),
        _InjectionPattern(
            "system_prompt_leak",
            _compile_pattern(
                r"\b(?:reveal|print|show|display|output)\s+(?:your\s+)?"
                r"(?:system\s+)?prompt\b"
            ),
        ),
        _InjectionPattern(
            "system_prompt_question",
            _compile_pattern(r"\bwhat(?:\s+is|'s)\s+your\s+system\s+prompt\b"),
        ),
        _InjectionPattern(
            "system_prompt_injection",
            _compile_pattern(r"\bsystem\s+prompt\s*[:=]"),
        ),
        _InjectionPattern(
            "system_override",
            _compile_pattern(r"\bsystem\s*:\s*override\b"),
        ),
        _InjectionPattern(
            "developer_message_leak",
            _compile_pattern(
                r"\b(?:reveal|show|print|display)\s+(?:the\s+)?developer\s+message\b"
            ),
        ),
        _InjectionPattern(
            "secret_leak_request",
            _compile_pattern(
                r"\b(?:reveal|print|show|display|output)\s+(?:all\s+)?"
                r"(?:secrets|secret|keys|api\s+keys|tokens|instructions|data)\b"
            ),
        ),
        _InjectionPattern(
            "role_switch",
            _compile_pattern(r"\byou\s+are\s+(?:now|no\s+longer)\b"),
        ),
        _InjectionPattern(
            "act_as_role",
            _compile_pattern(r"\bact\s+as\s+(?:a|an|my)?\s*.+"),
        ),
        _InjectionPattern(
            "new_instructions",
            _compile_pattern(r"\bnew\s+instructions?\s*[:=]"),
        ),
        _InjectionPattern(
            "instruction_override",
            _compile_pattern(
                r"\boverride\s+(?:all\s+)?(?:instructions|rules|safety)\b"
            ),
        ),
        _InjectionPattern(
            "dan_mode",
            _compile_pattern(
                r"\b(?:dan|do\s+anything\s+now)\s+(?:mode\s+)?(?:enabled|activated)\b"
            ),
        ),
        _InjectionPattern(
            "jailbreak",
            _compile_pattern(r"\bjail\s*break\b|\bjailbreak\b"),
        ),
        _InjectionPattern(
            "ignore_safety_guidelines",
            _compile_pattern(r"\bignore\s+(?:all\s+)?safety\s+guidelines?\b"),
        ),
        _InjectionPattern(
            "ignore_transcript",
            _compile_pattern(r"\bignore\s+(?:the\s+)?(?:call\s+)?transcript\b"),
        ),
        _InjectionPattern(
            "conversation_injection",
            _compile_pattern(r"(?:^|\n)\s*human\s*:.+\n\s*assistant\s*:", re.DOTALL),
        ),
        _InjectionPattern(
            "llama_system_tag",
            _compile_pattern(r"<<\s*sys\s*>>|<<\s*/\s*sys\s*>>"),
        ),
        _InjectionPattern(
            "llama_inst_tag",
            _compile_pattern(r"\[/?inst\]"),
        ),
        _InjectionPattern(
            "xml_system_tag",
            _compile_pattern(r"<\s*/?\s*system\s*>"),
        ),
        _InjectionPattern(
            "translate_attack",
            _compile_pattern(
                r"\btranslate\s+(?:the\s+)?(?:above|previous)\s+instructions?\b"
            ),
        ),
        _InjectionPattern(
            "base64_decode_attack",
            _compile_pattern(r"\b(?:base64\s+)?decode\s+(?:this|the\s+following)\b"),
        ),
        _InjectionPattern(
            "prompt_boundary_attack",
            _compile_pattern(
                r"\b(?:end|close)\s+(?:of\s+)?(?:system|developer)\s+(?:prompt|message)\b"
            ),
        ),
    )

    def scan_text(self, text: str) -> PromptInjectionResult:
        """Return every named injection pattern found in text."""
        matches: list[InjectionMatch] = []
        for injection_pattern in self._patterns:
            for match in injection_pattern.pattern.finditer(text):
                matches.append(
                    InjectionMatch(
                        pattern_name=injection_pattern.name,
                        start=match.start(),
                        end=match.end(),
                        excerpt=self._excerpt(text, match.start(), match.end()),
                    )
                )

        matches.sort(key=lambda item: item.start)
        return PromptInjectionResult(
            injection_detected=bool(matches),
            matches=matches,
        )

    @staticmethod
    def _excerpt(text: str, start: int, end: int) -> str:
        context_start = max(0, start - 40)
        context_end = min(len(text), end + 40)
        return text[context_start:context_end].strip()
