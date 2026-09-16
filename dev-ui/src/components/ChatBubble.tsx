import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Check, Clock, Copy, Loader2, ThumbsUp, Volume2, VolumeX } from "lucide-react";
import { api } from "../services/api";
import { playPcmStream } from "../utils/pcmStreamPlayer";
import type { PcmStreamPlayer } from "../utils/pcmStreamPlayer";
import { OrbAvatar } from "./OrbAvatar";

interface ChatBubbleProps {
  role: "user" | "assistant";
  children: ReactNode;
  cursor?: boolean;
  // A scheduled check-back landing (agent/followups.py) rather than a
  // direct reply - tinted so it visually reads as its own event dropping
  // into the conversation, not just another line in the same turn.
  checkedBack?: boolean;
}

export function ChatBubble({ role, children, cursor, checkedBack }: ChatBubbleProps) {
  const isUser = role === "user";
  return (
    <div
      className={`animate-rise-in whitespace-pre-wrap rounded-2xl px-4 py-3 text-[15px] leading-relaxed ${
        isUser
          ? "max-w-[75%] self-end rounded-br-md bg-gradient-to-br from-[var(--color-user-bubble)] to-[#5b21b6] text-white shadow-[0_4px_20px_-6px_rgba(124,58,237,0.5)]"
          : checkedBack
            ? "max-w-full self-start rounded-bl-md border border-amber-400/30 bg-amber-400/[0.06] text-[var(--color-text)] shadow-[0_4px_16px_-8px_rgba(0,0,0,0.4)]"
            : "max-w-full self-start rounded-bl-md border border-[var(--color-border-soft)] bg-[var(--color-panel)] text-[var(--color-text)] shadow-[0_4px_16px_-8px_rgba(0,0,0,0.4)]"
      }`}
    >
      {children}
      {cursor && <span className="animate-blink ml-0.5 inline-block w-1.5 translate-y-0.5 bg-current">▍</span>}
    </div>
  );
}

function formatTime(ms: number): string {
  return new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

type SpeakState = "idle" | "loading" | "playing";

/** The copy / like / read-aloud row under a finished assistant turn. Copy
 * is genuinely functional; like is a local, unpersisted affordance only -
 * there's no rating store behind it. Read-aloud tries this persona's real
 * voice first (POST /api/sessions/{id}/speak-stream, section C) and falls
 * back to the browser's own generic speech synthesis on any failure - no
 * voice configured (422), synthesis erroring (503), or being offline - so
 * the button always does *something* rather than silently failing. */
function MessageActions({ text, sessionId }: { text: string; sessionId: string }) {
  const [copied, setCopied] = useState(false);
  const [liked, setLiked] = useState(false);
  const [speakState, setSpeakState] = useState<SpeakState>("idle");
  const playerRef = useRef<PcmStreamPlayer | null>(null);

  useEffect(() => {
    return () => {
      playerRef.current?.stop();
      window.speechSynthesis?.cancel();
    };
  }, []);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be denied by the browser - silently no-op.
    }
  }

  function speakWithBrowser() {
    if (!("speechSynthesis" in window)) {
      setSpeakState("idle");
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = () => setSpeakState("idle");
    utterance.onerror = () => setSpeakState("idle");
    window.speechSynthesis.speak(utterance);
    setSpeakState("playing");
  }

  async function handleSpeak() {
    if (speakState !== "idle") {
      playerRef.current?.stop();
      window.speechSynthesis?.cancel();
      setSpeakState("idle");
      return;
    }

    setSpeakState("loading");
    try {
      const response = await api.speakStream(sessionId, text);
      const player = playPcmStream(response);
      playerRef.current = player;
      setSpeakState("playing");
      // Unlike the old <audio>.play() call this replaced, playPcmStream's
      // `ended` always eventually settles on its own (stream finishes or
      // errors out internally) rather than sometimes never resolving -
      // no timeout race needed to guard against a stuck "playing" state.
      player.ended.then(() => {
        if (playerRef.current === player) {
          playerRef.current = null;
          setSpeakState((s) => (s === "playing" ? "idle" : s));
        }
      });
    } catch {
      speakWithBrowser();
    }
  }

  return (
    <div className="flex items-center gap-2.5 text-[var(--color-sub-dim)]">
      <button onClick={handleCopy} title="Copy" className="transition-colors hover:text-[var(--color-text)]">
        {copied ? <Check size={13} /> : <Copy size={13} />}
      </button>
      <button
        onClick={() => setLiked((v) => !v)}
        title="Like"
        className={`transition-colors hover:text-[var(--color-text)] ${liked ? "text-[var(--color-accent-2)]" : ""}`}
      >
        <ThumbsUp size={13} fill={liked ? "currentColor" : "none"} />
      </button>
      <button
        onClick={handleSpeak}
        title={speakState === "loading" ? "Synthesizing…" : "Read aloud"}
        disabled={speakState === "loading"}
        className="transition-colors hover:text-[var(--color-text)] disabled:cursor-wait"
      >
        {speakState === "loading" ? (
          <Loader2 size={13} className="animate-spin" />
        ) : speakState === "playing" ? (
          <VolumeX size={13} />
        ) : (
          <Volume2 size={13} />
        )}
      </button>
    </div>
  );
}

/** An assistant turn as a whole: orb avatar beside a stacked column of
 * line-bubbles, with a timestamp + action row under the last bubble. */
export function AssistantTurn({
  lines,
  copyText,
  sentAt,
  live,
  sessionId,
  checkedBack,
}: {
  lines: ReactNode[];
  copyText?: string;
  sentAt?: number;
  live?: boolean;
  sessionId?: string;
  // This turn was delivered by a scheduled check-back (see
  // agent/followups.py), not sent as a direct reply - shows a small label
  // and tints the bubble so it reads as the persona coming back on their
  // own, distinct from a normal reply in the same box.
  checkedBack?: boolean;
}) {
  return (
    <div className="animate-rise-in flex items-end gap-2.5 self-start">
      <OrbAvatar size={40} />
      <div className="flex max-w-[75%] flex-col items-start gap-1">
        {checkedBack && (
          <span className="flex items-center gap-1 px-1 text-[11px] font-medium text-amber-400/90">
            <Clock size={11} />
            checking back in
          </span>
        )}
        {lines.map((line, i) => (
          <ChatBubble key={i} role="assistant" cursor={live && i === lines.length - 1} checkedBack={checkedBack}>
            {line}
          </ChatBubble>
        ))}
        {!live && (
          <div className="flex items-center gap-3 px-1">
            {sentAt != null && <span className="text-[11px] text-[var(--color-sub-dim)]">{formatTime(sentAt)}</span>}
            {copyText && sessionId && <MessageActions text={copyText} sessionId={sessionId} />}
          </div>
        )}
      </div>
    </div>
  );
}

export function UserTimestamp({ sentAt }: { sentAt?: number }) {
  if (sentAt == null) return null;
  return <span className="self-end px-1 text-[11px] text-[var(--color-sub-dim)]">{formatTime(sentAt)}</span>;
}

export function TypingIndicator({ title }: { title: string }) {
  return (
    <div className="animate-rise-in flex items-center gap-2.5 self-start">
      <OrbAvatar size={40} />
      <div className="flex items-center gap-2 rounded-2xl rounded-bl-md border border-[var(--color-border-soft)] bg-[var(--color-panel)] px-4 py-3 text-sm font-semibold text-[var(--color-text)] shadow-[0_4px_14px_-6px_rgba(0,0,0,0.4)]">
        <Loader2 size={14} className="animate-spin text-[var(--color-sub-dim)]" />
        {title ? `${title} is typing…` : "Typing…"}
      </div>
    </div>
  );
}
