# Adding a voice

There are two independent things a "voice" means here, and adding one only
covers the frontend-visible half unless you also have a Mac:

- **Voice picking + preview** - works everywhere, no dependencies. A
  short pre-recorded clip lets you audition a voice before assigning it to
  a persona.
- **Live synthesis** (`POST /api/sessions/{id}/speak`, the read-aloud
  button in chat) - real text-to-speech via `mlx-audio`, which only ships
  wheels for Apple Silicon. Everywhere else this endpoint 503s with a clear
  message instead of pretending to work - see "Installing live synthesis"
  below.

## Adding a new preview voice

1. **Drop a `.wav` into `data/voice_samples/`**, named `<voice_id>.wav`
   (e.g. `data/voice_samples/nova.wav`). This directory is served directly
   at `/media/voice-samples/<voice_id>.wav` (`main.py` mounts
   `settings.voice_samples_dir` as static files) - no build step, no
   copying into the frontend.

2. **Add the matching entry to `dev-ui/src/data/voices.ts`**:

   ```ts
   export const VOICES: Voice[] = [
     // ...
     {
       id: "nova",
       name: "Nova",
       style: "Short description of the voice",
       colors: ["#hexFrom", "#hexTo"],
     },
   ];
   ```

   - `id` must match the `.wav` filename (minus extension) - it's also
     what a persona's `game.yaml` sets as `voice:`.
   - `colors` is a `[from, to]` gradient pair used for the card's glow and
     detail-rail accent (the avatar's own art comes from a separate
     vendored SVG, not this gradient).
   - `sampleUrlFor(id)` in the same file builds the `/media/voice-samples/`
     URL - you don't need to touch it.

3. **If this id is also meant to be synthesizable** (not just previewable),
   it needs to be one of the real preset speakers the TTS model actually
   supports. `src/roleplay_agent/services/tts/tts.py`'s `SUPPORTED_VOICES`
   is the curated, verified subset (`ryan`, `aiden`, `dylan`, `serena`,
   `vivian`) of the model's real 9 speakers - it must stay in
   sync with `voices.ts`. Adding a voice id that *isn't* in
   `SUPPORTED_VOICES` gets you preview-only: the picker shows it, but a
   persona assigned it will fail `/speak` at synthesis time. (A WAV placed
   under `data/voice_samples/` whose name is *not* a preset id is treated
   differently - as a voice-cloning reference clip - which is a separate,
   heavier path; see `configs/tts.yaml`'s `clone_model_repo` comment and
   `docs/ARCHITECTURE.md`'s "Local text-to-speech" if you need that instead
   of a preset.)

## Installing live synthesis

Real synthesis depends on the optional `tts` extra
(`pyproject.toml`'s `[project.optional-dependencies]`), which pulls in
`mlx-audio` - and transitively `mlx`, which **only ships macOS/arm64
wheels**. Install it on Apple Silicon with either:

```bash
uv sync --extra tts
# or
pip install -e ".[tts]"
```

The first call to `/speak` loads the model (`configs/tts.yaml`'s
`model_repo`, resolved from Hugging Face on first use, ~1GB, cached after)
into a persistent worker process and reuses it for every call after -
budget several real seconds for a cold first call.

**Windows/Linux**: `mlx-audio` simply isn't installable there today (no
non-macOS/arm64 `mlx` wheel exists). Voice picking, preview clips, and
assigning a `voice:` to a persona all still work - only the live `/speak`
call is affected, and it fails as a clean `503` (frontend falls back to the
browser's own `speechSynthesis`) rather than a crash or a hang. There's no
config flag for this - it's a hard platform constraint of the `mlx`
dependency, not a feature this app chooses to gate.
