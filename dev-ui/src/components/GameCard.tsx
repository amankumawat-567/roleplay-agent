import { Mic, Sparkles } from "lucide-react";
import { colorsFor } from "../utils/gradient";
import { coverUrlFor } from "../utils/gameTileVisuals";
import { useAppStore } from "../stores/useAppStore";
import { hasAudioInputCapability } from "../utils/voiceMode";
import { PersonaAvatar } from "./PersonaAvatar";
import { PersonaMenu } from "./PersonaMenu";
import type { Game } from "../types";

interface GameCardProps {
  game: Game;
  onStart: () => void;
  /** Landing straight on VoiceCallPage instead of a normal chat - the mic
   * button below only renders when this is given AND the persona's model
   * actually supports voice mode (same hasAudioInputCapability check
   * ChatPage's own "Voice mode" switch uses), so a card never offers a
   * mode the persona can't do. */
  onStartVoice?: () => void;
}

export function GameCard({ game, onStart, onStartVoice }: GameCardProps) {
  const [from] = colorsFor(game.id);
  const [badgeTag, ...restTags] = game.tags;
  const coverUrl = coverUrlFor(game.id, game.cover_image);
  const models = useAppStore((s) => s.models);
  const canStartVoice = !!onStartVoice && hasAudioInputCapability(game.provider, game.model, models);

  return (
    <div className="group relative aspect-[4/5] w-full">
      <div
        className="absolute -inset-3 -z-10 rounded-[32px] opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-40"
        style={{ background: `radial-gradient(circle, ${from}, transparent 70%)` }}
      />

      <div className="relative flex h-full flex-col overflow-hidden rounded-[28px] border border-[var(--color-border)] bg-[var(--color-panel)] shadow-[0_18px_40px_-24px_rgba(0,0,0,0.8)] transition-all duration-500 ease-[var(--ease-out-expo)] group-hover:-translate-y-1.5 group-hover:border-white/20 group-hover:shadow-[0_28px_56px_-20px_rgba(0,0,0,0.7)]">
        {coverUrl ? (
          <img
            src={coverUrl}
            alt=""
            className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:scale-105"
          />
        ) : (
          <div
            className="absolute inset-0 opacity-80 transition-opacity duration-500 group-hover:opacity-100"
            style={{ background: `radial-gradient(circle at 30% 20%, ${from}77, transparent 65%)` }}
          />
        )}
        <div className="bg-grain absolute inset-0 opacity-[0.05]" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/15 to-transparent" />

        {badgeTag && (
          <span className="absolute left-3 top-3 z-10 rounded-full border border-white/15 bg-black/30 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-white/90 backdrop-blur-md">
            {badgeTag}
          </span>
        )}

        <div className="absolute right-3 top-3 z-10 flex items-center gap-1.5 opacity-0 transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100">
          {canStartVoice && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onStartVoice?.();
              }}
              title="Start in voice mode"
              className="rounded-full bg-black/40 p-1.5 text-white/80 backdrop-blur-md transition hover:bg-black/60 hover:text-white"
            >
              <Mic size={14} aria-hidden="true" />
            </button>
          )}
          <PersonaMenu
            game={game}
            triggerClassName="rounded-full bg-black/40 p-1.5 text-white/80 backdrop-blur-md transition hover:bg-black/60 hover:text-white"
          />
        </div>

        <button onClick={onStart} className="relative z-10 flex flex-1 flex-col">
          {!coverUrl && (
            <div className="flex flex-1 items-center justify-center pt-8 transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:scale-105">
              <PersonaAvatar id={game.id} size={76} />
            </div>
          )}
          {coverUrl && <div className="flex-1" />}

          <div className="px-4 pb-4 text-left">
            <p className="text-base font-semibold leading-snug text-white drop-shadow-sm">{game.title}</p>
            {restTags.length > 0 && (
              <p className="mt-1 truncate text-xs text-white/55">{restTags.slice(0, 2).join(" · ")}</p>
            )}
            <span className="mt-2.5 flex translate-y-1 items-center gap-1.5 text-xs font-medium text-white opacity-0 transition-all duration-300 group-hover:translate-y-0 group-hover:opacity-100">
              <Sparkles size={12} aria-hidden="true" /> Start chatting
            </span>
          </div>
        </button>
      </div>
    </div>
  );
}
