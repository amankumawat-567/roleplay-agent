"""Local text-to-speech via mlx-audio's Qwen3-TTS CustomVoice model. See
docs/ARCHITECTURE.md's "Local text-to-speech" for the full rationale:
verified live on this machine, ~1.2x real-time-factor, ~6GB peak memory
for the 8-bit CustomVoice checkpoint.

Runs in a single persistent *process* (ProcessPoolExecutor(max_workers=1)),
not a thread or the main event loop - loading the model is what's slow to
redo per call, so one long-lived worker amortizes that across every
synthesis request instead of reloading it each time. A separate process
also means a model crash/OOM only takes down that worker (a fresh one
spins up on the next call), never the main chat app, and keeps mlx-audio's
~6GB working set off the main process. mlx_audio itself is only ever
imported inside the worker function below, never at module import time -
the main process's dependency footprint stays light, and the app runs fine
with mlx-audio not installed at all (every voice request just 503s until
`pip install '.[tts]'` is run and a worker successfully loads the model)."""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import queue as stdlib_queue
from collections.abc import AsyncIterator
from concurrent.futures import ProcessPoolExecutor
from multiprocessing.managers import SyncManager
from pathlib import Path
from typing import Any

# The real CustomVoice speaker ids (verified against the loaded model's own
# `get_supported_speakers()`, not the model card) - dev-ui/src/data/voices.ts
# curates the same 5 out of the model's real 9 and must stay in sync with
# this tuple; see that file's own comment.
SUPPORTED_VOICES = ("ryan", "aiden", "dylan", "serena", "vivian")


def list_cloned_voices(voice_samples_dir: Path) -> list[str]:
    """Voice ids inferred purely by presence, not a registered/curated list
    like SUPPORTED_VOICES above: any WAV under `voice_samples_dir` whose
    stem isn't one of the curated presets is a cloneable voice, ready to
    select and speak with via synthesize()'s clone_model_repo branch below.
    No registration step - `scripts/extract_audio_sample.py` (24000 Hz
    mono, matching this checkpoint's own sample rate) into
    data/voice_samples/ is the whole workflow."""
    if not voice_samples_dir.exists():
        return []
    return sorted(p.stem for p in voice_samples_dir.glob("*.wav") if p.stem not in SUPPORTED_VOICES)


class TtsError(RuntimeError):
    """Synthesis failed - an unsupported voice, mlx-audio not installed, or
    the worker process itself erroring (model load, OOM, etc)."""


# Set inside the pool's single worker process only - the model is loaded
# once there on the first call and reused by every call after, since
# ProcessPoolExecutor doesn't recycle a worker unless told to.
_model = None
_model_repo: str | None = None


def _synthesize_in_worker(
    text: str, model_repo: str, voice: str | None, ref_audio: str | None, instruct: str | None
) -> bytes:
    """Runs inside the pool's worker process (see the module docstring for
    why a separate process, not a thread). Exactly one of `voice`
    (a SUPPORTED_VOICES preset) or `ref_audio` (a cloned-voice WAV path) is
    set - see synthesize()'s branch below - matching the two mutually
    exclusive ways `generate_audio`/the underlying model accept a speaker.
    `ref_text` is deliberately omitted for the cloning path: `generate_audio`
    auto-transcribes `ref_audio` via its own default Whisper model when
    `ref_text` is absent, so no hand-authored transcript is needed."""
    import tempfile

    global _model, _model_repo
    if _model is None or _model_repo != model_repo:
        from mlx_audio.tts.utils import load_model

        _model = load_model(model_repo)
        _model_repo = model_repo

    from mlx_audio.tts.generate import generate_audio

    with tempfile.TemporaryDirectory() as tmp:
        generate_audio(
            text=text,
            model=_model,
            voice=voice,
            ref_audio=ref_audio,
            # instruct (emotion/style) is only meaningful for a CustomVoice
            # preset - the cloning checkpoint has no such control, so this
            # is silently dropped for a ref_audio call rather than passed
            # through to an API that doesn't use it.
            instruct=instruct if voice else None,
            output_path=tmp,
            file_prefix="reply",
            audio_format="wav",
            verbose=False,
            play=False,
            stream=False,
        )
        wav_path = Path(tmp) / "reply_000.wav"
        if not wav_path.exists():
            raise TtsError("mlx-audio produced no audio output")
        return wav_path.read_bytes()


def build_tts_pool() -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=1)


# Backs synthesize_stream()'s cross-process queue - lazy, module-level
# singleton (mirrors the worker's own warm _model/_model_repo globals
# above), not one Manager per call: a Manager is itself a small spawned
# process, and a plain multiprocessing.Queue can't do this job at all -
# verified live that passing one as a ProcessPoolExecutor call argument
# raises "Queue objects should only be shared between processes through
# inheritance", since a plain Queue can only reach a process that inherited
# it at creation (fork/spawn time), never one passed in as an argument to
# an already-running pool worker afterwards. A SyncManager's own Queue is a
# picklable *proxy* built for exactly this - passing it as a call argument,
# not inheriting it - at the cost of routing every get()/put() through the
# manager's own process instead of a plain in-memory pipe.
_manager: SyncManager | None = None


def _get_manager() -> SyncManager:
    global _manager
    if _manager is None:
        _manager = mp.Manager()
    return _manager


def shutdown_tts_manager() -> None:
    """Mirrors build_tts_pool()'s own worker process: the manager above is
    a real spawned process too, so main.py's lifespan shuts this down
    alongside the TTS pool on exit rather than leaving it dangling (a
    no-op if synthesize_stream() was never actually called)."""
    global _manager
    if _manager is not None:
        _manager.shutdown()
        _manager = None


def _resolve_voice(
    voice: str, model_repo: str, clone_model_repo: str | None, voice_samples_dir: Path | None
) -> tuple[str | None, str | None, str]:
    """Shared by synthesize() and synthesize_stream(): resolves `voice` into
    (ref_audio, preset_voice, resolved_repo) - the same SUPPORTED_VOICES-
    preset-vs-cloned-WAV branch synthesize()'s docstring describes, factored
    out so both entry points make exactly the same decision instead of two
    copies drifting apart."""
    if voice in SUPPORTED_VOICES:
        return None, voice, model_repo

    clone_path = voice_samples_dir / f"{voice}.wav" if voice_samples_dir else None
    if not clone_model_repo or not clone_path or not clone_path.exists():
        choices = ", ".join(SUPPORTED_VOICES)
        cloned = list_cloned_voices(voice_samples_dir) if voice_samples_dir else []
        if cloned:
            choices += ", " + ", ".join(cloned)
        raise TtsError(f"Unknown voice {voice!r} - choose one of: {choices}.")
    return str(clone_path), None, clone_model_repo


# How often mlx-audio's own stream=True hands back a chunk of freshly
# synthesized audio (generate_audio's "streaming_interval", in seconds) -
# smaller means audio starts sooner but with more per-chunk IPC overhead.
# 0.3s verified live as a good balance: ~4x faster time-to-first-audio than
# the non-streaming path, still comfortably above the overhead of one
# multiprocessing.Queue round trip.
_STREAMING_INTERVAL_SECONDS = 0.3


def _synthesize_stream_in_worker(
    text: str,
    model_repo: str,
    voice: str | None,
    ref_audio: str | None,
    instruct: str | None,
    chunk_queue: Any,
) -> None:
    """Runs inside the pool's worker process, same as _synthesize_in_worker
    above (including reusing its warm _model/_model_repo globals - both
    worker functions run in the same single persistent process, so whichever
    one loaded the model already leaves it hot for the other). Unlike
    _synthesize_in_worker, which waits for generate_audio to fully finish
    and write a whole WAV file, this calls the model directly with
    stream=True and pushes each raw PCM16LE mono chunk onto `chunk_queue` (a
    SyncManager Queue proxy - see _get_manager()) as mlx-audio produces it,
    since the Future backing a submitted ProcessPoolExecutor call only ever
    resolves once, with a single return value, and can't carry incremental
    results on its own.

    Protocol on `chunk_queue`, mirroring synthesize_stream()'s reader:
    exactly one `("rate", sample_rate)` first, then any number of
    `("chunk", pcm_bytes)`, then exactly one of `("done", None)` or
    `("error", message)` - never both, and nothing after either."""
    global _model, _model_repo
    try:
        if _model is None or _model_repo != model_repo:
            from mlx_audio.tts.utils import load_model

            _model = load_model(model_repo)
            _model_repo = model_repo

        import numpy as np

        results = _model.generate(
            text=text,
            voice=voice,
            ref_audio=ref_audio,
            instruct=instruct if voice else None,
            stream=True,
            streaming_interval=_STREAMING_INTERVAL_SECONDS,
            verbose=False,
        )
        sent_rate = False
        for result in results:
            if not sent_rate:
                chunk_queue.put(("rate", result.sample_rate))
                sent_rate = True
            pcm = (np.asarray(result.audio) * 32767.0).clip(-32768, 32767).astype("<i2").tobytes()
            chunk_queue.put(("chunk", pcm))
        if not sent_rate:
            # No audio produced at all (e.g. text that's all silence) -
            # still owe the "rate" message synthesize_stream()'s reader
            # blocks on first, or it would wait forever for one that's
            # never coming.
            chunk_queue.put(("rate", _model.sample_rate))
        chunk_queue.put(("done", None))
    except Exception as exc:  # noqa: BLE001 - forwarded to the caller as TtsError, not raised in this process
        chunk_queue.put(("error", str(exc)))


async def synthesize(
    pool: ProcessPoolExecutor,
    text: str,
    voice: str,
    model_repo: str,
    instruct: str | None = None,
    clone_model_repo: str | None = None,
    voice_samples_dir: Path | None = None,
) -> bytes:
    """WAV bytes for `text` spoken in `voice`. Raises TtsError on anything
    that goes wrong - an unrecognized voice, mlx-audio missing, the model
    failing to load, or the worker crashing mid-call.

    `instruct` is mlx_audio.tts.generate.generate_audio's own "instruction
    for emotion/style (CustomVoice)" parameter - verified live (see
    docs/ARCHITECTURE.md's "Voice mode") to actually change delivery, not
    just accepted and ignored. Optional and `None` by default so every
    existing caller (text mode's plain read-aloud button) is unaffected;
    a voice-mode SpeechSegment's `delivery` field is the intended source
    of a real value here.

    `clone_model_repo`/`voice_samples_dir` are also both optional and
    `None` by default - a caller that omits them gets exactly the original
    SUPPORTED_VOICES-only behavior (every existing call site/test), never a
    changed error for a voice that was never valid before. A real caller
    (api/routes/chat.py's /speak) always passes both, so `voice` naming a
    WAV under `voice_samples_dir` (list_cloned_voices) routes to a real-
    time voice-cloning call against `clone_model_repo` instead of a
    SUPPORTED_VOICES preset - see _synthesize_in_worker."""
    ref_audio, preset_voice, resolved_repo = _resolve_voice(voice, model_repo, clone_model_repo, voice_samples_dir)

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            pool, _synthesize_in_worker, text, resolved_repo, preset_voice, ref_audio, instruct
        )
    except ModuleNotFoundError as exc:
        raise TtsError("mlx-audio isn't installed - run `pip install '.[tts]'` (Apple Silicon only).") from exc
    except Exception as exc:
        raise TtsError(f"Speech synthesis failed: {exc}") from exc


async def synthesize_stream(
    pool: ProcessPoolExecutor,
    text: str,
    voice: str,
    model_repo: str,
    instruct: str | None = None,
    clone_model_repo: str | None = None,
    voice_samples_dir: Path | None = None,
) -> tuple[int, AsyncIterator[bytes]]:
    """Same voice resolution and TtsError cases as synthesize() (an
    unrecognized voice raises before anything is submitted to the pool,
    exactly like synthesize() does), but for a caller that can't afford to
    wait for the whole reply's synthesis to finish before it hears
    anything - the read-aloud button and voice mode
    (api/routes/chat.py's /speak-stream).

    Returns `(sample_rate, chunks)`: `chunks` is an async generator of raw
    PCM16LE mono byte chunks, forwarded the moment mlx-audio's own
    stream=True produces each one - verified live (llm/tts.py's module
    docstring benchmark) to cut time-to-first-audio from the whole reply's
    synthesis time (several seconds) down to a few hundred milliseconds,
    since a caller can start forwarding bytes to the client as soon as the
    first chunk exists rather than after the last one does. The sample
    rate is returned up front, not as part of the byte stream, because a
    caller building a chunked HTTP response (chat.py) needs it for a
    response header before the body starts.

    Streams across the worker process boundary via a SyncManager Queue
    (see _get_manager()) passed into the submitted call - a plain
    multiprocessing.Queue can't do this (verified live: it raises "Queue
    objects should only be shared between processes through inheritance"
    the moment ProcessPoolExecutor tries to pickle it as a call argument,
    since a plain Queue can only reach a process that inherited it at
    creation, not one passed in afterward) - and a ProcessPoolExecutor
    Future only ever resolves once with a single return value, so it can't
    carry incremental results on its own either.  See
    _synthesize_stream_in_worker for the producer side and its queue
    protocol."""
    ref_audio, preset_voice, resolved_repo = _resolve_voice(voice, model_repo, clone_model_repo, voice_samples_dir)

    chunk_queue = _get_manager().Queue()
    loop = asyncio.get_running_loop()
    worker_future = loop.run_in_executor(
        pool, _synthesize_stream_in_worker, text, resolved_repo, preset_voice, ref_audio, instruct, chunk_queue
    )

    async def next_message() -> tuple[str, object]:
        # Polls with a bounded per-attempt timeout, rather than one
        # indefinitely blocking queue.get(): a crashed worker (OOM,
        # segfault - see the module docstring on why this runs in its own
        # process) would otherwise leave this coroutine waiting forever on
        # a message that's never coming. Bounded polling also avoids
        # leaking a thread stuck in a blocking call forever - a plain
        # asyncio.wait()-based race against worker_future doesn't actually
        # achieve that, since cancelling a Future backed by a call that's
        # already running inside run_in_executor's thread pool doesn't
        # stop it; only a bounded call itself does.
        while True:
            if worker_future.done() and worker_future.exception() is not None:
                raise TtsError(f"Speech synthesis failed: {worker_future.exception()}")
            try:
                return await loop.run_in_executor(None, chunk_queue.get, True, 0.5)
            except stdlib_queue.Empty:
                continue

    kind, payload = await next_message()
    if kind == "error":
        raise TtsError(f"Speech synthesis failed: {payload}")
    sample_rate = payload

    async def chunks() -> AsyncIterator[bytes]:
        while True:
            kind, payload = await next_message()
            if kind == "error":
                raise TtsError(f"Speech synthesis failed: {payload}")
            if kind == "done":
                return
            yield payload

    return sample_rate, chunks()
