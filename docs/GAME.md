# Authoring a game

A "game" is a persona/scenario definition. Three ways to arrive at one:

- **"New persona"** (sidebar or home screen) / the pencil icon on a persona
  card - a form for every field below, saving through `POST`/`PUT
  /api/games`.
- **"Build with AI"** (sidebar or home screen) - chat with an assistant
  about who you want the persona to be, then click "Generate draft" to
  turn the conversation into a persona via a structured-output call. The
  draft opens in the same form above for review - nothing saves until you
  do. This is a separate assistant from the roleplay agent itself
  (`game_builder.py`, `configs/models.yaml`'s `builder_provider`/
  `builder_model`, independent of any persona's own model) - its only job
  is proposing a persona, not playing a character.
- **Hand-edit the YAML** directly - create
  `data/games/<your_game_id>/game.yaml` (copy
  `data/games/template.yaml.example` as a starting point):

```yaml
title: "My Game"
character_name: "Alex"  # optional - who the AI plays, shown in chat instead of title. Falls back to title when blank.
tags: [casual, drama]   # shown as chips in the picker
provider: ollama         # optional - ollama (default) | openai | anthropic, see configs/providers.yaml
model: llama3.1
starter: ai              # ai | user
num_ctx: 8192             # optional - context window to request from Ollama; omit to use the app default
persona: |
  Who the AI plays.
user_role: |
  Who the human is playing.
script: |
  Vague background + beats, not literal dialogue.
research_query: "optional search seed for tone/style lookup"
memory_recall: false    # optional - long-term memory across sessions, see below
skills: []               # optional - in-conversation tools the model can call, see below
```

The directory name (`your_game_id`) becomes the game's id. Do **not** put
`research_notes` in `game.yaml` - the research step writes those separately
to the `game_research` sqlite table (`data/app.db`), so authored content and
generated notes never share a file.

## Using a hosted model instead of Ollama

`provider` defaults to `ollama` and needs no setup - every game without it
keeps behaving exactly as before. To point a specific persona at OpenAI or
Anthropic instead, set `provider: openai` (or `anthropic`) and export the
matching API key (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, see `.env.example`)
- `model` then names that provider's model (e.g. `gpt-4o-mini`,
`claude-3-5-sonnet-20241022`) instead of an Ollama tag. See
`configs/providers.yaml` for the provider list itself; `num_ctx` and the
research pipeline's `keep_alive` behavior are Ollama-specific and simply
don't apply to hosted providers.

A `game.yaml` that's missing a required field (`persona`, `user_role`,
`script`, `model`) fails validation - it's simply left out of `/api/games`
(so a broken game doesn't take down the whole picker), while trying to load
it directly (starting a session, running research on it) raises a clear
error naming the game id and the missing field.

## Running research

Click "Refresh research" next to a game in the picker, or run:

```bash
python scripts/research.py <your_game_id>
```

This browses the web once (fresh, incognito-equivalent browser context,
closed immediately after), distills dialogue/tone notes, and writes one row
per game into the `game_research` table (`data/app.db`, via
`GameResearchRepository`):

- `notes` - the notes actually used at chat time (read by
  `games/loader.py` alongside `game.yaml`).
- `sources_json` - the raw artifacts behind those notes (the query, which
  pages were scraped, and their raw text) as one JSON blob, kept separately
  so you can audit or re-summarize without re-scraping.

Research notes get reused by every future session of that game.

## Sessions and memory

Chats are saved to SQLite (`data/app.db`) and resumable from the
picker screen. Older turns fold into a running summary once a session
passes `keep_last_messages` (`configs/app.yaml`, default 20) raw messages,
so memory holds even in long conversations - see
`docs/ARCHITECTURE.md#why-summarization-isnt-in-the-chat-graph` for how
that folding is kept off the critical path of a reply.

### Long-term memory recall (opt-in)

The running summary above is *within* a session, and compresses detail away
as it goes - fine facts from a session that ended a while ago are gone once
they've aged out. Set `memory_recall: true` (or the checkbox in the persona
editor) to also embed and store each folded chunk, and recall the most
relevant ones - **from any past session with this same persona** - into
every new reply's prompt.

Requires an embedding model pulled in Ollama: `ollama pull nomic-embed-text`
(the default; change it via `embedding_model` in `configs/models.yaml`).
Off by default - every existing game behaves identically until you turn it
on, and a tightly-scripted persona can just leave it off if fully
predictable behavior matters more than long recall.

## In-conversation skills (opt-in)

`skills` is a list of tool ids the model can call *mid-reply* - different
from research above, which only ever runs once, before any chat happens.
Set `skills: [web_research]` (or the "Web search skill" checkbox in the
editor) to let the persona search the web itself when it needs current
facts it doesn't already know. Off by default - `skills: []` (or omitting
the field) behaves exactly like today, no tool-calling at all.

A turn where the model actually calls a tool takes noticeably longer (a
real web search, via the same Playwright+Bing lookup the research step
uses) - nothing streams to the chat until that round finishes, since the
tool-deciding round has no reply text of its own to show yet.
