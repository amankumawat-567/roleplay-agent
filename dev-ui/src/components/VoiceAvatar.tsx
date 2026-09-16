import { useState } from "react";
import { gradientFor } from "../utils/gradient";

/** A real illustrated avatar per voice, generated via Draftbit's Personas
 * (https://github.com/draftbit/avatar-generator, MIT licensed;
 * personas.draftbit.com/api/avatar.svg for a specific trait combination)
 * and vendored once as a static file under public/voice-avatars/ rather
 * than called live: this app otherwise never depends on an external
 * service at runtime (Ollama, Playwright/Bing search, everything else is
 * local), and Personas' own hosted generator is a one-time asset source,
 * not something that needs to run per-request. Each voice's
 * hair/eyes/mouth/skin/color combo was hand-picked to loosely match its
 * style tag and gender presentation, the same "specific identity, not a
 * random hash" reasoning skillVisuals.ts uses for its own hand-picked
 * icons.
 *
 * Works for any voice id, not just the curated presets: a cloned voice
 * (see useClonedVoices) gets one the same way, on request, as new ones are
 * vendored in - `onError` falls back to the same hash-gradient-plus-initial
 * placeholder personas without cover art already use, so an id with no
 * vendored SVG yet never renders a broken image. */
export function VoiceAvatar({ id, size = 64 }: { id: string; size?: number }) {
  const [broken, setBroken] = useState(false);

  if (broken) {
    return (
      <div
        className="flex shrink-0 items-center justify-center rounded-full text-white ring-2 ring-white/10"
        style={{ width: size, height: size, background: gradientFor(id), fontSize: size * 0.4 }}
      >
        {id.charAt(0).toUpperCase()}
      </div>
    );
  }

  return (
    <img
      src={`/voice-avatars/${id}.svg`}
      alt=""
      width={size}
      height={size}
      onError={() => setBroken(true)}
      className="shrink-0 rounded-full ring-2 ring-white/10"
      style={{ width: size, height: size }}
    />
  );
}
