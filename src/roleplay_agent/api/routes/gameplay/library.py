from fastapi import APIRouter

from roleplay_agent.api.dependencies import get_game_loader, get_session_repo
from roleplay_agent.schema.library import LibraryEntry

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("", response_model=list[LibraryEntry])
def list_library():
    # Only personas with at least one session show up here - this is
    # "games you've played," not every game that exists (that's Explore).
    stats = get_session_repo().library_stats()
    games_by_id = {g.id: g for g in get_game_loader().list_all()}

    entries = [
        LibraryEntry(
            id=game_id,
            title=games_by_id[game_id].title if game_id in games_by_id else data["title"],
            character_name=games_by_id[game_id].character_name if game_id in games_by_id else None,
            tags=games_by_id[game_id].tags if game_id in games_by_id else [],
            cover_image=games_by_id[game_id].cover_image if game_id in games_by_id else None,
            session_count=data["session_count"],
            rounds=data["rounds"],
            played_seconds=data["played_seconds"],
            last_played=data["last_played"],
        )
        for game_id, data in stats.items()
    ]
    entries.sort(key=lambda e: e.last_played, reverse=True)
    return entries
