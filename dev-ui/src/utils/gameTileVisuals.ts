import type { LucideIcon } from "lucide-react";
import { Compass, Drama, Ghost, Heart, Rocket, Skull, Sparkles, Star, Swords, Wand2 } from "lucide-react";
import { colorsFor, hash } from "./gradient";

const ICON_POOL: LucideIcon[] = [Sparkles, Compass, Wand2, Swords, Ghost, Heart, Rocket, Drama, Skull, Star];

/** A deterministic "random" icon per game id - a placeholder face until
 * games get real cover art or generated logos. */
export function iconFor(id: string): LucideIcon {
  return ICON_POOL[hash(`icon:${id}`) % ICON_POOL.length];
}

/** The accent glow color a game's default tile lights up with. */
export function accentFor(id: string): string {
  const [from] = colorsFor(id);
  return from;
}

/** The URL for a game's uploaded cover image (see POST
 * /api/games/{id}/cover), or null if it doesn't have one yet. */
export function coverUrlFor(id: string, coverImage: string | null): string | null {
  return coverImage ? `/media/games/${id}/${coverImage}` : null;
}

/** A grid of GameTiles that reflows by the column's real width rather than
 * viewport breakpoints alone - shared by Explore's "All Games" and Skills'
 * card grid so both gain/lose columns the same way (e.g. when the sidebar
 * collapses) without cards stretching past a sensible size. */
export const GAME_TILE_GRID_CLASS = "grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(160px,210px))]";
