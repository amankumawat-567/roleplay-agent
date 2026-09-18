# Adding a voice

There are two independent things a "voice" means here, and adding one only
covers the frontend-visible half unless you also have live synthesis
installed for the backend `configs/tts.yaml`'s `backend` names:

- **Voice picking + preview** - works everywhere, no dependencies. A
  short pre-recorded clip lets you audition a voice before assigning it to
  a persona.
- **Live synthesis** (`POST /api/sessions/{id}/speak`, the read-aloud
  button in chat) - real text-to-speech via whichever backend
  `configs/tts.yaml`'s `backend` names (see `docs/ARCHITECTURE.md`'s
  "Local text-to-speech"): `chatterbox` (cross-platform) or `qwen3`
  (`mlx-audio`, Apple Silicon only). Missing that backend's own optional
  dependency 503s this endpoint with a clear message instead of pretending
  to work - see "Installing live synthesis" below.

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
   whether it needs to be a curated preset name depends on the backend
   `configs/tts.yaml`'s `backend` currently names:
   - **`qwen3`**: it needs to be one of the real preset speakers that
     backend's model actually supports.
     `src/roleplay_agent/services/tts/tts.py`'s `SUPPORTED_VOICES` is the
     curated, verified subset (`ryan`, `aiden`, `dylan`, `serena`,
     `vivian`) of the model's real 9 speakers - it must stay in sync with
     `voices.ts`. Adding a voice id that *isn't* in `SUPPORTED_VOICES` gets
     you preview-only under this backend: the picker shows it, but a
     persona assigned it will fail `/speak` at synthesis time. (A WAV
     placed under `data/voice_samples/` whose name is *not* a preset id is
     treated differently - as a voice-cloning reference clip against
     `configs/tts.yaml`'s `qwen3.clone_model_repo` - a separate, heavier
     path; see `docs/ARCHITECTURE.md`'s "Local text-to-speech" if you need
     that instead of a preset.)
   - **`chatterbox`**: there's no preset list at all - every synthesizable
     voice is a cloned reference clip, i.e. the same `.wav` you dropped
     under `data/voice_samples/` in step 1 *is* the synthesis voice, no
     extra config needed. A `voice:` naming a qwen3 preset id (e.g.
     `ryan`) fails `/speak` under this backend with a clear "no preset
     speakers" error.

## Installing live synthesis

Real synthesis depends on the optional extra matching
`configs/tts.yaml`'s `backend` (`pyproject.toml`'s
`[project.optional-dependencies]`):

- **`chatterbox`**: pulls in the `chatterbox-tts` pip package (plain
  PyTorch - CPU/CUDA/MPS, works on any platform). Install with either:

  ```bash
  uv sync --extra tts-chatterbox
  # or
  pip install -e ".[tts-chatterbox]"
  ```

- **`qwen3`**: pulls in `mlx-audio` - and transitively `mlx`, which
  **only ships macOS/arm64 wheels**. Install on Apple Silicon with either:

  ```bash
  uv sync --extra tts
  # or
  pip install -e ".[tts]"
  ```

The first call to `/speak` loads the configured backend's model
(`configs/tts.yaml`'s `chatterbox.model_repo` or `qwen3.model_repo`,
resolved from Hugging Face on first use and cached after) into a
persistent worker process and reuses it for every call after - budget
several real seconds for a cold first call.

**Windows/Linux**: use the `chatterbox` backend - it's cross-platform.
`qwen3`/`mlx-audio` simply isn't installable there today (no non-macOS/arm64
`mlx` wheel exists); with `backend: qwen3` set, voice picking, preview
clips, and assigning a `voice:` to a persona all still work - only the live
`/speak` call is affected there, and it fails as a clean `503` (frontend
falls back to the browser's own `speechSynthesis`) rather than a crash or a
hang.
