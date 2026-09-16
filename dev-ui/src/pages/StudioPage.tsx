import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, FileText, Plus, Sparkles, Wand2 } from "lucide-react";
import { HeroOrb } from "../components/HeroOrb";

function StudioCard({
  icon,
  tag,
  title,
  description,
  onClick,
  delay,
}: {
  icon: ReactNode;
  tag: string;
  title: string;
  description: string;
  onClick: () => void;
  delay: number;
}) {
  return (
    <button
      onClick={onClick}
      style={{ animationDelay: `${delay}ms` }}
      className="animate-fade-up group relative flex flex-1 flex-col gap-4 overflow-hidden rounded-[28px] border border-[var(--color-border)] bg-[var(--color-panel)] p-6 text-left transition-all duration-300 ease-[var(--ease-out-expo)] hover:-translate-y-1.5 hover:border-[var(--color-accent)]/50 hover:shadow-[0_28px_56px_-20px_rgba(168,85,247,0.35)]"
    >
      <div
        className="absolute inset-0 opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-30"
        style={{ background: "radial-gradient(circle at 30% 20%, var(--color-accent), transparent 65%)" }}
      />
      <div className="relative flex items-start justify-between">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--color-accent)]/20 to-[var(--color-accent-2)]/20 text-[var(--color-text)] transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:scale-110">
          {icon}
        </div>
        <span className="rounded-full border border-[var(--color-border)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-sub-dim)]">
          {tag}
        </span>
      </div>
      <div className="relative">
        <p className="text-lg font-semibold">{title}</p>
        <p className="mt-1.5 text-sm leading-relaxed text-[var(--color-sub)]">{description}</p>
      </div>
      <span className="relative flex items-center gap-1.5 text-xs font-medium text-[var(--color-accent)] opacity-0 transition-opacity duration-300 group-hover:opacity-100">
        Get started <ArrowRight size={12} />
      </span>
    </button>
  );
}

export function StudioPage() {
  const navigate = useNavigate();

  return (
    <div className="h-full flex-1 overflow-y-auto px-6 py-10">
      <div className="mx-auto max-w-4xl">
        <div className="animate-fade-up flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--color-accent)]/20 to-[var(--color-accent-2)]/20">
            <Wand2 size={17} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight">Studio</h1>
              <span className="rounded-full border border-[var(--color-accent)]/40 bg-[var(--color-accent)]/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-accent)]">
                AI Builder
              </span>
            </div>
            <p className="text-sm text-[var(--color-sub)]">Three ways to make a new persona.</p>
          </div>
        </div>

        <div
          className="animate-fade-up mt-8 grid gap-2.5 overflow-hidden rounded-[28px] border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5 sm:grid-cols-2"
          style={{ animationDelay: "60ms" }}
        >
          <div className="relative flex flex-col items-center justify-center gap-5 overflow-hidden rounded-[22px] bg-white/[0.02] py-12">
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(168,85,247,0.18),transparent_70%)]" />
            <HeroOrb size={104} />
            <span className="relative rounded-full border border-[var(--color-border)] bg-black/30 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-sub)] backdrop-blur-md">
              AI Persona Engine
            </span>
          </div>

          <div className="flex flex-col justify-center gap-4 p-6">
            <span className="flex w-fit items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-white/[0.03] px-3 py-1 text-xs font-medium text-[var(--color-sub)]">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              Local + hosted models
            </span>
            <h2 className="text-2xl font-bold leading-tight sm:text-[28px]">
              Design any character.
              <br /> Bring them to life.
            </h2>
            <p className="text-sm leading-relaxed text-[var(--color-sub)]">
              Fill in every field yourself, or describe who you want and let AI draft a full
              persona - tone, backstory, and the scene it opens in - for you to review and tweak.
            </p>
            <div className="mt-1 flex items-center justify-between gap-3 border-t border-[var(--color-border-soft)] pt-4">
              <span className="text-xs text-[var(--color-sub-dim)]">3 ways to start · Manual, AI-guided, or from a video</span>
              <button
                onClick={() => navigate("/games/builder")}
                className="flex shrink-0 items-center gap-1.5 rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:scale-105 hover:shadow-[0_4px_16px_-2px_rgba(168,85,247,0.6)] active:scale-95"
              >
                Ready to start? <ArrowRight size={14} />
              </button>
            </div>
          </div>
        </div>

        <div className="mt-10">
          <div className="animate-fade-up mb-4 flex items-center gap-2.5" style={{ animationDelay: "120ms" }}>
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] text-xs font-bold text-white">
              1
            </span>
            <p className="text-sm font-semibold">Choose how to start</p>
          </div>

          <div className="flex flex-col gap-5 sm:flex-row">
            <StudioCard
              icon={<Plus size={20} />}
              tag="Manual"
              title="New persona"
              description="Fill in every field yourself - title, tags, persona, script, and the rest - with full control over each one."
              onClick={() => navigate("/games/new")}
              delay={160}
            />
            <StudioCard
              icon={<Sparkles size={20} />}
              tag="AI-guided"
              title="Build with AI"
              description="Describe who you want, answer a couple of questions, and get a full draft to review and tweak before saving."
              onClick={() => navigate("/games/builder")}
              delay={220}
            />
            <StudioCard
              icon={<FileText size={20} />}
              tag="From a video"
              title="Import from a transcript"
              description="Paste a transcript, or point at a captioned YouTube video, and get a draft persona inspired by it."
              onClick={() => navigate("/games/from-transcript")}
              delay={280}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
