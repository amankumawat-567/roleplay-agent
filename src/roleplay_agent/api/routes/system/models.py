from fastapi import APIRouter, Depends

from roleplay_agent.api.dependencies import get_settings_repo
from roleplay_agent.schema.models import ModelsResponse
from roleplay_agent.services.llm.capabilities import get_available_models, get_default_provider
from roleplay_agent.services.storage.repositories import SettingsRepository

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=ModelsResponse)
def list_models(settings_repo: SettingsRepository = Depends(get_settings_repo)):
    """Only shows what's actually usable right now - a provider with
    Ollama unreachable, or a hosted provider with no key, doesn't appear
    at all (see llm/capabilities.py), never disabled/greyed-out."""
    providers = get_available_models(settings_repo)
    return ModelsResponse(
        default_provider=get_default_provider(settings_repo, providers),
        providers=providers,
    )
