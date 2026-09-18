import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, Sparkles } from "lucide-react";
import { api, ApiError, streamBuilderSessionChat } from "../services/api";
import { ChatBubble } from "../components/ChatBubble";
import { Composer } from "../components/Composer";
import { GameGenerateBar } from "../components/GameGenerateBar";
import { HeroOrb } from "../components/HeroOrb";
import { renderRichText } from "../utils/richText";
import type { BuilderMessage } from "../types";

interface ExistingGameContext {
  title: string;
  tags: string;
  persona: string;
  user_role: string;
  script: string;
  research_query: string;
}

function TypingIndicator() {
  return (
    <div className="animate-rise-in flex w-fit items-center gap-1 self-start rounded-2xl rounded-bl-md border border-[var(--color-border-soft)] bg-[var(--color-panel)] px-4 py-3">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-sub-dim)]"
          style={{ animationDelay: `${i * 0.15}s`, animationDuration: "0.9s" }}
        />
      ))}
    </div>
  );
}

/** The builder's entry screen - deliberately mirrors Home's hero (same
 * orb, heading treatment, and generate bar) since "describe what you
 * want" is the same move in both places, just without a games grid
 * below it (there's nothing to browse mid-flow). */
function BuilderHero({ onSubmit }: { onSubmit: (text: string) => void }) {
  return (
    <div className="flex w-full flex-1 flex-col items-center justify-center px-6">
      <div className="animate-pop-in">
        <HeroOrb size={88} />
      </div>
      <h1 className="animate-fade-up mt-4 text-center text-3xl font-bold tracking-tight text-white sm:text-4xl">
        Describe Your Persona
      </h1>
      <p
        className="animate-fade-up mt-2.5 max-w-md text-center text-[15px] leading-relaxed text-[var(--color-sub)]"
        style={{ animationDelay: "80ms" }}
      >
        Tell the assistant who you want the AI to play - it'll ask a few questions, then turn the
        conversation into a full persona you can review and save.
      </p>

      <div className="animate-fade-up mt-6 w-full max-w-3xl" style={{ animationDelay: "160ms" }}>
        <GameGenerateBar onSubmit={onSubmit} />
      </div>
    </div>
  );
}

export function GameBuilderPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const editState = location.state as { gameId?: string; existingGame?: ExistingGameContext } | null;
  const gameId = editState?.gameId;
  const existingGame = editState?.existingGame;
  const isEditingGame = Boolean(gameId);
  const backTarget = isEditingGame ? `/games/${gameId}/edit` : "/";

  const [messages, setMessages] = useState<BuilderMessage[]>(() => [
    {
      role: "assistant",
      content:
        isEditingGame && existingGame
          ? `Let's refine "${existingGame.title || "this persona"}". What would you like to change?`
          : "Hey! Let's build a persona together. Who do you want the AI to play?",
    },
  ]);
  const [streaming, setStreaming] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const autoSent = useRef(false);
  // Persisted server-side (see docs/ARCHITECTURE.md's "AI Studio gets its
  // own persisted session type") once the first message actually goes
  // out - null until then, since a builder chat nobody's typed into yet
  // has nothing worth a DB row.
  const [builderSessionId, setBuilderSessionId] = useState<string | null>(null);

  // Grounds the model in the persona's current fields without cluttering
  // the visible transcript - prepended only to what's sent to the backend
  // (both call sites below), transient and never persisted as a turn in
  // its own right (see api/routes/game_builder.py's `_with_context`).
  const context: string | undefined = existingGame
    ? [
        "Here is the persona as it stands today - use it as the starting point to refine, not a blank slate.",
        `Title: ${existingGame.title}`,
        `Tags: ${existingGame.tags}`,
        `Persona: ${existingGame.persona}`,
        `User role: ${existingGame.user_role}`,
        `Script: ${existingGame.script}`,
        `Research query: ${existingGame.research_query}`,
      ].join("\n")
    : undefined;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  async function handleSend(text: string) {
    setMessages((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: "" }]);
    setStreaming(true);
    setError(null);

    try {
      let sessionId = builderSessionId;
      if (!sessionId) {
        const title = isEditingGame ? `Refining ${existingGame?.title || "this persona"}` : "New persona";
        const created = await api.createBuilderSession(title, gameId);
        sessionId = created.builder_session_id;
        setBuilderSessionId(sessionId);
      }

      let full = "";
      for await (const piece of streamBuilderSessionChat(sessionId, text, context)) {
        full += piece;
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: "assistant", content: full };
          return next;
        });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong talking to the model.");
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setStreaming(false);
    }
  }

  useEffect(() => {
    const initialMessage = (location.state as { initialMessage?: string } | null)?.initialMessage;
    if (initialMessage && !autoSent.current) {
      autoSent.current = true;
      handleSend(initialMessage);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleGenerateDraft() {
    if (!builderSessionId) return; // the button's disabled until there's a session to draft from
    setDrafting(true);
    setError(null);
    try {
      const draft = await api.generateBuilderDraft(builderSessionId, context);
      navigate(isEditingGame ? `/games/${gameId}/edit` : "/games/new", { state: { draft } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to generate a draft from this conversation.");
    } finally {
      setDrafting(false);
    }
  }

  const hasStarted = isEditingGame || messages.some((m) => m.role === "user");
  const waitingForReply = streaming && messages[messages.length - 1]?.content === "";

  return (
    <div className="relative flex h-full flex-1 flex-col overflow-hidden">
      {!hasStarted && (
        <>
          {/* Same viewport-anchored corner glow as Home, for the same reason:
              fixed (not absolute) so it never shifts when the sidebar
              collapses/expands. */}
          <div className="pointer-events-none fixed left-0 top-0 -z-10 h-[950px] w-[950px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(147,51,234,0.42),rgba(147,51,234,0.14)_45%,transparent_72%)] blur-3xl" />
          <div className="pointer-events-none fixed right-0 top-0 -z-10 h-[1000px] w-[1000px] translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(236,20,140,0.46),rgba(219,39,150,0.16)_45%,transparent_72%)] blur-3xl" />
        </>
      )}

      <header className="relative z-10 flex items-center gap-3 bg-gradient-to-b from-white/[0.05] to-transparent px-5 py-3.5">
        <button
          onClick={() => navigate(backTarget)}
          aria-label="Back"
          className="flex h-8 w-8 items-center justify-center rounded-full text-[var(--color-sub)] transition-all duration-150 hover:bg-white/[0.06] hover:text-[var(--color-text)] active:scale-90"
        >
          <ArrowLeft size={16} aria-hidden="true" />
        </button>
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)]">
          <Sparkles size={13} className="text-white" aria-hidden="true" />
        </div>
        <span className="font-medium">{isEditingGame ? "Refine with AI" : "Build a persona with AI"}</span>
      </header>

      {!hasStarted ? (
        <BuilderHero onSubmit={handleSend} />
      ) : (
        <>
          <div className="flex-1 overflow-y-auto px-5 py-6">
            <div className="sr-only" aria-live="polite" aria-atomic="true" role="status">
              {messages.length > 0 && messages[messages.length - 1]?.role === "assistant" ? "New message from the assistant" : ""}
            </div>
            <div className="mx-auto flex min-h-full max-w-2xl flex-col justify-end gap-2.5">
              {messages.map((message, i) => {
                const isLast = i === messages.length - 1;
                const isLiveStreaming = isLast && streaming && message.role === "assistant";
                // Before any tokens have arrived, message.content is still
                // "" - rendering a cursor-only bubble here duplicated the
                // waiting state TypingIndicator below already shows, so
                // this stays hidden until there's real text to show.
                if (!message.content) return null;
                return (
                  <ChatBubble key={i} role={message.role} cursor={isLiveStreaming}>
                    {renderRichText(message.content)}
                  </ChatBubble>
                );
              })}
              {waitingForReply && <TypingIndicator />}
              <div ref={bottomRef} />
            </div>
          </div>

          <div className="relative z-10 bg-gradient-to-t from-[var(--color-bg)] via-[var(--color-bg)]/85 to-transparent px-5 pb-4 pt-10">
            <div className="mx-auto flex max-w-2xl flex-col gap-3">
              {error && (
                <p className="animate-fade-up text-xs text-rose-400" role="alert">
                  {error}
                </p>
              )}
              <button
                onClick={handleGenerateDraft}
                disabled={streaming || drafting || !builderSessionId}
                className="flex items-center justify-center gap-1.5 self-start rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] px-4 py-1.5 text-sm font-medium text-white transition-all duration-200 enabled:hover:scale-105 enabled:hover:shadow-[0_4px_16px_-2px_rgba(168,85,247,0.6)] disabled:cursor-not-allowed disabled:opacity-30 active:scale-95"
              >
                <Sparkles size={14} className={drafting ? "animate-pulse" : ""} />
                {drafting ? "Generating draft…" : "Generate draft"}
              </button>
              <Composer disabled={streaming || drafting} onSend={handleSend} placeholder="Describe the persona…" />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
