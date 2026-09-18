"""Validates an uploaded WAV before it's accepted as a voice-cloning
reference clip (see api/routes/system/voices.py's POST /cloned). Nothing
elsewhere in this codebase validates a WAV's actual contents - list_cloned_voices
(tts.py) only checks the file *extension*, and chat.py's voice-turn upload
forwards raw bytes straight to the model - so this is deliberately the one
place that does, since a bad clip here becomes a permanent, silently-broken
entry in data/voice_samples/ rather than a one-off failed request."""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass

# Generous but bounded - a voice-cloning reference clip only needs a few
# seconds of clean audio (scripts/extract_audio_sample.py defaults to 12s),
# these just guard against something absurd (an empty file, an hour-long
# recording) rather than encoding a "correct" length.
MAX_WAV_BYTES = 20 * 1024 * 1024
MIN_DURATION_SECONDS = 1.0
MAX_DURATION_SECONDS = 120.0


class WavValidationError(ValueError):
    """Raised with a human-readable reason - the route handler turns this
    straight into a 422 response body, so the message is the whole point."""


@dataclass
class WavInfo:
    channels: int
    sample_rate: int
    sample_width_bytes: int
    duration_seconds: float


def validate_wav(data: bytes) -> WavInfo:
    """Rejects (raising WavValidationError with a specific reason) anything
    that isn't a real, mono, 16-bit-PCM WAV within the size/duration bounds
    above. Returns the parsed info on success."""
    if not data:
        raise WavValidationError("File is empty.")
    if len(data) > MAX_WAV_BYTES:
        raise WavValidationError(
            f"File is too large ({len(data) / 1_000_000:.1f}MB) - max is {MAX_WAV_BYTES // 1_000_000}MB."
        )

    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            channels = wav.getnchannels()
            sample_rate = wav.getframerate()
            sample_width = wav.getsampwidth()
            n_frames = wav.getnframes()
    except (wave.Error, EOFError) as exc:
        raise WavValidationError(
            "Not a valid WAV file - it must be an uncompressed PCM .wav with a proper RIFF/WAVE header."
        ) from exc

    if sample_rate <= 0:
        raise WavValidationError(
            "Not a valid WAV file - it must be an uncompressed PCM .wav with a proper RIFF/WAVE header."
        )

    duration = n_frames / sample_rate

    if channels != 1:
        raise WavValidationError(f"Must be mono - this file has {channels} channels.")
    if sample_width != 2:
        raise WavValidationError(f"Must be 16-bit PCM - this file is {sample_width * 8}-bit.")
    if duration < MIN_DURATION_SECONDS:
        raise WavValidationError(
            f"Clip is too short ({duration:.1f}s) - it needs to be at least {MIN_DURATION_SECONDS:.0f}s."
        )
    if duration > MAX_DURATION_SECONDS:
        raise WavValidationError(
            f"Clip is too long ({duration:.1f}s) - max is {MAX_DURATION_SECONDS:.0f}s."
        )

    return WavInfo(
        channels=channels,
        sample_rate=sample_rate,
        sample_width_bytes=sample_width,
        duration_seconds=duration,
    )
