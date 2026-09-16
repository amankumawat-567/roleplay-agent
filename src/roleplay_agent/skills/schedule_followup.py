import time
from typing import Annotated

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import InjectedState

from roleplay_agent.config.settings import AppConfig, Settings
from roleplay_agent.services.storage.database import Database
from roleplay_agent.services.storage.repositories import FollowupRepository
from roleplay_agent.skills.registry import register

SKILL_ID = "schedule_followup"

_MIN_MINUTES = 1
_MAX_MINUTES = 24 * 60  # a day out - "check back later," not an open-ended reminder


def build_schedule_followup_tool(settings: Settings, app_config: AppConfig) -> BaseTool:
    # A fresh Database/FollowupRepository per tool instance - same thin
    # per-call-connection pattern every other repository in this codebase
    # uses (see storage/database.py), so there's no shared connection to
    # manage across the tool's lifetime.
    followup_repo = FollowupRepository(Database(settings.db_path))

    # session_id is read straight from the live graph state via
    # InjectedState (agent/context.ChatState already carries it) instead
    # of being a model-supplied argument - the model has no business
    # knowing or inventing session ids, and InjectedState args are
    # automatically excluded from the schema the model sees.
    @tool
    def schedule_followup(
        minutes: float, reason: str, session_id: Annotated[str, InjectedState("session_id")]
    ) -> str:
        """Schedule yourself to check back in on this conversation later -
        a real message the user will see even if they've closed the app,
        not just a promise. Use this when you tell the user you'll follow
        up, check on them, or think of something later. `minutes` is how
        long from now to wait (1 to 1440, i.e. up to a day out). `reason`
        is a short private note to yourself about what prompted this and
        what to bring up when you check back - the user never sees it."""
        clamped = max(_MIN_MINUTES, min(_MAX_MINUTES, minutes))
        followup_repo.schedule(session_id, time.time() + clamped * 60, reason)
        return f"Scheduled - you'll check back in {clamped:.0f} minute(s)."

    return schedule_followup


register(SKILL_ID, build_schedule_followup_tool)
