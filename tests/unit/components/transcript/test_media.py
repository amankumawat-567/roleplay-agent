import pytest

from roleplay_agent.components.transcript import media as media_module
from roleplay_agent.components.transcript.media import (
    TranscriptFetchError,
    _parse_cue_text,
    _parse_json3,
    _pick_caption_track,
    fetch_transcript,
    normalize_url,
)


def test_normalize_url_expands_bare_youtube_id():
    assert normalize_url("  jNQXAC9IVRw  ") == "https://www.youtube.com/watch?v=jNQXAC9IVRw"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://youtu.be/jNQXAC9IVRw",
        "https://vimeo.com/12345",
    ],
)
def test_normalize_url_leaves_real_urls_untouched(url):
    assert normalize_url(url) == url


def test_parse_cue_text_strips_timestamps_tags_and_repeats():
    vtt = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000
<c>hello</c> there

00:00:02.000 --> 00:00:04.000
hello there
general kenobi
"""
    assert _parse_cue_text(vtt) == "hello there general kenobi"


def test_parse_cue_text_drops_cue_index_lines():
    srt = """1
00:00:00,000 --> 00:00:02,000
hello world
"""
    assert _parse_cue_text(srt) == "hello world"


def test_parse_json3_joins_segments():
    raw = '{"events": [{"segs": [{"utf8": "hello "}, {"utf8": "world"}]}]}'
    assert _parse_json3(raw) == "hello world"


def test_pick_caption_track_prefers_manual_over_automatic():
    info = {
        "subtitles": {"en": [{"ext": "vtt", "url": "manual.vtt"}]},
        "automatic_captions": {"en": [{"ext": "vtt", "url": "auto.vtt"}]},
    }
    assert _pick_caption_track(info) == ("manual.vtt", "vtt")


def test_pick_caption_track_falls_back_to_automatic():
    info = {"automatic_captions": {"en": [{"ext": "vtt", "url": "auto.vtt"}]}}
    assert _pick_caption_track(info) == ("auto.vtt", "vtt")


def test_pick_caption_track_none_when_no_tracks():
    assert _pick_caption_track({}) is None


def test_pick_caption_track_skips_unparseable_formats():
    info = {"subtitles": {"en": [{"ext": "mhtml", "url": "x"}]}}
    assert _pick_caption_track(info) is None


class _FakeDownloadError(Exception):
    pass


class _FakeYoutubeDL:
    """Stands in for yt_dlp.YoutubeDL as a context manager."""

    def __init__(self, info=None, probe_error=None):
        self._info = info
        self._probe_error = probe_error

    def __call__(self, opts):
        self._opts = opts
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if self._probe_error:
            raise self._probe_error
        return self._info

    def download(self, urls):
        pass


def _patch_yt_dlp(monkeypatch, fake):
    fake_utils = type("U", (), {"DownloadError": _FakeDownloadError})
    monkeypatch.setattr(media_module, "yt_dlp", type("M", (), {"YoutubeDL": fake, "utils": fake_utils}))


def test_fetch_transcript_uses_captions_when_available(monkeypatch):
    info = {"subtitles": {"en": [{"ext": "vtt", "url": "https://example.com/captions.vtt"}]}}
    _patch_yt_dlp(monkeypatch, _FakeYoutubeDL(info=info))

    class _Resp:
        text = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello world\n"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(media_module.httpx, "get", lambda url, timeout=30: _Resp())

    result = fetch_transcript("https://youtu.be/jNQXAC9IVRw", max_chars=1000)

    assert result == "hello world"


def test_fetch_transcript_falls_back_to_whisper_when_no_captions(monkeypatch):
    _patch_yt_dlp(monkeypatch, _FakeYoutubeDL(info={}))
    monkeypatch.setattr(media_module, "_transcribe_audio", lambda url, model_size: "spoken words here")

    result = fetch_transcript("https://example.com/clip.mp4", max_chars=1000)

    assert result == "spoken words here"


def test_fetch_transcript_truncates_to_max_chars(monkeypatch):
    _patch_yt_dlp(monkeypatch, _FakeYoutubeDL(info={}))
    monkeypatch.setattr(media_module, "_transcribe_audio", lambda url, model_size: "x" * 100)

    result = fetch_transcript("https://example.com/clip.mp4", max_chars=10)

    assert result == "x" * 10


def test_fetch_transcript_wraps_probe_errors(monkeypatch):
    _patch_yt_dlp(monkeypatch, _FakeYoutubeDL(probe_error=_FakeDownloadError("Unsupported URL")))

    with pytest.raises(TranscriptFetchError):
        fetch_transcript("not a url", max_chars=1000)


def test_fetch_transcript_raises_when_nothing_found(monkeypatch):
    _patch_yt_dlp(monkeypatch, _FakeYoutubeDL(info={}))
    monkeypatch.setattr(media_module, "_transcribe_audio", lambda url, model_size: "")

    with pytest.raises(TranscriptFetchError):
        fetch_transcript("https://example.com/silent.mp4", max_chars=1000)


def test_whisper_model_missing_dependency_raises_clear_error(monkeypatch):
    # faster-whisper is an optional extra (`pip install '.[transcribe]'`) -
    # simulate it being absent regardless of whether this environment
    # happens to have it installed (sys.modules[name] = None makes the
    # import raise ModuleNotFoundError, same as a real missing package).
    import sys

    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    media_module._whisper_models.clear()

    with pytest.raises(TranscriptFetchError, match="pip install"):
        media_module._whisper_model("base")
