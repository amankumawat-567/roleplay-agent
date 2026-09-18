import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useAppStore } from "../stores/useAppStore";
import { useStartChat } from "../hooks/useStartChat";
import { GameGenerateBar } from "../components/GameGenerateBar";
import { HeroOrb } from "../components/HeroOrb";
import { TopBar } from "../components/TopBar";
import { GameTile } from "../components/GameTile";
import { accentFor, coverUrlFor, iconFor } from "../utils/gameTileVisuals";

const TOP_COUNT = 5;

function shuffled<T>(items: T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

export function HomePage() {
  const { games } = useAppStore();
  const navigate = useNavigate();
  const startChat = useStartChat();

  // No ranking signal yet, so "Popular Personas" is just a random slice for now.
  const topGames = useMemo(() => shuffled(games).slice(0, TOP_COUNT), [games]);

  function handleGenerate(text: string) {
    navigate("/games/builder", { state: { initialMessage: text } });
  }

  return (
    <div className="relative flex h-full flex-1 flex-col items-center overflow-hidden px-6 py-6">
      {/* Anchored to the browser viewport's own top corners (fixed, not
          absolute) so the glow's center sits exactly on those vertices and
          never shifts when the sidebar collapses/expands the content
          pane's width - it's a backdrop, not part of this pane's layout. */}
      <div className="pointer-events-none fixed left-0 top-0 -z-10 h-[950px] w-[950px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(147,51,234,0.42),rgba(147,51,234,0.14)_45%,transparent_72%)] blur-3xl" />
      <div className="pointer-events-none fixed right-0 top-0 -z-10 h-[1000px] w-[1000px] translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(236,20,140,0.46),rgba(219,39,150,0.16)_45%,transparent_72%)] blur-3xl" />

      <TopBar />

      <div className="flex w-full flex-1 flex-col items-center justify-center">
        <div className="animate-pop-in">
          <HeroOrb size={88} />
        </div>
        <h1 className="sr-only">Create a New Persona</h1>
        <h2 className="animate-fade-up mt-4 text-center text-3xl font-bold tracking-tight text-white sm:text-4xl">
          Create a New Persona
        </h2>
        <p
          className="animate-fade-up mt-2.5 max-w-md text-center text-[15px] leading-relaxed text-[var(--color-sub)]"
          style={{ animationDelay: "80ms" }}
        >
          Describe a character, remix one you already have, or start from a persona below to create
          something uniquely yours.
        </p>

        <div className="animate-fade-up mt-6 w-full max-w-3xl" style={{ animationDelay: "160ms" }}>
          <GameGenerateBar onSubmit={handleGenerate} />
        </div>

        <div className="mt-8 w-full max-w-5xl">
          <p className="animate-fade-up mb-3.5 text-sm font-medium text-[var(--color-sub)]" style={{ animationDelay: "280ms" }}>
            Popular Personas
          </p>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {topGames.map((game, i) => (
              <div key={game.id} className="animate-fade-up" style={{ animationDelay: `${320 + i * 60}ms` }}>
                <GameTile
                  icon={iconFor(game.id)}
                  title={game.title}
                  subtitle={game.tags.slice(1).join(" · ") || "Persona"}
                  badge={game.tags[0] ?? "Persona"}
                  accent={accentFor(game.id)}
                  coverUrl={coverUrlFor(game.id, game.cover_image)}
                  onClick={() => startChat(game.id)}
                  onStartVoice={() => startChat(game.id, { voice: true })}
                  game={game}
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
