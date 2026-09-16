import asyncio
import time

from roleplay_agent.agents.game_play.agent import RoleplayAgent
from roleplay_agent.components.observability.logging import logger
from roleplay_agent.components.observability.metrics import log_followup_delivered, log_followup_failed
from roleplay_agent.games.loader import GameLoader
from roleplay_agent.services.storage.repositories import FollowupRepository, MessageRepository, SessionRepository

# Matches the roadmap's "~30s" - frequent enough that a scheduled check-back
# never lags noticeably behind its fire_at, infrequent enough to be free at
# single-user scale.
POLL_INTERVAL_SECONDS = 30


async def deliver_due_followups(
    followup_repo: FollowupRepository,
    session_repo: SessionRepository,
    message_repo: MessageRepository,
    game_loader: GameLoader,
    agent: RoleplayAgent,
    default_num_ctx: int,
    now: float | None = None,
) -> int:
    """One polling pass: runs every pending follow-up whose fire_at has
    arrived through the exact same graph a `starter: ai` opening line
    already uses (no incoming user message, just a reason folded into the
    prompt - see agent.prompts.build_system_prompt), then persists the
    reply as a normal assistant message. Durable across restarts because
    due-ness is computed from the stored fire_at, never from anything held
    only in memory.

    A follow-up whose session no longer exists, or whose turn otherwise
    fails (game deleted, model unreachable, ...), is logged and dropped
    rather than retried forever - same "log and move on" choice
    api.routes.chat's _fold_task already makes for its own background
    work. Returns how many were actually delivered."""
    due = followup_repo.due(now if now is not None else time.time())
    delivered = 0
    for followup in due:
        try:
            session = session_repo.get(followup.session_id)
            if session is None:
                continue
            game = game_loader.load(session.game_id)
            initial_state = {
                "session_id": followup.session_id,
                "game": game,
                "num_ctx": game.num_ctx or default_num_ctx,
                "message": None,
                "followup_reason": followup.reason,
                "history": [],
                "reply": "",
            }
            result = await agent.graph.ainvoke(initial_state)
            message_repo.add(followup.session_id, "assistant", result["reply"], kind="followup")
            log_followup_delivered(session_id=followup.session_id)
            delivered += 1
        except Exception:
            log_followup_failed(followup.session_id)
        finally:
            followup_repo.delete(followup.id)
    return delivered


async def run_followup_loop(
    followup_repo: FollowupRepository,
    session_repo: SessionRepository,
    message_repo: MessageRepository,
    game_loader: GameLoader,
    agent: RoleplayAgent,
    default_num_ctx: int,
    interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> None:
    """Runs until cancelled (see main.py's lifespan, which cancels it on
    shutdown). Polling a table instead of an in-process timer is what
    makes a scheduled follow-up survive a server restart in the first
    place - checked once immediately (so anything that came due while the
    server was down fires right away), then every interval_seconds."""
    while True:
        try:
            await deliver_due_followups(
                followup_repo, session_repo, message_repo, game_loader, agent, default_num_ctx
            )
        except Exception:
            logger.exception("followup poll loop failed")
        await asyncio.sleep(interval_seconds)
