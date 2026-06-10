"""Transcription clients for raw call audio."""

from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import RawTranscriptSegment, SpeakerRole, TranscriptionResult

DEFAULT_TRANSCRIPTION_MODEL = "base"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_OPENAI_DIARIZED_TRANSCRIPTION_MODEL = "gpt-4o-transcribe-diarize"
DEFAULT_OPENAI_DIARIZED_CHUNK_SECONDS = 180
ARTIFACT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\[?BLANK_AUDIO\]?",
        r"\[?MUSIC\]?",
        r"\[?APPLAUSE\]?",
        r"\[?LAUGHTER\]?",
        r"字幕由\s*Amara\.org\s*社区提供",
    )
]
AGENT_CUES = (
    "thank you for calling",
    "how may help",
    "how may i help",
    "i can definitely help",
    "i can help",
    "i will now",
    "i will need",
    "may i know",
    "can you please verify",
    "for me to do this",
    "for me to initiate",
    "i understand",
    "i am now going to",
    "i have submitted",
    "i have also taken note",
    "as mandated by law",
    "you should receive",
    "we appreciate your business",
    "is there anything else that i can help",
    "please read the code",
)
CUSTOMER_CUES = (
    "my purse was stolen",
    "my credit card was in it",
    "i need your help",
    "i'm in so much panic",
    "i lost access",
    "somebody's draining my account",
    "my phone was in there",
    "i told you",
    "how would i know",
    "my address is",
    "my email is",
    "my other mobile number",
    "i don't know",
    "i cannot log into the app",
    "i just got paid",
    "i bought",
    "i didn't go",
    "not me",
    "i never allowed",
    "i really need to go",
    "i'll call back",
    "thank you so much for helping me",
    "you've been very helpful",
)


class TranscriptionClient(Protocol):
    """Boundary for local speech-to-text over validated temporary audio."""

    def transcribe(self, audio_path: str | Path) -> TranscriptionResult:
        """Transcribe a local audio file into raw timestamped transcript text."""


class MockTranscriptionClient:
    """Deterministic transcription client for tests and local graph development."""

    def __init__(
        self,
        *,
        transcript_text: str | None = None,
        model_name: str = "mock",
    ) -> None:
        self.transcript_text = (
            transcript_text
            if transcript_text is not None
            else (
                "Agent: Hello, I can help with your billing issue. "
                "Customer: My email is customer@example.com."
            )
        )
        self.model_name = model_name

    def transcribe(self, audio_path: str | Path) -> TranscriptionResult:
        _ = audio_path
        return TranscriptionResult(
            full_text=self.transcript_text,
            segments=[
                RawTranscriptSegment(
                    speaker_role=SpeakerRole.UNKNOWN,
                    start_seconds=0,
                    end_seconds=10,
                    text=self.transcript_text,
                )
            ],
            model_name=self.model_name,
        )


class FasterWhisperTranscriptionClient:
    """Local faster-whisper transcription adapter."""

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_TRANSCRIPTION_MODEL,
        device: str = "auto",
        compute_type: str = DEFAULT_COMPUTE_TYPE,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def transcribe(self, audio_path: str | Path) -> TranscriptionResult:
        model = self._load_model()
        segments, _info = model.transcribe(
            str(audio_path),
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        raw_segments: list[RawTranscriptSegment] = []
        previous_role = SpeakerRole.UNKNOWN
        previous_end_seconds: float | None = None
        previous_text: str | None = None
        for segment in segments:
            cleaned_text = clean_transcript_text(segment.text)
            if not cleaned_text or cleaned_text == previous_text:
                continue
            gap_seconds = (
                float(segment.start) - previous_end_seconds
                if previous_end_seconds is not None
                else 0
            )
            speaker_role = infer_speaker_role(
                cleaned_text,
                previous_role=previous_role,
                gap_seconds=gap_seconds,
            )
            raw_segments.append(
                RawTranscriptSegment(
                    speaker_role=speaker_role,
                    start_seconds=float(segment.start),
                    end_seconds=float(segment.end),
                    text=cleaned_text,
                    confidence=segment_confidence(segment),
                )
            )
            previous_role = speaker_role
            previous_end_seconds = float(segment.end)
            previous_text = cleaned_text

        full_text = " ".join(segment.text for segment in raw_segments).strip()
        if not full_text:
            raise ValueError("transcription produced no text")
        return TranscriptionResult(
            full_text=full_text,
            segments=raw_segments,
            model_name=self.model_name,
        )

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model


class OpenAIDiarizedTranscriptionClient:
    """OpenAI speech-to-text adapter with speaker diarization enabled."""

    def __init__(
        self,
        *,
        client: OpenAI | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        chunk_seconds: int | None = None,
    ) -> None:
        self.model_name = model_name or os.getenv(
            "OPENAI_TRANSCRIPTION_MODEL",
            DEFAULT_OPENAI_DIARIZED_TRANSCRIPTION_MODEL,
        )
        self.chunk_seconds = chunk_seconds or int(
            os.getenv(
                "OPENAI_DIARIZED_CHUNK_SECONDS",
                str(DEFAULT_OPENAI_DIARIZED_CHUNK_SECONDS),
            )
        )
        self.client = client or OpenAI(api_key=api_key)

    def transcribe(self, audio_path: str | Path) -> TranscriptionResult:
        diarized_segments = self._transcribe_chunks(Path(audio_path))
        if not diarized_segments:
            raise ValueError("diarized transcription produced no segments")

        speaker_role_map = infer_roles_for_diarized_speakers(diarized_segments)
        raw_segments = [
            RawTranscriptSegment(
                speaker_role=speaker_role_map.get(
                    segment["speaker"],
                    SpeakerRole.UNKNOWN,
                ),
                start_seconds=segment["start"],
                end_seconds=segment["end"],
                text=segment["text"],
            )
            for segment in diarized_segments
        ]
        full_text = " ".join(segment.text for segment in raw_segments).strip()
        if not full_text:
            raise ValueError("diarized transcription produced no text")
        return TranscriptionResult(
            full_text=full_text,
            segments=raw_segments,
            model_name=self.model_name,
        )

    def _transcribe_chunks(self, audio_path: Path) -> list[dict]:
        duration_seconds = audio_duration_seconds(audio_path)
        if duration_seconds <= self.chunk_seconds:
            response = self._create_transcription(audio_path)
            return parse_openai_diarized_segments(response)

        diarized_segments: list[dict] = []
        with tempfile.TemporaryDirectory(prefix="openai-diarized-chunks-") as temp_dir:
            chunk_specs = audio_chunk_specs(duration_seconds, self.chunk_seconds)
            for chunk_index, (offset_seconds, duration) in enumerate(chunk_specs, 1):
                chunk_path = Path(temp_dir) / f"chunk-{chunk_index:04d}.mp3"
                export_audio_chunk(
                    audio_path,
                    chunk_path,
                    offset_seconds=offset_seconds,
                    duration_seconds=duration,
                )
                response = self._create_transcription(chunk_path)
                diarized_segments.extend(
                    offset_diarized_segments(
                        parse_openai_diarized_segments(response),
                        offset_seconds=offset_seconds,
                    )
                )
        return diarized_segments

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
    )
    def _create_transcription(self, audio_path: str | Path):
        with Path(audio_path).open("rb") as audio_file:
            return self.client.audio.transcriptions.create(
                file=audio_file,
                model=self.model_name,
                response_format="diarized_json",
                chunking_strategy="auto",
            )


def audio_duration_seconds(audio_path: str | Path) -> float:
    """Return audio duration from ffprobe."""
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(completed.stdout.strip())


def audio_chunk_specs(
    duration_seconds: float,
    chunk_seconds: int,
) -> list[tuple[float, float]]:
    """Return `(offset, duration)` pairs covering the full audio duration."""
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be greater than zero")

    specs: list[tuple[float, float]] = []
    offset_seconds = 0.0
    while offset_seconds < duration_seconds:
        remaining_seconds = duration_seconds - offset_seconds
        specs.append((offset_seconds, min(float(chunk_seconds), remaining_seconds)))
        offset_seconds += chunk_seconds
    return specs


def export_audio_chunk(
    source_path: str | Path,
    output_path: str | Path,
    *,
    offset_seconds: float,
    duration_seconds: float,
) -> None:
    """Export one compressed audio chunk for provider transcription."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            str(offset_seconds),
            "-t",
            str(duration_seconds),
            "-i",
            str(source_path),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def clean_transcript_text(value: str) -> str:
    """Remove common non-speech artifacts emitted by speech-to-text models."""
    cleaned = value.strip()
    for pattern in ARTIFACT_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_openai_diarized_segments(response) -> list[dict]:
    """Extract normalized speaker segments from OpenAI diarized_json responses."""
    raw_segments = _read_response_value(response, "segments")
    if raw_segments is None:
        raise ValueError("OpenAI diarized response did not include segments")

    segments = []
    for raw_segment in raw_segments:
        text = clean_transcript_text(
            str(_read_response_value(raw_segment, "text") or "")
        )
        if not text:
            continue
        speaker = str(_read_response_value(raw_segment, "speaker") or "").strip()
        if not speaker:
            speaker = "unknown"
        start = _read_response_value(raw_segment, "start")
        end = _read_response_value(raw_segment, "end")
        if start is None or end is None:
            raise ValueError("OpenAI diarized segment is missing start/end timestamps")
        segments.append(
            {
                "speaker": speaker,
                "start": float(start),
                "end": float(end),
                "text": text,
            }
        )
    return segments


def offset_diarized_segments(
    segments: list[dict],
    *,
    offset_seconds: float,
) -> list[dict]:
    """Shift chunk-local diarized timestamps into full-audio time."""
    return [
        {
            **segment,
            "start": segment["start"] + offset_seconds,
            "end": segment["end"] + offset_seconds,
        }
        for segment in segments
    ]


def infer_roles_for_diarized_speakers(
    segments: list[dict],
) -> dict[str, SpeakerRole]:
    """Map diarized speaker IDs to call-center roles using aggregate text cues."""
    speaker_scores: dict[str, dict[SpeakerRole, int]] = {}
    speaker_order: list[str] = []
    for segment in segments:
        speaker = str(segment["speaker"])
        if speaker not in speaker_scores:
            speaker_scores[speaker] = {
                SpeakerRole.AGENT: 0,
                SpeakerRole.CUSTOMER: 0,
            }
            speaker_order.append(speaker)

        text = str(segment["text"]).lower()
        speaker_scores[speaker][SpeakerRole.AGENT] += sum(
            1 for cue in AGENT_CUES if cue in text
        )
        speaker_scores[speaker][SpeakerRole.CUSTOMER] += sum(
            1 for cue in CUSTOMER_CUES if cue in text
        )

    roles: dict[str, SpeakerRole] = {}
    for speaker, scores in speaker_scores.items():
        agent_score = scores[SpeakerRole.AGENT]
        customer_score = scores[SpeakerRole.CUSTOMER]
        if agent_score > customer_score:
            roles[speaker] = SpeakerRole.AGENT
        elif customer_score > agent_score:
            roles[speaker] = SpeakerRole.CUSTOMER
        else:
            roles[speaker] = SpeakerRole.UNKNOWN

    if len(speaker_order) == 2:
        first, second = speaker_order
        if roles[first] is SpeakerRole.AGENT and roles[second] is SpeakerRole.UNKNOWN:
            roles[second] = SpeakerRole.CUSTOMER
        elif (
            roles[first] is SpeakerRole.CUSTOMER
            and roles[second] is SpeakerRole.UNKNOWN
        ):
            roles[second] = SpeakerRole.AGENT
        elif roles[second] is SpeakerRole.AGENT and roles[first] is SpeakerRole.UNKNOWN:
            roles[first] = SpeakerRole.CUSTOMER
        elif (
            roles[second] is SpeakerRole.CUSTOMER
            and roles[first] is SpeakerRole.UNKNOWN
        ):
            roles[first] = SpeakerRole.AGENT

    return roles


def infer_speaker_role(
    text: str,
    *,
    previous_role: SpeakerRole = SpeakerRole.UNKNOWN,
    gap_seconds: float = 0,
) -> SpeakerRole:
    """Apply lightweight role heuristics without claiming true diarization."""
    lowered = text.lower()
    if lowered.startswith("agent:") or any(cue in lowered for cue in AGENT_CUES):
        return SpeakerRole.AGENT
    if lowered.startswith("customer:") or any(cue in lowered for cue in CUSTOMER_CUES):
        return SpeakerRole.CUSTOMER
    if gap_seconds >= 1.5 and previous_role is SpeakerRole.AGENT:
        return SpeakerRole.CUSTOMER
    if gap_seconds >= 1.5 and previous_role is SpeakerRole.CUSTOMER:
        return SpeakerRole.AGENT
    return SpeakerRole.UNKNOWN


def _read_response_value(value, key: str):
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def segment_confidence(segment) -> float | None:
    """Estimate confidence from faster-whisper segment probabilities."""
    avg_logprob = getattr(segment, "avg_logprob", None)
    no_speech_prob = getattr(segment, "no_speech_prob", None)
    confidence_parts = []
    if avg_logprob is not None:
        confidence_parts.append(max(0.0, min(1.0, math.exp(float(avg_logprob)))))
    if no_speech_prob is not None:
        confidence_parts.append(max(0.0, min(1.0, 1.0 - float(no_speech_prob))))
    if not confidence_parts:
        return None
    return round(sum(confidence_parts) / len(confidence_parts), 2)
