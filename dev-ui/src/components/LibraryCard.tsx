import { Clock, Mic, Repeat2, Timer } from "lucide-react";
import { iconFor, accentFor, coverUrlFor } from "../utils/gameTileVisuals";
import { formatLastPlayed, formatPlayedTime } from "../utils/playStats";
import { PersonaMenu } from "./PersonaMenu";
import type { LibraryEntry } from "../types";

interface LibraryCardProps {
  entry: LibraryEntry;
  onClick: () => void;
  /** Landing straight on VoiceCallPage instead of a normal chat - the mic
   * button below renders whenever this is given (see GameCard's identical
   * prop for the full rationale). */
  onStartVoice?: () => void;
  /** Called after this persona is deleted via the corner menu - LibraryPage
   * fetches its own `library` list independent of the app-wide store, so
   * it needs its own way to drop the now-gone entry. */
  onDeleted?: () => void;
}

/** A played-game card for the Library grid - same dark-base-plus-glow
 * treatment as GameTile, but with a stat row (last played, time played,
 * rounds) in place of a plain subtitle, since this represents everything
 * you've done with a persona, not just its description. A `<div>` wrapping
 * an inner click-target `<button>` (not one outer button), so the corner
 * `PersonaMenu`'s own button can sit beside it without nesting buttons. */
export function LibraryCard({ entry, onClick, onStartVoice, onDeleted }: LibraryCardProps) {
  const canStartVoice = !!onStartVoice;
  const Icon = iconFor(entry.id);
  const accent = accentFor(entry.id);
  const coverUrl = coverUrlFor(entry.id, entry.cover_image);
  const badge = entry.tags[0] ?? "Persona";

  return (
    <div className="group relative aspect-[4/4.6] w-full shrink-0 overflow-hidden rounded-[24px] border border-white/[0.06] bg-[#0a090f] shadow-[0_18px_40px_-24px_rgba(0,0,0,0.9)] transition-all duration-500 ease-[var(--ease-out-expo)] hover:-translate-y-1.5 hover:border-white/20 hover:shadow-[0_28px_56px_-20px_rgba(0,0,0,0.8)]">
      <button type="button" onClick={onClick} className="absolute inset-0 text-left">
        {coverUrl ? (
          <img
            src={coverUrl}
            alt=""
            className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:scale-105"
          />
        ) : (
          <>
            <div
              className="absolute inset-0 opacity-70 transition-opacity duration-500 group-hover:opacity-90"
              style={{ background: `radial-gradient(circle at 78% 8%, ${accent}, transparent 60%)` }}
            />
            <div className="bg-grain absolute inset-0 opacity-[0.08]" />
            <Icon
              size={122}
              strokeWidth={1}
              className="absolute -right-3 bottom-16 transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:scale-105"
              style={{ color: `${accent}66` }}
            />
          </>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/50 to-black/10" />

        <span className="absolute left-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-[9px] font-bold uppercase tracking-wide text-[#1a1025] backdrop-blur-md">
          {badge}
        </span>

        <div className="absolute inset-x-0 bottom-0 px-4 pb-4">
          <p className="text-base font-semibold leading-snug text-white drop-shadow-sm">{entry.title}</p>
          <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-white/65">
            <span className="flex items-center gap-1" title="Last played">
              <Clock size={11} />
              {formatLastPlayed(entry.last_played)}
            </span>
            <span className="flex items-center gap-1" title="Time played">
              <Timer size={11} />
              {formatPlayedTime(entry.played_seconds)}
            </span>
            <span className="flex items-center gap-1" title="Rounds played">
              <Repeat2 size={11} />
              {entry.rounds} {entry.rounds === 1 ? "round" : "rounds"}
            </span>
          </div>
        </div>
      </button>

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
          game={entry}
          onDeleted={onDeleted}
          triggerClassName="rounded-full bg-black/40 p-1.5 text-white/80 backdrop-blur-md transition hover:bg-black/60 hover:text-white"
        />
      </div>
    </div>
  );
}
