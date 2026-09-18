import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from roleplay_agent.config.settings import Settings, get_settings
from roleplay_agent.schema.voices import ClonedVoiceInfo, ClonedVoicesResponse
from roleplay_agent.services.tts import SUPPORTED_VOICES, WavValidationError, list_cloned_voices, validate_wav

router = APIRouter(prefix="/api/voices", tags=["voices"])

# Content-type -> file extension, same allowlist/rationale as games.py's
# own _ALLOWED_COVER_TYPES (not sniffed from bytes - single-user local
# tool, not a public upload surface) - kept as a separate copy rather than
# a shared import since it's each route module's own private detail.
_ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

_SLUG_COLLAPSE_RE = re.compile(r"[^a-z0-9]+")


def _slug_for_name(name: str, taken: set[str]) -> str:
    """Directory-safe id derived from a display name, disambiguated with a
    numeric suffix on collision - same approach as GameLoader.slug_for_title."""
    base = _SLUG_COLLAPSE_RE.sub("-", name.strip().lower()).strip("-") or "voice"
    slug = base
    n = 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def _voice_info(voice_id: str, samples_dir: Path) -> ClonedVoiceInfo:
    """Builds the frontend-facing name/image for a cloned voice id. Falls
    back to a capitalized id (the frontend's own previous behavior, see
    AudioPage's now-removed clonedVoiceEntry) when there's no `<id>.json`
    sidecar - true for any voice dropped in by hand per docs/AUDIO.md
    rather than created via POST /cloned below."""
    name = voice_id[:1].upper() + voice_id[1:] if voice_id else voice_id
    meta_path = samples_dir / f"{voice_id}.json"
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text())
            name = data.get("name") or name
        except (json.JSONDecodeError, OSError):
            pass

    image = None
    for ext in _ALLOWED_IMAGE_TYPES.values():
        candidate = samples_dir / f"{voice_id}{ext}"
        if candidate.exists():
            image = candidate.name
            break

    return ClonedVoiceInfo(id=voice_id, name=name, image=image)


@router.get("/cloned", response_model=ClonedVoicesResponse)
def get_cloned_voices(settings: Settings = Depends(get_settings)):
    """Voice ids discovered purely by presence in data/voice_samples/ - see
    llm.tts.list_cloned_voices. No registration step: dropping a correctly
    formatted WAV in (scripts/extract_audio_sample.py), or using POST
    /cloned below, is the whole workflow, and this is how the frontend's
    VoicePicker/AudioPage learn about one without a hardcoded entry in
    dev-ui/src/data/voices.ts."""
    samples_dir = settings.voice_samples_dir
    return ClonedVoicesResponse(
        voices=[_voice_info(voice_id, samples_dir) for voice_id in list_cloned_voices(samples_dir)]
    )


@router.post("/cloned", response_model=ClonedVoiceInfo, status_code=201)
async def create_cloned_voice(
    name: str = Form(...),
    wav: UploadFile = File(...),
    image: UploadFile | None = File(None),
    settings: Settings = Depends(get_settings),
):
    """Adds a new voice-cloning reference clip - the "Add audio" form's
    submit handler. `wav` is validated against validate_wav's rules
    (mono, 16-bit PCM, RIFF/WAVE header, size/duration bounds) and rejected
    with a specific reason on failure rather than silently accepted the way
    a hand-dropped file (docs/AUDIO.md) is."""
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(422, "Name is required.")

    image_ext = None
    if image is not None and image.filename:
        image_ext = _ALLOWED_IMAGE_TYPES.get(image.content_type or "")
        if not image_ext:
            raise HTTPException(422, f"Unsupported image type: {image.content_type!r}")

    wav_bytes = await wav.read()
    try:
        validate_wav(wav_bytes)
    except WavValidationError as exc:
        raise HTTPException(422, str(exc)) from exc

    samples_dir = settings.voice_samples_dir
    samples_dir.mkdir(parents=True, exist_ok=True)
    taken = set(SUPPORTED_VOICES) | set(list_cloned_voices(samples_dir))
    voice_id = _slug_for_name(clean_name, taken)

    (samples_dir / f"{voice_id}.wav").write_bytes(wav_bytes)
    (samples_dir / f"{voice_id}.json").write_text(json.dumps({"name": clean_name}))

    image_filename = None
    if image is not None and image_ext:
        image_bytes = await image.read()
        image_filename = f"{voice_id}{image_ext}"
        (samples_dir / image_filename).write_bytes(image_bytes)

    return ClonedVoiceInfo(id=voice_id, name=clean_name, image=image_filename)
