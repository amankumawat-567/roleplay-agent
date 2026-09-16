import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from ollama import ResponseError

from roleplay_agent.agents.game_builder import generate_draft, generate_draft_from_transcript, stream_builder_reply
from roleplay_agent.api.dependencies import (
    get_builder_message_repo,
    get_builder_session_or_404,
    get_builder_session_repo,
    get_settings_repo,
)
from roleplay_agent.components.transcript.media import TranscriptFetchError, fetch_transcript
from roleplay_agent.config.settings import AppConfig, get_app_config
from roleplay_agent.schema.game_builder import (
    BuilderMessage,
    BuilderSessionChatRequest,
    BuilderSessionDetail,
    BuilderSessionDraftRequest,
    BuilderSessionMessagesResponse,
    CreateBuilderSessionRequest,
    CreateBuilderSessionResponse,
    GameDraft,
    TranscriptDraftRequest,
    VideoDraftRequest,
)
from roleplay_agent.services.llm.capabilities import resolve_builder_model
from roleplay_agent.services.llm.errors import describe_llm_error
from roleplay_agent.services.llm.providers import ProviderConfigError
from roleplay_agent.services.storage.models import BuilderSession
from roleplay_agent.services.storage.repositories import BuilderMessageRepository, SettingsRepository

router = APIRouter(prefix="/api/games/builder", tags=["game-builder"])


def _resolved(settings_repo: SettingsRepository, app_config: AppConfig) -> AppConfig:
    """`app_config.builder_provider`/`builder_model` may be unset (no
    override in configs/models.yaml) - resolves them to the computed
    default up front, so `game_builder.py`'s functions (unchanged, still
    just read `app_config.builder_provider`/`builder_model` directly)
    never need to know that resolution happened. Raises ProviderConfigError
    (caught by main.py's global handler) when nothing anywhere is usable."""
    provider, model = resolve_builder_model(settings_repo, app_config)
    if (provider, model) == (app_config.builder_provider, app_config.builder_model):
        return app_config
    return app_config.model_copy(update={"builder_provider": provider, "builder_model": model})


def _with_context(context: str | None, history: list[BuilderMessage]) -> list[BuilderMessage]:
    """Prepends the "here's the persona as it stands today" priming block
    (an "Edit with AI" conversation only) ahead of the persisted history -
    transient grounding for this call, never itself written to
    builder_messages (see schemas/game_builder.py's BuilderSessionChatRequest)."""
    context_messages = [BuilderMessage(role="user", content=context)] if context else []
    return context_messages + history


@router.post("/sessions", response_model=CreateBuilderSessionResponse)
def create_builder_session(body: CreateBuilderSessionRequest):
    session_id = get_builder_session_repo().create(body.title, body.game_id)
    return CreateBuilderSessionResponse(builder_session_id=session_id)


@router.get("/sessions/{builder_session_id}/messages", response_model=BuilderSessionMessagesResponse)
def builder_session_messages(session: BuilderSession = Depends(get_builder_session_or_404)):
    messages = get_builder_message_repo().list_for_session(session.id)
    return BuilderSessionMessagesResponse(
        session=BuilderSessionDetail.model_validate(session),
        messages=[BuilderMessage(role=m.role, content=m.content) for m in messages],
    )


@router.post("/sessions/{builder_session_id}/chat")
def builder_session_chat(
    body: BuilderSessionChatRequest,
    session: BuilderSession = Depends(get_builder_session_or_404),
    message_repo: BuilderMessageRepository = Depends(get_builder_message_repo),
):
    app_config = _resolved(get_settings_repo(), get_app_config())
    message_repo.add(session.id, "user", body.message)
    history = [BuilderMessage(role=m.role, content=m.content) for m in message_repo.list_for_session(session.id)]
    convo = _with_context(body.context, history)

    async def token_stream():
        full = ""
        try:
            async for piece in stream_builder_reply(convo, app_config):
                full += piece
                yield piece
        except (httpx.TransportError, ResponseError) as exc:
            # Same reasoning as api/routes/chat.py: the HTTP status is
            # already committed by the time streaming starts, so this
            # can't become a 503/502 - end the stream with a clear message
            # and skip persisting a broken/partial reply.
            yield f"\n\n[{describe_llm_error(exc)}]"
            return
        except ProviderConfigError as exc:
            yield f"\n\n[{exc}]"
            return
        message_repo.add(session.id, "assistant", full)

    return StreamingResponse(token_stream(), media_type="text/plain")


@router.post("/sessions/{builder_session_id}/draft", response_model=GameDraft)
def builder_session_draft(
    body: BuilderSessionDraftRequest,
    session: BuilderSession = Depends(get_builder_session_or_404),
    message_repo: BuilderMessageRepository = Depends(get_builder_message_repo),
):
    history = [BuilderMessage(role=m.role, content=m.content) for m in message_repo.list_for_session(session.id)]
    app_config = _resolved(get_settings_repo(), get_app_config())
    return generate_draft(_with_context(body.context, history), app_config)


@router.post("/draft-from-transcript", response_model=GameDraft)
def builder_draft_from_transcript(body: TranscriptDraftRequest):
    app_config = get_app_config()
    transcript = body.transcript.strip()[: app_config.transcript_max_chars]
    if not transcript:
        raise HTTPException(422, "Transcript is empty")
    return generate_draft_from_transcript(transcript, _resolved(get_settings_repo(), app_config))


@router.post("/draft-from-video", response_model=GameDraft)
def builder_draft_from_video(body: VideoDraftRequest):
    app_config = get_app_config()
    try:
        transcript = fetch_transcript(body.url, app_config.transcript_max_chars, app_config.whisper_model_size)
    except TranscriptFetchError as exc:
        raise HTTPException(422, str(exc))
    return generate_draft_from_transcript(transcript, _resolved(get_settings_repo(), app_config))
