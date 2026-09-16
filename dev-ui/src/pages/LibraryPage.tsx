import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Library, Search } from "lucide-react";
import { api } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import { LibraryCard } from "../components/LibraryCard";
import { TopBar } from "../components/TopBar";
import type { LibraryEntry, SearchResult } from "../types";

export function LibraryPage() {
  const { sessions } = useAppStore();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";

  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);

  const [library, setLibrary] = useState<LibraryEntry[] | null>(null);
  const [libraryError, setLibraryError] = useState<string | null>(null);

  useEffect(() => {
    if (!query.trim()) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    api
      .search(query.trim())
      .then(setSearchResults)
      .catch(() => setSearchResults([]))
      .finally(() => setSearching(false));
  }, [query]);

  useEffect(() => {
    api
      .listLibrary()
      .then(setLibrary)
      .catch((err) => setLibraryError(err instanceof Error ? err.message : "Failed to load your library"));
  }, []);

  // The most recent session per game, so a card opens straight into
  // wherever that conversation left off instead of starting a new one.
  const latestSessionByGame = useMemo(() => {
    const map = new Map<string, string>();
    for (const session of sessions) {
      if (!map.has(session.game_id)) map.set(session.game_id, session.id); // sessions are newest-first
    }
    return map;
  }, [sessions]);

  function openGame(gameId: string) {
    const sessionId = latestSessionByGame.get(gameId);
    if (sessionId) navigate(`/chat/${sessionId}`);
  }

  return (
    <div className="relative h-full flex-1 overflow-y-auto px-6 py-10">
      <TopBar />
      <div className="mx-auto max-w-5xl">
        <div className="animate-fade-up flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--color-accent)]/20 to-[var(--color-accent-2)]/20">
            <Library size={17} />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">Library</h1>
            <p className="text-sm text-[var(--color-sub)]">Every game you've played, and how much time you've put in.</p>
          </div>
        </div>

        {query.trim() ? (
          <div className="animate-fade-up mt-8" style={{ animationDelay: "80ms" }}>
            <p className="mb-4 flex items-center gap-2 text-sm text-[var(--color-sub-dim)]">
              <Search size={14} />
              Results for "{query.trim()}"
            </p>
            {searching && <p className="text-sm text-[var(--color-sub-dim)]">Searching…</p>}
            {!searching && searchResults?.length === 0 && (
              <p className="text-sm text-[var(--color-sub-dim)]">No messages match "{query.trim()}".</p>
            )}
            <div className="flex flex-col gap-2">
              {searchResults?.map((r) => (
                <button
                  key={r.session_id}
                  onClick={() => navigate(`/chat/${r.session_id}`)}
                  className="glass-panel flex flex-col items-start rounded-2xl p-4 text-left transition-all duration-150 hover:border-white/20"
                >
                  <span className="font-medium">{r.title}</span>
                  <span className="mt-1 truncate text-sm text-[var(--color-sub-dim)]">{r.snippet}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mt-8">
            {libraryError && <p className="text-sm text-rose-400">{libraryError}</p>}

            {!libraryError && library === null && (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
                {[0, 1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="animate-fade-up aspect-[4/4.6] overflow-hidden rounded-[24px] border border-white/[0.06]"
                    style={{ animationDelay: `${i * 60}ms` }}
                  >
                    <div className="animate-shimmer h-full w-full" />
                  </div>
                ))}
              </div>
            )}

            {library?.length === 0 && (
              <p className="animate-fade-up text-sm text-[var(--color-sub-dim)]">
                No games played yet - start a chat with a persona from Home or Explore.
              </p>
            )}

            {library && library.length > 0 && (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
                {library.map((entry, i) => (
                  <div key={entry.id} className="animate-fade-up" style={{ animationDelay: `${i * 60}ms` }}>
                    <LibraryCard
                      entry={entry}
                      onClick={() => openGame(entry.id)}
                      onDeleted={() => setLibrary((prev) => prev?.filter((e) => e.id !== entry.id) ?? null)}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
