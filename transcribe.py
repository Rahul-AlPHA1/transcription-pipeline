#!/usr/bin/env python3
"""
Simple audio transcription pipeline.

Usage:
    python transcribe.py input.mp3 --output transcript.json
    python transcribe.py input.wav --mock

The real transcription path uses faster-whisper, an open-source Whisper
implementation. The mock path is useful for demos, CI, or environments where a
speech model has not been installed yet.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Protocol


SUPPORTED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".webm",
}


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    source_file: str
    language: str | None
    duration_seconds: float | None
    segments: List[TranscriptSegment]

    @property
    def text(self) -> str:
        return " ".join(segment.text.strip() for segment in self.segments).strip()

    def to_json_dict(self) -> dict:
        data = asdict(self)
        data["text"] = self.text
        return data


class Transcriber(Protocol):
    def transcribe(self, audio_file: Path, language: str | None) -> tuple[str | None, List[TranscriptSegment]]:
        ...


class MockTranscriber:
    """Deterministic transcriber for demos and tests."""

    def transcribe(self, audio_file: Path, language: str | None) -> tuple[str | None, List[TranscriptSegment]]:
        return (
            language or "en",
            [
                TranscriptSegment(0.0, 3.2, "This is a mock transcript for pipeline testing."),
                TranscriptSegment(3.2, 6.4, "In production this segment would come from a speech-to-text model."),
            ],
        )


class FasterWhisperTranscriber:
    """Real transcription adapter using the open-source faster-whisper package."""

    def __init__(self, model_size: str, device: str, compute_type: str) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. Install requirements.txt or run with --mock."
            ) from exc

        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_file: Path, language: str | None) -> tuple[str | None, List[TranscriptSegment]]:
        segments, info = self.model.transcribe(
            str(audio_file),
            language=language,
            vad_filter=True,
            word_timestamps=False,
        )

        transcript_segments = [
            TranscriptSegment(
                start=round(float(segment.start), 3),
                end=round(float(segment.end), 3),
                text=segment.text.strip(),
            )
            for segment in segments
        ]
        return info.language, transcript_segments


def run_command(command: list[str]) -> str:
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or f"Command failed: {' '.join(command)}")
    return process.stdout.strip()


def require_supported_audio(input_file: Path) -> None:
    if not input_file.exists():
        raise FileNotFoundError(f"Audio file not found: {input_file}")
    if input_file.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported audio extension '{input_file.suffix}'. Supported: {supported}")


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def get_duration_seconds(audio_file: Path) -> float | None:
    if audio_file.suffix.lower() == ".wav" and not ffmpeg_available():
        with wave.open(str(audio_file), "rb") as wav_file:
            frames = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
            return frames / float(sample_rate)

    if not ffmpeg_available():
        return None

    output = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_file),
        ]
    )
    try:
        return float(output)
    except ValueError:
        return None


def normalize_audio(input_file: Path, output_file: Path) -> None:
    if not ffmpeg_available():
        if input_file.suffix.lower() == ".wav":
            shutil.copyfile(input_file, output_file)
            return
        raise RuntimeError("FFmpeg is required to read non-WAV files. Install ffmpeg or provide a WAV file.")

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_file),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-vn",
            "-f",
            "wav",
            str(output_file),
        ]
    )


def make_chunks(audio_file: Path, work_dir: Path, chunk_seconds: int, overlap_seconds: int) -> list[tuple[Path, float]]:
    duration = get_duration_seconds(audio_file)
    if duration is None or duration <= chunk_seconds:
        return [(audio_file, 0.0)]
    if not ffmpeg_available():
        raise RuntimeError("FFmpeg is required to split long audio files into chunks.")

    chunks: list[tuple[Path, float]] = []
    step = max(1, chunk_seconds - overlap_seconds)
    chunk_count = math.ceil(duration / step)

    for index in range(chunk_count):
        start = index * step
        if start >= duration:
            break

        chunk_path = work_dir / f"chunk_{index:04d}.wav"
        run_command(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-i",
                str(audio_file),
                "-t",
                str(chunk_seconds),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-vn",
                str(chunk_path),
            ]
        )
        chunks.append((chunk_path, float(start)))

    return chunks


def merge_segments(chunks: Iterable[tuple[float, list[TranscriptSegment]]], overlap_seconds: int) -> list[TranscriptSegment]:
    merged: list[TranscriptSegment] = []

    for offset, segments in chunks:
        for segment in segments:
            adjusted = TranscriptSegment(
                start=round(segment.start + offset, 3),
                end=round(segment.end + offset, 3),
                text=segment.text,
            )

            if merged and adjusted.end <= merged[-1].end:
                continue

            # Drop likely duplicate text from the overlap area.
            if merged and adjusted.start < merged[-1].end + overlap_seconds:
                previous_text = merged[-1].text.strip().lower()
                current_text = adjusted.text.strip().lower()
                if current_text and (current_text in previous_text or previous_text in current_text):
                    continue

            merged.append(adjusted)

    return merged


def transcribe_pipeline(
    input_file: Path,
    transcriber: Transcriber,
    language: str | None,
    chunk_seconds: int,
    overlap_seconds: int,
) -> TranscriptResult:
    require_supported_audio(input_file)

    with tempfile.TemporaryDirectory(prefix="transcription_pipeline_") as tmp:
        work_dir = Path(tmp)
        normalized_audio = work_dir / "normalized.wav"
        normalize_audio(input_file, normalized_audio)
        duration = get_duration_seconds(normalized_audio)

        chunk_files = make_chunks(normalized_audio, work_dir, chunk_seconds, overlap_seconds)
        detected_language: str | None = language
        chunk_results: list[tuple[float, list[TranscriptSegment]]] = []

        for chunk_file, offset in chunk_files:
            detected_language, segments = transcriber.transcribe(chunk_file, language)
            chunk_results.append((offset, segments))

        merged_segments = merge_segments(chunk_results, overlap_seconds)

    return TranscriptResult(
        source_file=str(input_file),
        language=detected_language,
        duration_seconds=round(duration, 3) if duration is not None else None,
        segments=merged_segments,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe an audio file and return timestamped text segments.")
    parser.add_argument("audio_file", type=Path, help="Input audio file, for example WAV, MP3, M4A, FLAC, OGG, or WEBM.")
    parser.add_argument("--output", type=Path, help="Write JSON transcript to this path. Prints to stdout if omitted.")
    parser.add_argument("--language", help="Optional language code, for example en, es, fr. Omit for auto-detect.")
    parser.add_argument("--model-size", default="small", help="faster-whisper model size: tiny, base, small, medium, large-v3.")
    parser.add_argument("--device", default="cpu", help="Model device, usually cpu or cuda.")
    parser.add_argument("--compute-type", default="int8", help="Compute type for faster-whisper, for example int8 or float16.")
    parser.add_argument("--chunk-seconds", type=int, default=600, help="Chunk size for long audio files.")
    parser.add_argument("--overlap-seconds", type=int, default=5, help="Overlap between chunks to avoid clipped words.")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock transcription instead of a speech model.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.chunk_seconds <= 0:
        raise ValueError("--chunk-seconds must be greater than zero.")
    if args.overlap_seconds < 0 or args.overlap_seconds >= args.chunk_seconds:
        raise ValueError("--overlap-seconds must be at least zero and smaller than --chunk-seconds.")

    transcriber: Transcriber
    if args.mock:
        transcriber = MockTranscriber()
    else:
        transcriber = FasterWhisperTranscriber(
            model_size=args.model_size,
            device=args.device,
            compute_type=args.compute_type,
        )

    result = transcribe_pipeline(
        input_file=args.audio_file,
        transcriber=transcriber,
        language=args.language,
        chunk_seconds=args.chunk_seconds,
        overlap_seconds=args.overlap_seconds,
    )

    payload = json.dumps(result.to_json_dict(), indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
