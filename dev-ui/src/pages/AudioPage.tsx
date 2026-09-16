import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AudioLines, Pause, Play, Search, Settings } from "lucide-react";
import { ProfileAvatar } from "../components/ProfileAvatar";
import { VoiceAvatar } from "../components/VoiceAvatar";
import { useClonedVoices } from "../hooks/useClonedVoices";
import { colorsFor } from "../utils/gradient";
import { GAME_TILE_GRID_CLASS } from "../utils/gameTileVisuals";
import { VOICES, sampleUrlFor } from "../data/voices";
import type { Voice } from "../data/voices";

const PRESET_IDS = new Set(VOICES.map((v) => v.id));

/** A cloned voice (see useClonedVoices) has no curated name/style/color the
 * way a preset does - synthesized here so it can slot into the exact same
 * `Voice`-shaped grid/detail-rail code below rather than a parallel branch
 * of markup, distinguished only by `PRESET_IDS` where the avatar/source
 * label actually differ. */
function clonedVoiceEntry(id: string): Voice {
  return { id, name: id.charAt(0).toUpperCase() + id.slice(1), style: "Custom voice", colors: colorsFor(id) };
}

function VoiceCard({ voice, playing, onPlay }: { voice: Voice; playing: boolean; onPlay: () => void }) {
  return (
    <button
      type="button"
      onClick={onPlay}
      className="group relative flex aspect-[4/4.6] w-full flex-col items-center justify-center gap-3 overflow-hidden rounded-[24px] border border-white/[0.06] bg-[#0a090f] p-4 text-center shadow-[0_18px_40px_-24px_rgba(0,0,0,0.9)] transition-all duration-500 ease-[var(--ease-out-expo)] hover:-translate-y-1.5 hover:border-white/20 hover:shadow-[0_28px_56px_-20px_rgba(0,0,0,0.8)]"
    >
      <div
        className="absolute inset-0 opacity-60 transition-opacity duration-500 group-hover:opacity-80"
        style={{ background: `radial-gradient(circle at 50% 15%, ${voice.colors[0]}55, transparent 65%)` }}
      />
      <div className="bg-grain absolute inset-0 opacity-[0.06]" />

      <VoiceAvatar id={voice.id} size={72} />
      <div className="relative">
        <p className="text-base font-semibold text-white">{voice.name}</p>
        <p className="mt-0.5 text-xs text-white/60">{voice.style}</p>
      </div>
      <span
        className={`relative flex h-9 w-9 items-center justify-center rounded-full backdrop-blur-md transition-all duration-200 group-hover:scale-110 ${
          playing ? "bg-white text-[#1a1025]" : "bg-white/10 text-white"
        }`}
      >
        {playing ? <Pause size={14} /> : <Play size={14} className="ml-0.5" />}
      </span>
    </button>
  );
}

export function AudioPage() {
  const clonedVoiceIds = useClonedVoices();
  const allVoices = [...VOICES, ...clonedVoiceIds.map(clonedVoiceEntry)];
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(VOICES[0]?.id ?? null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const filtered = allVoices.filter((v) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return v.name.toLowerCase().includes(q) || v.style.toLowerCase().includes(q);
  });

  const selected = allVoices.find((v) => v.id === selectedId) ?? null;

  function playVoice(voice: Voice) {
    setSelectedId(voice.id);
    const audio = audioRef.current;
    if (!audio) return;

    if (playingId === voice.id) {
      audio.pause();
      setPlayingId(null);
      return;
    }

    audio.src = sampleUrlFor(voice.id);
    audio.play().catch(() => setPlayingId(null));
    setPlayingId(voice.id);
  }

  return (
    <div className="flex h-full flex-1 flex-col overflow-hidden">
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio ref={audioRef} onEnded={() => setPlayingId(null)} className="hidden" />

      <div className="animate-fade-up flex items-center gap-4 px-6 pb-4 pt-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--color-accent)]/20 to-[var(--color-accent-2)]/20">
            <AudioLines size={17} />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">Audio</h1>
            <p className="text-sm text-[var(--color-sub)]">
              Voice presets a persona can speak with in chat - preview each one below, then assign one from a
              persona's editor.
            </p>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-3">
          <span className="hidden items-center gap-1.5 rounded-full border border-white/[0.06] bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-[var(--color-sub)] backdrop-blur-md sm:flex">
            <AudioLines size={13} />
            {allVoices.length} Voices
          </span>
          <Link
            to="/profile#settings"
            title="Settings"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/[0.06] bg-white/[0.04] text-[var(--color-sub)] backdrop-blur-md transition-colors hover:text-[var(--color-text)]"
          >
            <Settings size={15} />
          </Link>
          <ProfileAvatar size={36} />
        </div>
      </div>

      <div className="flex flex-1 gap-6 overflow-hidden px-6 pb-6">
        <div className="glass-panel flex-1 overflow-y-auto rounded-[28px] p-5">
          <div className="relative mb-5 max-w-md">
            <Search
              size={15}
              className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[var(--color-sub-dim)]"
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search voices"
              autoComplete="off"
              className="w-full rounded-full border border-white/[0.07] bg-white/[0.04] py-2.5 pl-10 pr-4 text-sm outline-none transition-all duration-150 placeholder:text-[var(--color-sub-dim)] focus:border-[var(--color-accent)]/40"
            />
          </div>

          {filtered.length === 0 && (
            <p className="text-sm text-[var(--color-sub-dim)]">No voices match "{query.trim()}".</p>
          )}

          {filtered.length > 0 && (
            <div className={GAME_TILE_GRID_CLASS}>
              {filtered.map((voice, i) => (
                <div
                  key={voice.id}
                  className={`animate-fade-up rounded-[24px] transition-shadow duration-200 ${
                    selectedId === voice.id
                      ? "ring-2 ring-[var(--color-accent)] ring-offset-2 ring-offset-[var(--color-bg)]"
                      : ""
                  }`}
                  style={{ animationDelay: `${i * 60}ms` }}
                >
                  <VoiceCard voice={voice} playing={playingId === voice.id} onPlay={() => playVoice(voice)} />
                </div>
              ))}
            </div>
          )}
        </div>

        {selected && (
          <aside
            className="animate-fade-up glass-panel hidden w-[300px] shrink-0 flex-col overflow-y-auto rounded-[28px] p-5 @5xl:flex"
            style={{ animationDelay: "120ms" }}
          >
            <div
              className="flex flex-col items-center gap-4 rounded-2xl p-6"
              style={{ background: `radial-gradient(circle at 50% 15%, ${selected.colors[0]}33, transparent 70%)` }}
            >
              <VoiceAvatar id={selected.id} size={96} />
              <div className="text-center">
                <h2 className="text-lg font-bold tracking-tight">{selected.name}</h2>
                <span className="mt-2 inline-flex w-fit rounded-full border border-[var(--color-border)] bg-white/[0.03] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-sub)]">
                  {selected.style}
                </span>
              </div>
              <button
                onClick={() => playVoice(selected)}
                className="flex items-center gap-1.5 rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:scale-105 hover:shadow-[0_4px_16px_-2px_rgba(168,85,247,0.6)] active:scale-95"
              >
                {playingId === selected.id ? <Pause size={14} /> : <Play size={14} />}
                {playingId === selected.id ? "Playing…" : "Play sample"}
              </button>
            </div>

            <p className="mt-5 text-xs font-semibold uppercase tracking-wide text-[var(--color-sub-dim)]">Details</p>
            <div className="mt-1.5 flex flex-col gap-2 text-xs">
              <div className="flex items-center justify-between border-t border-[var(--color-border-soft)] pt-2">
                <span className="text-[var(--color-sub-dim)]">Voice ID</span>
                <span className="font-mono text-[var(--color-sub)]">{selected.id}</span>
              </div>
              <div className="flex items-center justify-between border-t border-[var(--color-border-soft)] pt-2">
                <span className="text-[var(--color-sub-dim)]">Source</span>
                <span className="text-[var(--color-sub)]">
                  {PRESET_IDS.has(selected.id) ? "Qwen3-TTS CustomVoice" : "Qwen3-TTS Base (cloned)"}
                </span>
              </div>
            </div>

            <p className="mt-5 rounded-xl border border-dashed border-[var(--color-border)] bg-white/[0.02] p-3 text-xs leading-relaxed text-[var(--color-sub-dim)]">
              {PRESET_IDS.has(selected.id)
                ? "Assign this voice to a persona from its editor's \"Voice\" field, then use the read-aloud button on any of its replies in chat to hear it synthesized live."
                : "Cloned from a reference clip in data/voice_samples/ (see scripts/extract_audio_sample.py) - assign it the same way as a preset, from a persona's editor \"Voice\" field."}
            </p>
          </aside>
        )}
      </div>
    </div>
  );
}
