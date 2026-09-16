from pydantic import BaseModel


class ClonedVoicesResponse(BaseModel):
    """GET /api/voices/cloned - see llm.tts.list_cloned_voices. Preset
    voices (llm.tts.SUPPORTED_VOICES) aren't included here - the frontend
    already curates those with real names/styles/colors
    (dev-ui/src/data/voices.ts) and doesn't need them re-served."""

    voices: list[str]
