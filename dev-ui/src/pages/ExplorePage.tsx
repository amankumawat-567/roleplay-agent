import { useEffect, useMemo, useState } from "react";
import type { UIEvent } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronLeft, ChevronRight, Gamepad2, Play, Search, Settings } from "lucide-react";
import { useAppStore } from "../stores/useAppStore";
import { useStartChat } from "../hooks/useStartChat";
import { GameTile } from "../components/GameTile";
import { ProfileAvatar } from "../components/ProfileAvatar";
import { GAME_TILE_GRID_CLASS, accentFor, iconFor } from "../utils/gameTileVisuals";
import type { Game } from "../types";

const FEATURED_COUNT = 5;
const EXAMPLE_TAG_COUNT = 4;
const DISMISS_SCROLL_THRESHOLD = 24;

function shuffled<T>(items: T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function TagPill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`shrink-0 rounded-full border px-4 py-2 text-sm font-medium capitalize transition-all duration-150 ${
        active
          ? "border-transparent bg-gradient-to-r from-[var(--color-accent)] to-[var(--color-accent-2)] text-white"
          : "border-[var(--color-border)] bg-white/[0.03] text-[var(--color-sub)] hover:border-white/20 hover:text-[var(--color-text)]"
      }`}
    >
      {label}
    </button>
  );
}

/** Every slot keeps one constant width/height - only `transform` (and the
 * cheap `filter`) ever change, so rotating the stack scales and slides
 * cards as rigid units instead of resizing their boxes. Resizing a box with
 * text/icons inside makes its content visibly reflow mid-transition (the
 * "breaking" look); a pure transform never touches layout, so it's smooth
 * on every frame - the same trick behind most CSS carousel patterns (e.g.
 * the transform-driven examples on animista.net). */
const STAGE_HEIGHT = "h-[300px] sm:h-[400px]";
const CARD_SIZE = "w-56 sm:w-72";

function FeaturedCarousel({
  games,
  onStart,
  onStartVoice,
}: {
  games: Game[];
  onStart: (id: string) => void;
  onStartVoice: (id: string) => void;
}) {
  const center = Math.floor(games.length / 2);

  return (
    <div className={`relative mx-auto w-full ${STAGE_HEIGHT}`} style={{ maxWidth: 980 }}>
      {games.map((game, i) => {
        const offset = i - center;
        const distance = Math.abs(offset);
        const isCenter = distance === 0;
        const scale = isCenter ? 1 : distance === 1 ? 0.84 : 0.7;
        const translateX = offset * 150;
        const translateY = isCenter ? -10 : 14 + distance * 18;

        return (
          <div
            key={game.id}
            className={`group absolute left-1/2 top-4 origin-top shrink-0 transition-[transform,filter] duration-500 ease-[var(--ease-out-expo)] will-change-transform ${CARD_SIZE} ${
              isCenter ? "" : "brightness-[0.82] group-hover:brightness-100"
            }`}
            style={{
              zIndex: 50 - distance,
              transform: `translateX(-50%) translate(${translateX}px, ${translateY}px) scale(${scale})`,
            }}
          >
            <GameTile
              icon={iconFor(game.id)}
              title={game.title}
              subtitle={game.tags.slice(1).join(" · ") || "Persona"}
              badge={game.tags[0] ?? "Persona"}
              accent={accentFor(game.id)}
              onClick={() => onStart(game.id)}
              onStartVoice={() => onStartVoice(game.id)}
              game={game}
            />
            {isCenter && (
              <button
                onClick={() => onStart(game.id)}
                title="Start chatting"
                className="absolute bottom-5 right-5 z-20 flex h-14 w-14 items-center justify-center rounded-full bg-white text-[#1a1025] shadow-[0_8px_24px_-6px_rgba(0,0,0,0.6)] transition-transform duration-200 hover:scale-110 active:scale-95"
              >
                <Play size={20} fill="currentColor" className="ml-0.5" />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function ExplorePage() {
  const { games, loading, error } = useAppStore();
  const startChat = useStartChat();
  const [query, setQuery] = useState("");
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [showMoreTags, setShowMoreTags] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [stackDismissed, setStackDismissed] = useState(false);
  const [stackRemoved, setStackRemoved] = useState(false);
  const [rotation, setRotation] = useState(0);

  // Once the collapse transition has visibly finished, drop the section
  // from the DOM entirely instead of leaving an invisible 0-height husk.
  useEffect(() => {
    if (!stackDismissed) return;
    const timer = setTimeout(() => setStackRemoved(true), 520);
    return () => clearTimeout(timer);
  }, [stackDismissed]);

  const featured = useMemo(() => shuffled(games).slice(0, FEATURED_COUNT), [games]);

  // Rotating the array (not the visual slots) is what makes "<"/">" slide
  // every card smoothly into its neighbor's spot - same key, new position.
  const rotatedFeatured = useMemo(() => {
    const n = featured.length;
    if (n === 0) return featured;
    return Array.from({ length: n }, (_, i) => featured[(i + rotation) % n]);
  }, [featured, rotation]);

  // Reset the loop whenever the underlying featured set changes so the
  // rotation index can't drift out of range.
  useEffect(() => {
    setRotation(0);
  }, [featured]);

  const allTags = useMemo(() => {
    const tags = new Set<string>();
    for (const game of games) for (const tag of game.tags) tags.add(tag);
    return [...tags].sort();
  }, [games]);

  const exampleTags = allTags.slice(0, EXAMPLE_TAG_COUNT);
  const otherTags = allTags.slice(EXAMPLE_TAG_COUNT);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return games.filter((g) => {
      const matchesTag = !selectedTag || g.tags.includes(selectedTag);
      const matchesQuery = !q || g.title.toLowerCase().includes(q) || g.tags.some((t) => t.toLowerCase().includes(q));
      return matchesTag && matchesQuery;
    });
  }, [games, query, selectedTag]);

  function rotateFeatured(dir: 1 | -1) {
    setRotation((r) => (r + dir + featured.length) % featured.length);
  }

  function handleScroll(e: UIEvent<HTMLDivElement>) {
    const top = e.currentTarget.scrollTop;
    setScrolled(top > 16);
    // One-way switch: once the stack has been scrolled past, it stays
    // collapsed into the plain grid for the rest of the session - it only
    // comes back on a full page refresh.
    if (top > DISMISS_SCROLL_THRESHOLD) setStackDismissed(true);
  }

  return (
    <div onScroll={handleScroll} className="h-full flex-1 overflow-y-auto px-6 py-6">
      <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-8">
        {/* Search + profile row - sticky, and the search field widens once
            the page is scrolled to keep it reachable without the rest of
            the header hogging space. */}
        <div className="animate-fade-up sticky top-0 z-20 -mx-6 flex items-center gap-4 bg-[var(--color-bg)]/85 px-6 py-3 backdrop-blur-xl">
          <div className={`relative transition-all duration-300 ${scrolled ? "max-w-2xl flex-1" : "max-w-md flex-1"}`}>
            <label htmlFor="explore-search" className="sr-only">Search for a persona</label>
            <Search size={15} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[var(--color-sub-dim)]" />
            <input
              id="explore-search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search for a persona"
              autoComplete="off"
              className="w-full rounded-full border border-white/[0.07] bg-white/[0.04] py-2.5 pl-10 pr-4 text-sm outline-none backdrop-blur-md transition-all duration-150 placeholder:text-[var(--color-sub-dim)] focus:border-[var(--color-accent)]/40"
            />
          </div>

          <div className="ml-auto flex items-center gap-3">
            <span className="hidden items-center gap-1.5 rounded-full border border-white/[0.06] bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-[var(--color-sub)] backdrop-blur-md sm:flex">
              <Gamepad2 size={13} aria-hidden="true" />
              {games.length} Personas
            </span>
            <Link
              to="/profile#settings"
              aria-label="Settings"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/[0.06] bg-white/[0.04] text-[var(--color-sub)] backdrop-blur-md transition-colors hover:text-[var(--color-text)]"
            >
              <Settings size={15} aria-hidden="true" />
            </Link>
            <ProfileAvatar size={36} />
          </div>
        </div>

        <h1 className="sr-only">Explore Personas</h1>

        {error && <p className="animate-fade-up text-sm text-rose-400" role="alert">{error}</p>}

        {!loading && !error && games.length === 0 && (
          <p className="animate-fade-up text-sm text-[var(--color-sub-dim)]">
            No personas yet - generate one from Home, or head to the Studio.
          </p>
        )}

        {loading && (
          <div className="flex gap-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="aspect-[4/4.6] w-48 shrink-0 overflow-hidden rounded-[24px] border border-[var(--color-border-soft)]"
              >
                <div className="animate-shimmer h-full w-full" />
              </div>
            ))}
          </div>
        )}

        {!loading && !error && games.length > 0 && (
          <>
            {/* Featured - the overlapping, raised carousel from the
                reference. Collapses away permanently the first time the
                page is scrolled: it fades and slides up on its own
                transform/opacity (no layout properties involved, so it
                stays smooth), while the max-height shrink closes the gap
                it leaves behind for the categories/grid below. */}
            {!stackRemoved && (
              <div
                className={`overflow-hidden transition-[max-height,opacity,transform] duration-500 ease-[var(--ease-out-expo)] ${
                  stackDismissed ? "max-h-0 -translate-y-6 opacity-0" : "max-h-[480px] translate-y-0 opacity-100"
                }`}
              >
                <div className="animate-fade-up" style={{ animationDelay: "80ms" }}>
                  <FeaturedCarousel
                    games={rotatedFeatured}
                    onStart={startChat}
                    onStartVoice={(id) => startChat(id, { voice: true })}
                  />
                </div>

                {featured.length > 1 && (
                  <div className="mt-3 flex items-center justify-center gap-3">
                    <button
                      onClick={() => rotateFeatured(-1)}
                      title="Previous"
                      aria-label="Show previous featured persona"
                      className="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--color-border)] bg-white/[0.04] text-[var(--color-sub)] transition-all duration-150 hover:border-white/20 hover:text-[var(--color-text)] active:scale-90"
                    >
                      <ChevronLeft size={15} />
                    </button>
                    <button
                      onClick={() => rotateFeatured(1)}
                      title="Next"
                      aria-label="Show next featured persona"
                      className="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--color-border)] bg-white/[0.04] text-[var(--color-sub)] transition-all duration-150 hover:border-white/20 hover:text-[var(--color-text)] active:scale-90"
                    >
                      <ChevronRight size={15} />
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Select Categories - "All" plus a few examples, everything
                else tucked behind a "more" toggle instead of a long row. */}
            <div className="animate-fade-up" style={{ animationDelay: "160ms" }}>
              <h2 className="mb-3.5 text-lg font-bold tracking-tight">Select Categories</h2>
              <div className="flex flex-wrap items-center gap-2">
                <TagPill label="All" active={selectedTag === null} onClick={() => setSelectedTag(null)} />
                {exampleTags.map((tag) => (
                  <TagPill key={tag} label={tag} active={selectedTag === tag} onClick={() => setSelectedTag(tag)} />
                ))}
                {otherTags.length > 0 && (
                  <button
                    onClick={() => setShowMoreTags((v) => !v)}
                    className="flex shrink-0 items-center gap-1 rounded-full border border-dashed border-[var(--color-border)] bg-white/[0.02] px-3.5 py-2 text-sm font-medium text-[var(--color-sub)] transition-all duration-150 hover:border-white/20 hover:text-[var(--color-text)]"
                  >
                    {showMoreTags ? "Less" : `+${otherTags.length} more`}
                    <ChevronDown size={14} className={`transition-transform duration-200 ${showMoreTags ? "rotate-180" : ""}`} />
                  </button>
                )}
                {showMoreTags &&
                  otherTags.map((tag) => (
                    <TagPill key={tag} label={tag} active={selectedTag === tag} onClick={() => setSelectedTag(tag)} />
                  ))}
              </div>
            </div>

            {/* All Personas - every persona as a grid that reflows by the
                content column's real width, so it gains/loses columns when
                the sidebar opens or closes instead of only at viewport
                breakpoints. */}
            <div className="animate-fade-up" style={{ animationDelay: "240ms" }}>
              <h2 className="mb-3.5 text-lg font-bold tracking-tight">All Personas</h2>
              {filtered.length === 0 ? (
                <p className="text-sm text-[var(--color-sub-dim)]">
                  No personas match{selectedTag ? ` "${selectedTag}"` : ""}
                  {query.trim() ? ` "${query.trim()}"` : ""}.
                </p>
              ) : (
                <div className={GAME_TILE_GRID_CLASS}>
                  {filtered.map((game) => (
                    <GameTile
                      key={game.id}
                      icon={iconFor(game.id)}
                      title={game.title}
                      subtitle={game.tags.slice(1).join(" · ") || "Persona"}
                      badge={game.tags[0] ?? "Persona"}
                      accent={accentFor(game.id)}
                      onClick={() => startChat(game.id)}
                      onStartVoice={() => startChat(game.id, { voice: true })}
                      game={game}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
