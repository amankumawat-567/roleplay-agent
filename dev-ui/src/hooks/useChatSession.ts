import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, streamChat } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import type { ChatMessage } from "../types";

interface ChatSessionState {
  title: string;
  gameId: string | null;
  messages: ChatMessage[];
  loading: boolean;
  streaming: boolean;
  error: string | null;
  sendMessage: (text?: string) => Promise<void>;
  /** Re-fetches messages without touching the loading/streaming state -
   * used to pick up a section B2 follow-up the server delivered in the
   * background, which this tab wouldn't otherwise see land. */
  refresh: () => Promise<void>;
}

export function useChatSession(sessionId: string): ChatSessionState {
  // The store (kept current by both A0's auto-title and A3's rename, from
  // anywhere in the app - see useAppStore's setSessionTitle/renameSession)
  // is the source of truth for the title once it has this session; this
  // local copy is only the fallback for the moment before that's true
  // (e.g. a direct URL nav landing here before the store finishes loading).
  const storeTitle = useAppStore((s) => s.sessions.find((session) => session.id === sessionId)?.title);
  const setSessionTitle = useAppStore((s) => s.setSessionTitle);
  const [fallbackTitle, setFallbackTitle] = useState("");
  const [gameId, setGameId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedFor = useRef<string | null>(null);
  // Tracks whether this session already has a user-role message, so
  // sendMessage knows when it's sending the *first* one - that's the turn
  // the backend auto-titles from (see docs/roadmap.md A0).
  const hasUserMessageRef = useRef(false);

  useEffect(() => {
    if (loadedFor.current === sessionId) return;
    loadedFor.current = sessionId;
    setLoading(true);
    setError(null);
    api
      .getSessionMessages(sessionId)
      .then((res) => {
        setFallbackTitle(res.session.title);
        setSessionTitle(sessionId, res.session.title);
        setGameId(res.session.game_id);
        setMessages(res.messages);
        hasUserMessageRef.current = res.messages.some((m) => m.role === "user");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load session"))
      .finally(() => setLoading(false));
  }, [sessionId, setSessionTitle]);

  const sendMessage = useCallback(
    async (text?: string) => {
      const isFirstUserMessage = !!text && !hasUserMessageRef.current;
      if (text) {
        hasUserMessageRef.current = true;
        setMessages((prev) => [...prev, { role: "user", content: text }]);
      }
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
      setStreaming(true);
      setError(null);

      try {
        let full = "";
        for await (const piece of streamChat(sessionId, text)) {
          full += piece;
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = { role: "assistant", content: full };
            return next;
          });
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Something went wrong talking to the model.");
        setMessages((prev) => prev.slice(0, -1)); // drop the empty placeholder bubble
      } finally {
        setStreaming(false);
      }

      if (isFirstUserMessage) {
        // The backend already auto-titled this session from that first
        // message (A0) - pick up the real title instead of the persona-name
        // placeholder, and push it into the store so the header and the
        // sidebar's session list both pick it up.
        api
          .getSessionMessages(sessionId)
          .then((res) => setSessionTitle(sessionId, res.session.title))
          .catch(() => {
            // Best-effort - the title just stays on the placeholder until
            // the next load if this fails.
          });
      }
    },
    [sessionId, setSessionTitle],
  );

  const refresh = useCallback(async () => {
    try {
      const res = await api.getSessionMessages(sessionId);
      setSessionTitle(sessionId, res.session.title);
      setGameId(res.session.game_id);
      setMessages(res.messages);
      hasUserMessageRef.current = res.messages.some((m) => m.role === "user");
    } catch {
      // Best-effort - a countdown poll failing quietly is fine, the user
      // can still see/send messages; the next poll will just try again.
    }
  }, [sessionId, setSessionTitle]);

  return {
    title: storeTitle ?? fallbackTitle,
    gameId,
    messages,
    loading,
    streaming,
    error,
    sendMessage,
    refresh,
  };
}
