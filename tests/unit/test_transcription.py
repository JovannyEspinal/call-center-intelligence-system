from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.models import RawTranscriptSegment, SpeakerRole, TranscriptionResult
from src.services import (
    FasterWhisperTranscriptionClient,
    MockTranscriptionClient,
    OpenAIDiarizedTranscriptionClient,
)
from src.services.transcription import (
    audio_chunk_specs,
    clean_transcript_text,
    infer_roles_for_diarized_speakers,
    infer_speaker_role,
    offset_diarized_segments,
    parse_openai_diarized_segments,
    segment_confidence,
)


def test_raw_transcript_segment_requires_valid_time_range() -> None:
    with pytest.raises(
        ValidationError,
        match="end_seconds must be greater than start_seconds",
    ):
        RawTranscriptSegment(
            speaker_role=SpeakerRole.UNKNOWN,
            start_seconds=5,
            end_seconds=2,
            text="Agent: hello",
        )


def test_transcription_result_requires_full_text_to_match_segments() -> None:
    with pytest.raises(
        ValidationError,
        match="full_text must match joined transcript segment text",
    ):
        TranscriptionResult(
            full_text="Agent: Different text.",
            segments=[
                RawTranscriptSegment(
                    speaker_role=SpeakerRole.UNKNOWN,
                    start_seconds=0,
                    end_seconds=1,
                    text="Agent: Hello.",
                )
            ],
            model_name="mock",
        )


def test_mock_transcription_client_returns_deterministic_result(tmp_path: Path) -> None:
    client = MockTranscriptionClient(transcript_text="Agent: Hello.")

    result = client.transcribe(tmp_path / "call.wav")

    assert result == TranscriptionResult(
        full_text="Agent: Hello.",
        segments=[
            RawTranscriptSegment(
                speaker_role=SpeakerRole.UNKNOWN,
                start_seconds=0,
                end_seconds=10,
                text="Agent: Hello.",
            )
        ],
        model_name="mock",
    )


def test_mock_transcription_client_respects_explicit_empty_text(
    tmp_path: Path,
) -> None:
    client = MockTranscriptionClient(transcript_text="")

    with pytest.raises(ValidationError):
        client.transcribe(tmp_path / "call.wav")


def test_faster_whisper_adapter_maps_segments_without_loading_real_model(
    tmp_path: Path,
) -> None:
    calls = []

    def transcribe(audio_path, **kwargs):
        calls.append((audio_path, kwargs))
        return (
            [
                SimpleNamespace(
                    start=0,
                    end=1.5,
                    text=" Agent: Hello. ",
                    avg_logprob=-0.1,
                    no_speech_prob=0.2,
                ),
                SimpleNamespace(
                    start=1.5,
                    end=3,
                    text=" Customer: Hi. ",
                    avg_logprob=-0.2,
                    no_speech_prob=0.1,
                ),
            ],
            SimpleNamespace(),
        )

    client = FasterWhisperTranscriptionClient(model_name="tiny")
    client._model = SimpleNamespace(transcribe=transcribe)

    result = client.transcribe(tmp_path / "call.wav")

    assert calls == [
        (
            str(tmp_path / "call.wav"),
            {
                "beam_size": 1,
                "vad_filter": True,
                "condition_on_previous_text": False,
            },
        )
    ]
    assert result.full_text == "Agent: Hello. Customer: Hi."
    assert result.model_name == "tiny"
    assert result.segments == [
        RawTranscriptSegment(
            speaker_role=SpeakerRole.AGENT,
            start_seconds=0,
            end_seconds=1.5,
            text="Agent: Hello.",
            confidence=0.85,
        ),
        RawTranscriptSegment(
            speaker_role=SpeakerRole.CUSTOMER,
            start_seconds=1.5,
            end_seconds=3,
            text="Customer: Hi.",
            confidence=0.86,
        ),
    ]


def test_faster_whisper_adapter_rejects_empty_transcription(tmp_path: Path) -> None:
    client = FasterWhisperTranscriptionClient(model_name="tiny")
    client._model = SimpleNamespace(
        transcribe=lambda audio_path, **kwargs: (
            [SimpleNamespace(start=0, end=1, text="  ")],
            SimpleNamespace(),
        )
    )

    with pytest.raises(ValueError, match="transcription produced no text"):
        client.transcribe(tmp_path / "call.wav")


def test_openai_diarized_adapter_maps_segments_and_roles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio_path = tmp_path / "call.mp3"
    audio_path.write_bytes(b"fake mp3")
    monkeypatch.setattr(
        "src.services.transcription.audio_duration_seconds",
        lambda path: 9.0,
    )
    fake_client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    segments=[
                        SimpleNamespace(
                            speaker="speaker_0",
                            start=0.0,
                            end=2.0,
                            text="Thank you for calling Question Bank.",
                        ),
                        SimpleNamespace(
                            speaker="speaker_1",
                            start=2.0,
                            end=5.0,
                            text="My purse was stolen and my credit card was in it.",
                        ),
                        SimpleNamespace(
                            speaker="speaker_0",
                            start=5.0,
                            end=7.0,
                            text="Can you please verify your account?",
                        ),
                        SimpleNamespace(
                            speaker="speaker_1",
                            start=7.0,
                            end=9.0,
                            text="I lost access to the app.",
                        ),
                    ]
                )
            )
        )
    )
    client = OpenAIDiarizedTranscriptionClient(
        client=fake_client,
        model_name="gpt-4o-transcribe-diarize",
    )

    result = client.transcribe(audio_path)

    assert result.model_name == "gpt-4o-transcribe-diarize"
    assert result.full_text == (
        "Thank you for calling Question Bank. "
        "My purse was stolen and my credit card was in it. "
        "Can you please verify your account? I lost access to the app."
    )
    assert [segment.speaker_role for segment in result.segments] == [
        SpeakerRole.AGENT,
        SpeakerRole.CUSTOMER,
        SpeakerRole.AGENT,
        SpeakerRole.CUSTOMER,
    ]


def test_openai_diarized_adapter_sends_required_api_options(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio_path = tmp_path / "call.mp3"
    audio_path.write_bytes(b"fake mp3")
    calls = []
    monkeypatch.setattr(
        "src.services.transcription.audio_duration_seconds",
        lambda path: 1.0,
    )

    def create(**kwargs):
        calls.append(kwargs)
        return {
            "segments": [
                {
                    "speaker": "speaker_0",
                    "start": 0,
                    "end": 1,
                    "text": "Thank you for calling.",
                }
            ]
        }

    fake_client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
    )
    client = OpenAIDiarizedTranscriptionClient(
        client=fake_client,
        model_name="gpt-4o-transcribe-diarize",
    )

    client.transcribe(audio_path)

    call = calls[0]
    assert call["model"] == "gpt-4o-transcribe-diarize"
    assert call["response_format"] == "diarized_json"
    assert call["chunking_strategy"] == "auto"
    assert call["file"].name == str(audio_path)


def test_openai_diarized_adapter_chunks_long_audio_and_offsets_segments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio_path = tmp_path / "call.mp3"
    audio_path.write_bytes(b"fake mp3")
    exported_chunks = []
    calls = []

    monkeypatch.setattr(
        "src.services.transcription.audio_duration_seconds",
        lambda path: 7.0,
    )

    def fake_export(source_path, output_path, *, offset_seconds, duration_seconds):
        exported_chunks.append(
            (
                Path(source_path),
                Path(output_path).name,
                offset_seconds,
                duration_seconds,
            )
        )
        Path(output_path).write_bytes(b"chunk")

    monkeypatch.setattr(
        "src.services.transcription.export_audio_chunk",
        fake_export,
    )

    def create(**kwargs):
        chunk_number = len(calls)
        calls.append(kwargs)
        return {
            "segments": [
                {
                    "speaker": "speaker_0",
                    "start": 0,
                    "end": 1,
                    "text": (
                        "Thank you for calling."
                        if chunk_number == 0
                        else "Can you please verify your account?"
                    ),
                },
                {
                    "speaker": "speaker_1",
                    "start": 1,
                    "end": 2,
                    "text": (
                        "My purse was stolen."
                        if chunk_number == 0
                        else "I lost access to the app."
                    ),
                },
            ]
        }

    fake_client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
    )
    client = OpenAIDiarizedTranscriptionClient(
        client=fake_client,
        model_name="gpt-4o-transcribe-diarize",
        chunk_seconds=3,
    )

    result = client.transcribe(audio_path)

    assert [item[1:] for item in exported_chunks] == [
        ("chunk-0001.mp3", 0.0, 3.0),
        ("chunk-0002.mp3", 3.0, 3.0),
        ("chunk-0003.mp3", 6.0, 1.0),
    ]
    assert len(calls) == 3
    assert [segment.start_seconds for segment in result.segments] == [
        0.0,
        1.0,
        3.0,
        4.0,
        6.0,
        7.0,
    ]
    assert [segment.speaker_role for segment in result.segments] == [
        SpeakerRole.AGENT,
        SpeakerRole.CUSTOMER,
        SpeakerRole.AGENT,
        SpeakerRole.CUSTOMER,
        SpeakerRole.AGENT,
        SpeakerRole.CUSTOMER,
    ]


def test_parse_openai_diarized_segments_supports_dict_response() -> None:
    response = {
        "segments": [
            {
                "speaker": "speaker_0",
                "start": 0,
                "end": 1.5,
                "text": " [BLANK_AUDIO] Agent: Hello. ",
            }
        ]
    }

    assert parse_openai_diarized_segments(response) == [
        {
            "speaker": "speaker_0",
            "start": 0.0,
            "end": 1.5,
            "text": "Agent: Hello.",
        }
    ]


def test_audio_chunk_specs_cover_full_duration() -> None:
    assert audio_chunk_specs(7.0, 3) == [(0.0, 3.0), (3.0, 3.0), (6.0, 1.0)]


def test_audio_chunk_specs_rejects_invalid_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_seconds must be greater than zero"):
        audio_chunk_specs(7.0, 0)


def test_offset_diarized_segments_shifts_chunk_timestamps() -> None:
    assert offset_diarized_segments(
        [
            {
                "speaker": "speaker_0",
                "start": 1.5,
                "end": 2.5,
                "text": "Hello.",
            }
        ],
        offset_seconds=30.0,
    ) == [
        {
            "speaker": "speaker_0",
            "start": 31.5,
            "end": 32.5,
            "text": "Hello.",
        }
    ]


def test_infer_roles_for_diarized_speakers_maps_two_speaker_call() -> None:
    segments = [
        {
            "speaker": "speaker_0",
            "start": 0.0,
            "end": 2.0,
            "text": "Thank you for calling Question Bank.",
        },
        {
            "speaker": "speaker_1",
            "start": 2.0,
            "end": 5.0,
            "text": "Okay.",
        },
    ]

    assert infer_roles_for_diarized_speakers(segments) == {
        "speaker_0": SpeakerRole.AGENT,
        "speaker_1": SpeakerRole.CUSTOMER,
    }


def test_clean_transcript_text_removes_common_artifacts() -> None:
    assert clean_transcript_text(" [BLANK_AUDIO]  Agent: Hello.  ") == "Agent: Hello."


def test_infer_speaker_role_uses_content_and_gap_heuristics() -> None:
    assert infer_speaker_role("Agent: Hello.") is SpeakerRole.AGENT
    assert infer_speaker_role("Customer: Hi.") is SpeakerRole.CUSTOMER
    assert (
        infer_speaker_role(
            "I need help.",
            previous_role=SpeakerRole.AGENT,
            gap_seconds=2.0,
        )
        is SpeakerRole.CUSTOMER
    )


@pytest.mark.parametrize(
    "text",
    [
        "My purse was stolen and my credit card was in it.",
        "I lost access to the app.",
        "My email is Tatiana1989 at gmail.com.",
        "I don't know. Ask me something I remember.",
        "Thank you so much for helping me.",
    ],
)
def test_infer_speaker_role_labels_obvious_customer_segments(text: str) -> None:
    assert infer_speaker_role(text) is SpeakerRole.CUSTOMER


@pytest.mark.parametrize(
    "text",
    [
        "Thank you for calling Question Bank.",
        "I can definitely help you with this.",
        "May I know your full name?",
        "Can you please verify the last four digits?",
        "I have submitted the dispute.",
    ],
)
def test_infer_speaker_role_labels_obvious_agent_segments(text: str) -> None:
    assert infer_speaker_role(text) is SpeakerRole.AGENT


def test_infer_speaker_role_keeps_uncertain_segments_unknown() -> None:
    assert infer_speaker_role("Okay.") is SpeakerRole.UNKNOWN


def test_segment_confidence_combines_logprob_and_speech_probability() -> None:
    segment = SimpleNamespace(avg_logprob=-0.1, no_speech_prob=0.2)

    assert segment_confidence(segment) == 0.85
