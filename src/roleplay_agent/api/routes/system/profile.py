import json

from fastapi import APIRouter, Depends

from roleplay_agent.api.dependencies import get_game_loader, get_session_repo, get_settings_repo
from roleplay_agent.games.loader import GameLoader
from roleplay_agent.schema.profile import (
    DEFAULT_AVATAR_ID,
    ProfileOut,
    ProfileStats,
    ProfileStatsResponse,
    ProfileUpdateRequest,
    RecentActivityItem,
)
from roleplay_agent.services.storage.repositories import SessionRepository, SettingsRepository

router = APIRouter(prefix="/api/profile", tags=["profile"])

# "Recent activity" - the honest substitute for a badge/trophy list (see
# docs/ARCHITECTURE.md's "Profile page"): just the last few sessions
# started and personas created, not a new achievements engine.
_RECENT_ACTIVITY_LIMIT = 6

_PROFILE_KEY = "profile"


@router.get("", response_model=ProfileOut)
def get_profile(settings_repo: SettingsRepository = Depends(get_settings_repo)):
    raw = settings_repo.get(_PROFILE_KEY)
    if raw is None:
        return ProfileOut()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ProfileOut()
    return ProfileOut(**data)


@router.put("", response_model=ProfileOut)
def update_profile(body: ProfileUpdateRequest, settings_repo: SettingsRepository = Depends(get_settings_repo)):
    display_name = (body.display_name.strip() if body.display_name else None) or None
    profile = ProfileOut(avatar_id=body.avatar_id.strip() or DEFAULT_AVATAR_ID, display_name=display_name)
    settings_repo.set(_PROFILE_KEY, profile.model_dump_json())
    return profile


def _recent_activity(game_loader: GameLoader, session_repo: SessionRepository) -> list[RecentActivityItem]:
    items = [
        RecentActivityItem(kind="session", title=s.title, game_id=s.game_id, created_at=s.created_at)
        for s in session_repo.list_all()[:_RECENT_ACTIVITY_LIMIT]
    ]
    # Game.created_at doesn't exist (a persona is just a YAML file, no
    # creation timestamp tracked) - the game.yaml's own mtime is the
    # closest real proxy, same spirit as Ollama's own modified_at-based
    # "most recent" ordering (see llm/capabilities.py).
    for path in game_loader.games_dir.glob("*/game.yaml"):
        try:
            game = game_loader.load(path.parent.name)
        except Exception:
            continue
        items.append(
            RecentActivityItem(
                kind="persona", title=game.title, game_id=game.id, created_at=path.stat().st_mtime
            )
        )
    items.sort(key=lambda i: i.created_at, reverse=True)
    return items[:_RECENT_ACTIVITY_LIMIT]


@router.get("/stats", response_model=ProfileStatsResponse)
def get_profile_stats(
    game_loader: GameLoader = Depends(get_game_loader),
    session_repo: SessionRepository = Depends(get_session_repo),
):
    by_game = session_repo.library_stats()
    stats = ProfileStats(
        persona_count=len(game_loader.list_all()),
        session_count=sum(s["session_count"] for s in by_game.values()),
        message_count=sum(s["rounds"] for s in by_game.values()),
        played_seconds=sum(s["played_seconds"] for s in by_game.values()),
    )
    return ProfileStatsResponse(stats=stats, recent_activity=_recent_activity(game_loader, session_repo))
