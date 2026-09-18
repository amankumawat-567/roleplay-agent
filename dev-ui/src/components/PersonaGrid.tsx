import { GameCard } from "./GameCard";
import { useStartChat } from "../hooks/useStartChat";
import type { Game } from "../types";

/** The persona card grid shared by Home, Explore, and Tags - same cards,
 * same "start chatting" behavior, just a different subset of `games`. */
export function PersonaGrid({ games }: { games: Game[] }) {
  const startChat = useStartChat();

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
      {games.map((game, i) => (
        <div key={game.id} className="animate-fade-up min-w-0" style={{ animationDelay: `${i * 60}ms` }}>
          <GameCard game={game} onStart={() => startChat(game.id)} onStartVoice={() => startChat(game.id, { voice: true })} />
        </div>
      ))}
    </div>
  );
}

export function PersonaGridSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="animate-fade-up aspect-[4/5] min-w-0 overflow-hidden rounded-[28px] border border-[var(--color-border-soft)]"
          style={{ animationDelay: `${i * 60}ms` }}
        >
          <div className="animate-shimmer h-full w-full" />
        </div>
      ))}
    </div>
  );
}
