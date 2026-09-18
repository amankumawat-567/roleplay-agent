import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Puzzle, Search, Settings, X } from "lucide-react";
import { api } from "../services/api";
import { GameTile } from "../components/GameTile";
import { ProfileAvatar } from "../components/ProfileAvatar";
import { GAME_TILE_GRID_CLASS } from "../utils/gameTileVisuals";
import { accentForSkill, iconForSkill } from "../utils/skillVisuals";
import type { SkillSummary } from "../types";

function titleCase(id: string): string {
  return id
    .split("_")
    .map((w) => w[0]?.toUpperCase() + w.slice(1))
    .join(" ");
}

export function SkillsPage() {
  const [skills, setSkills] = useState<SkillSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);

  useEffect(() => {
    api
      .listSkills()
      .then((list) => {
        setSkills(list);
        setSelectedId((current) => current ?? list[0]?.id ?? null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load skills"));
  }, []);

  const filtered = useMemo(() => {
    if (!skills) return [];
    const q = query.trim().toLowerCase();
    if (!q) return skills;
    return skills.filter((s) => titleCase(s.id).toLowerCase().includes(q) || s.description.toLowerCase().includes(q));
  }, [skills, query]);

  const selected = skills?.find((s) => s.id === selectedId) ?? null;

  function handleSelectSkill(skillId: string) {
    setSelectedId(skillId);
    // On mobile, open the bottom sheet
    if (window.innerWidth < 1280) { // 5xl breakpoint
      setMobileDetailOpen(true);
    }
  }

  const mobileDetailContent = selected && mobileDetailOpen ? (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
        onClick={() => setMobileDetailOpen(false)}
        aria-hidden="true"
      />
      <aside
        className="animate-fade-up fixed bottom-0 left-0 right-0 z-50 w-full max-h-[80vh] bg-[var(--color-bg-soft)] rounded-t-[28px] shadow-[0_-30px_60px_-20px_rgba(0,0,0,0.8)] lg:hidden flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-label={`${titleCase(selected.id)} details`}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
          <h2 className="text-lg font-bold tracking-tight">{titleCase(selected.id)}</h2>
          <button
            onClick={() => setMobileDetailOpen(false)}
            className="flex h-10 w-10 items-center justify-center rounded-full text-[var(--color-sub)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-text)]"
            aria-label="Close details"
          >
            <X size={20} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          <div
            className="relative flex aspect-[4/3] shrink-0 items-center justify-center overflow-hidden rounded-2xl mb-4"
            style={{ background: `radial-gradient(circle at 30% 20%, ${accentForSkill(selected.id)}55, transparent 70%)` }}
          >
            <div className="bg-grain absolute inset-0 opacity-[0.05]" />
            {(() => {
              const Icon = iconForSkill(selected.id);
              return <Icon size={64} strokeWidth={1.1} style={{ color: accentForSkill(selected.id) }} />;
            })()}
          </div>

          <span className="inline-flex w-fit rounded-full border border-[var(--color-border)] bg-white/[0.03] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-sub)] mb-4">
            Tool
          </span>

          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-sub-dim)]">Description</p>
          <p className="mt-1.5 line-clamp-5 text-sm leading-relaxed text-[var(--color-sub)]">{selected.description}</p>

          <p className="mt-5 text-xs font-semibold uppercase tracking-wide text-[var(--color-sub-dim)]">Details</p>
          <div className="mt-1.5 flex flex-col gap-2 text-xs">
            <div className="flex items-center justify-between border-t border-[var(--color-border-soft)] pt-2">
              <span className="text-[var(--color-sub-dim)]">Skill ID</span>
              <span className="font-mono text-[var(--color-sub)]">{selected.id}</span>
            </div>
            <div className="flex items-center justify-between border-t border-[var(--color-border-soft)] pt-2">
              <span className="text-[var(--color-sub-dim)]">Type</span>
              <span className="text-[var(--color-sub)]">Built-in tool</span>
            </div>
          </div>

          <p className="mt-5 rounded-xl border border-dashed border-[var(--color-border)] bg-white/[0.02] p-3 text-xs leading-relaxed text-[var(--color-sub-dim)]">
            Enable this for a persona from its Skills section in the editor - it isn't turned on anywhere by
            default.
          </p>
        </div>
      </aside>
    </>
  ) : null;

  return (
    // The detail rail on the right needs to hold its ground on screen while
    // the grid scrolls past it, so this page - unlike every other page here
    // - doesn't scroll as one column. The header stays outside both scroll
    // regions, and the grid and the rail each get their own independent
    // `overflow-y-auto`, the rail's just never actually needing to scroll.
    <div className="flex h-full flex-1 flex-col overflow-hidden">
      <div className="animate-fade-up flex items-center gap-4 px-6 pb-4 pt-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--color-accent)]/20 to-[var(--color-accent-2)]/20">
            <Puzzle size={17} />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">Skills</h1>
            <p className="text-sm text-[var(--color-sub)]">
              Tools a persona can call on mid-conversation - turn them on per-persona in the editor.
            </p>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-3">
          <span className="hidden items-center gap-1.5 rounded-full border border-white/[0.06] bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-[var(--color-sub)] backdrop-blur-md sm:flex">
            <Puzzle size={13} />
            {skills?.length ?? 0} Tools
          </span>
          <Link
            to="/profile#settings"
            aria-label="Settings"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/[0.06] bg-white/[0.04] text-[var(--color-sub)] backdrop-blur-md transition-colors hover:text-[var(--color-text)]"
          >
            <Settings size={15} />
          </Link>
          <ProfileAvatar size={36} />
        </div>
      </div>

      <div className="flex flex-1 gap-6 overflow-hidden px-6 pb-6">
        <div className="glass-panel flex-1 overflow-y-auto rounded-[28px] p-5">
          <div className="relative mb-5 max-w-md">
            <label htmlFor="skills-search" className="sr-only">Search skills</label>
            <Search size={15} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[var(--color-sub-dim)]" />
            <input
              id="skills-search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search skills"
              autoComplete="off"
              className="w-full rounded-full border border-white/[0.07] bg-white/[0.04] py-2.5 pl-10 pr-4 text-sm outline-none transition-all duration-150 placeholder:text-[var(--color-sub-dim)] focus:border-[var(--color-accent)]/40"
            />
          </div>

          {error && <p className="text-sm text-rose-400" role="alert">{error}</p>}

          {skills === null && !error && (
            <div className={GAME_TILE_GRID_CLASS}>
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="aspect-[4/4.6] overflow-hidden rounded-[24px] border border-[var(--color-border-soft)]"
                >
                  <div className="animate-shimmer h-full w-full" />
                </div>
              ))}
            </div>
          )}

          {skills !== null && filtered.length === 0 && (
            <p className="text-sm text-[var(--color-sub-dim)]">
              {skills.length === 0 ? "No skills registered yet." : `No skills match "${query.trim()}".`}
            </p>
          )}

          {filtered.length > 0 && (
            <div className={GAME_TILE_GRID_CLASS}>
              {filtered.map((skill, i) => (
                <div
                  key={skill.id}
                  className={`animate-fade-up rounded-[24px] transition-shadow duration-200 ${
                    selectedId === skill.id ? "ring-2 ring-[var(--color-accent)] ring-offset-2 ring-offset-[var(--color-bg)]" : ""
                  }`}
                  style={{ animationDelay: `${i * 60}ms` }}
                >
                  <GameTile
                    icon={iconForSkill(skill.id)}
                    title={titleCase(skill.id)}
                    subtitle={skill.description}
                    badge="Tool"
                    accent={accentForSkill(skill.id)}
                    onClick={() => handleSelectSkill(skill.id)}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Desktop detail rail */}
        {selected && (
          <aside
            className="animate-fade-up glass-panel hidden w-[300px] shrink-0 flex-col overflow-y-auto rounded-[28px] p-5 @5xl:flex"
            style={{ animationDelay: "120ms" }}
          >
            <div
              className="relative flex aspect-[4/3] shrink-0 items-center justify-center overflow-hidden rounded-2xl"
              style={{ background: `radial-gradient(circle at 30% 20%, ${accentForSkill(selected.id)}55, transparent 70%)` }}
            >
              <div className="bg-grain absolute inset-0 opacity-[0.05]" />
              {(() => {
                const Icon = iconForSkill(selected.id);
                return <Icon size={64} strokeWidth={1.1} style={{ color: accentForSkill(selected.id) }} />;
              })()}
            </div>

            <h2 className="mt-4 text-lg font-bold tracking-tight">{titleCase(selected.id)}</h2>
            <span className="mt-2 inline-flex w-fit rounded-full border border-[var(--color-border)] bg-white/[0.03] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-sub)]">
              Tool
            </span>

            <p className="mt-5 text-xs font-semibold uppercase tracking-wide text-[var(--color-sub-dim)]">Description</p>
            <p className="mt-1.5 line-clamp-5 text-sm leading-relaxed text-[var(--color-sub)]">{selected.description}</p>

            <p className="mt-5 text-xs font-semibold uppercase tracking-wide text-[var(--color-sub-dim)]">Details</p>
            <div className="mt-1.5 flex flex-col gap-2 text-xs">
              <div className="flex items-center justify-between border-t border-[var(--color-border-soft)] pt-2">
                <span className="text-[var(--color-sub-dim)]">Skill ID</span>
                <span className="font-mono text-[var(--color-sub)]">{selected.id}</span>
              </div>
              <div className="flex items-center justify-between border-t border-[var(--color-border-soft)] pt-2">
                <span className="text-[var(--color-sub-dim)]">Type</span>
                <span className="text-[var(--color-sub)]">Built-in tool</span>
              </div>
            </div>

            <p className="mt-5 rounded-xl border border-dashed border-[var(--color-border)] bg-white/[0.02] p-3 text-xs leading-relaxed text-[var(--color-sub-dim)]">
              Enable this for a persona from its Skills section in the editor - it isn't turned on anywhere by
              default.
            </p>
          </aside>
        )}

        {/* Mobile detail bottom sheet */}
        {mobileDetailContent}
      </div>
    </div>
  );
}
