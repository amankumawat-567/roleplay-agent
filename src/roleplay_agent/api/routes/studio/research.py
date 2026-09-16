from fastapi import APIRouter, Depends

from roleplay_agent.api.dependencies import get_game_or_404, get_researcher
from roleplay_agent.games.models import Game
from roleplay_agent.schema.research import ResearchResponse

router = APIRouter(prefix="/api/games", tags=["research"])


@router.post("/{game_id}/research", response_model=ResearchResponse)
def research_game(game_id: str, game: Game = Depends(get_game_or_404)):
    notes = get_researcher().research(game_id)
    return ResearchResponse(research_notes=notes)
