"""Shared local Whisper transcription. Two independent callers both need
"turn audio into text" without loading their own separate model instance:
`components/transcript/media.py`'s no-captions fallback (Section A3) and
voice mode's non-audio-model fallback (`agents/game_play/voice.py`,
dispatched from `api/routes/gameplay/chat.py`'s `/voice-turn`). One
process-wide model cache here, not one per caller, so both features loading
the same `model_size` (`"base"` by default - `config/settings.py`'s
`whisper_model_size`) share a single loaded instance instead of doubling
memory for what's often the exact same weights.

faster-whisper is an optional dependency (`pip install '.[transcribe]'`),
imported lazily inside `get_whisper_model` only, so the app runs fine (and
every other feature works) with it never installed - a caller that needs it
just gets SttUnavailableError with an install hint until then."""

from __future__ import annotations

import tempfile
from pathlib import Path

_whisper_models: dict[str, object] = {}


class SttUnavailableError(RuntimeError):
    """faster-whisper isn't installed - mirrors `llm/tts.py`'s TtsError: a
    clear message a caller turns into a 422 (a config fact - this optional
    feature isn't installed - not a 500)."""


def get_whisper_model(model_size: str):
    if model_size not in _whisper_models:
        try:
            from faster_whisper import WhisperModel
        except ModuleNotFoundError as exc:
            raise SttUnavailableError(
                "faster-whisper isn't installed - run `pip install '.[transcribe]'` to use local "
                "speech-to-text."
            ) from exc
        _whisper_models[model_size] = WhisperModel(model_size, device="auto", compute_type="int8")
    return _whisper_models[model_size]


def transcribe_wav_bytes(audio: bytes, model_size: str) -> str:
    """A turn's raw mic capture (WAV bytes) -> plain transcript text.
    Written to a temp file since faster-whisper's `transcribe()` wants a
    path (same as `media.py`'s own audio-file transcription), not because
    the bytes themselves need any WAV-specific handling."""
    model = get_whisper_model(model_size)
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = Path(tmp) / "clip.wav"
        audio_path.write_bytes(audio)
        segments, _ = model.transcribe(str(audio_path))
        return " ".join(segment.text.strip() for segment in segments)
