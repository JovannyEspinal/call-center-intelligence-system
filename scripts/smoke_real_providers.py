"""Optional smoke test for real transcription and analysis providers.

This script is intentionally not part of the normal pytest suite. It requires a
real audio file and whatever provider credentials/models are selected in `.env`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from src.ui.app import analyze_uploaded_call, create_app_runtime, load_app_settings

    parser = argparse.ArgumentParser(
        description="Run one end-to-end analysis through configured real providers."
    )
    parser.add_argument(
        "--audio",
        required=True,
        help="Path to a local audio file with speech.",
    )
    parser.add_argument("--caller-id", default=None)
    parser.add_argument("--department", default="smoke-test")
    args = parser.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"Audio file does not exist: {audio_path}", file=sys.stderr)
        return 2

    settings = load_app_settings()
    if settings.analysis_backend == "mock" or settings.transcription_backend == "mock":
        print(
            "This smoke path is intended for real providers. Set "
            "ANALYSIS_BACKEND=openai and TRANSCRIPTION_BACKEND=openai_diarized "
            "or TRANSCRIPTION_BACKEND=faster_whisper "
            "in .env before running.",
            file=sys.stderr,
        )
        return 2

    runtime = create_app_runtime(settings)
    status, summary, transcript, _report_json, flags = analyze_uploaded_call(
        runtime,
        audio_file=audio_path,
        caller_id=args.caller_id,
        department=args.department,
        analysis_backend=settings.analysis_backend,
        transcription_backend=settings.transcription_backend,
    )
    print(f"Status: {status}")
    print(summary)
    print(f"Redacted transcript characters: {len(transcript)}")
    print(f"Compliance flags: {len(flags)}")
    return 0 if status in {"completed", "supervisor_review"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
