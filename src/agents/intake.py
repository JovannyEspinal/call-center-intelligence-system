"""Audio intake validation agent."""

from __future__ import annotations

import hashlib
import io
import tempfile
import wave
from pathlib import Path

from mutagen import File as MutagenFile

from src.models import (
    AnalysisMetadata,
    AudioFormat,
    AudioInput,
    AudioProperties,
    IntakeResult,
    PrivacyEvent,
    PromptInjectionResult,
    RawAnalysisMetadata,
)
from src.services.security import RegexPIIRedactor, RegexPromptInjectionDetector

MAX_AUDIO_SIZE_BYTES = 50 * 1024 * 1024
MAX_AUDIO_DURATION_SECONDS = 60 * 60
SUPPORTED_FORMATS = {
    AudioFormat.WAV,
    AudioFormat.MP3,
    AudioFormat.FLAC,
    AudioFormat.M4A,
}


class IntakeValidationError(ValueError):
    """Raised when submitted audio cannot enter the analysis pipeline."""


class IntakeSecurityBlocked(IntakeValidationError):
    """Raised when intake metadata contains a prompt injection attempt."""

    def __init__(
        self,
        message: str,
        *,
        injection_result: PromptInjectionResult,
        metadata: AnalysisMetadata,
        privacy_events: list[PrivacyEvent],
    ) -> None:
        super().__init__(message)
        self.injection_result = injection_result
        self.metadata = metadata
        self.privacy_events = privacy_events


def validate_audio_input(
    audio_input: AudioInput,
    *,
    max_size_bytes: int = MAX_AUDIO_SIZE_BYTES,
    max_duration_seconds: int = MAX_AUDIO_DURATION_SECONDS,
    temp_dir: str | Path | None = None,
) -> IntakeResult:
    """Validate audio bytes and sanitize metadata for downstream stages."""
    detected_format = detect_audio_format(audio_input.audio_bytes[:12])
    if detected_format not in SUPPORTED_FORMATS:
        supported = ", ".join(sorted(item.value for item in SUPPORTED_FORMATS))
        raise IntakeValidationError(f"unsupported audio format; supported: {supported}")

    properties = extract_audio_properties(audio_input.audio_bytes, detected_format)
    if (
        properties.duration_seconds is not None
        and properties.duration_seconds > max_duration_seconds
    ):
        raise IntakeValidationError("audio duration exceeds 60 minutes")

    if len(audio_input.audio_bytes) > max_size_bytes:
        raise IntakeValidationError("audio file exceeds 50 MB size limit")

    sanitized_metadata, privacy_events = sanitize_metadata(
        audio_input.metadata,
        filename=audio_input.filename,
    )
    metadata_injection_result = scan_metadata_for_injection(sanitized_metadata)
    if metadata_injection_result.injection_detected:
        patterns = ", ".join(metadata_injection_result.matched_pattern_names)
        raise IntakeSecurityBlocked(
            f"metadata prompt injection detected: {patterns}",
            injection_result=metadata_injection_result,
            metadata=sanitized_metadata,
            privacy_events=privacy_events,
        )

    temp_audio_path = write_temp_audio_file(
        audio_input.audio_bytes,
        detected_format,
        temp_dir=temp_dir,
    )

    return IntakeResult(
        audio_hash=hashlib.sha256(audio_input.audio_bytes).hexdigest(),
        detected_format=detected_format,
        file_size_bytes=len(audio_input.audio_bytes),
        properties=properties,
        temp_audio_path=str(temp_audio_path),
        metadata=sanitized_metadata,
        privacy_events=privacy_events,
        metadata_injection_result=metadata_injection_result,
    )


def detect_audio_format(header: bytes) -> AudioFormat | None:
    """Detect supported audio format from magic bytes."""
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return AudioFormat.WAV
    if header.startswith(b"ID3") or header[:2] in {
        b"\xff\xfb",
        b"\xff\xf3",
        b"\xff\xf2",
    }:
        return AudioFormat.MP3
    if header.startswith(b"fLaC"):
        return AudioFormat.FLAC
    if (
        len(header) >= 12
        and header[4:8] == b"ftyp"
        and header[8:12]
        in {
            b"M4A ",
            b"mp42",
            b"isom",
        }
    ):
        return AudioFormat.M4A
    return None


def extract_audio_properties(
    audio_bytes: bytes,
    detected_format: AudioFormat,
) -> AudioProperties:
    """Extract audio properties available during intake."""
    if detected_format is AudioFormat.WAV:
        return extract_wav_properties(audio_bytes)
    return extract_mutagen_properties(audio_bytes)


def extract_mutagen_properties(audio_bytes: bytes) -> AudioProperties:
    """Extract non-WAV audio properties with mutagen when available."""
    try:
        audio = MutagenFile(io.BytesIO(audio_bytes))
    except Exception:
        return AudioProperties()
    if audio is None or getattr(audio, "info", None) is None:
        return AudioProperties()

    info = audio.info
    return AudioProperties(
        duration_seconds=getattr(info, "length", None),
        sample_rate_hz=getattr(info, "sample_rate", None),
        channels=getattr(info, "channels", None),
    )


def extract_wav_properties(audio_bytes: bytes) -> AudioProperties:
    """Extract WAV properties from the RIFF header."""
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
            frame_count = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
    except (EOFError, wave.Error) as exc:
        raise IntakeValidationError("invalid WAV audio header") from exc

    if sample_rate <= 0:
        raise IntakeValidationError("invalid WAV sample rate")

    return AudioProperties(
        duration_seconds=frame_count / sample_rate,
        sample_rate_hz=sample_rate,
        channels=channels,
    )


def write_temp_audio_file(
    audio_bytes: bytes,
    detected_format: AudioFormat,
    *,
    temp_dir: str | Path | None = None,
) -> Path:
    """Write validated audio bytes to a temporary file for downstream stages."""
    suffix = f".{detected_format.value}"
    temp_root = Path(temp_dir) if temp_dir is not None else None
    if temp_root is not None:
        temp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=suffix,
        dir=temp_root,
        delete=False,
    ) as temp_file:
        temp_file.write(audio_bytes)
        return Path(temp_file.name)


def sanitize_metadata(
    metadata: RawAnalysisMetadata,
    *,
    filename: str,
) -> tuple[AnalysisMetadata, list[PrivacyEvent]]:
    """Redact ordinary PII from user-provided analysis metadata."""
    redactor = RegexPIIRedactor()
    privacy_events: list[PrivacyEvent] = []
    redacted_values: dict[str, str | None] = {}

    raw_values = {
        "filename": filename,
        "caller_id": metadata.caller_id,
        "department": metadata.department,
    }
    for field_name, value in raw_values.items():
        if value is None:
            redacted_values[field_name] = None
            continue
        result = redactor.redact_text(value)
        redacted_values[field_name] = result.redacted_text
        privacy_events.extend(result.privacy_events)

    return AnalysisMetadata(**redacted_values), privacy_events


def scan_metadata_for_injection(metadata: AnalysisMetadata) -> PromptInjectionResult:
    """Scan sanitized metadata fields for prompt injection attempts."""
    detector = RegexPromptInjectionDetector()
    metadata_text = "\n".join(
        value
        for value in (metadata.filename, metadata.caller_id, metadata.department)
        if value
    )
    return detector.scan_text(metadata_text)
