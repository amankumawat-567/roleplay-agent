"""Extract a short WAV audio sample from any video/audio URL.

Reuses the same universal "any URL" resolution as the transcript pipeline
(src/roleplay_agent/transcript/media.py): yt-dlp picks whichever of its
~1800 site extractors matches (YouTube, Vimeo, TikTok, X/Twitter,
SoundCloud, podcast RSS items, raw audio/video links, ...), including a
bare YouTube id pasted straight out of a URL. ffmpeg then trims the
downloaded audio down to a fixed-length clip.

Usage:
    python scripts/extract_audio_sample.py <url> [output.wav] [--start 30] [--duration 12]
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from roleplay_agent.transcript.media import TranscriptFetchError, download_audio


def _trim(source: Path, dest: Path, start: float, duration: float) -> None:
    # 24000 Hz mono 16-bit PCM - matches data/voice_samples/*.wav's existing
    # convention (the TTS-generated preview clips) and, not coincidentally,
    # mlx-audio's own Qwen3-TTS model.sample_rate (see llm/tts.py) - a
    # voice-cloning reference clip gets resampled to this internally anyway,
    # so producing it at the right rate up front keeps every file in
    # data/voice_samples/ in the same format rather than two conventions.
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss", str(start),
            "-i", str(source),
            "-t", str(duration),
            "-ac", "1",
            "-ar", "24000",
            "-sample_fmt", "s16",
            str(dest),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def extract_sample(url_or_id: str, dest: Path, start: float = 0.0, duration: float = 12.0) -> Path:
    """Download `url_or_id` (any yt-dlp-supported URL, or a bare YouTube id)
    and write a `duration`-second WAV clip (starting at `start` seconds) to
    `dest`. Returns `dest`."""
    with tempfile.TemporaryDirectory() as tmp:
        source = download_audio(url_or_id, Path(tmp))
        _trim(source, dest, start, duration)
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Video/audio URL (anything yt-dlp supports), or a bare YouTube id")
    parser.add_argument("output", nargs="?", default="sample.wav", help="Output WAV path (default: sample.wav)")
    parser.add_argument("--start", type=float, default=0.0, help="Start offset in seconds (default: 0)")
    parser.add_argument("--duration", type=float, default=12.0, help="Clip length in seconds (default: 12)")
    args = parser.parse_args()

    try:
        dest = extract_sample(args.url, Path(args.output), args.start, args.duration)
    except TranscriptFetchError as exc:
        parser.error(str(exc))
    print(f"Wrote {args.duration:g}s sample to {dest}")


if __name__ == "__main__":
    main()
