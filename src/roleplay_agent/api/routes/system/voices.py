from fastapi import APIRouter, Depends

from roleplay_agent.config.settings import Settings, get_settings
from roleplay_agent.schema.voices import ClonedVoicesResponse
from roleplay_agent.services.tts import list_cloned_voices

router = APIRouter(prefix="/api/voices", tags=["voices"])


@router.get("/cloned", response_model=ClonedVoicesResponse)
def get_cloned_voices(settings: Settings = Depends(get_settings)):
    """Voice ids discovered purely by presence in data/voice_samples/ - see
    llm.tts.list_cloned_voices. No registration step: dropping a correctly
    formatted WAV in (scripts/extract_audio_sample.py) is the whole
    workflow, and this is how the frontend's VoicePicker/AudioPage learn
    about one without a hardcoded entry in dev-ui/src/data/voices.ts."""
    return ClonedVoicesResponse(voices=list_cloned_voices(settings.voice_samples_dir))
