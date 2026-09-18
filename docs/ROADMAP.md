# Future scope / roadmap

Longer-term directions being considered for the project. Nothing here is
scheduled or committed - this is a holding place for ideas so they don't
get lost, and a starting point for scoping when work on them begins.

## 1. Multi-provider model support

We currently touch four model categories, each of which is a separate
integration point today:

1. **Chat model** - the main capability handler, i.e. the roleplay agent
   itself (persona play, the "Build with AI" game-builder assistant).
2. **Speech recognition (STT)** - transcribing the user's spoken input.
3. **TTS** - synthesizing the persona's voice.
4. **Embeddings** - used for memory recall / research lookups.

Goal: support multiple providers per category instead of being tied to
one, so a deployment (or an individual user) can choose the provider
that fits their cost, latency, privacy, or quality needs - including
local/self-hosted options via **Hugging Face** and **Ollama** across
*all four* categories, not just chat.

Things to work out:

- A common provider interface per category (chat, STT, TTS, embeddings)
  that hides provider-specific request/response shapes, auth, and
  streaming behavior behind one contract, similar in spirit to how
  `provider`/`model` already work for chat in `configs/providers.yaml`.
- Per-category config: which provider/model a given game, user, or
  deployment defaults to, with sane fallback behavior if a provider is
  unavailable or a call fails (retry another provider vs. hard error).
- Capability differences between providers (e.g. not every STT/TTS
  provider supports streaming, voice cloning, or every language) need to
  be surfaced instead of silently degrading.
- Local providers (Hugging Face model hub, Ollama) imply a story for
  model download/caching, hardware requirements (GPU vs CPU), and
  startup cost, which cloud providers don't have.
- Before implementing: research how other AI applications structure
  multi-provider support (abstraction boundaries, config shape,
  fallback/routing behavior, how they handle capability differences) so
  we're not reinventing a pattern that's already been worked out
  elsewhere.

## 2. Scalability

The app currently assumes a single local user and flat-file storage.
This track is about removing both assumptions so the app can support
many concurrent users with isolated data.

### 2.1 Login and user profiles

- Real authentication (sign up / sign in), replacing the current
  single-user assumption.
- A user profile: display name, avatar/profile picture, and whatever
  preferences make sense to attach to an account (default provider,
  theme, etc. - ties into sections 1 and 4).
- Session/auth token handling across the API and dev UI.

### 2.2 Per-user data segregation

Once there are multiple accounts, data needs to be partitioned per user
rather than shared globally. This covers at least:

- **Play sessions, per game** - a user's conversation history/transcripts
  for a given game shouldn't be visible to or overwritten by another
  user playing the same game.
- **Newly created games** - games authored or generated ("Build with AI")
  by a user are scoped to that user (with a path to make some public/
  shared, see 2.3).
- **Newly created audio** - generated TTS clips and any uploaded audio
  (e.g. voice samples) are scoped to their owner.

Needs a concrete ownership model (user id on every record) and access
checks in the API, not just filtering in the UI.

### 2.3 Share game / share score

- Let a user share a game (persona) they created with others, either via
  a shareable link or by publishing it somewhere discoverable.
- Let a user share a score/result from a play session (e.g. "I got X in
  this game") - implies scores/results need to be a first-class,
  storable concept, not just ephemeral chat output.
- Needs a decision on visibility levels (private / link-only / public)
  and whether shared content is a read-only snapshot or stays linked to
  the live game.

### 2.4 Rate a game

- Let users rate games (e.g. a star rating, thumbs up/down), and surface
  aggregate ratings when browsing/picking games.
- Implies basic anti-abuse consideration (rate limiting, one rating per
  user per game) once this is multi-user.

### 2.5 Move storage to a proper database

- Replace the current JSON/YAML file storage (`data/games/*.yaml`,
  transcripts, etc.) with a real database so the app can scale past a
  single local install.
- Explicitly includes **audio** storage, not just structured data -
  audio files are larger and need a different storage strategy (object
  storage / blob storage rather than rows in a relational DB, with the
  DB holding metadata + a reference).
- This is a prerequisite for 2.1-2.4: accounts, per-user segregation,
  sharing, and ratings all need durable, queryable, concurrent-safe
  storage that flat files don't give us.
- Needs a migration path for existing local file-based data so current
  users/games aren't lost when this lands.

## 3. Skill extensibility

Make it easy to extend model capability via skills, beyond what's
possible in [SKILLS.md](SKILLS.md) today:

- **Public skill packets** that can be discovered, added, and used
  easily - effectively a small marketplace/registry of reusable skills,
  with versioning and metadata (what the skill does, what permissions/
  tools it needs).
- **Sandboxed execution** - a stable, isolated execution environment for
  running third-party skill code, with appropriate protections against
  exploitation (resource limits, no arbitrary filesystem/network access
  by default, review or signing before a skill is trusted).
- **In-UI authoring** - users can add their own skills directly from the
  UI, without editing files or redeploying the app. Implies a UI flow for
  writing/uploading a skill, testing it, and enabling it on a specific
  game.

Security is the hard part of this section: skills are effectively
user-supplied code that gets executed on behalf of the platform, so the
sandboxing and permission model need to be designed before the "easy to
add" UX is built, not after.

## 4. UX customization

- **Avatar generator** - a built-in customizer for building a persona's
  (or the user's own) visual identity from parts, rather than only
  uploading a picture. A reasonable shape for this:
  - Character appearance broken into independent, swappable categories
    (e.g. body/base, hair, facial hair, eyes, mouth/expression,
    accessories) plus color pickers for the relevant parts (skin, hair,
    accessory, background color, etc.).
  - Assets built as layered, vector (SVG) art per category/option so
    combinations stay crisp at any size and are cheap to render/compose
    in the browser.
  - A picker UI showing live preview as selections change, plus a
    "randomize" action to get a starting point quickly.
  - The full set of choices should reduce to a small, shareable
    configuration (e.g. encoded in a URL or a compact string) so an
    avatar can be reproduced or linked without server-side storage of
    the rendered image, and exported as a static image/SVG when needed
    (profile picture, game card, etc.).
  - Could later add an AI-generation path (prompt-based portrait) as an
    alternative to manual part-picking, feeding into the same profile/
    card slots as the layered generator.
- **Game-card generator** - similar part-based or AI-based customization
  applied to the card representation of a game, so cards don't have to
  be hand-uploaded images.
- Together, these mean a user can build a profile picture, game card,
  skill card, or audio profile either by uploading their own asset or by
  generating one through these in-app tools.
- **Themes** - add theming to the app shell and to the in-game chat
  (light/dark plus possibly per-user accent/theme choice, stored on the
  profile from 2.1).

## 5. Multi-AI, role-based games

Games/scenarios involving more than one AI-driven role at once, rather
than a single AI persona opposite the user. Implies:

- A game definition that can declare more than one AI-played role
  (today's `game.yaml` assumes one persona opposite the user).
- Turn/conversation management across multiple AI participants (who
  responds when, how they stay aware of each other's dialogue).
- Interaction with section 6 below, since multiplayer PvP rooms may want
  a mix of human and AI-played roles in the same room.

## 6. Online PvP modes

### Game selection modes

1. Random game pick
2. Category-based random game pick (constrained by tag/category, see
   `tags` in `game.yaml`)
3. Specific game pick (chosen explicitly by the player/room owner)

### Player matching modes

1. Global random matchmaking
2. Regional random matchmaking (implies knowing/asking player region)
3. Public room - shareable with friends, with remaining seats fillable
   by random players (global or regional)
4. Private room - only players who were explicitly invited/shared the
   room link can join

### Role assignment modes

1. Random role allotment (with a gender preference option, where
   applicable to the game's roles)
2. Room owner assigns roles to players
3. Players pick their own role (first-come or via some selection UI)

This track depends heavily on sections 2.1 (accounts) and 2.5 (proper
database) landing first, since matchmaking and rooms need real user
identity and low-latency shared state that file-based storage can't
provide.
