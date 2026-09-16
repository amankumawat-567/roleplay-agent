import { useMemo, useState } from "react";
import { Tag } from "lucide-react";
import { useAppStore } from "../stores/useAppStore";
import { PersonaGrid, PersonaGridSkeleton } from "../components/PersonaGrid";

export function TagsPage() {
  const { games, loading, error } = useAppStore();
  const [selected, setSelected] = useState<string | null>(null);

  const allTags = useMemo(() => {
    const tags = new Set<string>();
    for (const game of games) for (const tag of game.tags) tags.add(tag);
    return [...tags].sort();
  }, [games]);

  const filtered = selected ? games.filter((g) => g.tags.includes(selected)) : games;

  return (
    <div className="h-full flex-1 overflow-y-auto px-6 py-10">
      <div className="mx-auto max-w-5xl">
        <div className="animate-fade-up flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--color-accent)]/20 to-[var(--color-accent-2)]/20">
            <Tag size={17} />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">Tags</h1>
            <p className="text-sm text-[var(--color-sub)]">Browse your personas by category.</p>
          </div>
        </div>

        {!loading && allTags.length > 0 && (
          <div className="animate-fade-up mt-6 flex flex-wrap gap-2" style={{ animationDelay: "80ms" }}>
            <button
              onClick={() => setSelected(null)}
              className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-all duration-150 ${
                selected === null
                  ? "border-[var(--color-accent)]/50 bg-[var(--color-accent)]/15 text-[var(--color-text)]"
                  : "border-[var(--color-border)] bg-white/[0.03] text-[var(--color-sub)] hover:border-[var(--color-accent)]/40 hover:text-[var(--color-text)]"
              }`}
            >
              All
            </button>
            {allTags.map((tag) => (
              <button
                key={tag}
                onClick={() => setSelected(tag)}
                className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-all duration-150 ${
                  selected === tag
                    ? "border-[var(--color-accent)]/50 bg-[var(--color-accent)]/15 text-[var(--color-text)]"
                    : "border-[var(--color-border)] bg-white/[0.03] text-[var(--color-sub)] hover:border-[var(--color-accent)]/40 hover:text-[var(--color-text)]"
                }`}
              >
                {tag}
              </button>
            ))}
          </div>
        )}

        <div className="mt-8">
          {error && <p className="text-sm text-rose-400">{error}</p>}
          {loading && <PersonaGridSkeleton count={8} />}
          {!loading && !error && games.length === 0 && (
            <p className="text-sm text-[var(--color-sub-dim)]">No personas yet - none have tags to browse.</p>
          )}
          {!loading && !error && games.length > 0 && filtered.length === 0 && (
            <p className="text-sm text-[var(--color-sub-dim)]">No personas tagged "{selected}".</p>
          )}
          {!loading && !error && filtered.length > 0 && <PersonaGrid games={filtered} />}
        </div>
      </div>
    </div>
  );
}
