from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str | None = None


class SpeakRequest(BaseModel):
    text: str
    # Emotion/delivery instruction for mlx-audio's CustomVoice `instruct`
    # param (see docs/ARCHITECTURE.md's "Local text-to-speech" and "Voice
    # mode" - a SpeechSegment's `delivery` field is the intended source of
    # this for a voice-mode turn; text mode's plain read-aloud button just
    # omits it, same as before).
    instruct: str | None = None


class VoiceSegmentResponse(BaseModel):
    text: str
    delivery: str | None = None


class VoiceTurnResponse(BaseModel):
    """POST /api/sessions/{id}/voice-turn's response - segments only, no
    audio inline. The frontend synthesizes each segment itself via the
    existing /speak endpoint (passing `delivery` as `instruct`), so this
    stays small JSON rather than duplicating TTS here."""

    user_said: str
    segments: list[VoiceSegmentResponse]
