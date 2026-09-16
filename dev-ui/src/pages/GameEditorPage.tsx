import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, FormEvent, MouseEvent, ReactNode } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Camera, ChevronDown, Image as ImageIcon, Pause, Play, Sparkles, Trash2, X } from "lucide-react";
import { api, ApiError } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import { coverUrlFor } from "../utils/gameTileVisuals";
import { ModelPicker } from "../components/ModelPicker";
import { VoiceAvatar } from "../components/VoiceAvatar";
import { useClonedVoices } from "../hooks/useClonedVoices";
import { VOICES, sampleUrlFor } from "../data/voices";
import type { GameCreateRequest, SkillSummary } from "../types";

/** What `location.state.draft` can carry into this page: either the AI
 * builder's `GameDraft` (persona-shaped fields only) or a full persona's
 * settings for "Duplicate" (see docs/ARCHITECTURE.md's "manage this
 * persona" menu) - a strict subset of `GameCreateRequest`, so either
 * shape satisfies it and whichever fields are present win over
 * `EMPTY_FORM`'s defaults. */
type IncomingDraft = Partial<GameCreateRequest>;

interface FormState {
  title: string;
  character_name: string;
  tags: string;
  provider: string;
  model: string;
  starter: "ai" | "user";
  persona: string;
  user_role: string;
  script: string;
  research_query: string;
  num_ctx: string;
  memory_recall: boolean;
  skills: string[];
  voice: string | null;
}

// No hardcoded provider/model here - "the default" is computed from
// GET /api/models (see docs/ARCHITECTURE.md's "Dynamic model discovery"),
// filled in by an effect below for a genuinely new, untouched persona.
const EMPTY_FORM: FormState = {
  title: "",
  character_name: "",
  tags: "",
  provider: "",
  model: "",
  starter: "user",
  persona: "",
  user_role: "",
  script: "",
  research_query: "",
  num_ctx: "",
  memory_recall: false,
  skills: [],
  voice: null,
};

function titleCase(id: string): string {
  return id
    .split("_")
    .map((w) => w[0]?.toUpperCase() + w.slice(1))
    .join(" ");
}

function fieldClasses() {
  return "w-full rounded-xl border border-[var(--color-border)] bg-white/[0.03] px-3.5 py-2.5 text-sm outline-none transition-all duration-200 placeholder:text-[var(--color-sub-dim)] focus:border-[var(--color-accent)]/60 focus:bg-white/[0.05] focus:shadow-[0_0_0_4px_rgba(168,85,247,0.1)]";
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium uppercase tracking-wider text-[var(--color-sub-dim)]">
        {label}
      </span>
      {children}
      {hint && <span className="text-xs text-[var(--color-sub-dim)]">{hint}</span>}
    </label>
  );
}

function Section({
  title,
  description,
  children,
  delay,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  delay: number;
}) {
  return (
    <section
      className="glass-panel animate-fade-up rounded-3xl p-6"
      style={{ animationDelay: `${delay}ms` }}
    >
      <h2 className="text-sm font-semibold text-[var(--color-text)]">{title}</h2>
      {description && <p className="mt-0.5 text-xs text-[var(--color-sub-dim)]">{description}</p>}
      <div className="mt-4 flex flex-col gap-4">{children}</div>
    </section>
  );
}

/** Same card chrome as Section, but starts collapsed and toggles open -
 * used for "Advanced" so a new persona's form leads with what actually
 * matters (identity, model, character) and hides the rarer knobs. */
function CollapsibleSection({
  title,
  description,
  defaultOpen = false,
  delay,
  children,
}: {
  title: string;
  description?: string;
  defaultOpen?: boolean;
  delay: number;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section
      className="glass-panel animate-fade-up rounded-3xl p-6"
      style={{ animationDelay: `${delay}ms` }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <div>
          <h2 className="text-sm font-semibold text-[var(--color-text)]">{title}</h2>
          {description && <p className="mt-0.5 text-xs text-[var(--color-sub-dim)]">{description}</p>}
        </div>
        <ChevronDown
          size={16}
          className={`shrink-0 text-[var(--color-sub-dim)] transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && <div className="mt-4 flex flex-col gap-4">{children}</div>}
    </section>
  );
}

function CheckboxRow({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  hint: string;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-[var(--color-border-soft)] bg-white/[0.02] p-3.5 transition-colors duration-150 hover:bg-white/[0.04]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-accent)]"
      />
      <span className="text-sm">
        <span className="font-medium">{label}</span>
        <span className="mt-0.5 block text-xs text-[var(--color-sub-dim)]">{hint}</span>
      </span>
    </label>
  );
}

/** Section C - assigns one of the 6 CustomVoice presets (see
 * dev-ui/src/data/voices.ts) as this persona's voice, or none. Reuses
 * AudioPage's own sample-clip/avatar assets so a card here looks and
 * sounds identical to its entry there. */
function VoicePicker({ selected, onChange }: { selected: string | null; onChange: (voice: string | null) => void }) {
  const [playingId, setPlayingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const clonedVoices = useClonedVoices();

  function preview(e: MouseEvent, voiceId: string) {
    e.stopPropagation();
    const audio = audioRef.current;
    if (!audio) return;
    if (playingId === voiceId) {
      audio.pause();
      setPlayingId(null);
      return;
    }
    audio.src = sampleUrlFor(voiceId);
    audio.play().catch(() => setPlayingId(null));
    setPlayingId(voiceId);
  }

  return (
    <div className="flex flex-wrap gap-2">
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio ref={audioRef} onEnded={() => setPlayingId(null)} className="hidden" />
      <button
        type="button"
        onClick={() => onChange(null)}
        className={`flex items-center gap-2 rounded-full border py-1.5 pl-2 pr-3.5 text-sm transition-colors ${
          selected === null
            ? "border-[var(--color-accent)]/40 bg-[var(--color-accent)]/10 text-[var(--color-text)]"
            : "border-[var(--color-border)] bg-white/[0.02] text-[var(--color-sub)] hover:bg-white/[0.05]"
        }`}
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white/[0.06] text-[var(--color-sub-dim)]">
          <X size={13} />
        </span>
        No voice
      </button>
      {VOICES.map((voice) => (
        <button
          key={voice.id}
          type="button"
          onClick={() => onChange(voice.id)}
          className={`flex items-center gap-2 rounded-full border py-1.5 pl-2 pr-1.5 text-sm transition-colors ${
            selected === voice.id
              ? "border-[var(--color-accent)]/40 bg-[var(--color-accent)]/10 text-[var(--color-text)]"
              : "border-[var(--color-border)] bg-white/[0.02] text-[var(--color-sub)] hover:bg-white/[0.05]"
          }`}
        >
          <VoiceAvatar id={voice.id} size={28} />
          {voice.name}
          <span
            onClick={(e) => preview(e, voice.id)}
            title="Preview"
            className="flex h-6 w-6 items-center justify-center rounded-full text-[var(--color-sub-dim)] transition-colors hover:bg-white/10 hover:text-[var(--color-text)]"
          >
            {playingId === voice.id ? <Pause size={11} /> : <Play size={11} />}
          </span>
        </button>
      ))}
      {clonedVoices.map((id) => (
        <button
          key={id}
          type="button"
          onClick={() => onChange(id)}
          title="Cloned from a reference clip in data/voice_samples/"
          className={`flex items-center gap-2 rounded-full border py-1.5 pl-2 pr-1.5 text-sm transition-colors ${
            selected === id
              ? "border-[var(--color-accent)]/40 bg-[var(--color-accent)]/10 text-[var(--color-text)]"
              : "border-[var(--color-border)] bg-white/[0.02] text-[var(--color-sub)] hover:bg-white/[0.05]"
          }`}
        >
          <VoiceAvatar id={id} size={28} />
          {id.charAt(0).toUpperCase() + id.slice(1)}
          <span
            onClick={(e) => preview(e, id)}
            title="Preview"
            className="flex h-6 w-6 items-center justify-center rounded-full text-[var(--color-sub-dim)] transition-colors hover:bg-white/10 hover:text-[var(--color-text)]"
          >
            {playingId === id ? <Pause size={11} /> : <Play size={11} />}
          </span>
        </button>
      ))}
    </div>
  );
}

/** Search-and-add tag picker for skills, backed by the live skill
 * registry (/api/skills) - generalizes to whatever's registered rather
 * than hardcoding one checkbox per known skill. The listbox is portaled
 * to <body> and positioned from the input's own rect, the same fix used
 * for ModelPicker: a glass-panel ancestor's backdrop-blur creates a
 * stacking context that would otherwise trap it behind later content. */
function SkillTagInput({ selected, onChange }: { selected: string[]; onChange: (skills: string[]) => void }) {
  const [allSkills, setAllSkills] = useState<SkillSummary[]>([]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0, width: 0 });
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .listSkills()
      .then(setAllSkills)
      .catch(() => setAllSkills([]));
  }, []);

  function openMenu() {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (rect) setCoords({ top: rect.bottom + 6, left: rect.left, width: rect.width });
    setOpen(true);
  }

  const available = allSkills.filter(
    (s) => !selected.includes(s.id) && titleCase(s.id).toLowerCase().includes(query.trim().toLowerCase()),
  );

  function add(id: string) {
    onChange([...selected, id]);
    setQuery("");
  }

  function remove(id: string) {
    onChange(selected.filter((s) => s !== id));
  }

  return (
    <div>
      {selected.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {selected.map((id) => (
            <span
              key={id}
              className="flex items-center gap-1.5 rounded-full border border-[var(--color-accent)]/40 bg-[var(--color-accent)]/10 py-1 pl-3 pr-1.5 text-xs text-[var(--color-text)]"
            >
              {titleCase(id)}
              <button
                type="button"
                onClick={() => remove(id)}
                className="flex h-4 w-4 items-center justify-center rounded-full text-[var(--color-sub-dim)] transition-colors hover:text-[var(--color-text)]"
              >
                <X size={10} />
              </button>
            </span>
          ))}
        </div>
      )}

      <div ref={wrapRef}>
        <input
          className={fieldClasses()}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={openMenu}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          placeholder="Search skills to add…"
        />
      </div>

      {open &&
        available.length > 0 &&
        createPortal(
          <div
            className="fixed z-[110] max-h-52 overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-panel-hover)] p-1.5 shadow-xl"
            style={{ top: coords.top, left: coords.left, width: coords.width }}
          >
            {available.map((s) => (
              <button
                key={s.id}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => add(s.id)}
                className="flex w-full flex-col items-start rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-white/[0.06]"
              >
                <span className="font-medium">{titleCase(s.id)}</span>
                <span className="line-clamp-1 text-xs text-[var(--color-sub-dim)]">{s.description}</span>
              </button>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}

function CoverImagePicker({ previewUrl, onPick }: { previewUrl: string | null; onPick: (file: File) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) onPick(file);
  }

  return (
    <div className="flex items-center gap-4">
      <div className="relative h-24 w-[84px] shrink-0 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white/[0.03]">
        {previewUrl ? (
          <img src={previewUrl} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-[var(--color-sub-dim)]">
            <ImageIcon size={22} />
          </div>
        )}
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          title="Upload a game card image"
          className="absolute bottom-1.5 right-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] text-white shadow-md transition-transform hover:scale-110"
        >
          <Camera size={12} />
        </button>
      </div>
      <div>
        <p className="text-sm font-medium">Game card image</p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="text-xs font-medium text-[var(--color-accent)] transition-opacity hover:opacity-80"
        >
          {previewUrl ? "Change photo" : "Upload photo"}
        </button>
        <p className="mt-0.5 text-xs text-[var(--color-sub-dim)]">PNG, JPG, or WEBP - shown on this persona's card.</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        hidden
        onChange={handleChange}
      />
    </div>
  );
}

export function GameEditorPage() {
  const { gameId } = useParams<{ gameId: string }>();
  const isEditing = Boolean(gameId);
  const navigate = useNavigate();
  const location = useLocation();
  const loadAll = useAppStore((s) => s.loadAll);
  const draft = (location.state as { draft?: IncomingDraft } | null)?.draft;

  const [form, setForm] = useState<FormState>(() =>
    !isEditing && draft
      ? {
          title: draft.title ?? EMPTY_FORM.title,
          character_name: draft.character_name ?? EMPTY_FORM.character_name,
          tags: draft.tags ? draft.tags.join(", ") : EMPTY_FORM.tags,
          provider: draft.provider ?? EMPTY_FORM.provider,
          model: draft.model ?? EMPTY_FORM.model,
          starter: draft.starter ?? EMPTY_FORM.starter,
          persona: draft.persona ?? EMPTY_FORM.persona,
          user_role: draft.user_role ?? EMPTY_FORM.user_role,
          script: draft.script ?? EMPTY_FORM.script,
          research_query: draft.research_query ?? EMPTY_FORM.research_query,
          num_ctx: draft.num_ctx != null ? String(draft.num_ctx) : EMPTY_FORM.num_ctx,
          memory_recall: draft.memory_recall ?? EMPTY_FORM.memory_recall,
          skills: draft.skills ?? EMPTY_FORM.skills,
          voice: draft.voice ?? EMPTY_FORM.voice,
        }
      : EMPTY_FORM,
  );
  const [loading, setLoading] = useState(isEditing);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  // A new persona (blank form, or an AI draft - neither ever carries a
  // provider/model) starts with no provider/model at all now that neither
  // is hardcoded (see docs/ARCHITECTURE.md's "Dynamic model discovery") -
  // fill in the computed default once it's known, but only if the field is
  // still untouched by the time it resolves (a Duplicate's own carried-over
  // provider/model, or anything the user already picked, must win).
  useEffect(() => {
    if (isEditing) return;
    api
      .getModels()
      .then((res) => {
        const provider = res.default_provider;
        const model = provider ? res.providers.find((p) => p.provider === provider)?.models[0]?.id : undefined;
        if (!provider || !model) return;
        setForm((f) => (f.provider || f.model ? f : { ...f, provider, model }));
      })
      .catch(() => {
        // Best-effort - the ModelPicker itself still shows "No models
        // available" and the form just stays blank there until picked.
      });
  }, [isEditing]);

  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [existingCoverUrl, setExistingCoverUrl] = useState<string | null>(null);
  const filePreviewUrl = useMemo(() => (coverFile ? URL.createObjectURL(coverFile) : null), [coverFile]);
  useEffect(() => {
    return () => {
      if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl);
    };
  }, [filePreviewUrl]);
  const coverPreviewUrl = filePreviewUrl ?? existingCoverUrl;

  useEffect(() => {
    if (!gameId) return;
    setLoading(true);
    api
      .getGame(gameId)
      .then((game) => {
        // provider/model/starter/num_ctx/memory_recall/skills/cover always
        // come from the saved game - an AI-generated draft never produces
        // those, so a draft only ever overrides the persona-shaped fields.
        setForm({
          title: draft?.title ?? game.title,
          character_name: draft?.character_name ?? game.character_name ?? "",
          tags: draft?.tags ? draft.tags.join(", ") : game.tags.join(", "),
          provider: game.provider,
          model: game.model,
          starter: game.starter,
          persona: draft?.persona ?? game.persona,
          user_role: draft?.user_role ?? game.user_role,
          script: draft?.script ?? game.script,
          research_query: draft?.research_query ?? game.research_query,
          num_ctx: game.num_ctx?.toString() ?? "",
          memory_recall: game.memory_recall,
          skills: game.skills,
          voice: game.voice,
        });
        setExistingCoverUrl(coverUrlFor(game.id, game.cover_image));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load game"))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!form.provider.trim() || !form.model.trim()) {
      setError("Pick a model before saving.");
      return;
    }
    setSaving(true);
    setError(null);

    const tags = form.tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const num_ctx = form.num_ctx.trim() ? Number(form.num_ctx) : null;

    const body: GameCreateRequest = {
      title: form.title,
      character_name: form.character_name.trim() || null,
      tags,
      provider: form.provider.trim(),
      model: form.model,
      starter: form.starter,
      persona: form.persona,
      user_role: form.user_role,
      script: form.script,
      research_query: form.research_query,
      num_ctx,
      memory_recall: form.memory_recall,
      skills: form.skills,
      voice: form.voice,
    };

    try {
      const saved = isEditing ? await api.updateGame(gameId!, body) : await api.createGame(body);
      if (coverFile) {
        await api.uploadGameCover(saved.id, coverFile);
      }
      await loadAll();
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save game");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!gameId) return;
    setDeleting(true);
    setError(null);
    try {
      await api.deleteGame(gameId);
      await loadAll();
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete game");
      setDeleting(false);
      setConfirmingDelete(false);
    }
  }

  function handleEditWithAi() {
    navigate("/games/builder", {
      state: {
        gameId,
        existingGame: {
          title: form.title,
          tags: form.tags,
          persona: form.persona,
          user_role: form.user_role,
          script: form.script,
          research_query: form.research_query,
        },
      },
    });
  }

  return (
    <div className="flex h-full flex-1 flex-col">
      <header className="flex items-center gap-3 bg-gradient-to-b from-white/[0.05] to-transparent px-5 py-3.5">
        <button
          onClick={() => navigate("/")}
          className="flex h-8 w-8 items-center justify-center rounded-full text-[var(--color-sub)] transition-all duration-150 hover:bg-white/[0.06] hover:text-[var(--color-text)] active:scale-90"
        >
          <ArrowLeft size={16} />
        </button>
        <span className="flex-1 font-medium">{isEditing ? `Edit ${form.title || "persona"}` : "New persona"}</span>
        {isEditing && !loading && (
          <button
            type="button"
            onClick={handleEditWithAi}
            className="flex items-center gap-1.5 rounded-full border border-[var(--color-accent)]/30 bg-[var(--color-accent)]/10 px-3.5 py-1.5 text-xs font-medium text-[var(--color-text)] transition-colors hover:bg-[var(--color-accent)]/20"
          >
            <Sparkles size={13} className="text-[var(--color-accent)]" />
            Edit with AI
          </button>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-8">
        {loading ? (
          <div className="mx-auto flex max-w-2xl flex-col gap-5">
            {[0, 1, 2].map((i) => (
              <div key={i} className="animate-shimmer h-40 rounded-3xl" style={{ animationDelay: `${i * 0.1}s` }} />
            ))}
          </div>
        ) : (
          <form id="editor-form" onSubmit={handleSubmit} className="mx-auto flex max-w-2xl flex-col gap-5 pb-28">
            {error && <p className="animate-fade-up text-sm text-rose-400">{error}</p>}
            {draft && (
              <p className="animate-fade-up flex items-center gap-2 rounded-xl border border-[var(--color-accent)]/30 bg-[var(--color-accent)]/10 px-3.5 py-2.5 text-xs text-[var(--color-sub)]">
                <Sparkles size={13} className="shrink-0 text-[var(--color-accent)]" />
                Prefilled from your AI conversation - review and adjust before saving.
              </p>
            )}

            <Section title="Basics" description="How this persona shows up in the picker" delay={0}>
              <CoverImagePicker previewUrl={coverPreviewUrl} onPick={setCoverFile} />
              <Field label="Title">
                <input
                  className={fieldClasses()}
                  value={form.title}
                  onChange={(e) => update("title", e.target.value)}
                  placeholder="My Persona"
                  required
                />
              </Field>
              <Field label="Character name" hint={'Who they are, e.g. "Alex" - not the scenario, e.g. "Rooftop First Date". Falls back to Title when blank.'}>
                <input
                  className={fieldClasses()}
                  value={form.character_name}
                  onChange={(e) => update("character_name", e.target.value)}
                  placeholder={form.title || "Alex"}
                />
              </Field>
              <Field label="Tags" hint="Comma-separated, shown as chips in the picker">
                <input
                  className={fieldClasses()}
                  value={form.tags}
                  onChange={(e) => update("tags", e.target.value)}
                  placeholder="casual, drama"
                />
              </Field>
            </Section>

            <Section title="Model" description="Which model runs this persona, and who speaks first" delay={80}>
              <Field label="Model" hint="Only models that are actually usable right now are offered - see docs/ARCHITECTURE.md's &quot;Dynamic model discovery&quot;.">
                <ModelPicker
                  provider={form.provider}
                  model={form.model}
                  onChange={(provider, model) => setForm((f) => ({ ...f, provider, model }))}
                />
              </Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Starter">
                  <select
                    className={fieldClasses()}
                    value={form.starter}
                    onChange={(e) => update("starter", e.target.value as "ai" | "user")}
                  >
                    <option value="user">User speaks first</option>
                    <option value="ai">AI speaks first</option>
                  </select>
                </Field>
                <Field label="Context window" hint="Blank uses the app default">
                  <input
                    type="number"
                    className={fieldClasses()}
                    value={form.num_ctx}
                    onChange={(e) => update("num_ctx", e.target.value)}
                    placeholder="8192"
                  />
                </Field>
              </div>
            </Section>

            <Section title="Character" description="The heart of the persona" delay={160}>
              <Field label="Persona" hint="Who the AI plays">
                <textarea
                  className={`${fieldClasses()} min-h-28 resize-y`}
                  value={form.persona}
                  onChange={(e) => update("persona", e.target.value)}
                  required
                />
              </Field>
              <Field label="User role" hint="Who the human is playing">
                <textarea
                  className={`${fieldClasses()} min-h-20 resize-y`}
                  value={form.user_role}
                  onChange={(e) => update("user_role", e.target.value)}
                  required
                />
              </Field>
              <Field label="Script" hint="Vague background + beats, not literal dialogue">
                <textarea
                  className={`${fieldClasses()} min-h-28 resize-y`}
                  value={form.script}
                  onChange={(e) => update("script", e.target.value)}
                  required
                />
              </Field>
            </Section>

            <CollapsibleSection
              title="Advanced"
              description="Research seed, memory, and in-conversation skills"
              delay={240}
            >
              <Field label="Research query" hint="Optional search seed for tone/style lookup">
                <input
                  className={fieldClasses()}
                  value={form.research_query}
                  onChange={(e) => update("research_query", e.target.value)}
                />
              </Field>
              <CheckboxRow
                checked={form.memory_recall}
                onChange={(v) => update("memory_recall", v)}
                label="Long-term memory recall"
                hint="Remembers details across sessions, not just the running summary. Requires an embedding model pulled in Ollama."
              />
              <Field label="Skills" hint="In-conversation tools this persona can call, searched from the skill registry">
                <SkillTagInput selected={form.skills} onChange={(skills) => update("skills", skills)} />
              </Field>
              <Field label="Voice" hint="Lets you hear this persona's replies read aloud in chat, via the read-aloud button">
                <VoicePicker selected={form.voice} onChange={(voice) => update("voice", voice)} />
              </Field>
            </CollapsibleSection>
          </form>
        )}
      </div>

      {!loading && (
        <div className="relative z-10 bg-gradient-to-t from-[var(--color-bg)] via-[var(--color-bg)]/85 to-transparent px-5 pb-4 pt-10">
          <div className="mx-auto flex max-w-2xl items-center gap-3">
            {confirmingDelete ? (
              <>
                <span className="text-sm text-rose-400">
                  Delete this persona? This also removes its chat history. This can't be undone.
                </span>
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={deleting}
                  className="ml-auto shrink-0 rounded-full bg-rose-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-rose-400 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {deleting ? "Deleting…" : "Delete"}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmingDelete(false)}
                  disabled={deleting}
                  className="shrink-0 rounded-full px-4 py-2 text-sm text-[var(--color-sub)] transition hover:text-[var(--color-text)]"
                >
                  Cancel
                </button>
              </>
            ) : (
              <>
                <button
                  type="submit"
                  form="editor-form"
                  disabled={saving}
                  className="rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] px-5 py-2 text-sm font-medium text-white transition-all duration-200 hover:scale-105 hover:shadow-[0_4px_16px_-2px_rgba(168,85,247,0.6)] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100"
                >
                  {saving ? "Saving…" : isEditing ? "Save changes" : "Create persona"}
                </button>
                <button
                  type="button"
                  onClick={() => navigate("/")}
                  className="rounded-full px-5 py-2 text-sm text-[var(--color-sub)] transition hover:text-[var(--color-text)]"
                >
                  Cancel
                </button>
                {isEditing && (
                  <button
                    type="button"
                    onClick={() => setConfirmingDelete(true)}
                    className="ml-auto flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-2 text-sm text-[var(--color-sub-dim)] transition-colors hover:text-rose-400"
                  >
                    <Trash2 size={14} />
                    Delete persona
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
