from pydantic import BaseModel

# The local user's own default look until they pick one - dev-ui/src/data/
# profileAvatars.ts's first curated option, must stay in sync (same
# precedent as llm.tts.SUPPORTED_VOICES / dev-ui/src/data/voices.ts).
DEFAULT_AVATAR_ID = "profile-avatar"


class ProfileOut(BaseModel):
    avatar_id: str = DEFAULT_AVATAR_ID
    display_name: str | None = None


class ProfileUpdateRequest(BaseModel):
    avatar_id: str
    display_name: str | None = None


class ProfileStats(BaseModel):
    """Account-level totals - the honest substitute for a game's "Wins /
    Total games / Finals" (see docs/ARCHITECTURE.md's "Profile page"):
    there's no competition or levels in a single-user companion chat app,
    just how much of it you've actually done."""

    persona_count: int
    session_count: int
    message_count: int
    played_seconds: float


class RecentActivityItem(BaseModel):
    kind: str  # "session" | "persona"
    title: str
    game_id: str | None = None
    created_at: float


class ProfileStatsResponse(BaseModel):
    stats: ProfileStats
    recent_activity: list[RecentActivityItem]
