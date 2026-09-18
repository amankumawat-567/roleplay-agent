import sys

import pytest

from roleplay_agent.services.stt import whisper as stt_whisper
from roleplay_agent.services.stt.whisper import SttUnavailableError, get_whisper_model, transcribe_wav_bytes


def test_get_whisper_model_missing_dependency_raises_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    stt_whisper._whisper_models.clear()

    with pytest.raises(SttUnavailableError, match="pip install"):
        get_whisper_model("base")


def test_transcribe_wav_bytes_joins_and_strips_segments(monkeypatch):
    class _Segment:
        def __init__(self, text):
            self.text = text

    class _FakeModel:
        def transcribe(self, path):
            assert path.endswith(".wav")
            return [_Segment(" hello "), _Segment("world ")], None

    monkeypatch.setattr(stt_whisper, "get_whisper_model", lambda model_size: _FakeModel())

    result = transcribe_wav_bytes(b"RIFF....WAVEfmt ", "base")

    assert result == "hello world"


def test_get_whisper_model_caches_per_model_size(monkeypatch):
    calls = []

    class _FakeWhisperModel:
        def __init__(self, model_size, device, compute_type):
            calls.append(model_size)

    monkeypatch.setitem(sys.modules, "faster_whisper", type("M", (), {"WhisperModel": _FakeWhisperModel}))
    stt_whisper._whisper_models.clear()

    first = get_whisper_model("base")
    second = get_whisper_model("base")

    assert first is second
    assert calls == ["base"]
