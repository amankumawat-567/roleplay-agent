from pydantic import BaseModel

from roleplay_agent.services.llm.capabilities import ProviderModels


class ModelsResponse(BaseModel):
    """None `default_provider` means "nothing usable at all right now"
    (Ollama unreachable and no hosted provider key configured) - the
    frontend falls back to empty free-text fields rather than a broken
    pre-fill. `ProviderModels` (llm/capabilities.py) is reused directly
    here rather than a parallel duplicate schema, the same way
    `games/models.py`'s `Game` doubles as `GET /api/games/{id}`'s own
    response model."""

    default_provider: str | None
    providers: list[ProviderModels]
