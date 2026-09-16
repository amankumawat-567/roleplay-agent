import { create } from "zustand";
import { api } from "../services/api";
import type { Game, ModelsResponse, Profile, SessionSummary } from "../types";

const DEFAULT_PROFILE: Profile = { avatar_id: "profile-avatar", display_name: null };

interface AppState {
  games: Game[];
  sessions: SessionSummary[];
  profile: Profile;
  /** The capability cache (llm/capabilities.py), loaded once here rather
   * than per-page - section F's voice mode switch (ChatPage) and
   * Composer's dictation gate both need it. Null until the first
   * loadAll() resolves; utils/voiceMode.ts treats that as "not available
   * yet" rather than guessing. */
  models: ModelsResponse | null;
  loading: boolean;
  error: string | null;
  researchingGameId: string | null;

  loadAll: () => Promise<void>;
  /** Persists a profile change and updates every ProfileAvatar on screen -
   * loaded once here rather than each avatar instance fetching its own
   * copy, the same "shared app-wide state" reasoning `games`/`sessions`
   * already use. */
  updateProfile: (profile: Profile) => Promise<void>;
  createSession: (gameId: string) => Promise<{ sessionId: string; starter: "ai" | "user" }>;
  deleteSession: (sessionId: string) => Promise<void>;
  /** Archives a session - removed from `sessions` the same way deleteSession
   * removes one (the backend's GET /api/sessions already excludes archived
   * rows, so this just keeps the optimistic local copy in sync), but the
   * row itself isn't gone - it reappears in the Archives view. */
  archiveSession: (sessionId: string) => Promise<void>;
  renameSession: (sessionId: string, title: string) => Promise<void>;
  /** Updates a session's title locally with no API call - for syncing the
   * sidebar after A0's server-side auto-title (already persisted, so
   * re-PATCHing it back would be redundant). renameSession (above) is the
   * user-initiated version that actually persists a new title. */
  setSessionTitle: (sessionId: string, title: string) => void;
  refreshResearch: (gameId: string) => Promise<void>;
}

export const useAppStore = create<AppState>((set, get) => ({
  games: [],
  sessions: [],
  profile: DEFAULT_PROFILE,
  models: null,
  loading: true,
  error: null,
  researchingGameId: null,

  loadAll: async () => {
    set({ loading: true, error: null });
    try {
      const [games, sessions, profile, models] = await Promise.all([
        api.listGames(),
        api.listSessions(),
        api.getProfile(),
        // Best-effort - a session with nothing usable right now (no
        // Ollama, no hosted key) just means voice mode never lights up
        // anywhere, not a load failure for the whole app.
        api.getModels().catch(() => null),
      ]);
      set({ games, sessions, profile, models, loading: false });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "Failed to load", loading: false });
    }
  },

  updateProfile: async (profile: Profile) => {
    const previous = get().profile;
    set({ profile });
    try {
      await api.updateProfile(profile);
    } catch (err) {
      set({ profile: previous });
      throw err;
    }
  },

  createSession: async (gameId: string) => {
    const res = await api.createSession(gameId);
    // Show it in the sidebar right away rather than waiting for a reload.
    const game = get().games.find((g) => g.id === gameId);
    set((state) => ({
      sessions: [
        {
          id: res.session_id,
          game_id: gameId,
          title: game?.title ?? gameId,
          created_at: Date.now() / 1000,
          archived_at: null,
        },
        ...state.sessions,
      ],
    }));
    return { sessionId: res.session_id, starter: res.starter };
  },

  deleteSession: async (sessionId: string) => {
    // Optimistic - the sidebar list should feel instant, and a failed
    // delete is rare enough to just reconcile via the next loadAll().
    const previous = get().sessions;
    set({ sessions: previous.filter((s) => s.id !== sessionId) });
    try {
      await api.deleteSession(sessionId);
    } catch (err) {
      set({ sessions: previous });
      throw err;
    }
  },

  archiveSession: async (sessionId: string) => {
    const previous = get().sessions;
    set({ sessions: previous.filter((s) => s.id !== sessionId) });
    try {
      await api.archiveSession(sessionId);
    } catch (err) {
      set({ sessions: previous });
      throw err;
    }
  },

  renameSession: async (sessionId: string, title: string) => {
    const previous = get().sessions;
    set({ sessions: previous.map((s) => (s.id === sessionId ? { ...s, title } : s)) });
    try {
      await api.renameSession(sessionId, title);
    } catch (err) {
      set({ sessions: previous });
      throw err;
    }
  },

  setSessionTitle: (sessionId: string, title: string) => {
    set((state) => ({
      sessions: state.sessions.map((s) => (s.id === sessionId ? { ...s, title } : s)),
    }));
  },

  refreshResearch: async (gameId: string) => {
    set({ researchingGameId: gameId });
    try {
      await api.runResearch(gameId);
    } finally {
      set({ researchingGameId: null });
    }
  },
}));
