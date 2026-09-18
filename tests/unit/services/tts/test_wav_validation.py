import io
import wave

import pytest

from roleplay_agent.services.tts.wav_validation import WavValidationError, validate_wav


def _wav_bytes(*, channels=1, sample_rate=24000, sample_width=2, duration=2.0) -> bytes:
    n_frames = int(sample_rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00" * n_frames * channels * sample_width)
    return buf.getvalue()


def test_accepts_a_valid_mono_16bit_wav():
    info = validate_wav(_wav_bytes())
    assert info.channels == 1
    assert info.sample_width_bytes == 2
    assert info.duration_seconds == pytest.approx(2.0, abs=0.05)


def test_rejects_empty_file():
    with pytest.raises(WavValidationError, match="empty"):
        validate_wav(b"")


def test_rejects_non_wav_bytes():
    with pytest.raises(WavValidationError, match="valid WAV"):
        validate_wav(b"not a real wav file at all")


def test_rejects_stereo():
    with pytest.raises(WavValidationError, match="mono"):
        validate_wav(_wav_bytes(channels=2))


def test_rejects_non_16bit():
    with pytest.raises(WavValidationError, match="16-bit"):
        validate_wav(_wav_bytes(sample_width=1))


def test_rejects_too_short_clip():
    with pytest.raises(WavValidationError, match="too short"):
        validate_wav(_wav_bytes(duration=0.2))


def test_rejects_too_long_clip():
    with pytest.raises(WavValidationError, match="too long"):
        validate_wav(_wav_bytes(duration=130.0))


def test_rejects_oversized_file():
    # A real WAV header wrapped around an oversized payload, so it fails on
    # the size check rather than being caught earlier as "not a valid wav".
    with pytest.raises(WavValidationError, match="too large"):
        validate_wav(_wav_bytes(duration=200.0) + b"\x00" * (21 * 1024 * 1024))
