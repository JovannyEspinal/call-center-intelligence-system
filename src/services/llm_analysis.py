"""LLM-backed structured call analysis clients."""

from __future__ import annotations

import os
from typing import Protocol

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import (
    CallPhase,
    CallSummary,
    ComplianceFlag,
    ComplianceSeverity,
    QADimension,
    QADimensionScore,
    QAScoreResult,
    RedactedTranscript,
    ResolutionStatus,
    SentimentPoint,
    SpeakerRole,
    TranscriptEvidence,
)

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

SUMMARY_SYSTEM_MESSAGE = (
    "You produce factual, non-evaluative call summaries. "
    "Use only the redacted transcript. Do not invent facts."
)

QA_SYSTEM_MESSAGE = (
    "You produce evidence-backed QA scores for call center agent behavior. "
    "Use only redacted transcript evidence. Every score must include evidence "
    "that supports agent accountability."
)


class AnalysisLLMClient(Protocol):
    """Boundary for structured LLM analysis over redacted transcripts."""

    def generate_summary(self, transcript: RedactedTranscript) -> CallSummary:
        """Create a factual call summary from a redacted transcript."""

    def score_qa(
        self,
        transcript: RedactedTranscript,
        summary: CallSummary,
    ) -> QAScoreResult:
        """Create evidence-backed QA scores from a redacted transcript."""


class MockAnalysisClient:
    """Deterministic analysis client for tests and local graph development."""

    def __init__(self, *, force_critical_compliance: bool = False) -> None:
        self.force_critical_compliance = force_critical_compliance

    def generate_summary(self, transcript: RedactedTranscript) -> CallSummary:
        _ = transcript
        return CallSummary(
            call_purpose="Customer called about a billing issue.",
            key_discussion_points=[
                "Customer described a billing issue.",
                "Agent acknowledged the request.",
                "Agent offered to help resolve the issue.",
            ],
            resolution_status=ResolutionStatus.RESOLVED,
            customer_sentiment_trajectory="Concerned -> Reassured",
            sentiment_points=[
                SentimentPoint(
                    phase=CallPhase.OPENING,
                    score=2,
                    observation="Customer opened concerned about the billing issue.",
                ),
                SentimentPoint(
                    phase=CallPhase.MIDDLE,
                    score=3,
                    observation="Customer engaged while the agent investigated.",
                ),
                SentimentPoint(
                    phase=CallPhase.CLOSING,
                    score=4,
                    observation="Customer reassured after the agent offered help.",
                ),
            ],
        )

    def score_qa(
        self,
        transcript: RedactedTranscript,
        summary: CallSummary,
    ) -> QAScoreResult:
        _ = (transcript, summary)
        evidence = TranscriptEvidence(
            speaker_role=SpeakerRole.AGENT,
            start_seconds=0,
            end_seconds=4,
            excerpt="Hello, I can help with your billing issue.",
            supports_agent_accountability=True,
        )
        return QAScoreResult(
            dimensions=[
                QADimensionScore(
                    dimension=dimension,
                    score=4,
                    justification=(
                        f"{dimension.value} is supported by transcript evidence."
                    ),
                    evidence=[evidence],
                )
                for dimension in QADimension
            ],
            compliance_flags=(
                [
                    ComplianceFlag(
                        title="Critical compliance issue",
                        description="Mock critical compliance flag.",
                        severity=ComplianceSeverity.CRITICAL,
                        evidence=[evidence],
                    )
                ]
                if self.force_critical_compliance
                else []
            ),
        )


class OpenAIAnalysisClient:
    """OpenAI implementation of the structured analysis client."""

    def __init__(
        self,
        *,
        client: OpenAI | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        self.client = client or OpenAI(api_key=api_key)

    def generate_summary(self, transcript: RedactedTranscript) -> CallSummary:
        return self._parse(
            response_format=CallSummary,
            system_message=SUMMARY_SYSTEM_MESSAGE,
            user_message=build_summary_user_message(transcript),
        )

    def score_qa(
        self,
        transcript: RedactedTranscript,
        summary: CallSummary,
    ) -> QAScoreResult:
        return self._parse(
            response_format=QAScoreResult,
            system_message=QA_SYSTEM_MESSAGE,
            user_message=build_qa_user_message(transcript, summary),
        )

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.01, max=0.05),
    )
    def _parse(self, *, response_format, system_message: str, user_message: str):
        response = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            response_format=response_format,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("OpenAI response did not include parsed structured data")
        return parsed


def build_summary_user_message(transcript: RedactedTranscript) -> str:
    return (
        "Create a call summary with 3 to 7 key discussion points. "
        "Provide sentiment_points scoring customer sentiment from 1 (very "
        "negative) to 5 (very positive) for the opening, middle, and closing "
        "phases of the call, in that order, each with a short factual "
        "observation.\n\n"
        f"Redacted transcript:\n{transcript.model_dump_json()}"
    )


def build_qa_user_message(
    transcript: RedactedTranscript,
    summary: CallSummary,
) -> str:
    return (
        "Score the call on every QA dimension exactly once. "
        "The final weighted score is computed by the app, not by you.\n\n"
        f"Call summary:\n{summary.model_dump_json()}\n\n"
        f"Redacted transcript:\n{transcript.model_dump_json()}"
    )
