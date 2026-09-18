"""Local speech-to-text via Hugging Face `transformers`' generic
`automatic-speech-recognition` pipeline - `model_repo` can be *any*
pipeline-compatible checkpoint on the Hub (a Whisper variant, Wav2Vec2,
HuBERT, Distil-Whisper, Moonshine, a fine-tune, ...), never one particular
model/engine baked into code (configs/transcript.yaml's `model_repo` is
the only place it's chosen). Shared by two callers so neither loads its
own separate model instance: components/transcript/media.py's no-captions
transcript fallback (via transcribe_file - it already has a downloaded
audio file) and voice mode's own non-audio-model fallback
(agents/game_play/voice.py, dispatched from api/routes/gameplay/chat.py's
/voice-turn, via transcribe_wav_bytes - it only has raw mic-capture bytes).

`transformers` (+ a torch backend) is an optional dependency (`pip
install '.[transcribe]'`), imported lazily inside `get_pipeline` only, so
the app runs fine (and every other feature works) with it never installed
- a caller that needs it just gets SttUnavailableError with an install
hint until then."""

from __future__ import annotations

import tempfile
from pathlib import Path

# Keyed on (model_repo, quantize) together - either changing what's loaded
# means a fresh pipeline, mirroring services/tts/tts.py's
# _chatterbox_model_key. Device is never part of the key since it's
# resolved once per process (see get_pipeline's own device detection), not
# something a caller varies per call the way TTS's chatterbox backend lets
# device vary by config.
_pipelines: dict[tuple[str, str | None], object] = {}


class SttUnavailableError(RuntimeError):
    """transformers (or its torch backend) isn't installed - mirrors
    services/tts/tts.py's TtsError: a clear message a caller turns into a
    422 (a config fact - this optional feature isn't installed - not a
    500)."""


def _detect_device() -> str:
    """CPU/CUDA/MPS is a hardware fact, not something worth a config knob
    - cuda first (fastest when present), then mps, else cpu. Mirrors
    services/tts/tts.py's own `_detect_chatterbox_device` - same reasoning,
    same order."""
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def get_pipeline(model_repo: str, quantize: str | None = None):
    key = (model_repo, quantize)
    if key not in _pipelines:
        try:
            from transformers import pipeline
        except ModuleNotFoundError as exc:
            raise SttUnavailableError(
                "transformers isn't installed - run `pip install '.[transcribe]'` to use local speech-to-text."
            ) from exc
        device = _detect_device()
        pipe = pipeline("automatic-speech-recognition", model=model_repo, device=device)

        if quantize == "int8" and device == "cpu":
            # Dynamic quantization of the model's Linear layers only -
            # mirrors services/tts/tts.py's _get_chatterbox_model. CPU-only:
            # PyTorch's dynamic quantization backend doesn't support
            # cuda/mps - silently skipped there rather than raised, since
            # device is auto-detected, not a config the author can change
            # to fix a "wrong" combination.
            import torch

            pipe.model = torch.ao.quantization.quantize_dynamic(pipe.model, {torch.nn.Linear}, dtype=torch.qint8)

        _pipelines[key] = pipe
    return _pipelines[key]


def transcribe_file(path: Path, model_repo: str, quantize: str | None = None) -> str:
    """An audio file already on disk -> plain transcript text -
    components/transcript/media.py's own caller (it already has a
    downloaded file, no bytes round-trip needed). The pipeline call itself
    handles decoding whatever audio format is on disk (ffmpeg/soundfile
    under the hood), not just WAV."""
    result = get_pipeline(model_repo, quantize)(str(path))
    return result["text"].strip()


def transcribe_wav_bytes(audio: bytes, model_repo: str, quantize: str | None = None) -> str:
    """Same transcription as transcribe_file, for a caller that only has
    raw WAV bytes (a turn's mic capture) rather than a file already on
    disk - the pipeline's real API wants a path, not bytes, so this is
    just transcribe_file with the bytes written to a temp file first."""
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = Path(tmp) / "clip.wav"
        audio_path.write_bytes(audio)
        return transcribe_file(audio_path, model_repo, quantize)
