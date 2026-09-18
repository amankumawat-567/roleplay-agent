import asyncio
import time
from concurrent.futures import ProcessPoolExecutor

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from ollama import ResponseError

from roleplay_agent.agents.game_play.agent import RoleplayAgent
from roleplay_agent.agents.game_play.prompts import build_voice_system_prompt
from roleplay_agent.agents.game_play.response import StreamingReply
from roleplay_agent.agents.game_play.voice import generate_voice_turn
from roleplay_agent.api.dependencies import (
    get_agent,
    get_embedding_repo,
    get_embeddings,
    get_game_or_404,
    get_message_repo,
    get_session_or_404,
    get_session_repo,
    get_settings_repo,
    get_tts_pool,
)
from roleplay_agent.components.memory.context import get_context
from roleplay_agent.components.memory.manager import fold_overflow_into_summary
from roleplay_agent.components.memory.summarizer import build_summarizer
from roleplay_agent.components.observability.logging import logger
from roleplay_agent.components.observability.metrics import log_background_fold, log_background_fold_failed
from roleplay_agent.config.settings import AppConfig, Settings, get_app_config, get_settings
from roleplay_agent.games.models import Game
from roleplay_agent.schema.chat import ChatRequest, SpeakRequest, VoiceSegmentResponse, VoiceTurnResponse
from roleplay_agent.services import stt as stt_module
from roleplay_agent.services import tts as tts_module
from roleplay_agent.services.llm.capabilities import (
    AUDIO_INPUT_CAPABILITY,
    get_available_models,
    has_capability,
    resolve_game_model,
)
from roleplay_agent.services.llm.errors import describe_llm_error
from roleplay_agent.services.llm.providers import ProviderConfigError
from roleplay_agent.services.storage.models import Session
from roleplay_agent.services.storage.repositories import SettingsRepository
from roleplay_agent.services.stt import SttUnavailableError
from roleplay_agent.services.tts import TtsError

router = APIRouter(prefix="/api/sessions", tags=["chat"])

_TITLE_SNIPPET_CHARS = 50


def _num_ctx_for(game: Game, app_config: AppConfig) -> int:
    return game.num_ctx or app_config.default_num_ctx


def _resolved_game(game: Game, settings_repo: SettingsRepository) -> Game:
    """Every route that's about to actually run `game`'s model (chat,
    voice-turn) needs to resolve a `model: default` game.yaml (see
    resolve_game_model) before touching provider/model anywhere - not just
    once at build_llm time, since a resolved model also has to reach
    has_capability's own lookup (voice_turn's audio-capability gate below)
    and the background _fold_task summarizer. Routes that don't build_llm
    at all (speak/speak-stream, which only read `game.voice`) don't need
    this."""
    provider, model = resolve_game_model(game.provider, game.model, settings_repo)
    if (provider, model) == (game.provider, game.model):
        return game
    return game.model_copy(update={"provider": provider, "model": model})


def _title_from_message(text: str) -> str:
    """A ChatGPT/Claude-style history title: a truncated snippet of the
    first user message, not the persona's name (A0)."""
    snippet = " ".join(text.split())
    if len(snippet) <= _TITLE_SNIPPET_CHARS:
        return snippet
    return snippet[:_TITLE_SNIPPET_CHARS].rstrip() + "…"


def _fold_task(session_id: str, game: Game, num_ctx: int, app_config: AppConfig) -> None:
    """Runs after the HTTP response has finished streaming (see
    BackgroundTasks below) - folding old turns into the summary never adds
    latency to the reply the user is waiting on. When the game has opted
    into memory_recall, this is also where the folded chunk gets embedded
    and stored (see memory.manager) - still off the reply's critical path."""
    t_start = time.monotonic()
    try:
        summarizer = build_summarizer(
            game.provider, game.model, num_ctx, app_config.keep_alive, enable_thinking=app_config.enable_thinking
        )
        embedding_repo = get_embedding_repo() if game.memory_recall else None
        embed_fn = get_embeddings().embed_query if game.memory_recall else None
        folded = fold_overflow_into_summary(
            get_session_repo(),
            get_message_repo(),
            session_id,
            app_config.keep_last_messages,
            summarizer,
            embedding_repo=embedding_repo,
            embed_fn=embed_fn,
            game_id=game.id,
        )
        if folded:
            log_background_fold(session_id=session_id, took_s=time.monotonic() - t_start)
    except Exception:
        log_background_fold_failed(session_id)


@router.post("/{session_id}/chat")
def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session_or_404),
    app_config: AppConfig = Depends(get_app_config),
    agent: RoleplayAgent = Depends(get_agent),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    game = _resolved_game(get_game_or_404(session.game_id), settings_repo)
    num_ctx = _num_ctx_for(game, app_config)

    if body.message:
        message_repo = get_message_repo()
        message_repo.add(session.id, "user", body.message)
        # First user-role message in this session - replace the placeholder
        # persona-name title with a real snippet (A0).
        # A starter: ai session's opening line is the persona's, not the
        # user's, so this only fires once the user actually replies.
        if message_repo.count_role(session.id, "user") == 1:
            get_session_repo().update_title(session.id, _title_from_message(body.message))

    # Scheduled now, but Starlette only runs it after the streamed response
    # below has been fully sent - it never adds latency to this turn's reply.
    background_tasks.add_task(_fold_task, session.id, game, num_ctx, app_config)

    initial_state = {
        "session_id": session.id,
        "game": game,
        "num_ctx": num_ctx,
        "message": body.message,
        "followup_reason": None,
        "history": [],
        "reply": "",
    }

    async def token_stream():
        reply = StreamingReply(session.id, game.model)
        try:
            async for piece in reply.consume(agent.graph, initial_state):
                yield piece
        except (httpx.TransportError, ResponseError) as exc:
            # The HTTP status is already committed by the time streaming
            # starts, so this can't become a 503/502 - the best we can do is
            # end the stream with a clear message instead of a traceback,
            # log it properly, and skip persisting a broken/partial turn.
            logger.error("chat turn failed session=%s: %s", session.id, exc)
            yield f"\n\n[{describe_llm_error(exc)}]"
            return
        except ProviderConfigError as exc:
            logger.error("chat turn failed session=%s: %s", session.id, exc)
            yield f"\n\n[{exc}]"
            return
        get_message_repo().add(session.id, "assistant", reply.full_text)
        reply.log()

    return StreamingResponse(token_stream(), media_type="text/plain", background=background_tasks)


@router.post("/{session_id}/speak")
async def speak(
    body: SpeakRequest,
    session: Session = Depends(get_session_or_404),
    app_config: AppConfig = Depends(get_app_config),
    settings: Settings = Depends(get_settings),
    pool: ProcessPoolExecutor = Depends(get_tts_pool),
):
    """Synthesizes `body.text` in this session's persona voice as one plain
    WAV blob, only after synthesis fully finishes - not eagerly after every
    reply, so personas nobody listens to never pay the synthesis cost.
    Superseded by /speak-stream below for this app's own two callers (the
    read-aloud button and voice mode), which can't afford to wait for a
    whole reply's synthesis before hearing anything; kept as-is for any
    caller that just wants one complete audio file back. 422 (not 503)
    when the persona simply has no voice configured - that's a config fact
    about this game, not a service outage, and lets a frontend fall back
    to browser speech synthesis without treating it as an error worth
    surfacing."""
    game = get_game_or_404(session.game_id)
    if not game.voice:
        raise HTTPException(422, "This persona has no voice configured.")

    text = body.text.strip()[: app_config.tts_max_chars]
    if not text:
        raise HTTPException(422, "No text to speak.")

    try:
        audio = await tts_module.synthesize(
            pool,
            text,
            game.voice,
            instruct=body.instruct,
            voice_samples_dir=settings.voice_samples_dir,
            **tts_module.backend_call_kwargs(app_config),
        )
    except TtsError as exc:
        logger.error("tts synthesis failed session=%s: %s", session.id, exc)
        raise HTTPException(503, str(exc))
    return Response(content=audio, media_type="audio/wav")


@router.post("/{session_id}/speak-stream")
async def speak_stream(
    body: SpeakRequest,
    session: Session = Depends(get_session_or_404),
    app_config: AppConfig = Depends(get_app_config),
    settings: Settings = Depends(get_settings),
    pool: ProcessPoolExecutor = Depends(get_tts_pool),
):
    """Same persona-voice resolution, text truncation, and 422s as /speak
    above - called on demand from the read-aloud button (ChatBubble.tsx)
    and voice mode (VoiceCallPage.tsx), neither of which can afford to
    wait for a whole reply's synthesis to finish before hearing anything.
    Streams raw PCM16LE mono audio via tts_module.synthesize_stream as
    mlx-audio produces it, rather than one complete WAV file - see that
    function's docstring for why (verified live: cuts time-to-first-audio
    from several seconds down to a few hundred milliseconds). The sample
    rate rides out as an X-Sample-Rate header, not inside the byte stream
    itself, since a caller needs it before it can even start decoding
    (there's no WAV header here to carry it instead)."""
    game = get_game_or_404(session.game_id)
    if not game.voice:
        raise HTTPException(422, "This persona has no voice configured.")

    text = body.text.strip()[: app_config.tts_max_chars]
    if not text:
        raise HTTPException(422, "No text to speak.")

    try:
        sample_rate, chunks = await tts_module.synthesize_stream(
            pool,
            text,
            game.voice,
            instruct=body.instruct,
            voice_samples_dir=settings.voice_samples_dir,
            **tts_module.backend_call_kwargs(app_config),
        )
    except TtsError as exc:
        logger.error("tts stream synthesis failed session=%s: %s", session.id, exc)
        raise HTTPException(503, str(exc))
    return StreamingResponse(
        chunks,
        media_type="application/octet-stream",
        headers={"X-Sample-Rate": str(sample_rate)},
    )


@router.post("/{session_id}/voice-turn", response_model=VoiceTurnResponse)
async def voice_turn(
    audio: UploadFile = File(...),
    session: Session = Depends(get_session_or_404),
    app_config: AppConfig = Depends(get_app_config),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Section F's voice mode end to end (F3 - see docs/ARCHITECTURE.md's
    "Voice mode"): `audio` is the turn's raw mic capture as a WAV file. A
    model that reports AUDIO_INPUT_CAPABILITY hears it directly (agent.voice's
    to_audio_message/generate_voice_turn); every other model gets it
    transcribed locally first (services.stt.stt) and only the resulting
    text is sent - see agent/voice.py's own docstring for why. 422 when
    transcription is needed but transformers isn't installed, or when the
    clip transcribes to nothing - the same "config fact, not a service
    outage" shape as /speak's missing-voice 422 above."""
    game = _resolved_game(get_game_or_404(session.game_id), settings_repo)
    providers = get_available_models(settings_repo)
    audio_capable = has_capability(providers, game.provider, game.model, AUDIO_INPUT_CAPABILITY)

    num_ctx = _num_ctx_for(game, app_config)
    session_repo = get_session_repo()
    message_repo = get_message_repo()
    summary, recent = get_context(session_repo, message_repo, session.id, app_config.keep_last_messages)
    system_prompt = build_voice_system_prompt(game, summary)
    audio_bytes = await audio.read()

    generate_kwargs: dict[str, bytes | str]
    if audio_capable:
        generate_kwargs = {"audio": audio_bytes}
    else:
        try:
            transcript = await asyncio.to_thread(
                stt_module.transcribe_wav_bytes, audio_bytes, app_config.stt_model_repo
            )
        except SttUnavailableError as exc:
            raise HTTPException(422, str(exc))
        if not transcript.strip():
            raise HTTPException(422, "Couldn't hear anything in that clip.")
        generate_kwargs = {"transcript": transcript}

    try:
        turn = await asyncio.to_thread(
            generate_voice_turn,
            system_prompt,
            recent,
            game.provider,
            game.model,
            num_ctx,
            app_config.keep_alive,
            enable_thinking=app_config.enable_thinking,
            **generate_kwargs,
        )
    except (httpx.TransportError, ResponseError) as exc:
        logger.error("voice turn failed session=%s: %s", session.id, exc)
        raise HTTPException(502, describe_llm_error(exc))
    except ProviderConfigError as exc:
        logger.error("voice turn failed session=%s: %s", session.id, exc)
        raise HTTPException(502, str(exc))

    message_repo.add(session.id, "user", turn.user_said)
    reply_text = " ".join(segment.text for segment in turn.segments)
    message_repo.add(session.id, "assistant", reply_text)
    if message_repo.count_role(session.id, "user") == 1:
        session_repo.update_title(session.id, _title_from_message(turn.user_said))

    return VoiceTurnResponse(
        user_said=turn.user_said,
        segments=[VoiceSegmentResponse(text=s.text, delivery=s.delivery) for s in turn.segments],
    )
