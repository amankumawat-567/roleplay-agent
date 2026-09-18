import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import { FloatingParticles } from "./FloatingParticles";

export type OrbPhase = "idle" | "listening" | "thinking" | "speaking";

// Ring/core color sets per phase - built once, not per-render, since none
// of it depends on props. "idle" is copied verbatim from this component's
// original single-phase gradients, so every caller that doesn't pass
// `phase` (HomePage, StudioPage, GameBuilderPage) renders pixel-identical
// to before this got voice-mode reactivity added.
const RING_GRADIENT: Record<OrbPhase, string> = {
  idle: "conic-gradient(from 0deg, transparent 0deg, rgba(236,72,153,0.4) 55deg, transparent 130deg, rgba(56,189,248,0.35) 210deg, transparent 290deg)",
  listening:
    "conic-gradient(from 0deg, transparent 0deg, rgba(56,189,248,0.5) 55deg, transparent 130deg, rgba(45,212,191,0.4) 210deg, transparent 290deg)",
  thinking:
    "conic-gradient(from 0deg, transparent 0deg, rgba(148,163,184,0.4) 55deg, transparent 130deg, rgba(129,140,248,0.35) 210deg, transparent 290deg)",
  speaking:
    "conic-gradient(from 0deg, transparent 0deg, rgba(236,72,153,0.55) 55deg, transparent 130deg, rgba(251,146,60,0.4) 210deg, transparent 290deg)",
};

const GLOW_GRADIENT: Record<OrbPhase, string> = {
  idle: "radial-gradient(circle at 35% 35%, rgba(217,70,160,0.4), rgba(147,51,234,0.28) 45%, transparent 70%)",
  listening: "radial-gradient(circle at 35% 35%, rgba(56,189,248,0.42), rgba(45,212,191,0.28) 45%, transparent 70%)",
  thinking: "radial-gradient(circle at 35% 35%, rgba(129,140,248,0.32), rgba(148,163,184,0.2) 45%, transparent 70%)",
  speaking: "radial-gradient(circle at 35% 35%, rgba(236,72,153,0.45), rgba(251,146,60,0.3) 45%, transparent 70%)",
};

const CORE_GRADIENT: Record<OrbPhase, string> = {
  idle: "conic-gradient(from 210deg at 50% 50%, rgba(45,212,191,0.55), rgba(168,85,247,0.5) 30%, rgba(236,72,153,0.5) 55%, rgba(251,146,60,0.45) 78%, rgba(45,212,191,0.55) 100%)",
  listening:
    "conic-gradient(from 210deg at 50% 50%, rgba(56,189,248,0.55), rgba(45,212,191,0.5) 30%, rgba(59,130,246,0.5) 55%, rgba(56,189,248,0.45) 78%, rgba(56,189,248,0.55) 100%)",
  thinking:
    "conic-gradient(from 210deg at 50% 50%, rgba(148,163,184,0.5), rgba(129,140,248,0.45) 30%, rgba(99,102,241,0.45) 55%, rgba(148,163,184,0.4) 78%, rgba(148,163,184,0.5) 100%)",
  speaking:
    "conic-gradient(from 210deg at 50% 50%, rgba(236,72,153,0.6), rgba(251,146,60,0.5) 30%, rgba(168,85,247,0.5) 55%, rgba(236,72,153,0.5) 78%, rgba(236,72,153,0.6) 100%)",
};

export function HeroOrb({
  size = 140,
  phase = "idle",
  levelRef,
}: {
  size?: number;
  /** Voice-mode call state (see VoiceCallPage) - "idle" (the default) is
   * this component's original one-and-only look. Every other caller
   * (HomePage/StudioPage/GameBuilderPage) omits this and gets that exact
   * look, untouched. */
  phase?: OrbPhase;
  /** Live 0..1 amplitude (useWavRecorder's mic levelRef while listening,
   * useAudioLevel's playback levelRef while speaking) - read every
   * animation frame, not via React state/props, so the orb's pulse can
   * track real audio without re-rendering this component 60x/sec. Ignored
   * outside "listening"/"speaking". */
  levelRef?: RefObject<number>;
}) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const coreRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const reactive = !reducedMotion && (phase === "listening" || phase === "speaking");
    if (!reactive) {
      // Not audio-reactive right now - settle back to rest so a phase
      // change mid-pulse (e.g. the user stops talking) doesn't leave the
      // orb frozen scaled-up.
      if (wrapperRef.current) wrapperRef.current.style.transform = "scale(1)";
      if (coreRef.current) coreRef.current.style.filter = "";
      return;
    }
    let raf: number;
    const tick = () => {
      const level = levelRef?.current ?? 0;
      // A live amplitude nudge layered on top of the orb's own
      // always-running breathing animation (animate-orb below), not a
      // replacement for it - silence still looks alive, loud audio
      // visibly swells further.
      if (wrapperRef.current) wrapperRef.current.style.transform = `scale(${1 + level * 0.16})`;
      if (coreRef.current) coreRef.current.style.filter = `brightness(${1 + level * 0.35})`;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [phase, levelRef]);

  const ringMask = (innerPct: number, outerPct: number) => ({
    WebkitMaskImage: `radial-gradient(circle, transparent ${innerPct}%, black ${innerPct + 1}%, black ${outerPct}%, transparent ${outerPct + 1}%)`,
    maskImage: `radial-gradient(circle, transparent ${innerPct}%, black ${innerPct + 1}%, black ${outerPct}%, transparent ${outerPct + 1}%)`,
  });

  return (
    <div
      ref={wrapperRef}
      className="relative flex items-center justify-center transition-transform duration-150 ease-out"
      style={{ width: size, height: size }}
    >
      <div
        className="animate-glow-drift absolute left-1/2 top-1/2 rounded-full blur-2xl"
        style={{
          width: size * 1.5,
          height: size * 1.5,
          background: GLOW_GRADIENT[phase],
        }}
      />

      {/* A single faint rotating highlight ring, masked down to a thin
          band. Thinking spins it the opposite direction and much faster -
          reads as "working on it" rather than idle's slow ambient drift. */}
      <div
        className={`absolute rounded-full ${phase === "thinking" ? "animate-spin-fast-reverse" : "animate-spin-slow"}`}
        style={{
          width: size * 1.3,
          height: size * 1.3,
          background: RING_GRADIENT[phase],
          ...ringMask(66, 70),
        }}
      />

      {/* Sparkle particles read as ambient/idle chatter - dropped while
          thinking so the orb feels focused rather than distractingly busy. */}
      {phase !== "thinking" && <FloatingParticles />}

      <div
        ref={coreRef}
        className="animate-orb relative overflow-hidden rounded-full"
        style={{
          width: size,
          height: size,
          background: [
            "radial-gradient(circle at 30% 22%, rgba(255,255,255,0.95), rgba(255,255,255,0) 16%)",
            CORE_GRADIENT[phase],
            "radial-gradient(circle at 38% 32%, #241f33, #14101f 55%, #050308 100%)",
          ].join(", "),
          boxShadow: "0 0 50px rgba(147,51,234,0.35), inset 0 0 22px rgba(0,0,0,0.5), inset 0 -8px 16px rgba(0,0,0,0.4)",
        }}
      />
    </div>
  );
}
