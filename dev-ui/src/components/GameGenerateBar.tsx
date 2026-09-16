import { useRef, useState } from "react";
import type { ChangeEvent, KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight, FileAudio, FileUp, Image, Plus, Sparkle, X } from "lucide-react";
import { ModelPicker } from "./ModelPicker";

const GENRE_TAGS = ["Fantasy", "Sci-fi", "Mystery"];

const EXAMPLE_PROMPTS = [
  "A grumpy old wizard who hates visitors…",
  "A detective interrogating a nervous suspect…",
  "Two rivals stuck in an elevator together…",
  "A ship captain rallying a nervous crew…",
];

interface Attachment {
  name: string;
  kind: "image" | "file" | "audio";
}

interface GameGenerateBarProps {
  onSubmit: (text: string) => void;
}

/** The home page's "describe a persona, hit Create" bar - a text field, a
 * toolbar of genre chips plus an upload menu, a model picker, and a
 * use-skills switch (see GameEditorPage for where these actually get saved
 * once this flow wires up to game creation). Skills themselves aren't
 * picked here - toggling this on is meant to hand the choice to an AI step
 * later that searches the skill registry (/api/skills) for whatever's
 * relevant to the described game. */
export function GameGenerateBar({ onSubmit }: GameGenerateBarProps) {
  const [value, setValue] = useState("");
  const [exampleIndex, setExampleIndex] = useState(0);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [useSkills, setUseSkills] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploadMenuOpen, setUploadMenuOpen] = useState(false);
  const [uploadMenuCoords, setUploadMenuCoords] = useState({ bottom: 0, left: 0 });

  const uploadTriggerRef = useRef<HTMLButtonElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const audioInputRef = useRef<HTMLInputElement>(null);

  function openUploadMenu() {
    const rect = uploadTriggerRef.current?.getBoundingClientRect();
    if (rect) {
      setUploadMenuCoords({ bottom: window.innerHeight - rect.top + 8, left: rect.left });
    }
    setUploadMenuOpen(true);
  }

  function submit() {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") submit();
  }

  function appendTag(tag: string) {
    setValue((v) => (v.trim() ? `${v.trim()}, ${tag.toLowerCase()}` : `A ${tag.toLowerCase()} persona: `));
  }

  function cycleExample(dir: 1 | -1) {
    setExampleIndex((i) => (i + dir + EXAMPLE_PROMPTS.length) % EXAMPLE_PROMPTS.length);
  }

  function handleAttach(kind: Attachment["kind"]) {
    setUploadMenuOpen(false);
    if (kind === "image") imageInputRef.current?.click();
    if (kind === "file") fileInputRef.current?.click();
    if (kind === "audio") audioInputRef.current?.click();
  }

  function onFileChosen(kind: Attachment["kind"]) {
    return (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      setAttachments((prev) => [...prev, { name: file.name, kind }]);
    };
  }

  function removeAttachment(index: number) {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  }

  return (
    <div className="flex w-full flex-col items-end gap-2.5">
      <div className="relative w-full rounded-[28px] border border-white/[0.07] bg-[#0f0d16]/90 p-2.5 shadow-[0_30px_60px_-20px_rgba(236,72,153,0.25)] backdrop-blur-xl transition-all duration-200 focus-within:border-[var(--color-accent)]/40">
        <Sparkle size={16} className="absolute right-4 top-3.5 text-white/25" />

        <div className="flex items-center gap-2 px-3 pb-1 pt-2">
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={EXAMPLE_PROMPTS[exampleIndex]}
            autoComplete="off"
            className="w-full bg-transparent text-[15px] outline-none placeholder:text-[var(--color-sub-dim)]"
          />
        </div>

        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-3 pb-2">
            {attachments.map((a, i) => (
              <span
                key={`${a.name}-${i}`}
                className="flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.04] py-1 pl-2.5 pr-1.5 text-[11px] text-[var(--color-sub)]"
              >
                {a.kind === "image" && <Image size={11} />}
                {a.kind === "audio" && <FileAudio size={11} />}
                {a.kind === "file" && <FileUp size={11} />}
                <span className="max-w-[10rem] truncate">{a.name}</span>
                <button
                  type="button"
                  onClick={() => removeAttachment(i)}
                  title="Remove"
                  className="flex h-3.5 w-3.5 items-center justify-center rounded-full text-[var(--color-sub-dim)] hover:text-[var(--color-text)]"
                >
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-1.5 border-t border-white/[0.05] px-1.5 pt-2.5">
          <div className="relative">
            <button
              ref={uploadTriggerRef}
              type="button"
              onClick={() => (uploadMenuOpen ? setUploadMenuOpen(false) : openUploadMenu())}
              title="Attach image, file, or audio"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.03] text-[var(--color-sub)] transition-all duration-150 hover:border-white/20 hover:text-[var(--color-text)]"
            >
              <Plus size={13} />
            </button>
            {uploadMenuOpen &&
              createPortal(
                <>
                  <div className="fixed inset-0 z-[100]" onClick={() => setUploadMenuOpen(false)} />
                  <div
                    className="fixed z-[110] flex w-40 flex-col overflow-hidden rounded-xl border border-white/[0.08] bg-[#14121e] py-1 shadow-xl"
                    style={{ bottom: uploadMenuCoords.bottom, left: uploadMenuCoords.left }}
                  >
                    <button
                      type="button"
                      onClick={() => handleAttach("image")}
                      className="flex items-center gap-2 px-3 py-2 text-left text-xs text-[var(--color-sub)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-text)]"
                    >
                      <Image size={13} /> Image
                    </button>
                    <button
                      type="button"
                      onClick={() => handleAttach("file")}
                      className="flex items-center gap-2 px-3 py-2 text-left text-xs text-[var(--color-sub)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-text)]"
                    >
                      <FileUp size={13} /> File
                    </button>
                    <button
                      type="button"
                      onClick={() => handleAttach("audio")}
                      className="flex items-center gap-2 px-3 py-2 text-left text-xs text-[var(--color-sub)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-text)]"
                    >
                      <FileAudio size={13} /> Audio
                    </button>
                  </div>
                </>,
                document.body,
              )}
            <input ref={imageInputRef} type="file" accept="image/*" hidden onChange={onFileChosen("image")} />
            <input ref={fileInputRef} type="file" hidden onChange={onFileChosen("file")} />
            <input ref={audioInputRef} type="file" accept="audio/*" hidden onChange={onFileChosen("audio")} />
          </div>

          {GENRE_TAGS.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => appendTag(tag)}
              title={`Add "${tag}" to your description`}
              className="rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-[var(--color-sub)] transition-all duration-150 hover:border-white/20 hover:text-[var(--color-text)]"
            >
              {tag}
            </button>
          ))}

          <label
            className="ml-1 flex shrink-0 items-center gap-2 text-xs text-[var(--color-sub)]"
            title="AI will search the skill registry for whatever's relevant to this game and attach it automatically"
          >
            In game skill
            <button
              type="button"
              role="switch"
              aria-checked={useSkills}
              onClick={() => setUseSkills((v) => !v)}
              className={`relative h-4 w-8 shrink-0 rounded-full transition-colors duration-200 ${
                useSkills ? "bg-gradient-to-r from-pink-500 to-orange-400" : "bg-white/10"
              }`}
            >
              <span
                className={`absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform duration-200 ${
                  useSkills ? "translate-x-[18px]" : "translate-x-0.5"
                }`}
              />
            </button>
          </label>

          <div className="ml-auto">
            <ModelPicker
              provider={provider}
              model={model}
              onChange={(p, m) => {
                setProvider(p);
                setModel(m);
              }}
            />
          </div>

          <button
            onClick={submit}
            disabled={!value.trim()}
            className="flex shrink-0 items-center gap-1.5 rounded-full bg-gradient-to-r from-pink-500 to-orange-400 px-4 py-1.5 text-sm font-medium text-white transition-all duration-200 enabled:hover:scale-105 enabled:hover:shadow-[0_4px_20px_-4px_rgba(236,72,153,0.6)] disabled:cursor-not-allowed disabled:opacity-30 active:scale-95"
          >
            <Sparkle size={14} />
            Create
          </button>
        </div>
      </div>

      <div className="hidden shrink-0 items-center gap-2 sm:flex">
        <button
          onClick={() => cycleExample(-1)}
          title="Previous example"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-white/[0.05] text-[var(--color-sub)] transition-all duration-150 hover:bg-white/[0.1] hover:text-[var(--color-text)] active:scale-90"
        >
          <ChevronLeft size={14} />
        </button>
        <button
          onClick={() => cycleExample(1)}
          title="Next example"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-white/[0.05] text-[var(--color-sub)] transition-all duration-150 hover:bg-white/[0.1] hover:text-[var(--color-text)] active:scale-90"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}
