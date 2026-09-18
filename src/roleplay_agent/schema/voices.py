from pydantic import BaseModel


class ClonedVoiceInfo(BaseModel):
    """One cloned voice as the frontend needs to render it - `id` is the
    filename stem (what a persona's `voice:` field references), `name` is
    the display name given when it was added (or a capitalized fallback of
    `id` for one dropped in by hand with no sidecar metadata - see
    api/routes/system/voices.py's `_voice_info`), `image` is the sibling
    profile-image filename if one was uploaded, servable straight off the
    same /media/voice-samples/ mount as the wav itself."""

    id: str
    name: str
    image: str | None = None


class ClonedVoicesResponse(BaseModel):
    """GET /api/voices/cloned - see llm.tts.list_cloned_voices. Preset
    voices (llm.tts.SUPPORTED_VOICES) aren't included here - the frontend
    already curates those with real names/styles/colors
    (dev-ui/src/data/voices.ts) and doesn't need them re-served."""

    voices: list[ClonedVoiceInfo]
