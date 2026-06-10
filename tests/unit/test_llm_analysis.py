from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.models import (
    ActionItem,
    CallSummary,
    ComplianceSeverity,
    QADimension,
    QADimensionScore,
    QAScoreResult,
    RedactedTranscript,
    ResolutionStatus,
    SpeakerRole,
    TranscriptEvidence,
    TranscriptSegment,
)
from src.services import MockAnalysisClient, OpenAIAnalysisClient
from src.services.llm_analysis import (
    DEFAULT_OPENAI_MODEL,
    QA_SYSTEM_MESSAGE,
    SUMMARY_SYSTEM_MESSAGE,
    build_qa_user_message,
    build_summary_user_message,
)


def redacted_transcript() -> RedactedTranscript:
    return RedactedTranscript(
        full_text="Agent: Hello, I can help. Customer: My phone is [REDACTED_PHONE].",
        segments=[
            TranscriptSegment(
                speaker_role=SpeakerRole.AGENT,
                start_seconds=0,
                end_seconds=2,
                text="Hello, I can help.",
                confidence=0.95,
            ),
            TranscriptSegment(
                speaker_role=SpeakerRole.CUSTOMER,
                start_seconds=2,
                end_seconds=5,
                text="My phone is [REDACTED_PHONE].",
                confidence=0.91,
            ),
        ],
    )


def evidence() -> TranscriptEvidence:
    return TranscriptEvidence(
        speaker_role=SpeakerRole.AGENT,
        start_seconds=0,
        end_seconds=2,
        excerpt="Hello, I can help.",
        supports_agent_accountability=True,
    )


def summary() -> CallSummary:
    return CallSummary(
        call_purpose="Customer called about a billing issue.",
        key_discussion_points=[
            "Billing mismatch",
            "Refund timeline",
            "Confirmation email",
        ],
        action_items=[
            ActionItem(description="Email refund confirmation", owner="agent")
        ],
        resolution_status=ResolutionStatus.RESOLVED,
        customer_sentiment_trajectory="Frustrated -> Reassured",
    )


def qa_result() -> QAScoreResult:
    return QAScoreResult(
        dimensions=[
            QADimensionScore(
                dimension=dimension,
                score=4,
                justification=f"{dimension.value} justification",
                evidence=[evidence()],
            )
            for dimension in QADimension
        ]
    )


def test_mock_analysis_client_returns_valid_summary_and_qa() -> None:
    client = MockAnalysisClient()

    generated_summary = client.generate_summary(redacted_transcript())
    result = client.score_qa(redacted_transcript(), generated_summary)

    assert generated_summary.resolution_status is ResolutionStatus.RESOLVED
    assert result.weighted_overall_score == 4.0
    assert result.compliance_flags == []


def test_mock_analysis_client_can_force_critical_compliance() -> None:
    client = MockAnalysisClient(force_critical_compliance=True)

    result = client.score_qa(redacted_transcript(), summary())

    assert result.compliance_flags[0].severity is ComplianceSeverity.CRITICAL


@dataclass
class ParsedMessage:
    parsed: object | None


@dataclass
class Choice:
    message: ParsedMessage


@dataclass
class ParsedResponse:
    choices: list[Choice]


class FakeCompletions:
    def __init__(self) -> None:
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        response_format = kwargs["response_format"]
        if response_format is CallSummary:
            parsed = summary()
        elif response_format is QAScoreResult:
            parsed = qa_result()
        else:
            raise AssertionError(f"unexpected response_format: {response_format}")
        return ParsedResponse(choices=[Choice(message=ParsedMessage(parsed=parsed))])


class FakeChat:
    def __init__(self) -> None:
        self.completions = FakeCompletions()


class FakeBeta:
    def __init__(self) -> None:
        self.chat = FakeChat()


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.beta = FakeBeta()


def test_openai_analysis_client_uses_structured_summary_response_format() -> None:
    fake_client = FakeOpenAIClient()
    client = OpenAIAnalysisClient(client=fake_client, model="test-model")

    generated = client.generate_summary(redacted_transcript())

    call = fake_client.beta.chat.completions.calls[0]
    assert generated == summary()
    assert call["model"] == "test-model"
    assert call["response_format"] is CallSummary
    assert call["messages"][0]["role"] == "system"
    assert call["messages"][0]["content"] == SUMMARY_SYSTEM_MESSAGE
    assert "redacted transcript" in call["messages"][1]["content"].lower()
    assert call["messages"][1]["content"] == build_summary_user_message(
        redacted_transcript()
    )


def test_openai_analysis_client_uses_structured_qa_response_format() -> None:
    fake_client = FakeOpenAIClient()
    client = OpenAIAnalysisClient(client=fake_client, model="test-model")

    result = client.score_qa(redacted_transcript(), summary())

    call = fake_client.beta.chat.completions.calls[0]
    assert result == qa_result()
    assert call["messages"][0]["content"] == QA_SYSTEM_MESSAGE
    assert call["response_format"] is QAScoreResult
    assert call["messages"][1]["content"] == build_qa_user_message(
        redacted_transcript(),
        summary(),
    )
    assert "weighted score is computed by the app" in call["messages"][1]["content"]


def test_openai_analysis_client_raises_when_parsed_response_missing() -> None:
    class MissingParsedCompletions:
        def __init__(self) -> None:
            self.calls = 0

        def parse(self, **kwargs):
            self.calls += 1
            return ParsedResponse(choices=[Choice(message=ParsedMessage(parsed=None))])

    fake_client = FakeOpenAIClient()
    completions = MissingParsedCompletions()
    fake_client.beta.chat.completions = completions
    client = OpenAIAnalysisClient(client=fake_client, model="test-model")

    with pytest.raises(ValueError, match="parsed structured data"):
        client.generate_summary(redacted_transcript())
    assert completions.calls == 3


def test_openai_analysis_client_default_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    client = OpenAIAnalysisClient(client=FakeOpenAIClient())

    assert client.model == DEFAULT_OPENAI_MODEL
    assert client.model == "gpt-4o-mini"
