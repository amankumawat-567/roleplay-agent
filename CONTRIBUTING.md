# Contributing

This is a small, single-user local app - the bar for a contribution is
"does it work, is it tested, does it match the existing style," not a
formal process.

## Prerequisites

- Python >= 3.11
- Node.js (for `dev-ui/`)
- [Ollama](https://ollama.com), running locally, with at least one model
  pulled (`ollama pull llama3.1` or whatever your games use)
- [`uv`](https://docs.astral.sh/uv/) is the fastest path (there's a
  committed `uv.lock`); plain `pip` works too, see below

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
make install          # pip install -e ".[dev]" + npm install + npm run build (dev-ui/) + playwright install chromium
ollama pull llama3.1
```

Equivalent with `uv`:

```bash
uv sync --extra dev
uv run playwright install chromium
cd dev-ui && npm install && npm run build && cd ..
```

## Running it

```bash
make dev        # uvicorn roleplay_agent.main:app --reload, serves the built dev-ui/dist/ SPA at :8000
```

For frontend iteration with hot reload, run the UI's own dev server against
a separately-running backend:

```bash
make dev         # terminal 1 - backend on :8000
make ui-dev       # terminal 2 - Vite dev server on :5173, proxies /api to :8000
```

## Tests and type checking

```bash
pytest                        # backend
cd dev-ui && npx tsc -b --noEmit   # frontend type check
```

Use exactly `npx tsc -b --noEmit`, not `npx tsc --noEmit -p .` - the latter
silently misses real errors in this project's tsconfig project-references
setup.

- `tests/unit/` - one component at a time, real objects over mocks
  wherever practical (a real temp-file SQLite `Database` instead of
  mocking sqlite, a real streaming-capable fake chat model
  (`langchain_core`'s `GenericFakeChatModel`) instead of a hand-rolled
  stub).
- `tests/api/` - through the actual FastAPI app via `TestClient`, with
  `tests/conftest.py`'s `app_env` fixture pointing every cached singleton
  at an isolated tmp data dir for that one test.
- `tests/integration/` - a full session lifecycle (create -> chat ->
  resume) through the real app wiring.

## Code style

- **Python**: [ruff](https://docs.astral.sh/ruff/) is enforced -
  ```bash
  ruff check .
  ruff format .
  ```
- **TypeScript**: match the existing code (function components, hooks,
  Zustand for shared state, Tailwind v4 utility classes) - there's no
  separate linter configured beyond `tsc` above.
- **Docs**: this repo's docs are deliberately terse and decision-annotated
  - they explain *why*, not just *what* (see `docs/ARCHITECTURE.md` and
  `docs/GAME.md` for the house style). If your change touches a doc, match
  that tone rather than writing generic boilerplate. Add a durable design
  decision to `docs/ARCHITECTURE.md`.

## Adding things

- **A new skill** (in-conversation tool): `docs/SKILLS.md`.
- **A new voice**: `docs/AUDIO.md`.
- **A new persona/game**: `docs/GAME.md`.

## Configuration

Two separate objects (`src/roleplay_agent/config/settings.py`), not one -
see `docs/ARCHITECTURE.md`'s "Config hygiene" for why:

- **`Settings`** - environment/infra only (`host`, `port`, `data_dir`,
  `log_level`), sourced from `configs/app.yaml` and overridable via
  `ROLEPLAY_*` environment variables / a `.env` file, in that precedence
  order.
- **`AppConfig`** - everything else (model/generation behavior, research,
  transcript, TTS settings), sourced *only* from `configs/*.yaml`
  (`models.yaml`, `research.yaml`, `transcript.yaml`, `tts.yaml`) - no
  `ROLEPLAY_*` env var touches these, by design, so a stray env var can
  never silently diverge from what's checked in.

## Maintenance scripts

```bash
python scripts/research.py <game_id>   # run the one-shot web research step
python scripts/seed_games.py           # import legacy configs/<id>.yaml into data/games/ (idempotent)
python scripts/cleanup.py              # VACUUM the sqlite db
```

## Pull requests

- Keep unrelated churn out of a PR - a docs fix and a feature change
  don't belong in the same diff.
- Run `pytest` and the frontend `tsc` check above before opening one.
- If you touched `docs/`, keep the terse/decision-documented style rather
  than adding generic explanations already implied by the code.

## Platform notes

`make` isn't available out of the box on Windows. Every target is a thin
wrapper around plain commands - run these directly if you don't have
`make`:

| Target | Plain command |
| --- | --- |
| `make install` | `make ui-build` then `pip install -e ".[dev]"` then `playwright install chromium` |
| `make ui-install` | `cd dev-ui && npm install` |
| `make ui-build` | `cd dev-ui && npm install && npm run build` |
| `make ui-dev` | `cd dev-ui && npm run dev` |
| `make dev` | `uvicorn roleplay_agent.main:app --reload` |
| `make run` | `uvicorn roleplay_agent.main:app --host 0.0.0.0 --port 8000` |
| `make test` | `pytest` |
| `make seed-games` | `python scripts/seed_games.py` |
| `make research GAME=<id>` | `python scripts/research.py <id>` |
| `make cleanup` | `python scripts/cleanup.py` |

`ffmpeg` is needed for the yt-dlp/transcript-import path (turning a media
URL into a persona draft) - install it per OS:

```bash
brew install ffmpeg          # macOS
sudo apt install ffmpeg      # Debian/Ubuntu
choco install ffmpeg         # Windows (Chocolatey)
scoop install ffmpeg         # Windows (Scoop)
```

**Docker** sidesteps all of the above - it's already in the repo
(`Dockerfile`, `docker-compose.yml`) and is the platform-agnostic option if
you'd rather not install Python/Node/ffmpeg locally at all:

```bash
make docker-up   # docker compose up --build
```

The app container talks to Ollama running on your host machine (see
`docker-compose.yml` - `OLLAMA_HOST` points at `host.docker.internal`; on
Linux you'll need to uncomment its `extra_hosts` block).
