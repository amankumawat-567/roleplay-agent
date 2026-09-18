import type { LucideIcon } from "lucide-react";
import { PersonaMenu } from "./PersonaMenu";
import type { Game } from "../types";

interface GameTileProps {
  icon: LucideIcon;
  title: string;
  subtitle: string;
  badge: string;
  accent: string;
  /** An uploaded game-card image (see GameEditorPage). When present, it
   * replaces the placeholder icon+glow as the card's art. */
  coverUrl?: string | null;
  onClick: () => void;
  /** When given, renders the shared "manage this persona" menu (see
   * docs/ARCHITECTURE.md) in the tile's corner - omit for a tile that
   * isn't a real persona (there are none today, but keeps this prop
   * genuinely optional rather than assuming every caller has one). */
  game?: Game;
}

/** The default game tile shown on Home's "Top Games" - a near-black base
 * lit by a single accent glow with a placeholder icon standing in for
 * cover art, deterministically picked per game id (see gameTileVisuals.ts)
 * until a game has real uploaded art (`coverUrl`). A `<div>` wrapping an
 * inner click-target `<button>` (not one outer button), so the corner
 * `PersonaMenu`'s own button can sit beside it without nesting buttons. */
export function GameTile({ icon: Icon, title, subtitle, badge, accent, coverUrl, onClick, game }: GameTileProps) {
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
              className="absolute -right-3 bottom-10 transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:scale-105"
              style={{ color: `${accent}66` }}
            />
          </>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-black/10" />

        <span className="absolute left-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-[9px] font-bold uppercase tracking-wide text-[#1a1025] backdrop-blur-md">
          {badge}
        </span>

        <div className="absolute inset-x-0 bottom-0 px-4 pb-4">
          <p className="text-base font-semibold leading-snug text-white drop-shadow-sm">{title}</p>
          <p className="mt-1 line-clamp-1 text-xs text-white/60">{subtitle}</p>
        </div>
      </button>

      {game && (
        <div className="absolute right-3 top-3 z-10 opacity-0 transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100">
          <PersonaMenu
            game={game}
            triggerClassName="rounded-full bg-black/40 p-1.5 text-white/80 backdrop-blur-md transition hover:bg-black/60 hover:text-white"
          />
        </div>
      )}
    </div>
  );
}
