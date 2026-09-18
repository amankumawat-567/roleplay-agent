"""Local text-to-speech, backend-pluggable (see configs/tts.yaml's `backend`
- "chatterbox" or "qwen3", never hardcoded here). Both backends share the
same worker-process/streaming plumbing below; only the model-loading and
synthesis internals differ, in each backend's own _synthesize_*_in_worker/
_synthesize_*_stream_in_worker pair and _get_chatterbox_model/_resolve_*_
voice helpers.

"qwen3" is mlx-audio's Qwen3-TTS CustomVoice model. See
docs/ARCHITECTURE.md's "Local text-to-speech" for the full rationale:
verified live on this machine, ~1.2x real-time-factor, ~6GB peak memory
for the 8-bit CustomVoice checkpoint.

"chatterbox" is Resemble AI's Chatterbox-Turbo (github.com/resemble-ai/
chatterbox) via the `chatterbox-tts` pip package - plain PyTorch, so it
runs on CPU/CUDA/MPS rather than qwen3's Apple-Silicon-only mlx. It has no
curated preset speakers (SUPPORTED_VOICES below is qwen3-only) - every
voice is a cloned reference clip via `audio_prompt_path`, and it has no
native low-level audio streaming API, so synthesize_stream() falls back to
per-sentence pseudo-streaming for it (see _split_sentences).

Runs in a single persistent *process* (ProcessPoolExecutor(max_workers=1)),
not a thread or the main event loop - loading the model is what's slow to
redo per call, so one long-lived worker amortizes that across every
synthesis request instead of reloading it each time. A separate process
also means a model crash/OOM only takes down that worker (a fresh one
spins up on the next call), never the main chat app, and keeps the
backend's multi-GB working set off the main process. Both backends' real
libraries (mlx_audio, chatterbox/torch) are only ever imported inside the
worker function below, never at module import time - the main process's
dependency footprint stays light, and the app runs fine with neither
installed at all (every voice request just 503s until the extra configs/
tts.yaml's `backend` needs is installed and a worker successfully loads
the model)."""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import queue as stdlib_queue
import re
from collections.abc import AsyncIterator
from concurrent.futures import ProcessPoolExecutor
from multiprocessing.managers import SyncManager
from pathlib import Path
from typing import Any

from roleplay_agent.config.settings import AppConfig

# The real CustomVoice speaker ids (verified against the loaded model's own
# `get_supported_speakers()`, not the model card) - dev-ui/src/data/voices.ts
# curates the same 5 out of the model's real 9 and must stay in sync with
# this tuple; see that file's own comment. qwen3 backend only - chatterbox
# has no equivalent curated list, see the module docstring.
SUPPORTED_VOICES = ("ryan", "aiden", "dylan", "serena", "vivian")

# Text is split on this before being handed to the chatterbox backend one
# sentence at a time (see _split_sentences) - its generate() call has no
# native streaming/chunking of its own, unlike mlx-audio's stream=True, so
# a sentence is the smallest unit synthesize_stream() can flush early for
# it.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    return parts or [text]


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


def _synthesize_qwen3_in_worker(
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


def _detect_chatterbox_device() -> str:
    """CPU/CUDA/MPS is a hardware fact, not something worth a config
    knob - cuda first (fastest when present), then mps, else cpu. Only
    ever called inside the worker process (see the module docstring - real
    torch is never imported at module import time)."""
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


# Set inside the pool's single worker process only, mirroring _model/
# _model_repo above but keyed on (model_repo, quantize) together - either
# changing what's actually loaded/patched into memory, not just which
# weights, means reloading. Device isn't part of the key: it's a fixed
# hardware fact for the lifetime of this worker process, not something
# that changes between calls.
_chatterbox_model = None
_chatterbox_model_key: tuple[str, str | None] | None = None


def _get_chatterbox_model(model_repo: str, quantize: str | None):
    """Loads (and caches, warm across calls in this worker process) a
    ChatterboxTurboTTS instance from `model_repo` - a real HF repo id we
    resolve ourselves via snapshot_download + from_local, deliberately not
    ChatterboxTurboTTS.from_pretrained()'s own hardcoded REPO_ID constant,
    so configs/tts.yaml's chatterbox.model_repo is the actual source of
    truth for which checkpoint loads, not a default baked into the
    vendored library."""
    global _chatterbox_model, _chatterbox_model_key
    key = (model_repo, quantize)
    if _chatterbox_model is not None and _chatterbox_model_key == key:
        return _chatterbox_model

    import torch
    from chatterbox.tts_turbo import ChatterboxTurboTTS
    from huggingface_hub import snapshot_download

    device = _detect_chatterbox_device()

    local_path = snapshot_download(
        repo_id=model_repo, allow_patterns=["*.safetensors", "*.json", "*.txt", "*.pt", "*.model"]
    )
    model = ChatterboxTurboTTS.from_local(local_path, device)

    if quantize == "int8" and device == "cpu":
        # T3 (the GPT2-based text-to-speech-token transformer) only - its
        # Linear layers are what torch's dynamic quantization actually
        # covers. S3Gen (the conv-heavy flow-matching vocoder half of the
        # model) is left at full precision; dynamic quantization doesn't
        # touch Conv layers, so quantizing it here would be a no-op anyway.
        # CPU-only: PyTorch's dynamic quantization backend doesn't support
        # cuda/mps - silently skipped there rather than raised, since
        # device is auto-detected, not a config the author can change to
        # fix a "wrong" combination.
        model.t3.tfmr = torch.ao.quantization.quantize_dynamic(model.t3.tfmr, {torch.nn.Linear}, dtype=torch.qint8)

    _chatterbox_model = model
    _chatterbox_model_key = key
    return _chatterbox_model


def _wav_tensor_to_pcm16(wav_tensor) -> bytes:
    """`wav_tensor` is ChatterboxTurboTTS.generate()'s own return shape -
    float audio in [-1, 1], shape (1, num_samples). Same [-1,1]-float ->
    int16-PCM formula _synthesize_stream_in_worker below already uses for
    the qwen3 backend's raw mlx_audio output, kept identical so both
    backends hand callers the same PCM16LE mono byte layout."""
    return (wav_tensor.squeeze(0).detach().cpu().numpy() * 32767.0).clip(-32768, 32767).astype("<i2").tobytes()


def _pcm16_to_wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _synthesize_chatterbox_in_worker(text: str, model_repo: str, quantize: str | None, ref_audio: str) -> bytes:
    """Runs inside the pool's worker process. Unlike the qwen3 backend,
    there's no SUPPORTED_VOICES preset branch here - `ref_audio` (a cloned
    reference clip) is always required, resolved by
    _resolve_chatterbox_voice before this is submitted to the pool.
    `instruct` isn't accepted at all: Turbo's own generate() explicitly
    warns and ignores exaggeration/cfg_weight (its docstring's "not
    supported by the Turbo version"), and its paralinguistic control
    ([laugh], [cough], ...) is inline text, not a separate parameter."""
    model = _get_chatterbox_model(model_repo, quantize)
    wav = model.generate(text, audio_prompt_path=ref_audio)
    return _pcm16_to_wav_bytes(_wav_tensor_to_pcm16(wav), model.sr)


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


def _resolve_qwen3_voice(
    voice: str, model_repo: str, clone_model_repo: str | None, voice_samples_dir: Path | None
) -> tuple[str | None, str | None, str]:
    """Shared by the qwen3 branches of synthesize() and synthesize_stream():
    resolves `voice` into (ref_audio, preset_voice, resolved_repo) - the
    same SUPPORTED_VOICES-preset-vs-cloned-WAV branch synthesize()'s
    docstring describes, factored out so both entry points make exactly
    the same decision instead of two copies drifting apart."""
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


def _resolve_chatterbox_voice(voice: str, voice_samples_dir: Path | None) -> str:
    """The chatterbox backend has no SUPPORTED_VOICES-style curated preset
    list (see the module docstring) - every voice is a cloned reference
    clip, the same data/voice_samples/<id>.wav qwen3's own clone path
    resolves against (list_cloned_voices), just always required here
    rather than a fallback after a preset-name check."""
    clone_path = voice_samples_dir / f"{voice}.wav" if voice_samples_dir else None
    if not clone_path or not clone_path.exists():
        cloned = list_cloned_voices(voice_samples_dir) if voice_samples_dir else []
        choices = ", ".join(cloned) if cloned else "none yet - add one under data/voice_samples/"
        raise TtsError(
            f"Unknown voice {voice!r} - the chatterbox backend has no preset speakers, only cloned "
            f"reference clips. Available: {choices}."
        )
    return str(clone_path)


# How often mlx-audio's own stream=True hands back a chunk of freshly
# synthesized audio (generate_audio's "streaming_interval", in seconds) -
# smaller means audio starts sooner but with more per-chunk IPC overhead.
# 0.3s verified live as a good balance: ~4x faster time-to-first-audio than
# the non-streaming path, still comfortably above the overhead of one
# multiprocessing.Queue round trip.
_STREAMING_INTERVAL_SECONDS = 0.3


def _synthesize_qwen3_stream_in_worker(
    text: str,
    model_repo: str,
    voice: str | None,
    ref_audio: str | None,
    instruct: str | None,
    chunk_queue: Any,
) -> None:
    """Runs inside the pool's worker process, same as
    _synthesize_qwen3_in_worker above (including reusing its warm _model/
    _model_repo globals - both worker functions run in the same single
    persistent process, so whichever one loaded the model already leaves
    it hot for the other). Unlike _synthesize_qwen3_in_worker, which waits
    for generate_audio to fully finish and write a whole WAV file, this
    calls the model directly with stream=True and pushes each raw PCM16LE
    mono chunk onto `chunk_queue` (a
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


def _synthesize_chatterbox_stream_in_worker(
    text: str, model_repo: str, quantize: str | None, ref_audio: str, chunk_queue: Any
) -> None:
    """Runs inside the pool's worker process. chatterbox has no native
    streaming/chunked generation (unlike qwen3's stream=True - see the
    module docstring), so this pseudo-streams by calling generate() once
    per sentence (_split_sentences) and flushing each sentence's audio as
    its own chunk - still a real latency win for a caller (a several-
    sentence reply starts playing after the first sentence's synthesis
    time, not the whole reply's), just coarser-grained than qwen3's
    sub-second streaming_interval chunks. Same chunk_queue protocol as
    _synthesize_qwen3_stream_in_worker above: one ("rate", ...) first, any
    number of ("chunk", pcm_bytes), then exactly one of ("done", None) or
    ("error", message)."""
    try:
        model = _get_chatterbox_model(model_repo, quantize)
        sent_rate = False
        for sentence in _split_sentences(text):
            wav = model.generate(sentence, audio_prompt_path=ref_audio)
            if not sent_rate:
                chunk_queue.put(("rate", model.sr))
                sent_rate = True
            chunk_queue.put(("chunk", _wav_tensor_to_pcm16(wav)))
        if not sent_rate:
            chunk_queue.put(("rate", model.sr))
        chunk_queue.put(("done", None))
    except Exception as exc:  # noqa: BLE001 - forwarded to the caller as TtsError, not raised in this process
        chunk_queue.put(("error", str(exc)))


async def synthesize(
    pool: ProcessPoolExecutor,
    text: str,
    voice: str,
    backend: str,
    model_repo: str,
    instruct: str | None = None,
    clone_model_repo: str | None = None,
    voice_samples_dir: Path | None = None,
    quantize: str | None = None,
) -> bytes:
    """WAV bytes for `text` spoken in `voice`, via whichever of the two
    backends `backend` names ("chatterbox" or "qwen3" - see the module
    docstring; configs/tts.yaml's `backend` is the only place this should
    ever be chosen, never hardcoded at a call site). Raises TtsError on
    anything that goes wrong - an unrecognized voice, the backend's own
    library missing, the model failing to load, or the worker crashing
    mid-call.

    `instruct` only ever reaches the qwen3 backend - mlx_audio.tts.generate.
    generate_audio's own "instruction for emotion/style (CustomVoice)"
    parameter, verified live (see docs/ARCHITECTURE.md's "Voice mode") to
    actually change delivery, not just accepted and ignored. The
    chatterbox backend has no equivalent parameter (see
    _synthesize_chatterbox_in_worker's docstring), so this is silently
    dropped for it rather than passed to an API that doesn't use it.

    `clone_model_repo`/`quantize` are backend-specific: qwen3 reads
    `clone_model_repo` (and ignores `quantize`, mlx handling its own
    quantization), chatterbox reads `quantize` (and ignores
    `clone_model_repo` - it has no separate cloning checkpoint, cloning is
    its only mode). Device (cpu/cuda/mps) isn't a parameter at all -
    `_detect_chatterbox_device()` auto-detects it inside the worker, qwen3
    leaves its own device placement to mlx. `voice_samples_dir` is read by
    both: `voice` naming a WAV under it (list_cloned_voices) is how either
    backend does voice cloning."""
    loop = asyncio.get_running_loop()
    if backend == "chatterbox":
        ref_audio = _resolve_chatterbox_voice(voice, voice_samples_dir)
        worker_args = (pool, _synthesize_chatterbox_in_worker, text, model_repo, quantize, ref_audio)
        not_installed_msg = "chatterbox-tts isn't installed - run `pip install '.[tts-chatterbox]'`."
    else:
        ref_audio, preset_voice, resolved_repo = _resolve_qwen3_voice(
            voice, model_repo, clone_model_repo, voice_samples_dir
        )
        worker_args = (pool, _synthesize_qwen3_in_worker, text, resolved_repo, preset_voice, ref_audio, instruct)
        not_installed_msg = "mlx-audio isn't installed - run `pip install '.[tts]'` (Apple Silicon only)."

    try:
        return await loop.run_in_executor(*worker_args)
    except ModuleNotFoundError as exc:
        raise TtsError(not_installed_msg) from exc
    except Exception as exc:
        raise TtsError(f"Speech synthesis failed: {exc}") from exc


async def synthesize_stream(
    pool: ProcessPoolExecutor,
    text: str,
    voice: str,
    backend: str,
    model_repo: str,
    instruct: str | None = None,
    clone_model_repo: str | None = None,
    voice_samples_dir: Path | None = None,
    quantize: str | None = None,
) -> tuple[int, AsyncIterator[bytes]]:
    """Same `backend` dispatch, voice resolution, and TtsError cases as
    synthesize() (an unrecognized voice raises before anything is
    submitted to the pool, exactly like synthesize() does), but for a
    caller that can't afford to wait for the whole reply's synthesis to
    finish before it hears anything - the read-aloud button and voice mode
    (api/routes/chat.py's /speak-stream).

    Returns `(sample_rate, chunks)`: `chunks` is an async generator of raw
    PCM16LE mono byte chunks. For the qwen3 backend these are forwarded
    the moment mlx-audio's own stream=True produces each one - verified
    live (this module's docstring benchmark) to cut time-to-first-audio
    from the whole reply's synthesis time (several seconds) down to a few
    hundred milliseconds. The chatterbox backend has no equivalent native
    streaming, so its chunks are one per sentence instead (see
    _synthesize_chatterbox_stream_in_worker) - a coarser-grained but still
    real latency win over waiting for the whole reply. Either way, a
    caller can start forwarding bytes to the client as soon as the first
    chunk exists rather than after the last one does. The sample rate is
    returned up front, not as part of the byte stream, because a caller
    building a chunked HTTP response (chat.py) needs it for a response
    header before the body starts.

    Streams across the worker process boundary via a SyncManager Queue
    (see _get_manager()) passed into the submitted call - a plain
    multiprocessing.Queue can't do this (verified live: it raises "Queue
    objects should only be shared between processes through inheritance"
    the moment ProcessPoolExecutor tries to pickle it as a call argument,
    since a plain Queue can only reach a process that inherited it at
    creation, not one passed in afterward) - and a ProcessPoolExecutor
    Future only ever resolves once with a single return value, so it can't
    carry incremental results on its own either. See
    _synthesize_qwen3_stream_in_worker/_synthesize_chatterbox_stream_in_worker
    for the producer side and their shared queue protocol."""
    loop = asyncio.get_running_loop()
    if backend == "chatterbox":
        ref_audio = _resolve_chatterbox_voice(voice, voice_samples_dir)
        chunk_queue = _get_manager().Queue()
        worker_future = loop.run_in_executor(
            pool, _synthesize_chatterbox_stream_in_worker, text, model_repo, quantize, ref_audio, chunk_queue
        )
    else:
        ref_audio, preset_voice, resolved_repo = _resolve_qwen3_voice(
            voice, model_repo, clone_model_repo, voice_samples_dir
        )
        chunk_queue = _get_manager().Queue()
        worker_future = loop.run_in_executor(
            pool,
            _synthesize_qwen3_stream_in_worker,
            text,
            resolved_repo,
            preset_voice,
            ref_audio,
            instruct,
            chunk_queue,
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


def backend_call_kwargs(app_config: AppConfig) -> dict:
    """The backend-selection kwargs synthesize()/synthesize_stream() both
    need (`backend`, `model_repo`, and whichever of `clone_model_repo`/
    `quantize` that backend actually reads) - factored out here, not
    duplicated in both of api/routes/gameplay/chat.py's /speak and
    /speak-stream, so `app_config.tts_backend` is read in exactly one
    place. Callers spread this alongside their own per-call kwargs (`text`,
    `voice`, `instruct`, `voice_samples_dir`)."""
    if app_config.tts_backend == "chatterbox":
        return {
            "backend": "chatterbox",
            "model_repo": app_config.tts_chatterbox_model_repo,
            "quantize": app_config.tts_chatterbox_quantize,
        }
    return {
        "backend": "qwen3",
        "model_repo": app_config.tts_qwen3_model_repo,
        "clone_model_repo": app_config.tts_qwen3_clone_model_repo,
    }
