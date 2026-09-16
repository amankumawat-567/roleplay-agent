from fastapi import APIRouter

from roleplay_agent.api.dependencies import get_message_repo
from roleplay_agent.schema.search import SearchResultOut

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=list[SearchResultOut])
def search_messages(q: str = ""):
    return [SearchResultOut.model_validate(r) for r in get_message_repo().search(q)]
