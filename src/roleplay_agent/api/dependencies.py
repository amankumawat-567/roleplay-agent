from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache

from fastapi import HTTPException
from langchain_core.embeddings import Embeddings
from langchain_core.tools import BaseTool

from roleplay_agent.agents.game_play.agent import RoleplayAgent
from roleplay_agent.agents.research.researcher import Researcher
from roleplay_agent.config.settings import get_app_config, get_settings
from roleplay_agent.games.loader import GameLoader
from roleplay_agent.games.models import Game
from roleplay_agent.games.validator import GameConfigError
from roleplay_agent.services.llm.embeddings import build_embeddings
from roleplay_agent.services.storage.database import Database
from roleplay_agent.services.storage.models import BuilderSession, Session
from roleplay_agent.services.storage.repositories import (
    BuilderMessageRepository,
    BuilderSessionRepository,
    EmbeddingRepository,
    FollowupRepository,
    GameResearchRepository,
    MessageRepository,
    SessionRepository,
    SettingsRepository,
)
from roleplay_agent.services.tts import build_tts_pool
from roleplay_agent.skills import registry as skills_registry


@lru_cache
def get_database() -> Database:
    return Database(get_settings().db_path)


@lru_cache
def get_session_repo() -> SessionRepository:
    return SessionRepository(get_database())


@lru_cache
def get_message_repo() -> MessageRepository:
    return MessageRepository(get_database())


@lru_cache
def get_embedding_repo() -> EmbeddingRepository:
    return EmbeddingRepository(get_database())


@lru_cache
def get_followup_repo() -> FollowupRepository:
    return FollowupRepository(get_database())


@lru_cache
def get_builder_session_repo() -> BuilderSessionRepository:
    return BuilderSessionRepository(get_database())


@lru_cache
def get_builder_message_repo() -> BuilderMessageRepository:
    return BuilderMessageRepository(get_database())


@lru_cache
def get_settings_repo() -> SettingsRepository:
    return SettingsRepository(get_database())


@lru_cache
def get_game_research_repo() -> GameResearchRepository:
    return GameResearchRepository(get_database())


@lru_cache
def get_embeddings() -> Embeddings:
    return build_embeddings(get_app_config().embedding_model)


@lru_cache
def get_skill_tools() -> dict[str, BaseTool]:
    return skills_registry.build_tools(get_settings(), get_app_config())


@lru_cache
def get_tts_pool() -> ProcessPoolExecutor:
    # One process, created lazily - see llm/tts.py's module docstring for
    # why this is a persistent worker process rather than a thread.
    return build_tts_pool()


@lru_cache
def get_game_loader() -> GameLoader:
    return GameLoader(get_settings().games_dir, research_repo=get_game_research_repo())


@lru_cache
def get_researcher() -> Researcher:
    app_config = get_app_config()
    return Researcher(
        loader=get_game_loader(),
        research_repo=get_game_research_repo(),
        user_agent=app_config.research_user_agent,
        max_results=app_config.research_max_results,
        keep_alive=app_config.keep_alive,
        default_num_ctx=app_config.default_num_ctx,
        settings_repo=get_settings_repo(),
        enable_thinking=app_config.enable_thinking,
    )


@lru_cache
def get_agent() -> RoleplayAgent:
    app_config = get_app_config()
    return RoleplayAgent(
        session_repo=get_session_repo(),
        message_repo=get_message_repo(),
        keep_last=app_config.keep_last_messages,
        keep_alive=app_config.keep_alive,
        embedding_repo=get_embedding_repo(),
        embeddings=get_embeddings(),
        skill_tools=get_skill_tools(),
        enable_thinking=app_config.enable_thinking,
    )


def get_game_or_404(game_id: str) -> Game:
    try:
        return get_game_loader().load(game_id)
    except FileNotFoundError:
        raise HTTPException(404, f"No such game: {game_id}")
    except GameConfigError as exc:
        raise HTTPException(422, str(exc))


def get_session_or_404(session_id: str) -> Session:
    session = get_session_repo().get(session_id)
    if not session:
        raise HTTPException(404, "No such session")
    return session


def get_builder_session_or_404(builder_session_id: str) -> BuilderSession:
    session = get_builder_session_repo().get(builder_session_id)
    if not session:
        raise HTTPException(404, "No such builder session")
    return session
