import asyncio
import queue
import sys
import tempfile
import types

import pytest

from roleplay_agent.services.tts import TtsError, list_cloned_voices, synthesize, synthesize_stream
from roleplay_agent.services.tts import tts as tts_module


def test_list_cloned_voices_excludes_presets_and_non_wav_files(tmp_path):
    (tmp_path / "ryan.wav").write_bytes(b"x")  # a preset - excluded
    (tmp_path / "rosa.wav").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")  # not a WAV - excluded

    assert list_cloned_voices(tmp_path) == ["rosa"]


def test_list_cloned_voices_empty_when_dir_missing(tmp_path):
    assert list_cloned_voices(tmp_path / "does-not-exist") == []


def test_synthesize_uses_preset_repo_for_a_supported_voice(monkeypatch, tmp_path):
    captured = {}

    def fake_worker(text, model_repo, voice, ref_audio, instruct):
        captured.update(text=text, model_repo=model_repo, voice=voice, ref_audio=ref_audio, instruct=instruct)
        return b"preset-wav"

    monkeypatch.setattr(tts_module, "_synthesize_in_worker", fake_worker)

    result = asyncio.run(
        synthesize(None, "hi", "ryan", "preset-repo", clone_model_repo="clone-repo", voice_samples_dir=tmp_path)
    )

    assert result == b"preset-wav"
    assert captured == {
        "text": "hi",
        "model_repo": "preset-repo",
        "voice": "ryan",
        "ref_audio": None,
        "instruct": None,
    }


def test_synthesize_routes_to_clone_repo_for_a_discovered_wav(monkeypatch, tmp_path):
    (tmp_path / "rosa.wav").write_bytes(b"x")
    captured = {}

    def fake_worker(text, model_repo, voice, ref_audio, instruct):
        captured.update(model_repo=model_repo, voice=voice, ref_audio=ref_audio, instruct=instruct)
        return b"cloned-wav"

    monkeypatch.setattr(tts_module, "_synthesize_in_worker", fake_worker)

    result = asyncio.run(
        synthesize(
            None,
            "hi",
            "rosa",
            "preset-repo",
            "some delivery note",
            clone_model_repo="clone-repo",
            voice_samples_dir=tmp_path,
        )
    )

    assert result == b"cloned-wav"
    assert captured["model_repo"] == "clone-repo"
    assert captured["voice"] is None
    assert captured["ref_audio"] == str(tmp_path / "rosa.wav")
    # synthesize() itself forwards instruct unconditionally - dropping it
    # for a cloned voice happens one layer down, inside
    # _synthesize_in_worker's own call to generate_audio (see the test
    # below) - not here.
    assert captured["instruct"] == "some delivery note"


def test_synthesize_without_clone_params_only_accepts_presets(tmp_path):
    # No clone_model_repo/voice_samples_dir passed - matches every existing
    # call site's behavior from before cloning support existed.
    (tmp_path / "rosa.wav").write_bytes(b"x")

    async def run():
        with pytest.raises(TtsError, match="Unknown voice"):
            await synthesize(None, "hi", "rosa", "preset-repo")

    asyncio.run(run())


def test_synthesize_unknown_voice_error_lists_cloned_voices_too(tmp_path):
    (tmp_path / "rosa.wav").write_bytes(b"x")

    async def run():
        with pytest.raises(TtsError, match="rosa"):
            await synthesize(
                None,
                "hi",
                "not-a-real-voice",
                "preset-repo",
                clone_model_repo="clone-repo",
                voice_samples_dir=tmp_path,
            )

    asyncio.run(run())


def test_synthesize_in_worker_drops_instruct_for_a_cloned_voice(monkeypatch, tmp_path):
    # instruct is a CustomVoice-only control (mlx_audio.tts.generate's own
    # "instruction for emotion/style") - the cloning checkpoint has no such
    # parameter, so a ref_audio call must never forward it to generate_audio,
    # even though synthesize() itself passes instruct through unconditionally
    # (see the test above - the drop happens one layer down, here).
    monkeypatch.setattr(tts_module, "_model", object(), raising=False)
    monkeypatch.setattr(tts_module, "_model_repo", "clone-repo", raising=False)

    captured = {}

    def fake_generate_audio(**kwargs):
        captured.update(kwargs)
        (tmp_path / "reply_000.wav").write_bytes(b"RIFF....WAVEfmt ")

    fake_generate_module = types.SimpleNamespace(generate_audio=fake_generate_audio)
    monkeypatch.setitem(sys.modules, "mlx_audio.tts.generate", fake_generate_module)

    class _FakeTempDir:
        def __enter__(self):
            return str(tmp_path)

        def __exit__(self, *exc):
            return False

    # _synthesize_in_worker creates its own fresh tempdir for output_path -
    # redirected to tmp_path so the "reply_000.wav" fake_generate_audio
    # writes above is what gets read back.
    monkeypatch.setattr(tempfile, "TemporaryDirectory", lambda: _FakeTempDir())

    result = tts_module._synthesize_in_worker(
        "hi", "clone-repo", None, str(tmp_path / "rosa.wav"), "some delivery note"
    )

    assert result == b"RIFF....WAVEfmt "
    assert captured["instruct"] is None
    assert captured["voice"] is None
    assert captured["ref_audio"] == str(tmp_path / "rosa.wav")


def _fake_manager(fake_queue: queue.Queue):
    """A plain queue.Queue has the same get(block, timeout)/put() surface
    synthesize_stream() needs from a real SyncManager Queue proxy - swapping
    it in this way keeps these tests from spinning up a real Manager
    subprocess (or importing mlx_audio/numpy) just to exercise the
    rate/chunk/done/error protocol itself."""
    return types.SimpleNamespace(Queue=lambda: fake_queue)


def test_synthesize_stream_yields_rate_then_chunks_then_stops(monkeypatch):
    def fake_worker(text, model_repo, voice, ref_audio, instruct, chunk_queue):
        chunk_queue.put(("rate", 24000))
        chunk_queue.put(("chunk", b"aa"))
        chunk_queue.put(("chunk", b"bb"))
        chunk_queue.put(("done", None))

    monkeypatch.setattr(tts_module, "_synthesize_stream_in_worker", fake_worker)
    monkeypatch.setattr(tts_module, "_get_manager", lambda: _fake_manager(queue.Queue()))

    async def run():
        sample_rate, chunks = await synthesize_stream(None, "hi", "ryan", "preset-repo")
        assert sample_rate == 24000
        collected = [chunk async for chunk in chunks]
        assert collected == [b"aa", b"bb"]

    asyncio.run(run())


def test_synthesize_stream_raises_on_worker_error_before_any_chunk(monkeypatch):
    def fake_worker(text, model_repo, voice, ref_audio, instruct, chunk_queue):
        chunk_queue.put(("error", "boom"))

    monkeypatch.setattr(tts_module, "_synthesize_stream_in_worker", fake_worker)
    monkeypatch.setattr(tts_module, "_get_manager", lambda: _fake_manager(queue.Queue()))

    async def run():
        with pytest.raises(TtsError, match="boom"):
            await synthesize_stream(None, "hi", "ryan", "preset-repo")

    asyncio.run(run())


def test_synthesize_stream_raises_if_error_arrives_mid_stream(monkeypatch):
    # A worker error after some audio already went out (unlike the
    # before-any-chunk case above) has to surface from inside the chunks()
    # generator, once the caller is already iterating it - not from the
    # initial synthesize_stream() await, which by then has already
    # returned successfully with the sample rate.
    def fake_worker(text, model_repo, voice, ref_audio, instruct, chunk_queue):
        chunk_queue.put(("rate", 24000))
        chunk_queue.put(("chunk", b"aa"))
        chunk_queue.put(("error", "boom"))

    monkeypatch.setattr(tts_module, "_synthesize_stream_in_worker", fake_worker)
    monkeypatch.setattr(tts_module, "_get_manager", lambda: _fake_manager(queue.Queue()))

    async def run():
        sample_rate, chunks = await synthesize_stream(None, "hi", "ryan", "preset-repo")
        assert sample_rate == 24000
        collected = []
        with pytest.raises(TtsError, match="boom"):
            async for chunk in chunks:
                collected.append(chunk)
        assert collected == [b"aa"]

    asyncio.run(run())


def test_synthesize_stream_unknown_voice_raises_before_touching_worker(monkeypatch):
    called = False

    def fake_worker(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(tts_module, "_synthesize_stream_in_worker", fake_worker)

    async def run():
        with pytest.raises(TtsError, match="Unknown voice"):
            await synthesize_stream(None, "hi", "not-a-real-voice", "preset-repo")

    asyncio.run(run())
    assert called is False


def test_synthesize_stream_in_worker_puts_rate_then_pcm_chunks_then_done(monkeypatch):
    np = pytest.importorskip("numpy")

    class FakeResult:
        def __init__(self, audio, sample_rate):
            self.audio = audio
            self.sample_rate = sample_rate

    captured_kwargs = {}

    class FakeModel:
        sample_rate = 24000

        def generate(self, **kwargs):
            captured_kwargs.update(kwargs)
            return [
                FakeResult(np.array([0.0, 0.5, -0.5]), 24000),
                FakeResult(np.array([1.0, -1.0]), 24000),
            ]

    monkeypatch.setattr(tts_module, "_model", FakeModel(), raising=False)
    monkeypatch.setattr(tts_module, "_model_repo", "preset-repo", raising=False)

    fake_queue: queue.Queue = queue.Queue()
    tts_module._synthesize_stream_in_worker("hi", "preset-repo", "ryan", None, "cheerful", fake_queue)

    messages = []
    while not fake_queue.empty():
        messages.append(fake_queue.get_nowait())

    assert messages[0] == ("rate", 24000)
    assert messages[-1] == ("done", None)
    assert [kind for kind, _ in messages[1:-1]] == ["chunk", "chunk"]
    assert captured_kwargs["stream"] is True
    assert captured_kwargs["instruct"] == "cheerful"
