export interface Game {
  id: string;
  title: string;
  /** Who the AI plays, shown anywhere the app refers to "who you're
   * talking to" - distinct from `title` (the scenario/card display name,
   * e.g. "Rooftop First Date"). Null falls back to `title`, via
   * characterNameFor() in utils/persona.ts. */
  character_name: string | null;
  tags: string[];
  /** Filename only (e.g. "cover.jpg") - build the URL as `/media/games/{id}/{cover_image}`. */
  cover_image: string | null;
  /** Carried on the list response so voice mode's availability (section F -
   * see utils/voiceMode.ts) can be checked against the capability cache
   * without a per-persona fetch. */
  provider: string;
  model: string;
}

/** Full persona definition, as edited in GameEditorPage. */
export interface GameDetail {
  id: string;
  title: string;
  character_name: string | null;
  tags: string[];
  provider: string;
  model: string;
  starter: "ai" | "user";
  persona: string;
  user_role: string;
  script: string;
  research_query: string;
  research_notes: string;
  num_ctx: number | null;
  memory_recall: boolean;
  skills: string[];
  cover_image: string | null;
  /** One of dev-ui/src/data/voices.ts's ids (must stay in sync with
   * llm.tts.SUPPORTED_VOICES on the backend), or null for no audio replies. */
  voice: string | null;
}

/** Body for POST /api/games. `id` is optional - derived from title when omitted. */
export interface GameCreateRequest {
  id?: string;
  title: string;
  character_name: string | null;
  tags: string[];
  provider: string;
  model: string;
  starter: "ai" | "user";
  persona: string;
  user_role: string;
  script: string;
  research_query: string;
  num_ctx: number | null;
  memory_recall: boolean;
  skills: string[];
  voice: string | null;
}

/** Body for PUT /api/games/{id}. */
export type GameUpdateRequest = Omit<GameCreateRequest, "id">;

export interface SearchResult {
  session_id: string;
  title: string;
  snippet: string;
}

export interface SessionSummary {
  id: string;
  game_id: string;
  title: string;
  created_at: number;
  archived_at: number | null;
}

export interface SessionDetail extends SessionSummary {
  summary: string;
  summarized_count: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  // "followup" for an assistant message delivered by a scheduled check-back
  // (see agent/followups.py) rather than a direct reply - absent/"reply"
  // for everything else, including messages still streaming in live.
  kind?: "reply" | "followup";
}

export interface SessionMessagesResponse {
  session: SessionDetail;
  messages: ChatMessage[];
}

export interface CreateSessionResponse {
  session_id: string;
  starter: "ai" | "user";
}

export interface BuilderMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CreateBuilderSessionResponse {
  builder_session_id: string;
}

export interface BuilderSessionDetail {
  id: string;
  game_id: string | null;
  title: string;
  created_at: number;
}

export interface BuilderSessionMessagesResponse {
  session: BuilderSessionDetail;
  messages: BuilderMessage[];
}

/** What the AI game-builder proposes from a conversation - a subset of
 * GameDetail's fields; the rest (provider/model/starter/etc.) keep the
 * editor's own defaults. */
export interface GameDraft {
  title: string;
  tags: string[];
  persona: string;
  user_role: string;
  script: string;
  research_query: string;
}

export interface SkillSummary {
  id: string;
  description: string;
}

/** One "played game" card for the Library grid - a persona aggregated
 * across every session you've had with it. */
export interface LibraryEntry {
  id: string;
  title: string;
  character_name: string | null;
  tags: string[];
  cover_image: string | null;
  session_count: number;
  rounds: number;
  played_seconds: number;
  last_played: number;
}

/** Section B2 - the persona's next scheduled check-back for a session, if
 * any. `fire_at` is a unix-seconds timestamp; null means nothing pending. */
export interface ScheduledFollowup {
  fire_at: number | null;
}

/** Model discovery (docs/roadmap.md section D) - `GET /api/models` only
 * ever lists a provider that's actually usable right now (Ollama
 * reachable, or a hosted provider with its API key configured), never a
 * disabled/greyed-out entry for one that isn't. */
export interface ModelInfo {
  id: string;
  capabilities: string[];
  /** Unix-seconds - null for a hosted model (no real "last pulled"
   * timestamp exists for those the way an Ollama pull's mtime does). */
  modified_at: number | null;
}

export interface ProviderModels {
  provider: string;
  models: ModelInfo[];
}

export interface ModelsResponse {
  /** Null only when nothing anywhere is usable right now. */
  default_provider: string | null;
  providers: ProviderModels[];
}

/** One spoken line of a voice-mode reply, in the order it would be said -
 * see agent/voice.py's SpeechSegment. `delivery` is never spoken text
 * itself, only the /speak call's `instruct` param at synthesis time. */
export interface VoiceSegment {
  text: string;
  delivery: string | null;
}

/** POST /api/sessions/{id}/voice-turn's response (section F3). `user_said`
 * is the model's own transcript of the mic audio it was just given - the
 * only record of what the user said, since voice mode never runs a
 * separate speech-to-text step (see docs/roadmap.md F0). */
export interface VoiceTurnResponse {
  user_said: string;
  segments: VoiceSegment[];
}

/** One cloned voice as GET/POST /api/voices/cloned returns it - `id` is
 * the filename stem (what a persona's `voice:` field references), `name`
 * is its display name, `image` is a sibling profile-image filename (if
 * one was uploaded) servable off the same /media/voice-samples/ mount as
 * the wav itself. */
export interface ClonedVoiceInfo {
  id: string;
  name: string;
  image: string | null;
}

/** The local user's own "account" - one avatar pick + an optional display
 * name, nothing more (see docs/ARCHITECTURE.md's "Profile page"). */
export interface Profile {
  avatar_id: string;
  display_name: string | null;
}

/** Account-level totals - the honest substitute for a game's "Wins /
 * Total games / Finals": there's no competition in a single-user
 * companion chat app, just how much of it you've actually done. */
export interface ProfileStats {
  persona_count: number;
  session_count: number;
  message_count: number;
  played_seconds: number;
}

export interface RecentActivityItem {
  kind: "session" | "persona";
  title: string;
  game_id: string | null;
  created_at: number;
}

export interface ProfileStatsResponse {
  stats: ProfileStats;
  recent_activity: RecentActivityItem[];
}
