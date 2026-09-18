import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Clock, Mic, MessageSquare, Square, X } from "lucide-react";
import { HeroOrb } from "../components/HeroOrb";
import type { OrbPhase } from "../components/HeroOrb";
import { PersonaMenu } from "../components/PersonaMenu";
import { useFollowupCountdown } from "../hooks/useFollowupCountdown";
import { useWavRecorder } from "../hooks/useWavRecorder";
import { useAppStore } from "../stores/useAppStore";
import { api, ApiError, streamChat } from "../services/api";
import { characterNameFor } from "../utils/persona";
import { renderRichText, splitIntoLines } from "../utils/richText";
import { gradientFor } from "../utils/gradient";
import { formatCountdown } from "../utils/countdown";
import { playPcmStream } from "../utils/pcmStreamPlayer";
import type { PcmStreamPlayer } from "../utils/pcmStreamPlayer";
import type { VoiceSegment } from "../types";

type Phase = "idle" | "recording" | "thinking" | "speaking";

const IDLE_CAPTION = "Tap the mic to talk";

/** Section F4's voice-mode screen (`ref/ai voice chat.webp`) - a genuinely
 * different screen from ChatPage, no composer/typing UI at all (see
 * docs/roadmap.md F3/F4). Translated into this app's existing components
 * rather than a new design: HeroOrb as the reference's central sphere, the
 * existing PersonaMenu carried over, and renderRichText for the caption's
 * emphasis handling - no new visual/text-rendering work needed. */
export function VoiceCallPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [gameId, setGameId] = useState<string | null>(null);
  const game = useAppStore((s) => s.games.find((g) => g.id === gameId));
  const [phase, setPhase] = useState<Phase>("idle");
  const [caption, setCaption] = useState(IDLE_CAPTION);
  const [error, setError] = useState<string | null>(null);
  const { error: micError, start, stop, levelRef: micLevelRef } = useWavRecorder();
  const openingSpokenRef = useRef(false);
  // Written directly by whichever PcmStreamPlayer is currently playing
  // (see playBlob below) - one stable ref HeroOrb polls regardless of
  // which segment's player is live, rather than a new ref per segment.
  const playbackLevelRef = useRef(0);
  const activePlayerRef = useRef<PcmStreamPlayer | null>(null);

  // A schedule_followup check-back (agent/followups.py) landing while the
  // user is in voice mode - there's no message list here to just show it
  // in (unlike ChatPage), so it needs to actually be spoken. Only when
  // idle: a check-back landing mid-recording/thinking/speaking is left
  // for the next glance at text mode rather than talking over the user.
  const { remainingMs } = useFollowupCountdown(sessionId!, async () => {
    if (phase !== "idle") return;
    try {
      const res = await api.getSessionMessages(sessionId!);
      const last = res.messages[res.messages.length - 1];
      if (last && last.role === "assistant") {
        const segments: VoiceSegment[] = splitIntoLines(last.content).map((text) => ({ text, delivery: null }));
        if (segments.length > 0) await playSegments(segments);
      }
    } catch {
      // Best-effort - it's still there in text mode either way.
    }
  }, phase);

  useEffect(() => {
    if (!sessionId) return;
    api
      .getSessionMessages(sessionId)
      .then(async (res) => {
        setGameId(res.session.game_id);
        if (openingSpokenRef.current) return;

        const [first, ...rest] = res.messages;
        if (first && first.role === "assistant" && rest.length === 0) {
          // starter: "ai" session reached via ChatPage first (its own
          // autoStart already ran there before the user switched to voice
          // mode) - text mode shows this opening line but never spoke it
          // aloud. Read it now, the same way the plain-text read-aloud
          // button does (no `delivery`, since this line wasn't produced by
          // the voice-turn model).
          openingSpokenRef.current = true;
          const segments: VoiceSegment[] = splitIntoLines(first.content).map((text) => ({
            text,
            delivery: null,
          }));
          if (segments.length > 0) await playSegments(segments);
          return;
        }

        if (!first) {
          // Reached directly (GameCard's "start in voice mode", not via
          // ChatPage) - this session's very first turn hasn't happened at
          // all yet, so ChatPage's own autoStart effect never got a chance
          // to run either. Only a starter:"ai" persona has anything to say
          // unprompted; run that turn here instead of just sitting silent
          // and waiting for a mic tap that isn't coming.
          //
          // Set before the first await, not after: StrictMode's dev-mode
          // double-invoke of this effect otherwise lets both invocations'
          // .then() callbacks run past this guard (neither has set it yet)
          // and both call streamChat - verified live, two /chat calls and
          // two spoken replies for the same session.
          openingSpokenRef.current = true;
          const detail = await api.getGame(res.session.game_id).catch(() => null);
          if (detail?.starter !== "ai") return;

          setPhase("thinking");
          setCaption("…");
          try {
            let full = "";
            for await (const piece of streamChat(sessionId, undefined)) full += piece;
            const segments: VoiceSegment[] = splitIntoLines(full).map((text) => ({ text, delivery: null }));
            if (segments.length > 0) {
              await playSegments(segments);
            } else {
              setPhase("idle");
              setCaption(IDLE_CAPTION);
            }
          } catch {
            setError("Something went wrong starting the conversation.");
            setPhase("idle");
            setCaption(IDLE_CAPTION);
          }
        }
      })
      .catch(() => setError("Failed to load this session."));
  }, [sessionId]);

  useEffect(() => {
    return () => {
      // Don't let the persona keep talking after the user has left this
      // screen (navigated to text mode, ended the call, ...).
      activePlayerRef.current?.stop();
    };
  }, []);

  const characterName = game ? characterNameFor(game) : "…";

  async function playStream(response: Response): Promise<void> {
    playbackLevelRef.current = 0;
    const player = playPcmStream(response, playbackLevelRef);
    activePlayerRef.current = player;
    try {
      await player.ended;
    } finally {
      if (activePlayerRef.current === player) activePlayerRef.current = null;
      playbackLevelRef.current = 0;
    }
  }

  async function playSegments(segments: VoiceSegment[]) {
    setPhase("speaking");
    // Pipelined, not sequential: kicks off segment i+1's request (and the
    // start of its own streamed synthesis) the moment segment i's starts
    // playing, rather than only after segment i has finished playing -
    // overlaps the two so only the very first segment's synthesis start
    // time is ever on the critical path.
    const fetchSegment = (segment: VoiceSegment) =>
      api.speakStream(sessionId!, segment.text, segment.delivery).catch(() => null);
    let nextResponse = segments.length > 0 ? fetchSegment(segments[0]) : null;
    for (let i = 0; i < segments.length; i++) {
      setCaption(segments[i].text);
      const response = await nextResponse;
      nextResponse = i + 1 < segments.length ? fetchSegment(segments[i + 1]) : null;
      if (response) {
        try {
          await playStream(response);
        } catch {
          // Best-effort - one segment failing to play shouldn't stop the
          // rest of the reply from being heard.
        }
      }
    }
    setPhase("idle");
    setCaption(IDLE_CAPTION);
  }

  async function handleMicTap() {
    if (phase === "recording") {
      const clip = stop();
      if (!clip || !sessionId) {
        setPhase("idle");
        setCaption(IDLE_CAPTION);
        return;
      }
      setPhase("thinking");
      setCaption("…");
      try {
        const turn = await api.voiceTurn(sessionId, clip);
        await playSegments(turn.segments);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Something went wrong talking to the model.");
        setPhase("idle");
        setCaption(IDLE_CAPTION);
      }
      return;
    }

    if (phase !== "idle") return; // busy thinking/speaking - ignore a stray tap
    setError(null);
    const started = await start();
    if (!started) return;
    setPhase("recording");
    setCaption("Listening…");
  }

  const micLabel = phase === "recording" ? "Stop and send" : phase === "idle" ? "Talk" : "Please wait";
  const orbPhase: OrbPhase =
    phase === "recording" ? "listening" : phase === "thinking" ? "thinking" : phase === "speaking" ? "speaking" : "idle";
  const orbLevelRef = phase === "recording" ? micLevelRef : phase === "speaking" ? playbackLevelRef : undefined;

  return (
    <div className="relative flex h-full flex-1 flex-col">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-64 opacity-30 blur-3xl"
        style={{ background: characterName ? gradientFor(characterName) : undefined }}
      />

      <header className="relative z-10 flex items-center gap-3 bg-gradient-to-b from-[var(--color-bg)] via-[var(--color-bg)]/85 to-transparent px-5 pb-10 pt-3.5">
        <button
          onClick={() => navigate(`/chat/${sessionId}`)}
          aria-label="Back to text mode"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[var(--color-sub)] transition-all duration-150 hover:bg-white/[0.06] hover:text-[var(--color-text)] active:scale-90"
        >
          <MessageSquare size={16} aria-hidden="true" />
        </button>
        {characterName && (
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ background: gradientFor(characterName) }}
            aria-hidden
          />
        )}
        <span className="font-medium">{characterName || "…"}</span>
        {game && (
          <PersonaMenu
            game={game}
            onDeleted={() => navigate("/")}
            triggerClassName="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[var(--color-sub-dim)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-text)]"
          />
        )}
        {remainingMs != null && (
          <span
            className="ml-auto flex shrink-0 items-center gap-1.5 rounded-full border border-[var(--color-border-soft)] bg-white/[0.04] px-2.5 py-1 text-xs text-[var(--color-sub)]"
            aria-live="polite"
          >
            <Clock size={12} aria-hidden="true" />
            {remainingMs > 0 ? `checks back in ${formatCountdown(remainingMs)}` : "checking back…"}
          </span>
        )}
        <button
          onClick={() => navigate("/")}
          aria-label="End voice mode"
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[var(--color-sub)] transition-all duration-150 hover:bg-white/[0.06] hover:text-[var(--color-text)] active:scale-90 ${remainingMs != null ? "" : "ml-auto"}`}
        >
          <X size={16} aria-hidden="true" />
        </button>
      </header>

      <div className="flex flex-1 flex-col items-center justify-center gap-8 px-6">
        <div className="relative flex items-center justify-center">
          <HeroOrb size={200} phase={orbPhase} levelRef={orbLevelRef} />
        </div>
        <div aria-live="polite" aria-atomic="true" className="sr-only">
          {caption !== IDLE_CAPTION && caption}
        </div>
        <p className="max-w-md text-center text-lg leading-relaxed text-[var(--color-text)]">
          {renderRichText(caption)}
        </p>
        {error && <p className="text-center text-sm text-rose-400" role="alert">{error}</p>}
        {micError && <p className="text-center text-sm text-rose-400" role="alert">{micError}</p>}
      </div>

      <div className="relative z-10 flex items-center justify-center gap-8 bg-gradient-to-t from-[var(--color-bg)] via-[var(--color-bg)]/85 to-transparent px-5 pb-10 pt-10">
        <button
          onClick={() => navigate(`/chat/${sessionId}`)}
          aria-label="Back to text mode"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-sub)] transition-all duration-150 hover:bg-[var(--color-surface-hover)] active:scale-95"
        >
          <MessageSquare size={17} aria-hidden="true" />
        </button>
        <button
          onClick={handleMicTap}
          disabled={phase === "thinking" || phase === "speaking"}
          aria-label={micLabel}
          className={`flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] text-white shadow-[0_4px_20px_-4px_rgba(168,85,247,0.6)] transition-all duration-200 enabled:hover:scale-105 disabled:cursor-not-allowed disabled:opacity-50 ${
            phase === "recording" ? "animate-pulse" : ""
          }`}
        >
          {phase === "recording" ? <Square size={22} aria-hidden="true" /> : <Mic size={24} aria-hidden="true" />}
        </button>
        <button
          onClick={() => navigate("/")}
          aria-label="End voice mode"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-sub)] transition-all duration-150 hover:bg-[var(--color-surface-hover)] active:scale-95"
        >
          <X size={17} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
