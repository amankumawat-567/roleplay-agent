import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Clock, Phone } from "lucide-react";
import { useChatSession } from "../hooks/useChatSession";
import { useFollowupCountdown } from "../hooks/useFollowupCountdown";
import { AssistantTurn, ChatBubble, TypingIndicator, UserTimestamp } from "../components/ChatBubble";
import { Composer } from "../components/Composer";
import { PersonaMenu } from "../components/PersonaMenu";
import { useAppStore } from "../stores/useAppStore";
import { characterNameFor } from "../utils/persona";
import { renderRichText, splitIntoLines } from "../utils/richText";
import { gradientFor } from "../utils/gradient";
import { formatCountdown } from "../utils/countdown";

/** Backend messages carry no timestamp, so this records "first seen by this
 * tab" per message index - accurate for anything sent/streamed this session,
 * and a single shared "just loaded" time for history fetched on mount
 * (matching ref/chat.webp, where every bubble shows the same time too). */
function useMessageTimestamps(messageCount: number): (number | null)[] {
  const [sentAt, setSentAt] = useState<number[]>([]);
  useEffect(() => {
    setSentAt((prev) => {
      if (messageCount <= prev.length) return prev.slice(0, messageCount);
      return [...prev, ...Array(messageCount - prev.length).fill(Date.now())];
    });
  }, [messageCount]);
  return sentAt;
}

export function ChatPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { title, gameId, messages, loading, streaming, error, sendMessage, refresh } = useChatSession(sessionId!);
  // `streaming` as the refresh signal: it flips false->true->false around
  // every turn, so the countdown re-checks the schedule right as each
  // reply lands - including the very first time this persona ever
  // schedules a check-back, which a mount-only poll would otherwise miss.
  const { remainingMs } = useFollowupCountdown(sessionId!, refresh, streaming);
  const game = useAppStore((s) => s.games.find((g) => g.id === gameId));
  // Voice mode is offered for every persona (non-audio models fall back to
  // local Whisper transcription server-side - see docs/ARCHITECTURE.md's
  // "Voice mode") - this only waits for `game` to avoid flashing the
  // switch in before the persona itself has loaded.
  const voiceModeAvailable = !!game;
  // "Who you're talking to" - the persona's own identity, not the
  // session's title (a sidebar/history label since A0's auto-titling
  // shipped - see docs/ARCHITECTURE.md's "Character name, distinct from
  // the scenario title"). Falls back to the session title only for the
  // brief window before `game` has loaded, so the header isn't blank.
  const characterName = game ? characterNameFor(game) : title;
  const sentAt = useMessageTimestamps(messages.length);
  const autoStarted = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const autoStart = (location.state as { autoStart?: boolean } | null)?.autoStart;
    if (autoStart && !autoStarted.current && !loading) {
      autoStarted.current = true;
      sendMessage();
    }
  }, [loading, location.state, sendMessage]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const waitingForReply = streaming && messages.length > 0 && messages[messages.length - 1]?.content === "";

  return (
    <div className="relative flex h-full flex-1 flex-col">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-64 opacity-30 blur-3xl"
        style={{ background: characterName ? gradientFor(characterName) : undefined }}
      />

      <header className="relative z-10 flex items-center gap-3 bg-gradient-to-b from-[var(--color-bg)] via-[var(--color-bg)]/85 to-transparent px-5 pb-10 pt-3.5">
        <button
          onClick={() => navigate("/")}
          aria-label="Back to home"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[var(--color-sub)] transition-all duration-150 hover:bg-white/[0.06] hover:text-[var(--color-text)] active:scale-90"
        >
          <ArrowLeft size={16} />
        </button>
        {characterName && (
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ background: gradientFor(characterName) }}
            aria-hidden
          />
        )}
        <h1 className="font-medium sr-only">{characterName || "Chat"}</h1>
        <span className="font-medium">{characterName || "…"}</span>
        {game && (
          <PersonaMenu
            game={game}
            onDeleted={() => navigate("/")}
            triggerClassName="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[var(--color-sub-dim)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-text)]"
          />
        )}
        {voiceModeAvailable && (
          <button
            onClick={() => navigate(`/chat/${sessionId}/voice`)}
            aria-label="Switch to voice mode"
            className="ml-auto flex shrink-0 items-center gap-1.5 rounded-full border border-[var(--color-border-soft)] bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-[var(--color-sub)] transition-colors hover:bg-white/[0.08] hover:text-[var(--color-text)]"
          >
            <Phone size={12} />
            Voice mode
          </button>
        )}
        {remainingMs != null && (
          <span
            className={`flex shrink-0 items-center gap-1.5 rounded-full border border-[var(--color-border-soft)] bg-white/[0.04] px-2.5 py-1 text-xs text-[var(--color-sub)] ${voiceModeAvailable ? "" : "ml-auto"}`}
            aria-live="polite"
          >
            <Clock size={12} aria-hidden="true" />
            {remainingMs > 0 ? `checks back in ${formatCountdown(remainingMs)}` : "checking back…"}
          </span>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-6">
        {loading ? (
          <div className="mx-auto flex h-full max-w-2xl flex-col justify-end gap-2.5" aria-busy="true">
            <div className="animate-shimmer h-14 w-2/3 self-start rounded-2xl rounded-bl-md" />
            <div className="animate-shimmer h-10 w-1/2 self-end rounded-2xl rounded-br-md" style={{ animationDelay: "0.15s" }} />
          </div>
        ) : (
          <>
            <div 
              className="sr-only" 
              aria-live="polite" 
              aria-atomic="true"
              role="status"
            >
              {messages.length > 0 && messages[messages.length - 1]?.role === "assistant" 
                ? `New message from ${characterName}` 
                : ""}
            </div>
            <div className="mx-auto flex min-h-full max-w-2xl flex-col justify-end gap-2.5">
              {messages.map((message, i) => {
                const isLast = i === messages.length - 1;
                const isLiveStreaming = isLast && streaming && message.role === "assistant";

                if (isLiveStreaming) {
                  if (!message.content) return null;
                  return <AssistantTurn key={i} lines={[message.content]} live />;
                }

                if (message.role === "assistant") {
                  const lines = splitIntoLines(message.content);
                  return (
                    <AssistantTurn
                      key={i}
                      lines={lines.map((line) => renderRichText(line))}
                      copyText={message.content}
                      sentAt={sentAt[i] ?? undefined}
                      sessionId={sessionId}
                      checkedBack={message.kind === "followup"}
                    />
                  );
                }

                return (
                  <div key={i} className="flex flex-col items-end gap-1">
                    <ChatBubble role="user">{renderRichText(message.content)}</ChatBubble>
                    <UserTimestamp sentAt={sentAt[i] ?? undefined} />
                  </div>
                );
              })}
              {waitingForReply && <TypingIndicator title={characterName} />}
              <div ref={bottomRef} />
            </div>
          </>
        )}
      </div>

      <div className="relative z-10 bg-gradient-to-t from-[var(--color-bg)] via-[var(--color-bg)]/85 to-transparent px-5 pb-4 pt-10">
        <div className="mx-auto max-w-2xl">
          {error && <p className="animate-fade-up mb-2 text-xs text-rose-400" role="alert">{error}</p>}
          <Composer disabled={streaming || loading} onSend={sendMessage} hideDictation={voiceModeAvailable} />
        </div>
      </div>
    </div>
  );
}
