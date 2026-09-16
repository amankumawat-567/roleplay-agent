import type {
  BuilderSessionMessagesResponse,
  ChatMessage,
  CreateBuilderSessionResponse,
  CreateSessionResponse,
  Game,
  GameCreateRequest,
  GameDetail,
  GameDraft,
  GameUpdateRequest,
  LibraryEntry,
  ModelsResponse,
  Profile,
  ProfileStatsResponse,
  ScheduledFollowup,
  SearchResult,
  SessionMessagesResponse,
  SessionSummary,
  SkillSummary,
  VoiceTurnResponse,
} from "../types";

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(body?.detail ?? `Request failed: ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listGames: () => request<Game[]>("/api/games"),

  getGame: (gameId: string) => request<GameDetail>(`/api/games/${gameId}`),

  createGame: (body: GameCreateRequest) =>
    request<GameDetail>("/api/games", { method: "POST", body: JSON.stringify(body) }),

  updateGame: (gameId: string, body: GameUpdateRequest) =>
    request<GameDetail>(`/api/games/${gameId}`, { method: "PUT", body: JSON.stringify(body) }),

  // A bare DELETE returns 204 with no body - request<T>() always calls
  // res.json(), which throws on an empty body, so this bypasses it.
  deleteGame: async (gameId: string): Promise<void> => {
    const res = await fetch(`/api/games/${gameId}`, { method: "DELETE" });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new ApiError(body?.detail ?? `Request failed: ${res.status}`, res.status);
    }
  },

  uploadGameCover: async (gameId: string, file: File): Promise<GameDetail> => {
    const formData = new FormData();
    formData.append("file", file);
    // No Content-Type header here - the browser sets multipart/form-data
    // with the right boundary itself; overriding it breaks the upload.
    const res = await fetch(`/api/games/${gameId}/cover`, { method: "POST", body: formData });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new ApiError(body?.detail ?? `Request failed: ${res.status}`, res.status);
    }
    return res.json() as Promise<GameDetail>;
  },

  listSessions: () => request<SessionSummary[]>("/api/sessions"),

  createSession: (gameId: string) =>
    request<CreateSessionResponse>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ game_id: gameId }),
    }),

  getSessionMessages: (sessionId: string) =>
    request<SessionMessagesResponse>(`/api/sessions/${sessionId}/messages`),

  renameSession: (sessionId: string, title: string) =>
    request<SessionSummary>(`/api/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),

  listArchivedSessions: () => request<SessionSummary[]>("/api/sessions/archived"),

  archiveSession: (sessionId: string) =>
    request<SessionSummary>(`/api/sessions/${sessionId}/archive`, { method: "POST" }),

  unarchiveSession: (sessionId: string) =>
    request<SessionSummary>(`/api/sessions/${sessionId}/unarchive`, { method: "POST" }),

  // A bare DELETE returns 204 with no body - request<T>() always calls
  // res.json(), which throws on an empty body, so this bypasses it.
  deleteSession: async (sessionId: string) => {
    const res = await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new ApiError(body?.detail ?? `Request failed: ${res.status}`, res.status);
    }
  },

  getScheduledFollowup: (sessionId: string) =>
    request<ScheduledFollowup>(`/api/sessions/${sessionId}/scheduled`),

  // Returns a WAV Blob, not JSON - bypasses request<T>() the same way the
  // other binary/no-body calls above do. Throws ApiError on a 422 (this
  // persona has no voice configured - callers should fall back to browser
  // speech synthesis) same as any other failure, so the caller can
  // distinguish "not configured" (422) from a real synthesis failure (503).
  // `instruct` is a voice-mode SpeechSegment's own `delivery` note (section
  // F2) - omitted by the plain text-mode read-aloud button.
  speak: async (sessionId: string, text: string, instruct?: string | null): Promise<Blob> => {
    const res = await fetch(`/api/sessions/${sessionId}/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, instruct: instruct ?? null }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new ApiError(body?.detail ?? `Request failed: ${res.status}`, res.status);
    }
    return res.blob();
  },

  // Same request shape and error cases as speak() above, but the response
  // is a streamed body of raw PCM16LE mono chunks (sample rate in an
  // X-Sample-Rate header), not one complete WAV Blob - returns the raw
  // Response itself, not its parsed body, so utils/pcmStreamPlayer.ts can
  // read that body progressively via response.body's own reader instead
  // of waiting for it to fully arrive first. Used by both this app's
  // actual callers (the read-aloud button, voice mode) in place of
  // speak() - see chat.py's /speak-stream docstring for why.
  speakStream: async (sessionId: string, text: string, instruct?: string | null): Promise<Response> => {
    const res = await fetch(`/api/sessions/${sessionId}/speak-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, instruct: instruct ?? null }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new ApiError(body?.detail ?? `Request failed: ${res.status}`, res.status);
    }
    return res;
  },

  // Section F3 - `audio` is the turn's raw mic capture as a WAV Blob, sent
  // straight to the model (no transcription step, see docs/roadmap.md F0).
  // Multipart, not JSON, the same way uploadGameCover sends a file above.
  voiceTurn: async (sessionId: string, audio: Blob): Promise<VoiceTurnResponse> => {
    const formData = new FormData();
    formData.append("audio", audio, "turn.wav");
    const res = await fetch(`/api/sessions/${sessionId}/voice-turn`, { method: "POST", body: formData });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new ApiError(body?.detail ?? `Request failed: ${res.status}`, res.status);
    }
    return res.json() as Promise<VoiceTurnResponse>;
  },

  runResearch: (gameId: string) =>
    request<{ research_notes: string }>(`/api/games/${gameId}/research`, { method: "POST" }),

  search: (query: string) =>
    request<SearchResult[]>(`/api/search?q=${encodeURIComponent(query)}`),

  createBuilderSession: (title: string, gameId?: string) =>
    request<CreateBuilderSessionResponse>("/api/games/builder/sessions", {
      method: "POST",
      body: JSON.stringify({ title, game_id: gameId ?? null }),
    }),

  getBuilderSessionMessages: (builderSessionId: string) =>
    request<BuilderSessionMessagesResponse>(`/api/games/builder/sessions/${builderSessionId}/messages`),

  generateBuilderDraft: (builderSessionId: string, context?: string) =>
    request<GameDraft>(`/api/games/builder/sessions/${builderSessionId}/draft`, {
      method: "POST",
      body: JSON.stringify({ context: context ?? null }),
    }),

  generateDraftFromTranscript: (transcript: string) =>
    request<GameDraft>("/api/games/builder/draft-from-transcript", {
      method: "POST",
      body: JSON.stringify({ transcript }),
    }),

  generateDraftFromVideo: (url: string) =>
    request<GameDraft>("/api/games/builder/draft-from-video", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  listSkills: () => request<SkillSummary[]>("/api/skills"),

  listLibrary: () => request<LibraryEntry[]>("/api/library"),

  getModels: () => request<ModelsResponse>("/api/models"),

  // Voice ids discovered purely by presence in data/voice_samples/ (see
  // scripts/extract_audio_sample.py) - not curated in dev-ui/src/data/voices.ts
  // the way the preset speakers are, since a cloned voice has no hand-picked
  // name/style/avatar to author.
  getClonedVoices: () => request<{ voices: string[] }>("/api/voices/cloned"),

  getProfile: () => request<Profile>("/api/profile"),

  updateProfile: (body: Profile) =>
    request<Profile>("/api/profile", { method: "PUT", body: JSON.stringify(body) }),

  getProfileStats: () => request<ProfileStatsResponse>("/api/profile/stats"),
};

/** Streams the assistant's reply as it's generated. `message` is omitted
 * (undefined) when the AI is the one starting the conversation. */
export async function* streamChat(
  sessionId: string,
  message: string | undefined,
): AsyncGenerator<string> {
  const res = await fetch(`/api/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null);
    throw new ApiError(body?.detail ?? `Chat request failed: ${res.status}`, res.status);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) return;
    yield decoder.decode(value, { stream: true });
  }
}

/** Streams the game-builder assistant's reply as it's generated. `context`
 * is the "here's the persona as it stands today" priming block for an
 * "Edit with AI" conversation - transient grounding, never persisted as a
 * turn in its own right (see api/routes/game_builder.py). */
export async function* streamBuilderSessionChat(
  builderSessionId: string,
  message: string,
  context?: string,
): AsyncGenerator<string> {
  const res = await fetch(`/api/games/builder/sessions/${builderSessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, context: context ?? null }),
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null);
    throw new ApiError(body?.detail ?? `Builder chat request failed: ${res.status}`, res.status);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) return;
    yield decoder.decode(value, { stream: true });
  }
}

export type { ChatMessage };
export { ApiError };
