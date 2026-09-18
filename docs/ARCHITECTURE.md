# Architecture

Single-user, local, companion chat agent. Ollama is the zero-config default
model provider, with OpenAI/Anthropic available per-persona as opt-in
providers; personas can also carry in-conversation tool-calling skills and
an optional local text-to-speech voice. FastAPI backend, LangGraph for the
per-turn agentic conversation pipeline, SQLite for session/message/embedding
storage, YAML for persona ("game") definitions, a React/TypeScript SPA
frontend.

## Frontend (`dev-ui/`)

Vite + React 19 + TypeScript + Tailwind v4, built independently of the
Python package (`make ui-build` -> `dev-ui/dist/`) and served by `main.py`
as static files at `/` - same origin as the API in production, so there's
no CORS story to maintain. `vite.config.ts`'s dev-server proxy (`/api` ->
`:8000`) only matters for `make ui-dev`'s hot-reload workflow against a
separately-running backend.

- **`services/api.ts`** - the only place that calls `fetch`. `streamChat`/
  `streamBuilderChat` are async generators over their streamed bodies;
  `speak` returns a raw `Blob` (audio/wav) rather than JSON; everything
  else is a typed request/response pair mirroring `schemas/`.
- **`stores/useAppStore.ts`** (Zustand) - games + session list, the data the
  sidebar needs everywhere, plus `deleteSession` (optimistic - removes from
  the list immediately, reconciles from the next `loadAll()` on failure).
  Per-chat message state deliberately isn't here.
- **`hooks/useChatSession.ts`** - owns one chat's messages, loading state,
  and `sendMessage`, which appends a growing assistant message as
  `streamChat`'s chunks arrive. Scoped to one `ChatPage` instance rather
  than the global store, since nothing else needs it.
- **`hooks/useFollowupCountdown.ts`** - polls `GET
  /api/sessions/{id}/scheduled` and ticks a countdown down client-side from
  `fire_at`; once it hits zero it grace-polls the same endpoint every ~5s
  (the backend's own 30s sweep means delivery can lag zero slightly) until
  the pending entry clears, then calls `useChatSession`'s `refresh()`.
  Still polling, no WebSocket/SSE - this is a single-user local app, and
  polling is the simplest thing that works.
- **`hooks/useStartChat.ts`** - the create-session-then-navigate flow,
  shared by Home/Explore instead of duplicated per page.
- **`utils/richText.tsx`** - the quoted-lines-become-separate-bubbles
  fallback and `**bold**`/`*em*` rendering from the original vanilla-JS
  frontend, ported to build React nodes directly instead of
  `dangerouslySetInnerHTML` - model output never becomes raw HTML.
- **`utils/gradient.ts`** hashes a game's id to a fixed gradient from a
  small palette for chat-bubble/list accents - stable across reloads, no
  assets to manage. `utils/gameTileVisuals.ts` is the equivalent for the
  tile/card grids (Explore/Tags/Library/Home), and `utils/avatar.ts`/
  `utils/skillVisuals.ts` follow the same "hand-picked, not random" pattern
  used for `VoiceAvatar` (below) - a persona/skill's visual identity is
  fixed and specific, not re-hashed noise.
- **Pages**: `HomePage` (a "Generate New Game" bar plus a Top Games tile
  grid), `ExplorePage` (browse every game - featured slice, tag filtering,
  client-side text search), `LibraryPage` ("games you've played" - session
  count/rounds/played time per persona), `TagsPage` (every game grouped by
  tag, via the shared `PersonaGrid`), `StudioPage` (entry point for the
  three ways to create a persona - manual, AI-guided, from a transcript),
  `GameEditorPage` (the one form every creation path converges on),
  `GameBuilderPage` (the AI persona-builder chat, also reachable against an
  *existing* persona via "Edit with AI"), `TranscriptImportPage`,
  `SkillsPage` (lists whatever `skills/registry.py` has registered),
  `AudioPage` (browse/preview the TTS voice presets), `ChatPage`.
- **Shared visual primitives**: `GameTile`, `GameCard`, `PersonaAvatar`,
  `PersonaGrid`, `VoiceAvatar`/`OrbAvatar` (the assistant's avatar
  throughout chat), `Logo`, `GenerateBar`/`GameGenerateBar`.
- **`ModelPicker.tsx`** (the generate bar, and `GameEditorPage`'s own Model
  field) renders live off `GET /api/models` - see "Dynamic model
  discovery" below.

## Package layout (`src/roleplay_agent/`)

- **`api/`** - HTTP layer only. `routes/` are thin FastAPI routers (chat,
  game_builder, games, health, library, models, research, search, sessions,
  skills); request/response shapes live in `schemas/`, never raw domain
  objects. `dependencies.py` wires up the singletons (`Database`,
  repositories, `GameLoader`, `Researcher`, `RoleplayAgent`, the skill-tool
  registry, the TTS worker pool) other layers need, via
  `functools.lru_cache`.
- **`agent/`** - the roleplay intelligence. `agent.py`'s `StateGraph` is
  `prepare` (build the prompt from stored history + rolling summary + any
  recalled long-term memory) followed by an agentic `generate` loop, not a
  fixed two-node graph: a conditional edge after `generate` routes to a
  shared `ToolNode` (built from every registered skill) whenever the
  model's tool call falls within that specific game's authorized `skills`
  list, looping `generate -> ToolNode -> generate` until no more tool
  calls; a game with an empty `skills` list behaves exactly like a plain
  `prepare -> generate` graph. `prompts.py` builds the system prompt from a
  `Game`, including labeled `recalled_memories`/`followup_reason` sections
  when applicable - additive only, `persona`/`script`/`user_role` text is
  never rewritten. `context.py` holds the graph's state shape and the
  storage-Message -> LangChain-message conversion. `response.py` wraps a
  graph run to yield text chunks while collecting timing/stats for
  logging. `followups.py`'s `run_followup_loop`/`deliver_due_followups`
  runs the same graph unprompted (`message: None`, the same shape a
  `starter: ai` opening line already uses) to deliver a scheduled
  check-back. `voice.py` is a separate, parallel generation path for voice
  mode's structured `VoiceTurn` reply shape - see "Voice mode" below, not
  part of the `StateGraph` above.
- **`llm/`** - model construction, the only place `langchain_ollama`/
  `langchain_openai`/`langchain_anthropic` clients get built directly.
  `registry.py`'s `build_llm(provider, model, num_ctx, keep_alive)` is a
  small factory keyed by a provider's `kind` (`ollama.py`/`openai.py`/
  `anthropic.py`, each a thin adapter over LangChain's own chat model),
  resolved against `configs/providers.yaml` + `providers.py`'s
  `resolve_api_key` (checks `os.environ` then `.env` directly -
  pydantic-settings' own `env_file` loading only populates its declared
  `Settings` fields, never bare `os.environ`). Everything else (agent,
  memory summarizer, research summarizer, `game_builder.py`) calls through
  `build_llm(...)` polymorphically instead of importing a specific
  LangChain integration, so a game's `provider:` can point anywhere
  without touching call sites. `embeddings.py`'s `build_embeddings` is
  deliberately **not** routed through this provider registry - always
  `OllamaEmbeddings`, regardless of a game's chat `provider:`, since no
  hosted-embedding equivalent is wired up. `tts.py` is local
  text-to-speech, not a chat model - see "Local text-to-speech" below.
  `capabilities.py` is model *discovery* (what's usable, and what it can
  do), a layer above `registry.py`'s model *construction* - see "Dynamic
  model discovery" below.
- **`memory/`** - conversation memory, two tiers. `context.py` is a pure
  read (no model calls - stays on the hot path). `summarizer.py` builds
  the rolling-summary prompt/call. `manager.py`'s
  `fold_overflow_into_summary` is the fold step, deliberately not run as
  part of the chat graph (see "Why summarization isn't in the chat graph"
  below) - when a game has `memory_recall: true`, this is also where the
  folded chunk gets embedded and stored (optional `embedding_repo`/
  `embed_fn`/`game_id` kwargs, `None` by default so every other caller is
  unaffected) *before* `summarize_fn` compresses it away, still inside the
  same background task. Retrieval itself lives in `agent/agent.py`'s
  `_prepare` node, not here - see "Long-term memory recall" below.
- **`games/`** - persona ("game") definitions. `models.py`'s `Game` is the
  validated pydantic schema: identity/prompt fields (`persona`/
  `user_role`/`script`/`research_query`/`research_notes`), model choice
  (`provider`/`model`/`num_ctx`), and opt-in capabilities (`memory_recall`,
  `skills`, `voice`, `starter`, `cover_image`). `loader.py` reads
  `data/games/<id>/game.yaml` (+ an optional `game_research` row, via
  `GameResearchRepository`) and also owns the write path - `save()`,
  `slug_for_title()` (collision-checked
  directory-safe id derived from a title), `exists()` - used by the
  create/update/delete routes, not just chat-time reads. `validator.py`
  turns a pydantic `ValidationError` into a `GameConfigError` with the game
  id in the message.
- **`game_builder.py`** - a separate assistant from `agent/agent.py`'s
  roleplay agent: asks questions and proposes a persona rather than
  playing a character. `stream_builder_reply` streams a throwaway,
  client-held conversation (no persisted session - `GameBuilderPage.tsx`
  re-sends the whole message list each turn, and can also seed it with an
  *existing* persona's fields for "Edit with AI"). `generate_draft`/
  `generate_draft_from_transcript` each do one
  `.with_structured_output(GameDraft)` call rather than incremental
  tool-calling field updates (small local models' tool-calling is
  unreliable) - `GameDraft` is a deliberate subset of `Game`'s fields
  (title/tags/persona/user_role/script/research_query), leaving
  provider/model/starter/etc. to the editor's own defaults. Always runs
  against the same computed default model a brand-new persona gets (see
  `resolve_builder_model()` below), independent of any persona's own
  provider - no config override, so the builder can't be left pinned to a
  stale model.
- **`transcript/`** - `youtube.py` wraps `youtube-transcript-api` to turn a
  pasted video URL into caption text for `game_builder.py`'s
  transcript-draft path (`extract_video_id` handles the common paste forms
  via regex; `fetch_transcript` truncates to `transcript_max_chars`).
  YouTube-captions-only, no audio-transcription fallback.
- **`skills/`** - the in-conversation tool-calling framework `agent/
  agent.py`'s loop (above) runs against. `registry.py` maps a skill id ->
  a factory function (`Settings -> BaseTool`, built once and shared), and
  enforces that a tool's own `name` matches its registered skill id -
  `agent.py`'s tool-call routing depends on that equivalence.
  `web_research.py` wraps `research/browser.py`'s existing Playwright+Bing
  scraping as a mid-conversation tool (observation capped at 4000 chars -
  this feeds straight into the model's next reasoning step, unlike the
  one-shot research pipeline's separate summarization pass).
  `schedule_followup.py` registers a `schedule_followup(minutes, reason)`
  tool backed by `storage/repositories.py`'s `FollowupRepository` - the
  `session_id` it writes is **not** a model-supplied argument, it's read
  off the live LangGraph state via LangGraph's `InjectedState("session_id")`
  annotation (excluded from the schema the model sees), which only
  resolves inside a real compiled-graph run.
- **`research/`** - the one-shot web research step, run once before any
  chat happens (distinct from `skills/web_research.py`'s in-conversation
  version above). `browser.py` is the Playwright/Bing scraping (pure
  functions, easy to unit test in isolation from Playwright itself via
  `decode_bing_redirect`). `summarizer.py` distills scraped text into tone
  notes. `researcher.py` orchestrates both and writes the results.
- **`storage/`** - the only place that touches sqlite. `database.py` is a
  thin connection helper, and owns every table's DDL: `sessions`/
  `messages`, an FTS5 virtual table (`messages_fts`, external content over
  `messages`, kept in sync via insert/delete triggers - no update trigger,
  since messages are never edited), `embeddings`
  (`game_id, session_id, text, vector, created_at` - vector as a
  JSON-encoded float list, no new dependency to pack/unpack it), and
  `pending_followups` (`id, session_id, fire_at, reason, created_at`).
  `repositories.py` (`SessionRepository`, `MessageRepository`,
  `EmbeddingRepository`, `FollowupRepository`) is the only place executing
  SQL - `SessionRepository.delete`/`delete_for_game` cascade
  messages/embeddings/follow-ups in one connection; `EmbeddingRepository.
  search` does a brute-force cosine similarity scan in Python rather than
  a real vector index, fine at single-user, low-thousands-of-chunks scale.
  `models.py` are plain dataclasses (`Session`, `Message`) - not pydantic,
  since these never cross the API boundary directly (see `schemas/`).
- **`schemas/`** - pydantic request/response models for the API layer,
  separate from `storage/models.py` and `games/models.py` on purpose: the
  API's shape is allowed to diverge from the storage/domain shape without
  that leaking into either direction.
- **`config/settings.py`** - a single `Settings` object. `configs/*.yaml`
  (`app.yaml`, `models.yaml`, `providers.yaml`, `research.yaml`,
  `transcript.yaml`, `tts.yaml`, `logging.yaml`) set the checked-in
  defaults; `ROLEPLAY_*` env vars (or a `.env` file) override them without
  editing those files.
- **`observability/`** - `logging.py` (setup) and `metrics.py` (the
  structured per-turn latency/stats log line, and the background-fold log)
  - captured and logged, but with no UI surfacing it yet.

## Error handling

`llm/errors.py`'s `describe_llm_error` turns the two realistic Ollama
failure modes into a clear message instead of a raw traceback:
`httpx.TransportError` (Ollama isn't running/reachable) and `ollama.
ResponseError` (Ollama responded but rejected the request - e.g. an
unpulled model). `llm/providers.py`'s `ProviderConfigError` covers the
hosted-provider equivalent (missing/unset API key). Anything else keeps
its own traceback/500 - this is deliberately narrow, not a catch-all.

For regular (non-streaming) endpoints - `research_game` is the one that
actually calls the model - `main.py` registers these as FastAPI
`exception_handler`s, so they come back as a clean `503`/`502`/`422` JSON
body.

The chat endpoint can't use that mechanism: `StreamingResponse` commits the
`200` status and starts sending bytes before the generator inside it has
produced anything, so by the time an Ollama/provider error surfaces
mid-stream the HTTP status is already sent and can't change.
`api/routes/chat.py` instead wraps the token-streaming loop directly,
ending the stream with a clear `[...]` message instead of a traceback,
logging the failure server-side, and skipping the `add_message` call so a
broken/partial turn is never persisted as if it were a real reply. The
`/speak` endpoint (below) isn't streamed, so a `TtsError` there is just an
ordinary `503`.

`GET /api/health` (`api/routes/health.py`) does a cheap `ollama.Client().
list()` - listing locally available models, not running inference - to
report whether Ollama is actually reachable.

## Why summarization isn't in the chat graph

Early on, the fold-old-messages-into-a-summary step ran as part of handling
a chat turn, before generating the reply - so any turn that crossed the
`keep_last_messages` threshold paid for a full extra model call before the
user saw a single token. `agent/agent.py`'s graph never does that fold
inline; `api/routes/chat.py` schedules `memory.manager.
fold_overflow_into_summary` as a FastAPI `BackgroundTask`, which Starlette
only runs after the streamed reply has been fully sent. It can never add
latency to the turn the user is waiting on.

## Why LangGraph's own checkpointer isn't used

LangGraph ships a SQLite checkpointer for exactly this kind of app. It's
deliberately not used here: `storage/repositories.py`'s schema is simple,
human-inspectable, and the source of truth for the session picker/resume
list. Adding LangGraph's own checkpoint store would mean a second SQLite
file and two persistence mechanisms to keep straight, for no benefit at this
scale (single user, one process). LangGraph is used purely as the
per-turn orchestration/streaming engine (`astream_events`), not as the
storage layer.

## Design decisions

Durable rationale for choices that aren't obvious from reading the code -
organized by topic, cross-referencing the package-layout bullets above.

### Three ways to create a persona, one shared write path

`games/loader.py`'s `save()`/`slug_for_title()`/`exists()` plus
`api/routes/games.py`'s `POST`/`PUT /api/games/{id}` (both just
`validate_game()` + `loader.save()`, reusing the same pydantic validation
a bad manual edit already fails against at chat time) are the *only* write
path. All three ways to arrive at a `Game` converge on it rather than each
getting its own save flow:

1. **Manual** - `GameEditorPage.tsx`, a form with every `Game` field.
2. **AI-guided** (`game_builder.py`, above) - a drafting conversation
   ending in one structured-output call, opening a *draft* `Game` in the
   same editor (via router `location.state`, since it's client-side and
   doesn't need a server round-trip) for review before saving. The editor
   also reaches this path against an *existing* persona ("Edit with AI"),
   seeding the conversation with the persona's current fields as
   plain-text context (not added to the visible transcript) so the model
   refines rather than starts from a blank slate.
3. **From a transcript** - either a pasted transcript or a media URL.
   `transcript/media.py` handles the URL case: yt-dlp resolves virtually
   any URL (YouTube, Vimeo, TikTok, X, SoundCloud, a raw audio/video link,
   ...) and probes for existing captions first; only when none exist does
   it download the audio and transcribe it locally via Hugging Face
   `transformers`' ASR pipeline (see "Local speech-to-text" below) - an
   optional `pip install '.[transcribe]'` dependency. Both paths converge
   on the same `generate_draft_from_transcript` extraction step (2)
   already uses.

### Managing a persona: one shared menu, not per-surface hover icons

Edit, Edit with AI, Duplicate, Refresh research, and Delete all live in one
place - `PersonaMenu.tsx` - reused by `GameCard` (Tags), `GameTile` (Home's
Top Games, Explore, Library via `LibraryCard`), and `ChatPage`'s header,
rather than each surface growing its own hover icons. The gap this closed
was reachability, not missing features: every one of these actions already
existed as code before this component existed, just behind a single hover
pencil icon on a card grid nothing in the sidebar actually linked to.

- **No new backend endpoints** - the menu is a thin client-side
  orchestrator over what already existed: `GET /api/games/{id}` (full
  detail), `POST/PUT /api/games` (the one shared write path above),
  `DELETE /api/games/{id}`, and `POST /api/games/{id}/research`.
- **Duplicate**: `getGame(id)` client-side, drop `id`/`cover_image`, suffix
  the title, and open `GameEditorPage` (`/games/new`) pre-filled via the
  same `location.state.draft` mechanism the AI-builder's generated drafts
  already used - reusing "opens in the editor for review before saving"
  rather than a new save flow. This meant widening what that draft slot
  accepts: it used to be typed strictly as `GameDraft` (the AI-builder's
  persona-shaped subset - title/tags/persona/user_role/script/
  research_query), which would have silently dropped a duplicated
  persona's provider/model/starter/num_ctx/memory_recall/skills/voice back
  to `EMPTY_FORM`'s defaults. It's now `Partial<GameCreateRequest>` -
  `GameDraft` still satisfies it structurally (so the AI-builder path is
  untouched), and Duplicate's fuller draft rides the same field-by-field
  `draft.x ?? EMPTY_FORM.x` fallback instead of needing a second code path.
- **Delete** reuses the existing confirm-then-`DELETE /api/games/{id}`
  flow (a second click on the menu's own Delete item, not a native
  `confirm()` dialog this time) and always calls `loadAll()` to refresh
  `useAppStore`'s `games`/`sessions` afterward. An optional `onDeleted`
  callback covers what a plain refresh can't: `ChatPage` navigates back to
  `/` since the conversation you were just looking at is gone too
  (`DELETE /api/games/{id}` already cascades every session under it), and
  `LibraryCard` drops the entry from `LibraryPage`'s own `library` list
  (fetched independently via `GET /api/library`, not from the app-wide
  store, so it doesn't otherwise learn about the deletion).
- **`GameTile`/`LibraryCard` used to be a single outer `<button>`** for the
  whole card's click target - adding a corner menu meant a second
  interactive element, and nesting a `<button>` inside a `<button>` is
  invalid HTML. Both became a `<div>` wrapping an absolutely-positioned
  inner `<button>` for the click target (matching `GameCard`'s existing
  shape) plus the menu as a sibling overlay in the opposite corner -
  `GameTile` only renders the menu at all when given a `game` prop, since
  `SkillsPage` reuses the same tile for skills, which aren't personas.

### Character name, distinct from the scenario title

`Game.title` used to be asked to do two different jobs - a persona's
display name in the picker/card grids ("Rooftop First Date," a scenario,
not necessarily anyone's name) *and* the in-conversation identity shown
while chatting (`ChatPage`'s header, `TypingIndicator`'s `"{title} is
typing…"`). Conflating them was always slightly wrong (the typing
indicator reading `"Rooftop First Date is typing…"` instead of a
character's name); it became a visible bug once session titles started
being auto-derived from the first user message - the header would
literally show a snippet of what the user just typed, having lost the
coincidence that used to make reusing `title` look right.

- `Game.character_name: str | None = None` (`games/models.py`, and the
  matching `schemas/game.py` request/response schemas) is the name shown
  anywhere the app refers to "who you're talking to" - `GameEditorPage`'s
  Basics section gets a field for it alongside Title. Unset (or blank) for
  every game.yaml written before this field existed, and for the empty
  string a hand-authored YAML's `character_name: ""` leaves behind.
- `characterNameFor(game)` (`utils/persona.ts`) centralizes the fallback -
  `character_name || title`, `||` rather than `??` specifically so an
  empty string behaves exactly like unset rather than rendering blank.
  `ChatPage` looks the persona up from `useAppStore`'s already-loaded
  `games` (by the `gameId` `useChatSession` exposes, no new network call)
  and uses it for the header identity line, the header's accent gradient,
  and `TypingIndicator`'s text - all switched from the session's own
  `title` (now purely a sidebar/history label, see above) to this.
- Deliberately **not** wired into the AI builder: `GameDraft` (what
  `.with_structured_output()` produces) has no `character_name` field, and
  the "Edit with AI" priming context doesn't mention it either - the
  builder's job is proposing persona content, and a scene's protagonist
  name is something an author names deliberately, not something worth
  having a model guess at from a short chat.
- `PersonaMenu`'s **Duplicate** does carry `character_name` over, though -
  unlike the builder, a duplicate should be a real copy of everything the
  source persona has.

### AI Studio gets its own persisted session type - not shared, not mixed

The builder chat above (path 2) is itself a durable session now, in its
own `builder_sessions`/`builder_messages` tables - deliberately not a
nullable `game_id` + `kind` discriminator bolted onto the roleplay
`sessions`/`messages` tables. A builder conversation is a chat *about
designing* a persona, not a chat with one, and the roleplay tables already
have several things (full-text search, Library stats, long-term memory
embeddings) that assume every session row is a played persona chat; a
genuinely separate pair of tables can't leak into those by construction.

- `POST /api/games/builder/sessions` creates the row - called right when
  the *first* message is about to go out (mirroring how a roleplay session
  is created before its first chat turn), not eagerly when the page opens.
  `game_id` is set at creation for an "Edit with AI" conversation (already
  known - it's refining that persona) and stays `NULL` for a "New persona"
  conversation.
- `POST /api/games/builder/sessions/{id}/chat` (`{message, context}`)
  appends the user turn, streams the reply, and persists it - same shape
  as `api/routes/chat.py`'s real chat turn. `context` is the "here's the
  persona as it stands today" priming block for an "Edit with AI"
  conversation: prepended to the LLM call on every turn but **never
  written to `builder_messages`** - it's grounding, not a real turn, and
  persisting it would make a resumed/drafted transcript show a synthetic
  message nobody actually said.
- `POST /api/games/builder/sessions/{id}/draft` reads the persisted
  history (plus the same transient `context`) instead of the client
  re-sending the whole conversation, and calls the same `generate_draft`
  from `game_builder.py` used before this change - the low-level
  drafting/streaming functions didn't need to change at all, only the
  route layer that feeds them.
- `GameBuilderPage.tsx` no longer holds the conversation as the source of
  truth in React state re-sent whole every turn - it creates the session
  on first send and both `/chat` and `/draft` calls key off that id, same
  shape as `useChatSession`. `DELETE /api/games/{id}` does **not** cascade
  into `builder_sessions` the way it cascades into roleplay `sessions` - a
  builder conversation that led to a persona is a record of how that
  persona came to be, independent of the persona's later lifecycle.
- Not yet built: a list view over `builder_sessions` to browse/resume past
  builder conversations (there's no `GET .../sessions` listing endpoint,
  and no UI for one) - persistence is real value on its own even before
  that exists, and it's the natural next step whenever it's actually
  wanted.

**Structured-output reliability, checked, not assumed**: checked manually
against this project's own default local model
(`huihui_ai/gemma-4-abliterated`) rather than assumed reliable. Schema
validity was never the problem - `.with_structured_output()` returned a
correctly-typed `GameDraft` on every attempt. Content *quality* was, at
first: a bare call with no `Field` descriptions produced short
placeholder-ish labels (`persona: "The Grumpy Old Wizard (The Master)"`,
`script: "---"`) instead of real descriptive paragraphs. The fix:
`Field(description=...)` on every `GameDraft` field spelling out exactly
what "good" looks like, plus an explicit instruction in the draft prompt
itself, together reliably produce rich, well-formed persona/user_role/
script paragraphs. Takeaway for any future structured-output call in this
codebase: schema validity passing is not the same as content being good -
budget for real field descriptions and an explicit instruction, and
actually read the output once against your model before shipping UI
around it.

### Skills: an agentic tool-calling loop, not two one-off features

`skills/` (above) is a general extensible mechanism - `game.yaml` gains a
`skills:` list, each skill is a tool the model can invoke mid-turn - not a
pair of hardcoded special cases. This is also the natural next real use of
LangGraph beyond a fixed linear graph: `_generate` binds only the tools a
specific game's `skills` list authorizes (`llm.bind_tools(...)`), and the
conditional edge after `generate` only routes to the shared `ToolNode` when
the model's tool call is itself within that same authorized set -
belt-and-suspenders against a misbehaving model reaching a tool it was
never bound.

`schedule_followup`'s delivery (`agent/followups.py`, above) polls every
30s (`main.py`'s `lifespan`, cancelled on shutdown) - checked once
immediately on startup too, so anything that came due while the server was
down fires right away. A row whose session/game no longer resolves, or
whose turn otherwise fails, is logged and dropped rather than retried
forever, the same "log and move on" choice `chat.py`'s background fold
task already makes for its own background work. Known hazard, not a bug:
running two server instances against the same local `data/app.db`
makes both instances' poll loops race the same due row and can
double-deliver it - this app has never supported multiple instances
sharing one data dir, and this doesn't change that.

`GameEditorPage`'s skills field is a live search-and-add picker backed by
`GET /api/skills` (a newly-registered skill needs no editor change to show
up) - not a hardcoded checkbox per skill.

### Local text-to-speech: a persistent worker process, not a separate service

`services/tts/tts.py` synthesizes a persona's reply text via whichever
backend `configs/tts.yaml`'s `backend` names - **never a model or backend
hardcoded in code** (see "Dynamic model discovery" above; TTS gets the same
treatment). Both backends share the process/streaming plumbing this section
describes; only model loading and synthesis differ:

- **`chatterbox`** (the current default): [Resemble AI's
  Chatterbox-Turbo](https://github.com/resemble-ai/chatterbox) via the
  `chatterbox-tts` pip package (`pip install '.[tts-chatterbox]'`) - plain
  PyTorch, so it runs on CPU/CUDA/MPS rather than qwen3's Apple-Silicon-only
  mlx. It has no curated preset speaker list the way qwen3 does below -
  every `Game.voice` must name a cloned reference clip under
  `data/voice_samples/`. Device (cpu/cuda/mps) isn't a config knob - a
  hardware fact `_detect_chatterbox_device()` auto-detects once per worker
  process (cuda, then mps, then cpu). `configs/tts.yaml`'s
  `chatterbox.quantize: int8` applies PyTorch dynamic quantization to T3
  (the GPT2-based text-to-speech-token half of the model)'s `Linear`
  layers only, CPU-only (dynamic quantization doesn't cover S3Gen's conv
  layers, and PyTorch's dynamic quantization backend is CPU-only in the
  first place - `quantize: int8` on a machine that auto-detects to
  cuda/mps is silently skipped rather than raised, since there's no config
  knob left for an author to fix it with). It has no native low-level
  streaming API, so
  `synthesize_stream()` pseudo-streams one sentence at a time for it
  instead of qwen3's native sub-second chunking. **Not yet live-verified
  on real hardware in this repo** (unlike every "verified live" claim
  elsewhere in this section) - the real-time-factor/memory numbers below
  are qwen3-only; treat chatterbox's own performance as unmeasured until
  someone runs it.
- **`qwen3`**: [`mlx-audio`](https://github.com/Blaizzy/mlx-audio)'s port
  of Qwen3-TTS-12Hz-0.6B-**CustomVoice** (`mlx-community/
  Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit`) - the preset-speaker checkpoint,
  not the voice-cloning **Base** variant (which clones from a ~3s
  reference clip per persona, real asset-management overhead CustomVoice's
  zero-config preset list avoids; per Qwen's own docs a single model
  instance serves one checkpoint type, so mixing both would mean running
  two model instances, not a config flag). The rest of this section's
  "verified live" claims are about this backend specifically.

- **Official tooling (`transformers`/`vLLM`) is CUDA-first** - this app
  runs on Apple Silicon via `mlx-audio` instead, a third-party (not
  Qwen-maintained) MLX port. Verified real speaker ids against the loaded
  model's own `get_supported_speakers()`, not the model card or wrapper
  repos (which name speakers, e.g. "Ethan"/"Chelsie", that don't actually
  exist on this checkpoint): `serena`, `vivian`, `uncle_fu`, `ryan`,
  `aiden`, `ono_anna`, `sohee`, `eric`, `dylan`. `Game.voice` and
  `dev-ui/src/data/voices.ts` both curate the same 5 of these 9
  (`ryan`/`aiden`/`dylan`/`serena`/`vivian`) and must stay in sync -
  see `services.tts.tts.SUPPORTED_VOICES`'s own comment.
- **A single persistent worker process**
  (`ProcessPoolExecutor(max_workers=1)`), not a standalone HTTP service the
  user starts separately (the "run it like Ollama, a separate always-on
  local service" idea this started from) - same crash-isolation and
  "keeps ~6GB off the main process" goals at a fraction of the engineering
  cost: no port to manage, no second process for the user to remember to
  start, no client/server protocol to define. The model loads once in
  that worker on its first call (a module global in the worker's own
  process, `_synthesize_qwen3_in_worker`/`_get_chatterbox_model`) and is
  reused for every call after,
  since `ProcessPoolExecutor` doesn't recycle a worker unless told to -
  measured live: a cold first call took ~10.6s, a second call against the
  same warm worker took ~2.4s (~1.2x real-time-factor either way, ~6GB
  peak worker memory - budget for the measured number, not any README's
  marketing figure). `main.py`'s lifespan shuts the pool down on exit.
- Both backends' real libraries (`mlx_audio`, `chatterbox`/`torch`) are
  only ever imported *inside* the worker function, never at module import
  time, and each ships as its own **optional** dependency (`pip install
  '.[tts]'` for qwen3, Apple Silicon only - `mlx` has no non-macOS/arm64
  wheels; `pip install '.[tts-chatterbox]'` for chatterbox, cross-platform)
  - the main process's dependency footprint stays light, and every
  `/speak` call just 503s with a clear message if the one `backend` needs
  is missing, never an app-wide requirement.
- **Synthesized on demand, not eagerly after every reply**:
  `POST /api/sessions/{id}/speak` is called from `ChatBubble.tsx`'s
  read-aloud button, not scheduled automatically once a reply finishes -
  synthesis costs several real seconds and ~6GB of worker memory, so a
  persona nobody actually listens to never pays for it. `speak` derives
  the voice from the session's `game.voice` server-side (never trusts the
  frontend to say which voice) and 422s (not 503) when none is configured
  - a config fact about the game, not a service outage - which the
  frontend reads as "fall back to browser speech" rather than an error
  worth surfacing.
- **v1 is "generate full reply -> synthesize once -> serve the wav"**, not
  incremental per-sentence streaming: `generate_audio`'s `stream=True` flag
  doesn't hand back an HTTP-streamable chunk generator, it's wired to
  local speaker playback. True streaming would mean calling `mlx_audio`'s
  lower-level per-segment model API directly (the same `result.audio`
  chunks the high-level wrapper iterates over for local playback) - real
  future work, not a v1 requirement, and not blocked by anything shipped
  now.
- **Frontend fallback chain**: `ChatBubble.tsx`'s read-aloud button tries
  real synthesis first, and falls back to the browser's own
  `speechSynthesis` on *any* failure - no voice configured, synthesis
  erroring, or offline - guarded by an 8s `Promise.race` timeout around
  `audio.play()` so a stuck play promise can never leave the button
  disabled forever.

### Local speech-to-text: generic Hugging Face ASR, not pinned to one model

`services/stt/stt.py` transcribes audio (a downloaded video's no-captions
fallback via `transcribe_file`, a voice-mode mic capture via
`transcribe_wav_bytes`) via Hugging Face `transformers`' generic
`automatic-speech-recognition` pipeline - `configs/transcript.yaml`'s
`model_repo` can be *any* pipeline-compatible checkpoint on the Hub (a
Whisper variant, Wav2Vec2, HuBERT, Distil-Whisper, Moonshine, a
fine-tune, ...), never one particular model/engine hardcoded in code, the
same "no hardcoded model anywhere" rule "Local text-to-speech" above
applies to TTS.

- **`transformers` is an optional dependency** (`pip install
  '.[transcribe]'`, which also pulls in `torch`), imported lazily inside
  `get_pipeline` only, so the app runs fine (and every other feature
  works) with it never installed - a caller that needs it just gets
  `SttUnavailableError` with an install hint until then.
- **Device is always auto-detected, never a config knob** - `_detect_device`
  picks cuda > mps > cpu, whichever this machine's torch build actually
  supports, mirroring `services/tts/tts.py`'s own
  `_detect_chatterbox_device` (same reasoning: CPU/CUDA/MPS is a hardware
  fact, not something worth asking an author to guess).
- **Shared model cache** - `_pipelines` is a process-wide dict keyed on
  `model_repo`, so both callers above loading the same configured model
  share one loaded pipeline instead of doubling memory - same reasoning as
  "Local text-to-speech"'s worker-process model cache, just without a
  separate process (these calls are already synchronous/blocking, called
  via `asyncio.to_thread` at the one caller - `/voice-turn` - that can't
  afford to block the event loop; `media.py`'s own caller already runs
  outside the event loop entirely).
- **No Python-level fallback for the model** - `AppConfig.stt_model_repo`
  has no default (see "Config hygiene" below) - same reasoning as
  `embedding_model`: a model name belongs in `configs/`, not a string
  literal in code.

### Multi-provider model selection

Ollama stays the zero-config default; other providers become opt-in via
`provider:` on a game plus an API key env var (`configs/providers.yaml`,
`api_key_env` names an environment variable, never a key value, read from
`.env`). `Game.provider` is a field **separate from `model`**, not a
`provider:model` prefix on one string - Ollama's own tag syntax already
uses colons, so a prefix scheme would
be ambiguous about where the provider name ends and the model name begins.
Every existing `game.yaml` needs no changes (`provider` defaults to
`ollama`).

This ended up a smaller change than it sounds, and confirms something
about how Phase 1's original LangGraph refactor was built: `agent/agent.py`
's graph, `memory/summarizer.py`, and `research/summarizer.py` already
only called `build_llm(...)` and used the result polymorphically
(`.ainvoke`/`.invoke`/`astream_events`) - none of them were Ollama-specific
by accident, because the graph was built against LangChain's model
interface, not Ollama's raw client, specifically so this kind of swap
wouldn't touch it. The test suite already substituted
`GenericFakeChatModel` for `ChatOllama` at this exact boundary before any
of this existed, and each call site only needed one new argument
(`provider`), not a restructure.

See "Dynamic model discovery: no hardcoded model anywhere" below for how
`GET /api/models` (what `ModelPicker.tsx` and `GameEditorPage`'s own model
field now render from) discovers what's actually usable across every
configured provider, and how that replaced the config's old hardcoded
`default_model`/`default_provider`.

### Dynamic model discovery: no hardcoded model anywhere

`configs/models.yaml`'s old `default_model` and `configs/providers.yaml`'s
old `default_provider: ollama` were both literal strings nothing computed -
if that exact model wasn't pulled locally, a fresh persona or the AI
builder just broke with "model not found" instead of falling back to
whatever was actually available, and a user with multiple providers
configured always got funneled toward Ollama purely because it was listed
first. `llm/capabilities.py` replaces both with a real capability cache and
two independent "compute a default" functions:

- **Discovery, live, on a TTL** - the `app_settings` table's
  `model_capabilities` key (reserved for exactly this since the Phase 3
  restructure), refreshed
  when it's more than `CACHE_TTL_SECONDS` (300s) stale, not recomputed per
  request. **Ollama**: `ollama.Client().list()` enumerates every
  locally-pulled model with a real `modified_at` timestamp;
  `.show(model)` returns its real `capabilities` list
  (`['completion', 'vision', 'audio', 'tools', 'thinking']`) - populated
  once per listed model. Ollama unreachable means that provider simply
  doesn't appear in the result at all, not a crash (`_ollama_models()`
  catches broadly and returns `None`). **Hosted (OpenAI/Anthropic)**: no
  live "what can this exact model do" API worth relying on, so
  `HOSTED_MODEL_CAPABILITIES` is a small hand-maintained table (model id ->
  treated as `completion`-capable), gated on whether `resolve_api_key`
  actually succeeds right now - a hosted provider with no key configured
  doesn't appear either, the same "only shows what's actually usable, never
  disabled/greyed-out" rule as Ollama.
- **`GET /api/models`** (`api/routes/models.py`) returns
  `{default_provider, providers: [{provider, models: [{id, capabilities,
  modified_at}]}]}` straight off the cache. `ModelPicker.tsx` renders its
  provider-grouped dropdown directly from this instead of a hardcoded
  `MODEL_GROUPS` list; `GameEditorPage`'s Model field is this same picker
  instead of free-text provider/model inputs.
- **No hardcoded default model** - `default_chat_model(providers)`
  (`llm/capabilities.py`) picks the most recently pulled/updated Ollama
  model with `completion` in its capabilities, falling through to a hosted
  provider's own first chat-capable model only when no Ollama model
  qualifies. Computed at the moment it's needed, never a name baked into a
  YAML file or Python default.
- **Default provider - random once, then stable** -
  `get_default_provider()` picks uniformly at random among whichever
  providers actually pass the reachability check the first time a default
  is needed with no stored choice yet, then persists it to the
  `app_settings` table's `default_provider` key (a sibling to the
  capability cache, a bare string). `GameEditorPage`'s
  Model field defaults to this stored provider's own first model for a
  brand-new persona - filled in by an effect once `GET /api/models`
  resolves, and only if the field is still untouched by then (an AI
  draft's provider/model - it never has one - and a Duplicate's carried-
  over provider/model both still take priority; see "Managing a persona"
  above for Duplicate).
- **`builder_provider`/`builder_model` are never configured** -
  `resolve_builder_model()` always computes the same "most recently
  pulled/updated" pick a brand-new persona gets (`default_chat_model()`),
  no `configs/models.yaml` override. `api/routes/game_builder.py`'s
  `_resolved()` runs this before `game_builder.py`'s functions are called
  at all (before the user's message is even persisted, so a config error
  never leaves an orphaned turn nobody gets a reply to) - `game_builder.py`
  itself doesn't know resolution happened, it just reads
  `app_config.builder_provider`/`builder_model` directly off whatever
  `AppConfig` it's handed.
- **A persona's own `model: default`** (`Game.model`, `docs/GAME.md`) is
  the same idea applied to `game.yaml` itself -
  `resolve_game_model(provider, model, settings_repo)` returns
  `(provider, model)` unchanged for any real model name, and only for the
  literal string `"default"` (`GAME_MODEL_DEFAULT`) calls
  `default_chat_model()` fresh. `Game.provider` can't distinguish "the
  author picked ollama" from "the field was never set" (it defaults to
  `"ollama"`, not `None`), so `model: default` always computes across every
  reachable provider and ignores this game's own `provider` field entirely
  rather than trying to stay on it. Resolved fresh on every use
  (`api/routes/gameplay/chat.py`'s
  `_resolved_game()` for chat/voice-turn, `Researcher.research()` for the
  research pipeline - each reloads/receives the game independently, so
  each resolves independently too) rather than once at `game.yaml` load
  time, so a session always follows whatever's currently best rather than
  freezing in whatever was newest the first time this game was loaded.
- **Not done**: multimodal-capability-aware input (a `vision`/`audio`
  capable model taking image/audio directly) - the cache already carries
  this data (Ollama exposes it for free), but nothing in the app consumes
  it yet since no image/audio-input feature exists. Section F's voice mode
  would be the first consumer.

### Config hygiene: `.env` for secrets/infra only, `configs/` for everything else

`config/settings.py` used to be one flat `Settings(BaseSettings)` class -
`configs/*.yaml` supplied the baseline, but pydantic-settings'
`env_prefix="ROLEPLAY_"` mechanism meant *every* field on that class,
without exception, was also overridable via a `ROLEPLAY_<NAME>` env var,
whether or not that was actually appropriate. `keep_alive`,
`keep_last_messages`, `default_num_ctx`, `embedding_model`,
`enable_thinking`, `research_max_results`/
`research_user_agent`, `transcript_max_chars`, `stt_model_repo`,
`tts_backend`/`tts_chatterbox_model_repo`/`tts_qwen3_model_repo`/
`tts_max_chars` are all *application behavior*, not environment secrets -
none of them belong in `.env`.

**Split into two objects, not one, so the boundary is structural, not a
convention to remember:**

- **`Settings(BaseSettings)`** - true environment/infra config only:
  `host`, `port`, `data_dir` (deployment-topology facts - which port to
  bind, where the data volume lives), `log_level`. Still
  `env_prefix="ROLEPLAY_"` + `env_file=".env"`, just far fewer fields
  eligible. Provider API keys (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`) stay
  exactly as before: read directly from `os.environ`/`.env` by
  `llm/providers.py`'s `resolve_api_key`, never `ROLEPLAY_`-prefixed,
  already outside this class.
- **`AppConfig` - a plain `pydantic.BaseModel`, not `BaseSettings`** -
  sourced *only* from `configs/*.yaml` (`_yaml_defaults()`), literally not
  a `BaseSettings` field, so a `ROLEPLAY_KEEP_ALIVE` env var does nothing
  even if someone sets one. Carries everything that used to be on
  `Settings` except the four infra fields above.
- **No Python-level fallback for a model name** - `embedding_model`,
  `stt_model_repo`, and `tts_backend` are always *required* `AppConfig`
  fields (no default expression at all), and whichever of
  `tts_chatterbox_model_repo`/`tts_qwen3_model_repo` matches `tts_backend`
  becomes required too (see `_TTS_BACKEND_REQUIRED_KEYS`) - the other TTS
  backend's model repo field stays optional, since it's simply unused (STT
  has no such table - it's a single always-on backend, not a choice).
  `get_app_config()` checks all
  of this explicitly before constructing it and raises `ConfigError`
  naming exactly which key is missing and which YAML file it belongs in,
  rather than either a cryptic pydantic validation error or - the old
  behavior - a silently-applied hardcoded model string. Called eagerly at import time in `main.py`
  (`app_config = get_app_config()`, right where `get_settings()` already
  was), so a misconfigured deployment fails at process startup, not
  confusingly mid-conversation. Non-model values (`keep_alive`,
  `default_num_ctx`, etc.) keep ordinary Python-level fallback defaults -
  the rule is specifically "no model names in code," not "no defaults in
  code" generally.
- **Every call site that used to read `settings.X` for a now-moved field
  reads `app_config.X` instead** - a mechanical but real split:
  `api/dependencies.py`'s `get_researcher`/`get_agent`/`get_embeddings`/
  `get_skill_tools`, `api/routes/chat.py`'s `_num_ctx_for`/`_fold_task`/
  `speak`, `api/routes/game_builder.py`, `game_builder.py`'s three
  functions (now take `AppConfig`, not `Settings`), and the skills
  registry (`skills/registry.py`'s `ToolFactory` now takes *both* `Settings`
  and `AppConfig` - a skill takes whichever half it actually needs;
  `schedule_followup` needs `Settings.db_path`, `web_research` needs
  `AppConfig`'s research fields, so factories can't uniformly take just
  one). FastAPI routes take `AppConfig` via `Depends(get_app_config)`
  exactly like any other dependency; a test that needs a specific
  `AppConfig` for one of those overrides `app.dependency_overrides[
  get_app_config]` (the reference is captured at route-decoration/import
  time, so monkeypatching the module attribute doesn't reach it) - a
  route that instead calls `get_app_config()` directly inline (not via
  `Depends`, like every `game_builder.py` route) can just have that
  module-level name monkeypatched instead.
- `configs/app.yaml` now holds only `host`/`port` (env-overridable);
  `keep_alive`/`keep_last_messages` moved to `configs/models.yaml`
  alongside the rest of `AppConfig`'s chat-generation fields.
  `.env.example` was trimmed to match: only `ROLEPLAY_HOST`,
  `ROLEPLAY_PORT`, `ROLEPLAY_DATA_DIR`, `ROLEPLAY_LOG_LEVEL`, and the two
  provider API keys.

### Long-term memory recall: an always-on pipeline step, not a skill

The rolling summary (`memory/manager.py`) compresses old turns into 4-6
bullets the moment they age out of the last `keep_last_messages` - fine
detail is gone for good at that point. Long-term recall is deliberately
**not** a skill the model opts into via tool-calling (unlike `skills/`
above) - tool-calling reliability on local models is a known risk
elsewhere in this codebase, and memory recall should just work every turn,
not depend on the model remembering to ask for it. It follows the exact
pattern the rolling summary already uses safely instead: a new, clearly
labeled, additive prompt section, never a rewrite of `persona`/`script`/
`user_role`.

Retrieval (`agent/agent.py`'s `_prepare` node, via `_recall_memories`)
embeds the incoming user message and searches - **scoped to that same
`game_id`**, so one persona's memories never bleed into a different
persona's conversation (confirmed live: a query against one game's stored
memory returns zero results for a different `game_id`) - taking the top 3
(matching the summary's own "4-6 bullets" scale) most relevant chunks.
Opt-in per game (`Game.memory_recall: bool = False`) - every existing
`game.yaml` behaves identically until a game author turns it on, and a
tightly-scripted persona can simply never enable it if fully predictable,
author-only behavior matters more than long recall.

### Full-text search across sessions

Unlike memory recall, this has **no interaction with the model or the
prompt at all** - it's a lookup feature for the human, not something the
AI sees. `MessageRepository.search(query)` ANDs and phrase-quotes terms
(escaping embedded quotes) so arbitrary user input can't break FTS5's
query syntax, and deduplicates results to one (best-ranked) row per
session. `GET /api/search?q=...`; the sidebar's search box filters the
already-loaded session list by title client-side and debounces a call to
this endpoint for message-content matches, merged into the same results
list rather than a separate search UI. `Library` also surfaces this via
its own `?q=` param on `GET /api/search`.

### Session titles: auto-titled from the first user message, renamable, per-persona sidebar

`sessions.title` used to be set once at creation to the *persona's* title
and never changed - every session with the same persona had an identical
title, and the sidebar's "Recent chats" mixed every persona's sessions
together. Now:

- `api/routes/chat.py`'s `chat()` checks `MessageRepository.count_role(session_id,
  "user") == 1` right after storing the incoming message - a plain COUNT,
  not a dedicated `sessions.title_set` flag, since it's cheap enough at
  single-user scale. On exactly that first user-role message, the title is
  replaced with a truncated (~50 char) snippet of it via
  `SessionRepository.update_title`. A `starter: ai` session's opening line
  is the persona's, not the user's, so the placeholder (the persona's name)
  survives until the user actually replies.
- `PATCH /api/sessions/{id}` (`{title: str}`) calls the same
  `update_title` for a manual rename - auto-titled and manually-renamed are
  the same field, not two.
- `Sidebar.tsx`'s "Recent chats" filters to the currently-open session's
  `game_id` (via `useCurrentGameId`) before grouping into Today/Yesterday/
  Earlier - Library already covers "browse everything across every
  persona," so the in-chat sidebar specializes. Each row shows just the
  title text (no per-row persona avatar, now that every row is already
  scoped to one persona) plus hover-revealed rename/delete controls; rename
  swaps the row for an inline `<input>` in place.
- `useAppStore`'s `sessions` list is the single source of truth for a
  session's displayed title everywhere it appears at once - both A0's
  auto-title and a manual rename write through `setSessionTitle`/
  `renameSession`, and `useChatSession` derives `ChatPage`'s header title
  from the store (falling back to its own fetch only until the store has
  that session) rather than keeping a second, easily-stale copy.

### Archiving a session

`sessions.archived_at REAL` (`NULL` while active) - a timestamp rather
than a bare bool, so "when" is free to capture and the Archives view can
sort by recency-of-archiving. Since the column was added after the table
already existed in deployed databases, `Database.init_db()` migrates it in
place (`PRAGMA table_info` + `ALTER TABLE ... ADD COLUMN` if missing) -
the first migration this project has needed; `CREATE TABLE IF NOT EXISTS`
alone only covers a brand-new database.

- `SessionRepository.list_all()` (used by `GET /api/sessions`, which backs
  both the sidebar and Library) now filters `WHERE archived_at IS NULL` -
  archiving a session removes it from every list that call powers without
  those call sites needing their own `include_archived` flag.
  `list_archived()` is the mirror query for the Archives view.
  `library_stats()` deliberately does **not** filter - archiving hides a
  chat from the day-to-day lists, it doesn't erase the time you spent in
  it from Library's totals.
- `POST /api/sessions/{id}/archive` / `.../unarchive` toggle it.
- The archive action itself lives in `Sidebar.tsx`'s `ChatRow` - a third
  hover-revealed icon alongside rename and delete, the same discoverable
  spot A3's rename already established, right where the row about to
  disappear is visible. Archiving (or deleting) the session currently open
  in `ChatPage` navigates back to Library, same as delete already did.
- `ArchivesPage.tsx` (`/archives`, a nav item directly below Library, both
  in and out of chat mode - not folded into Library as a filter/tab) fetches
  `GET /api/sessions/archived` on its own, independent of `useAppStore`'s
  main `sessions` list (which only ever holds non-archived rows). Visually
  it reuses Library's card treatment, but per-*session* rather than
  per-persona - you archive one conversation at a time, not a whole
  persona's history. "Restore" calls `.../unarchive` then `loadAll()` so
  the row reappears in the sidebar/Library immediately rather than waiting
  for the next natural reload; "Delete" reuses the same
  `DELETE /api/sessions/{id}` every other delete flow already uses.

### Session/game delete cascades

`SessionRepository.delete`/`delete_for_game` (above) run every table
deletion for a session or game in one sqlite connection, so a crash
mid-delete can't leave the FTS index or embeddings orphaned pointing at a
session that no longer exists. `DELETE /api/games/{id}` cascades every
session under that game *first*, then removes the on-disk game directory -
if the process dies between the two, the game is still gone from every
listing/search surface, just with a harmless leftover directory rather
than a DB row pointing nowhere.

### Voice input and read-aloud: browser APIs first, server-side only where needed

`Composer.tsx`'s mic button dictates via the browser's own
`SpeechRecognition` API (Web Speech) - zero backend work, feature-detected
(the button disables itself where the API doesn't exist), only as good as
the browser's built-in recognizer. `ChatBubble.tsx`'s read-aloud button
mirrors this on the output side: real per-persona audio when `POST
/api/sessions/{id}/speak` succeeds (see "Local text-to-speech" above),
otherwise the browser's own `speechSynthesis` as a generic fallback rather
than failing silently.

### Voice mode: a real speech-in/speech-out conversation mode, shipped end to end

A real continuous speech-in/speech-out conversation mode, distinct from
text mode's typed-input-plus-read-aloud - originally scoped as "large,
higher-risk." F2 (the turn-shaping problem) is real, shipped, and
live-verified. F0/F1/F3/F4 (everything that depends
on sending audio *to* a model) were initially logged here as blocked - an
earlier pass concluded the `ollama`/`langchain-ollama` client libraries had
no way to attach audio to a request, based on `ollama.Message` having no
`audio` field. **That conclusion was wrong**, caught by actually testing
audio input live rather than trusting a field-name check: Ollama added
Gemma 4 audio support in **v0.33.3** (released ~Sept 2, 2026) via the
*existing* `images` field, not a new one - WAV bytes go in where an image
would, and the server routes them through the model's own audio encoder.
Verified directly on this machine (Ollama v0.34.1, newer than the release
that added this) against this project's actual pulled model
(`huihui_ai/gemma-4-abliterated`, GGUF format): a real synthesized WAV
clip asking "What is the capital of France?" sent via both the raw
`ollama` client's `chat(images=[audio_bytes])` and
`langchain_ollama.ChatOllama` (what `llm/ollama.py`'s `build_llm` actually
returns) via a `HumanMessage` content block
(`{"type": "image_url", "image_url": "data:audio/wav;base64,..."}`) both
got back answers that correctly referenced the spoken content ("Paris" /
"the capital of France") - real comprehension, not a fluke, tested twice
with different content. **Nothing in this app's LLM wrapper needs to
change to send audio** - `build_llm`'s signature is unaffected; sending
audio is entirely about how a caller constructs the message content, the
same way an image-capable persona already would.

**Shipped - F2, "the persona's own output isn't clean dialogue"**:
`agent/voice.py`'s `SpeechSegment`/`VoiceTurn` (a `.with_structured_output()`
call, the same proven pattern `game_builder.py`'s `GameDraft` already uses)
splits a reply into spoken `text` plus an optional `delivery` note, instead
of the freeform prose text mode generates today (which real usage confirmed
still leaks quoted dialogue and parenthetical stage directions despite
`agent/prompts.py`'s `RULES` explicitly forbidding both - small/local
models don't reliably follow negative style instructions). `generate_voice_turn`
is a genuinely separate generation path from `agent/agent.py`'s `generate`
node - text mode is completely untouched, still prose, still `RULES`, still
`richText.tsx`'s parsing. `agent/prompts.py`'s `build_voice_system_prompt`
swaps in `VOICE_RULES` (asking *for* segmented dialogue-plus-delivery,
the opposite of text mode's `RULES`) via a new `rules` parameter on
`build_system_prompt` that defaults to the original `RULES`, so text mode's
own prompt is byte-for-byte unaffected. `POST /api/sessions/{id}/speak`
(`SpeakRequest.instruct`) and `llm/tts.py`'s `synthesize()` now thread an
optional `instruct` string through to `generate_audio` - a `SpeechSegment.delivery`
is the intended source, never spoken as words itself, only ever steering
*how* that segment's `text` is synthesized.

**Verified live, not assumed** (this doc's established discipline for any
structured-output call - schema validity passing is not the same as
content being good): `generate_voice_turn` against this project's real
default model, twice, with different emotional registers (a nervous first
date, an angry confrontation) - both times came back as clean dialogue-only
`text` with no leaked asterisks/quotes/parentheses, and sensible `delivery`
notes attached only to the segments where tone genuinely mattered, left
`None` on the plain ones. `generate_audio`'s `instruct` param was verified
separately (`pip install '.[tts]'` on this machine, a real synthesis call)
to actually change delivery, not just be accepted and silently ignored.

**Follow-up - real usage found voice mode's audio flat**: `VOICE_RULES`'s
original wording told the model "most segments should have no delivery
note at all" and never told it a non-verbal sound has to be actual words,
not a `delivery` instruction. Re-verified live against this project's real
CustomVoice checkpoint with waveform measurements (pitch, RMS loudness,
duration, silence gaps), not just listening: an `instruct` string like
"Very happy and excited." genuinely shifts synthesized pitch and pacing
(243Hz mean / 4.3s for a flat reading of a sentence vs. 306Hz / 2.6s for
the same sentence with that instruct) and "voice dropping to a soft
whisper" drops RMS loudness ~40% - so withholding `delivery` by default was
leaving real expressiveness on the table. But `instruct` alone can't
manufacture a sound that isn't in `text`: asking for "laughing" as a
delivery note with no laugh in the words moved pitch variance far less
than writing "haha" directly into `text` did. And "..." inside `text`
reliably synthesizes as ~500-600ms of real silence, while a delivery note
describing a pause changes nothing about timing. `VOICE_RULES` and
`SpeechSegment`'s field docs (`agent/prompts.py`, `agent/voice.py`) now
reflect this: give `delivery` whenever tone/pacing/emotion genuinely
colors a line rather than defaulting to unset, write real non-verbal
sounds and "..." pauses directly into `text`, and phrase `delivery` short
and direct like a voice-actor cue instead of a literary description.

**F1's own open question, answered**: F1 asked whether Ollama's `'audio'`
capability tag (`llm/capabilities.py`) means input, output, or both.
`ollama show`'s `modelinfo` for this project's own audio-capable model has
`gemma4.audio.*` architecture fields (`audio.attention.head_count`,
`audio.block_count`, `audio.embedding_length`, ...) - the same shape as
the `gemma4.vision.*` fields that back known-working image input,
indicating an audio *encoder*, i.e. input capability - and the live audio
test above confirms it: `'audio'` means input, distinct from the shipped
TTS's always-available, chat-model-independent output.

**Shipped - F0/F1, gating**: `llm/capabilities.py`'s `has_capability(providers,
provider, model, capability)` is the one shared check - `AUDIO_INPUT_CAPABILITY
= "audio"` against the capability cache. `schemas/game.py`'s `GameSummary`
(and the TS `Game` type) now carries `provider`/`model` on the list response
too, not just `GET /api/games/{id}`'s full detail, so `ChatPage` can check
this without a per-persona fetch - `useAppStore` loads `/api/models` once
at startup alongside `games`/`sessions`/`profile` (best-effort: nothing
usable right now just means voice mode never lights up, not a load
failure). `utils/voiceMode.ts`'s `hasAudioInputCapability` is the frontend
mirror of the same check. Two UI consequences, both gated on the identical
boolean: `ChatPage`'s header shows a "Voice mode" switch only for a
qualifying persona (everyone else's `ChatPage` is pixel-identical to
before), and `Composer.tsx`'s browser-dictation mic button is hidden
entirely (not just disabled) for that same persona - voice mode is the
better fit, and a lesser transcribe-and-discard-tone approximation
shouldn't compete with it in text mode.

**Shipped - F3, the end-to-end turn**: `POST /api/sessions/{id}/voice-turn`
(`api/routes/chat.py`) takes the turn's mic capture as a multipart WAV
upload, 422s with the same "config fact, not a service outage" shape as
`/speak`'s missing-voice 422 when the persona's model isn't audio-capable,
otherwise calls `agent/voice.py`'s `generate_voice_turn` with that audio
appended (via the new `agent/context.py::to_audio_message` helper) after
the session's existing text history. The response is small JSON - just
`VoiceTurn`'s segments - not inline audio; the frontend synthesizes each
segment itself through the existing `/speak` endpoint (passing `delivery`
as `instruct`), so `/voice-turn` never duplicates TTS logic. One real
design question this raised: voice mode has no separate speech-to-text
step (F0's whole point), so what gets stored as this turn's "user"
message? The answer is `VoiceTurn` gained a `user_said` field - a faithful
transcript the model itself produces as a byproduct of hearing the audio,
never spoken back, existing purely so the turn can be persisted and recalled
in later turns' text history the same as any other. `agent/agent.py`'s
`ChatState`/`RoleplayAgent` graph is deliberately untouched - `generate_voice_turn`
stays the same kind of parallel generation path F2 already established (not
a route through the tool-calling/streaming graph, which doesn't fit
structured non-streamed output anyway), so "threading audio through `ChatState`"
turned out to mean *not* touching `ChatState` at all, just giving the
parallel path its own `audio: bytes` parameter.

On the frontend, `hooks/useWavRecorder.ts` captures mic audio via a
`ScriptProcessorNode` (deprecated but universally supported, no separate
AudioWorklet module to bundle - this app only ever has one capture running
at a time) routed through a zero-gain node before `destination` so the
user never hears their own mic looped back, then hand-encodes the buffered
Float32 samples as a 16-bit PCM WAV `Blob` on stop (browsers' `MediaRecorder`
doesn't produce WAV directly).

**Superseded - auto-listen endpointing**: F3's original note that push-to-
talk (not always-listening) "avoids voice-activity-detection/silence-
trimming complexity for what's still a local single-user app" held only
until the hands-free UX was actually wanted. `useWavRecorder` now runs a
semi-duplex energy-based VAD directly off the same per-buffer RMS the level
meter already computed (no new dependency): `start()` takes an optional
`onAutoStop(hadSpeech)` callback that fires once - after `SILENCE_HANGOVER_MS`
(800ms) of quiet following detected speech, after `NO_SPEECH_TIMEOUT_MS`
(6s) with no speech at all, or at the `MAX_RECORDING_MS` (45s) hard cap -
leaving the caller to actually call `stop()` and decide the clip's fate.
Deliberately not full-duplex/barge-in: the mic only ever opens once the
persona's own TTS playback has fully finished (`VoiceCallPage.tsx`'s
`playSegments` calls `beginListening()` in its own tail, covering the
opening turn, a resumed starter reply, and a spoken followup check-back
uniformly), never while it's speaking - avoiding the acoustic-echo-
cancellation problem a mic left open during local TTS playback would
otherwise create. `handleMicTap` still works as a manual override (tap to
start, or tap to stop early ahead of whatever the endpointer would have
decided).

**Shipped - F4, the screen**: `pages/VoiceCallPage.tsx` at
`/chat/:sessionId/voice` - no new visual asset, `HeroOrb` doubles as the
reference's central sphere. A small state machine (`idle` -> `recording`
-> `thinking` -> `speaking` -> back to `idle`) drives the mic button's
icon/pulse and the caption beneath the orb (`renderRichText`, reused
as-is); the bottom row's chat-bubble button returns to `ChatPage` for the
same session (conversation history is shared - `/voice-turn` persists
into the same `messages` table `/chat` does), and `X` leaves voice mode
entirely, back to the home page.

**Verified live, end to end, not just unit-tested**: a real synthesized
WAV clip ("What's the plan for tonight? I was thinking pizza.") sent
through the actual running server to a real session against
`huihui_ai/gemma-4-abliterated`, no mocks - `user_said` came back as an
accurate transcript of the spoken audio, `segments` came back as
in-character dialogue with sensible `delivery` notes, and the session's
messages/title persisted exactly as a real turn should. `npx tsc -b
--noEmit` and `npm run build` both pass with the new frontend code.

**Shipped - local STT fallback for non-audio models**: F0-F4 above
assumed a model that could actually hear the clip. Every other model
(every hosted provider, every non-audio Ollama model) now gets a second
path instead of a hard 422: `/voice-turn` transcribes the clip locally via
`services/stt/stt.py`'s `transcribe_wav_bytes` - Hugging Face
`transformers`' ASR pipeline against whichever model
`configs/transcript.yaml`'s `model_repo` names (see "Local
speech-to-text" below) - the same one Section A3's media-transcript
fallback already uses, one shared model cache, so the two features
loading the same model don't each pay for a separate loaded instance -
and sends the resulting text instead of the
raw audio. `agent/voice.py`'s `generate_voice_turn` grew a `transcript`
parameter alongside its original `audio` one: given a transcript, `user_said`
is just that transcript (no reason to ask the model to re-transcribe what
it was just handed verbatim) and the model is only asked for a new
`VoiceReply` schema's `segments`, wrapped back into a `VoiceTurn` for a
uniform return type. The frontend's "Voice mode" switch/card
button/dictation-hiding are consequently no longer gated on
`AUDIO_INPUT_CAPABILITY` at all (`utils/voiceMode.ts`'s
`hasAudioInputCapability` is gone) - voice mode is offered for every
persona, and a missing-`transformers` 422 surfaces through
`VoiceCallPage.tsx`'s existing error banner exactly the way a missing-TTS
failure already does elsewhere in the app.

**Still genuinely open, not blocking anything above**: whether Ollama's
audio-input support is specific to the MLX engine/safetensors checkpoints
(the release notes' own framing) or works generally for GGUF checkpoints
- the live tests in this doc only confirm this project's own pulled
model/format combination; whether `langchain-ollama` will eventually ship
a first-class multimodal content-block type rather than the
`image_url`-repurposed one used here; a hosted provider's audio input
(e.g. OpenAI's) is unexplored, no API key configured to verify against
live; and the actual in-browser mic-capture/playback UX (permission
prompts, mobile Safari's `AudioContext` quirks, real-world latency feel)
hasn't been driven through a real browser session yet - deliberately left
for manual testing rather than automated here.

### SPA fallback route

`main.py`'s catch-all `@app.get("/{full_path:path}")` serves a real static
file (`dev-ui/dist/assets/*.js`, `dist/profile-avatar.svg`, ...) as-is, and
falls back to `index.html`'s content for anything else - a client-side
route like `/explore` has no matching file on disk, so a hard refresh,
bookmark, or shared link on it would otherwise 404 even though the exact
same path works fine reached by clicking through the app.

**Deliberately not** `app.mount("/", StaticFiles(directory=..., html=True))`
plus a separate catch-all route registered after it, even though that's
the more obvious-looking design - verified live that it doesn't actually
work: Starlette commits to the first *matching* route, not the first one
that succeeds, and a `Mount("/")` matches every path (mount matching is
prefix-based, and `/` is a prefix of everything). It intercepts every
request before a route registered after it is ever reached, even a path
the mount itself would 404 on - so a route "after" it in registration
order never actually gets a chance to handle that 404. One combined
catch-all route, doing both the real-file-serving and the fallback job
itself (`FileResponse` for a real file under `dist/`, `index.html`
otherwise, with a resolved-path containment check against path
traversal), is what actually has to replace the mount, not sit behind it.

A path under `/api/` or `/media/` that no real router claims is an
explicit exception, `HTTPException(404)` rather than the SPA shell -
registration order alone keeps this catch-all from out-competing those
routers for a path they *do* claim, but a mistyped or removed endpoint
past that point would otherwise silently get a 200 HTML response instead
of a real 404, since nothing else claims it either.

### Profile page

`ProfileAvatar` is a real link (`/profile`) now, not a purely decorative
fixed image - one destination for identity, account-level stats, recent
activity, and settings, replacing three separate "Settings - coming soon"
buttons (`ExplorePage`, `SkillsPage`, `AudioPage`) that all pointed
nowhere. Translated from `ref/profile.webp` rather than copied literally:
that reference is a *game's* profile screen (3D character customization,
XP/levels, wins, "Finals," trophy achievements) - none of that maps onto a
single-user companion chat app, there's no competition or levels to have.
What translates is the *shape* - identity + stats + recent activity +
settings, one destination instead of three dead ends - not the specific
XP/trophy mechanics.

- **Identity**: `dev-ui/src/data/profileAvatars.ts` curates 7 pickable
  looks - the original single `public/profile-avatar.svg` plus the 6
  vendored Draftbit Personas illustrations `VoiceAvatar` already uses for
  TTS voice presets, offered here as "pick your own look" rather than
  "pick a voice's look." No new illustrated assets exist to draw from, so
  this deliberately reuses what's already vendored in the same art style
  rather than fabricating new ones. An optional display name is purely
  cosmetic (a "Hello, {name}" header, per the reference's own "Hello,
  Johnny") - nothing in this app previously tracked a user identity at
  all. Both persist to the `app_settings` table's `profile` key
  (`SettingsRepository`) - the same "single-user scale doesn't justify a
  dedicated table for a few fields" reasoning as the `default_provider`
  key above.
  `useAppStore`'s `profile` is loaded once via `loadAll()` (alongside
  `games`/`sessions`) rather than each `ProfileAvatar` instance fetching
  its own copy, since it's shown on nearly every page's `TopBar`.
- **Stats** - the honest substitute for "Wins / Total games / Finals":
  account-level totals, not competitive scores. `GET /api/profile/stats`
  sums `SessionRepository.library_stats()` across every persona (total
  sessions, total messages *sent* - `rounds`, which only counts the
  user's own turns - and total time played) plus `GameLoader.list_all()`'s
  count for total personas created. Deliberately **not** filtered to
  non-archived sessions, unlike the sidebar/Library lists - the same
  reasoning as `library_stats()` itself not filtering (see "Archiving a
  session" above): archiving hides a chat from day-to-day lists, it
  doesn't erase the time spent in it from an all-time total. This is also
  where a future stats page - surfacing the token/latency half of
  `observability/metrics.py`'s logging, which is plain log lines today,
  not persisted anywhere queryable - would eventually get a real
  destination - not built here, since surfacing it needs a metrics
  persistence layer that doesn't exist yet, a separate, bigger piece of
  work than this page.
- **"Recent activity"**, deliberately not "Last achievements" (see the
  translation note above) - the last few sessions started and personas
  created, merged and sorted by time, capped at 6. Sessions come from
  `SessionRepository.list_all()` (excludes archived, unlike the stats
  above - "recent" is about what's fresh, the same scoping A4's sidebar
  already uses). `Game` has no `created_at` field at all (a persona is
  just a YAML file, nothing tracks when it was authored) - each
  `game.yaml`'s own file mtime is the closest real proxy, the same
  "recency from a real filesystem/API timestamp, not a fabricated one"
  spirit as `llm/capabilities.py`'s Ollama `modified_at` sort.
- **Settings**: genuinely nothing in this app is configurable through a
  UI today (everything lives in `configs/*.yaml`/`.env`, see "Config
  hygiene" above) - rather than build fake settings toggles with nothing
  real behind them just to fill the space the old buttons implied, this
  section says so plainly and points at where real configuration actually
  lives. The identity fields above are the one thing that genuinely is a
  per-account setting.

## Data flow for one chat turn

1. `POST /api/sessions/{id}/chat` (`api/routes/chat.py`) loads the `Game`,
   stores the user's message, and schedules the background fold.
2. `RoleplayAgent.graph.astream_events(...)` runs `prepare` (embeds the
   message and recalls scoped long-term memory if `memory_recall` is on,
   then reads the summary + last `keep_last_messages` messages - all off
   the event loop) then `generate`, which streams from the model and loops
   through a shared `ToolNode` for any authorized skill calls before
   producing the reply the user sees.
3. `StreamingReply` (`agent/response.py`) yields text chunks to the HTTP
   response as they arrive, and captures the model's own timing/token
   stats from the `on_chat_model_end` event.
4. Once the stream ends, the assistant's full reply is persisted and the
   turn's stats are logged (`observability/metrics.log_chat_turn`).
5. Only now does Starlette run the background fold task (a no-op unless
   the session has crossed the fold threshold) - which, when
   `memory_recall` is on, also embeds and stores the folded chunk before
   compressing it away.
6. If the user later clicks read-aloud on the reply, `POST
   /api/sessions/{id}/speak` is a separate, on-demand request - not part
   of this turn's critical path.
