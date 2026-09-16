import { useEffect, useState } from "react";
import { Archive as ArchiveIcon, RotateCcw, Trash2 } from "lucide-react";
import { api, ApiError } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import { TopBar } from "../components/TopBar";
import { accentFor, coverUrlFor, iconFor } from "../utils/gameTileVisuals";
import { formatLastPlayed } from "../utils/playStats";
import type { SessionSummary } from "../types";

/** Section A4 - sessions tucked away via the sidebar's "Archive chat"
 * action (Sidebar.tsx's ChatRow), not folded into Library as a filter -
 * a separate destination directly below it in the nav. Reuses Library's
 * grid/card visual treatment, but scoped per-session rather than
 * per-persona, since you archive one conversation at a time. */
export function ArchivesPage() {
  const games = useAppStore((s) => s.games);
  const loadAll = useAppStore((s) => s.loadAll);

  const [archived, setArchived] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    api
      .listArchivedSessions()
      .then(setArchived)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load archives"));
  }, []);

  async function handleRestore(session: SessionSummary) {
    setBusyId(session.id);
    try {
      await api.unarchiveSession(session.id);
      setArchived((prev) => prev?.filter((s) => s.id !== session.id) ?? null);
      // Pulls the restored session back into the sidebar/Library, which
      // otherwise wouldn't know about it until the next full reload.
      await loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to restore this chat");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(session: SessionSummary) {
    if (!window.confirm(`Delete "${session.title}"? This can't be undone.`)) return;
    setBusyId(session.id);
    try {
      await api.deleteSession(session.id);
      setArchived((prev) => prev?.filter((s) => s.id !== session.id) ?? null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete this chat");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="relative h-full flex-1 overflow-y-auto px-6 py-10">
      <TopBar />
      <div className="mx-auto max-w-5xl">
        <div className="animate-fade-up flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--color-accent)]/20 to-[var(--color-accent-2)]/20">
            <ArchiveIcon size={17} />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">Archives</h1>
            <p className="text-sm text-[var(--color-sub)]">Chats you've tucked away - restore one, or delete it for good.</p>
          </div>
        </div>

        <div className="mt-8">
          {error && <p className="text-sm text-rose-400">{error}</p>}

          {!error && archived === null && (
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

          {archived?.length === 0 && (
            <p className="animate-fade-up text-sm text-[var(--color-sub-dim)]">
              Nothing archived yet - archive a chat from its sidebar row to tuck it away here.
            </p>
          )}

          {archived && archived.length > 0 && (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              {archived.map((session, i) => {
                const game = games.find((g) => g.id === session.game_id);
                const Icon = iconFor(session.game_id);
                const accent = accentFor(session.game_id);
                const coverUrl = coverUrlFor(session.game_id, game?.cover_image ?? null);
                const busy = busyId === session.id;
                return (
                  <div key={session.id} className="animate-fade-up" style={{ animationDelay: `${i * 60}ms` }}>
                    <div className="group relative aspect-[4/4.6] w-full overflow-hidden rounded-[24px] border border-white/[0.06] bg-[#0a090f] shadow-[0_18px_40px_-24px_rgba(0,0,0,0.9)]">
                      {coverUrl ? (
                        <img src={coverUrl} alt="" className="absolute inset-0 h-full w-full object-cover" />
                      ) : (
                        <>
                          <div
                            className="absolute inset-0 opacity-70"
                            style={{ background: `radial-gradient(circle at 78% 8%, ${accent}, transparent 60%)` }}
                          />
                          <div className="bg-grain absolute inset-0 opacity-[0.08]" />
                          <Icon size={122} strokeWidth={1} className="absolute -right-3 bottom-16" style={{ color: `${accent}66` }} />
                        </>
                      )}
                      <div className="absolute inset-0 bg-gradient-to-t from-black via-black/55 to-black/10" />

                      <div className="absolute inset-x-0 bottom-0 flex flex-col gap-2.5 px-4 pb-4">
                        <div>
                          <p className="truncate text-base font-semibold leading-snug text-white drop-shadow-sm">
                            {session.title}
                          </p>
                          <div className="mt-1 flex items-center gap-1.5 truncate text-[11px] text-white/65">
                            {game && <span className="truncate">{game.title}</span>}
                            {session.archived_at != null && <span>· Archived {formatLastPlayed(session.archived_at)}</span>}
                          </div>
                        </div>
                        <div className="flex gap-1.5">
                          <button
                            onClick={() => handleRestore(session)}
                            disabled={busy}
                            className="flex flex-1 items-center justify-center gap-1.5 rounded-full bg-white/90 px-2.5 py-1.5 text-xs font-semibold text-[#1a1025] transition hover:bg-white disabled:opacity-50"
                          >
                            <RotateCcw size={12} /> Restore
                          </button>
                          <button
                            onClick={() => handleDelete(session)}
                            disabled={busy}
                            title="Delete permanently"
                            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-black/40 text-white/80 backdrop-blur-md transition hover:bg-rose-500/70 hover:text-white disabled:opacity-50"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
