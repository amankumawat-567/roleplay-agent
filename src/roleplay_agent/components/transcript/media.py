"""Universal "any URL -> transcript" pipeline (see docs/ARCHITECTURE.md's
"Three ways to create a persona"). yt-dlp resolves the URL against
whichever of its ~1800 site extractors matches (YouTube, Vimeo, TikTok,
X/Twitter, SoundCloud, podcast RSS items, raw audio/video links, ...) and
probes for existing captions/subtitles first - manual, then
auto-generated. Only when neither exists does it fall back to downloading
audio and transcribing it locally via services/stt/stt.py's Hugging Face
`transformers` ASR pipeline (configs/transcript.yaml's `model_repo`).
Captions are near-instant and effectively free; the audio+STT path is the
slow, CPU/GPU-heavy path, so it's deliberately the fallback, not the
default.

`transformers` is an optional dependency (`pip install
'.[transcribe]'`) - the actual model loading lives in services/stt/
(shared with voice mode's own STT fallback, so the two features don't
each load a separate model instance), imported lazily there so the app
runs fine (and the caption-first path works) with it never installed.
Every request that needs it just raises TranscriptFetchError with an
install hint until then.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import httpx
import yt_dlp

from roleplay_agent.services.stt import SttUnavailableError, transcribe_file

# A bare id someone copy-pasted straight out of a YouTube URL - yt-dlp
# itself needs a real URL, so this is rewritten to one before dispatch.
_BARE_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_PREFERRED_LANGS = ("en", "en-US", "en-GB", "en-orig")
# Priority order, not the order yt-dlp lists them in: vtt/srt are plain
# cue-text formats a simple line-based strip handles well; json3/ttml are
# YouTube-specific auto-caption formats used only when nothing better is
# offered.
_PARSEABLE_EXTS = ("vtt", "srt", "json3", "ttml", "srv3", "srv1")

_TIMESTAMP_RE = re.compile(r"\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}")
_TAG_RE = re.compile(r"<[^>]+>")


class TranscriptFetchError(Exception):
    """No usable extractor/captions/audio for the given URL, or a real
    fetch/transcription failure - yt-dlp and transformers' own exception
    messages are already human-readable, so this just wraps them under one
    type the route can catch and turn into a 422."""


def normalize_url(url_or_id: str) -> str:
    """Resolve any URL yt-dlp supports (YouTube, Vimeo, TikTok, X/Twitter,
    SoundCloud, podcast RSS items, raw audio/video links, ...), plus a bare
    YouTube id someone copy-pasted straight out of a URL."""
    text = url_or_id.strip()
    if _BARE_YOUTUBE_ID_RE.match(text):
        return f"https://www.youtube.com/watch?v={text}"
    return text


def download_audio(url_or_id: str, tmp_dir: Path) -> Path:
    """Download the best audio track for any yt-dlp-supported URL into
    `tmp_dir` as a WAV file and return its path. Raises TranscriptFetchError
    on anything that goes wrong (unsupported URL, extractor/ffmpeg failure)."""
    url = normalize_url(url_or_id)
    outtmpl = str(tmp_dir / "audio.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav", "preferredquality": "192"}],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        # Same reasoning as _probe: a third-party extractor/ffmpeg
        # postprocessor call, not our own code.
        raise TranscriptFetchError(str(exc) or f"Couldn't download audio for: {url}") from exc

    audio_path = tmp_dir / "audio.wav"
    if not audio_path.exists():
        raise TranscriptFetchError(f"Couldn't extract audio from: {url}")
    return audio_path


def _probe(url: str) -> dict:
    ydl_opts = {"skip_download": True, "quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as exc:
        # Deliberately broad, not our usual narrow catch: this call runs
        # one of yt-dlp's ~1800 site-specific extractors against a live
        # third-party page, and a broken/changed site can make one raise
        # something other than its own DownloadError (seen live: a bare
        # TypeError from a extractor bug) - any of that should surface as
        # a clean 422 on this URL, not a 500 for the whole route.
        raise TranscriptFetchError(str(exc) or f"Couldn't fetch: {url}") from exc


def _pick_caption_track(info: dict) -> tuple[str, str] | None:
    """Manual subtitles first (a human wrote them), then auto-generated -
    within each, a preferred English variant if there is one, else
    whatever language happens to be first."""
    for source in ("subtitles", "automatic_captions"):
        tracks = info.get(source) or {}
        if not tracks:
            continue
        lang = next((code for code in _PREFERRED_LANGS if code in tracks), next(iter(tracks)))
        formats = {fmt.get("ext"): fmt for fmt in tracks[lang]}
        for ext in _PARSEABLE_EXTS:
            if ext in formats:
                return formats[ext]["url"], ext
    return None


def _parse_json3(raw: str) -> str:
    data = json.loads(raw)
    parts = []
    for event in data.get("events", []):
        for seg in event.get("segs") or []:
            text = seg.get("utf8", "")
            if text and text != "\n":
                parts.append(text)
    return "".join(parts)


def _parse_cue_text(raw: str) -> str:
    """vtt/srt/ttml/srv - line-based cue formats. Strips headers, cue
    index/timestamp lines and inline tags, and drops immediate repeats
    (rolling auto-captions re-emit the previous line as context)."""
    lines: list[str] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line == "WEBVTT" or line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        if line.isdigit() or _TIMESTAMP_RE.match(line):
            continue
        line = _TAG_RE.sub("", line).strip()
        if line and (not lines or lines[-1] != line):
            lines.append(line)
    return " ".join(lines)


def _fetch_caption_text(sub_url: str, ext: str) -> str:
    response = httpx.get(sub_url, timeout=30)
    response.raise_for_status()
    raw = response.text
    return _parse_json3(raw) if ext == "json3" else _parse_cue_text(raw)


def _transcribe_audio(url: str, model_repo: str, quantize: str | None = None) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = download_audio(url, Path(tmp))
        try:
            return transcribe_file(audio_path, model_repo, quantize)
        except SttUnavailableError as exc:
            raise TranscriptFetchError(f"{exc} (needed to transcribe videos that have no captions).") from exc


def fetch_transcript(url_or_id: str, max_chars: int, model_repo: str, quantize: str | None = None) -> str:
    """Captions when they exist (near-instant), local STT transcription of
    the downloaded audio when they don't - `model_repo`/`quantize` are
    `app_config.stt_model_repo`/`app_config.stt_quantize` (model_repo
    required, no default baked in here - see that field's own docstring).
    Truncates to max_chars so a long source can't blow the
    draft-generation prompt's budget."""
    url = normalize_url(url_or_id)
    info = _probe(url)

    track = _pick_caption_track(info)
    text = _fetch_caption_text(*track) if track else _transcribe_audio(url, model_repo, quantize)

    text = " ".join(text.split())
    if not text:
        raise TranscriptFetchError(f"No speech or captions found for: {url_or_id}")
    return text[:max_chars]
