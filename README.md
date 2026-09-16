# Roleplay Agent (local, Ollama-powered)

A local companion chat agent with memory. No narration, no scene
descriptions - just plain first-person chat, like an audio drama between
you and the AI.

FastAPI + LangGraph backend, SQLite storage, YAML-defined personas
("games"), a React + TypeScript frontend. See `docs/ARCHITECTURE.md` for
how it's put together.

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
make install                  # pip install -e ".[dev]" + builds dev-ui/ + playwright install chromium
ollama pull llama3.1          # or whatever model your games use
```

Needs Node.js (for `dev-ui/`) in addition to Python.

## Run

```bash
make dev
```

Open http://localhost:8000.

## Authoring a game

See `docs/GAME.md`. Short version: create
`data/games/<your_game_id>/game.yaml` (copy
`data/games/template.yaml.example`).

## More

- `docs/ARCHITECTURE.md` - how the pieces fit together, and why a few
  things are deliberately built the way they are.
- `docs/GAME.md` - persona/game YAML format, running the research
  step, how memory/summarization works.
- `docs/SKILLS.md` - how to add a new in-conversation skill.
- `docs/AUDIO.md` - how to add a new voice.
- `CONTRIBUTING.md` - setup, tests, configuration, maintenance scripts,
  Docker.
