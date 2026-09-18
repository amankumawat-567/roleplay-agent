import sys
from pathlib import Path

import pytest

from roleplay_agent.services.stt import stt as stt_module
from roleplay_agent.services.stt.stt import SttUnavailableError, get_pipeline, transcribe_file, transcribe_wav_bytes


def test_get_pipeline_missing_dependency_raises_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "transformers", None)
    stt_module._pipelines.clear()

    with pytest.raises(SttUnavailableError, match="pip install"):
        get_pipeline("openai/whisper-tiny")


def test_get_pipeline_auto_detects_device_and_caches_per_model_repo(monkeypatch):
    calls = []

    def fake_pipeline(task, model, device):
        calls.append((task, model, device))
        return object()

    class _FakeTorch:
        class cuda:
            @staticmethod
            def is_available():
                return False

        class backends:
            class mps:
                @staticmethod
                def is_available():
                    return True

    monkeypatch.setitem(sys.modules, "transformers", type("M", (), {"pipeline": staticmethod(fake_pipeline)}))
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch)
    stt_module._pipelines.clear()

    first = get_pipeline("openai/whisper-tiny")
    second = get_pipeline("openai/whisper-tiny")
    third = get_pipeline("facebook/wav2vec2-base-960h")

    assert first is second
    assert first is not third
    assert calls == [
        ("automatic-speech-recognition", "openai/whisper-tiny", "mps"),
        ("automatic-speech-recognition", "facebook/wav2vec2-base-960h", "mps"),
    ]


def test_transcribe_file_strips_the_pipeline_result_text(monkeypatch):
    class _FakePipeline:
        def __call__(self, path):
            assert path.endswith(".wav")
            return {"text": "  hello world  "}

    monkeypatch.setattr(stt_module, "get_pipeline", lambda model_repo, quantize=None: _FakePipeline())

    result = transcribe_file(Path("/tmp/clip.wav"), "openai/whisper-tiny")

    assert result == "hello world"


def test_transcribe_wav_bytes_writes_a_temp_file_and_delegates(monkeypatch):
    captured = {}

    def fake_transcribe_file(path, model_repo, quantize=None):
        captured["exists"] = path.exists()
        captured["contents"] = path.read_bytes()
        captured["model_repo"] = model_repo
        captured["quantize"] = quantize
        return "some text"

    monkeypatch.setattr(stt_module, "transcribe_file", fake_transcribe_file)

    result = transcribe_wav_bytes(b"RIFF....WAVEfmt ", "openai/whisper-tiny", "int8")

    assert result == "some text"
    assert captured["exists"] is True
    assert captured["contents"] == b"RIFF....WAVEfmt "
    assert captured["model_repo"] == "openai/whisper-tiny"
    assert captured["quantize"] == "int8"


def test_get_pipeline_int8_quantizes_on_cpu(monkeypatch):
    def fake_pipeline(task, model, device):
        return type("P", (), {"model": "fp32-model"})()

    quantize_calls = []

    class _FakeTorch:
        class cuda:
            @staticmethod
            def is_available():
                return False

        class backends:
            class mps:
                @staticmethod
                def is_available():
                    return False

        class nn:
            class Linear:
                pass

        class ao:
            class quantization:
                @staticmethod
                def quantize_dynamic(model, layers, dtype):
                    quantize_calls.append((model, dtype))
                    return "int8-model"

        qint8 = "qint8-dtype"

    monkeypatch.setitem(sys.modules, "transformers", type("M", (), {"pipeline": staticmethod(fake_pipeline)}))
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch)
    stt_module._pipelines.clear()

    pipe = get_pipeline("openai/whisper-tiny", "int8")

    assert pipe.model == "int8-model"
    assert quantize_calls == [("fp32-model", "qint8-dtype")]


def test_get_pipeline_int8_skipped_off_cpu(monkeypatch):
    def fake_pipeline(task, model, device):
        return type("P", (), {"model": "fp32-model"})()

    class _FakeTorch:
        class cuda:
            @staticmethod
            def is_available():
                return True

        class backends:
            class mps:
                @staticmethod
                def is_available():
                    return False

    monkeypatch.setitem(sys.modules, "transformers", type("M", (), {"pipeline": staticmethod(fake_pipeline)}))
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch)
    stt_module._pipelines.clear()

    pipe = get_pipeline("openai/whisper-tiny", "int8")

    assert pipe.model == "fp32-model"


def test_get_pipeline_caches_per_model_repo_and_quantize(monkeypatch):
    calls = []

    def fake_pipeline(task, model, device):
        calls.append(model)
        return type("P", (), {"model": "fp32-model"})()

    class _FakeTorch:
        class cuda:
            @staticmethod
            def is_available():
                return True

        class backends:
            class mps:
                @staticmethod
                def is_available():
                    return False

    monkeypatch.setitem(sys.modules, "transformers", type("M", (), {"pipeline": staticmethod(fake_pipeline)}))
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch)
    stt_module._pipelines.clear()

    plain = get_pipeline("openai/whisper-tiny")
    quantized = get_pipeline("openai/whisper-tiny", "int8")
    plain_again = get_pipeline("openai/whisper-tiny")

    assert plain is plain_again
    assert plain is not quantized
    assert calls == ["openai/whisper-tiny", "openai/whisper-tiny"]
