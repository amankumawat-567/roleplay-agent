import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, FormEvent, ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Camera, FileAudio, Image as ImageIcon, X } from "lucide-react";
import { api, ApiError } from "../services/api";

function fieldClasses() {
  return "w-full rounded-xl border border-[var(--color-border)] bg-white/[0.03] px-3.5 py-2.5 text-sm outline-none transition-all duration-200 placeholder:text-[var(--color-sub-dim)] focus:border-[var(--color-accent)]/60 focus:bg-white/[0.05] focus:shadow-[0_0_0_4px_rgba(168,85,247,0.1)]";
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium uppercase tracking-wider text-[var(--color-sub-dim)]">{label}</span>
      {children}
      {hint && <span className="text-xs text-[var(--color-sub-dim)]">{hint}</span>}
    </label>
  );
}

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="glass-panel animate-fade-up rounded-3xl p-6">
      <h2 className="text-sm font-semibold text-[var(--color-text)]">{title}</h2>
      {description && <p className="mt-0.5 text-xs text-[var(--color-sub-dim)]">{description}</p>}
      <div className="mt-4 flex flex-col gap-4">{children}</div>
    </section>
  );
}

/** Same shape/rationale as GameEditorPage's CoverImagePicker (a hidden file
 * input triggered by a camera-icon button), reused here for a cloned
 * voice's optional profile image. */
function ImagePicker({ previewUrl, onPick }: { previewUrl: string | null; onPick: (file: File) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) onPick(file);
  }

  return (
    <div className="flex items-center gap-4">
      <div className="relative h-24 w-24 shrink-0 overflow-hidden rounded-full border border-[var(--color-border)] bg-white/[0.03]">
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
          title="Upload a profile image"
          className="absolute bottom-0.5 right-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] text-white shadow-md transition-transform hover:scale-110"
        >
          <Camera size={12} />
        </button>
      </div>
      <div>
        <p className="text-sm font-medium">Profile image</p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="text-xs font-medium text-[var(--color-accent)] transition-opacity hover:opacity-80"
        >
          {previewUrl ? "Change photo" : "Upload photo"}
        </button>
        <p className="mt-0.5 text-xs text-[var(--color-sub-dim)]">Optional - PNG, JPG, WEBP, or GIF.</p>
      </div>
      <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden onChange={handleChange} />
    </div>
  );
}

/** The wav counterpart to ImagePicker above - a hidden file input behind a
 * dropzone-styled button, since a native <input type="file"> can't be
 * styled directly. Client-side this only checks the extension/mime type;
 * the real validation (mono, 16-bit PCM, RIFF header, size/duration) runs
 * server-side in POST /api/voices/cloned and its rejection reason is
 * surfaced as this page's error banner. */
function WavPicker({ file, onPick }: { file: File | null; onPick: (file: File | null) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0];
    e.target.value = "";
    if (picked) onPick(picked);
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="flex w-full items-center gap-3 rounded-xl border border-dashed border-[var(--color-border)] bg-white/[0.02] px-4 py-3.5 text-left transition-colors hover:bg-white/[0.04]"
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/[0.06] text-[var(--color-sub)]">
          <FileAudio size={16} />
        </span>
        <span className="flex-1 truncate text-sm">
          {file ? file.name : <span className="text-[var(--color-sub-dim)]">Choose a .wav file…</span>}
        </span>
        {file && (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              onPick(null);
            }}
            aria-label="Remove selected file"
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[var(--color-sub-dim)] transition-colors hover:bg-white/10 hover:text-[var(--color-text)]"
          >
            <X size={13} />
          </span>
        )}
      </button>
      <input ref={inputRef} type="file" accept="audio/wav,audio/x-wav,audio/wave,.wav" hidden onChange={handleChange} />
    </div>
  );
}

export function AudioCreatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [wavFile, setWavFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const imagePreviewUrl = useMemo(() => (imageFile ? URL.createObjectURL(imageFile) : null), [imageFile]);
  useEffect(() => {
    return () => {
      if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl);
    };
  }, [imagePreviewUrl]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
    if (!wavFile) {
      setError("Choose a .wav file to upload.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const voice = await api.createClonedVoice(name.trim(), wavFile, imageFile);
      navigate("/audio", { state: { newVoiceId: voice.id } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add audio");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex h-full flex-1 flex-col">
      <header className="flex items-center gap-3 bg-gradient-to-b from-white/[0.05] to-transparent px-5 py-3.5">
        <button
          onClick={() => navigate("/audio")}
          aria-label="Back to audio"
          className="flex h-8 w-8 items-center justify-center rounded-full text-[var(--color-sub)] transition-all duration-150 hover:bg-white/[0.06] hover:text-[var(--color-text)] active:scale-90"
        >
          <ArrowLeft size={16} />
        </button>
        <span className="flex-1 font-medium">Add audio</span>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-8">
        <form id="audio-create-form" onSubmit={handleSubmit} className="mx-auto flex max-w-2xl flex-col gap-5 pb-28">
          {error && <p className="animate-fade-up text-sm text-rose-400">{error}</p>}

          <Section title="New voice" description="Upload a reference clip to clone as a voice a persona can speak with">
            <ImagePicker previewUrl={imagePreviewUrl} onPick={setImageFile} />
            <Field label="Name">
              <input
                className={fieldClasses()}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Nova"
                required
              />
            </Field>
            <Field
              label="Audio (.wav)"
              hint="Mono, 16-bit PCM, between 1s and 120s, up to 20MB - anything else is rejected with a reason."
            >
              <WavPicker file={wavFile} onPick={setWavFile} />
            </Field>
          </Section>
        </form>
      </div>

      <div className="relative z-10 bg-gradient-to-t from-[var(--color-bg)] via-[var(--color-bg)]/85 to-transparent px-5 pb-4 pt-10">
        <div className="mx-auto flex max-w-2xl items-center gap-3">
          <button
            type="submit"
            form="audio-create-form"
            disabled={saving}
            className="rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] px-5 py-2 text-sm font-medium text-white transition-all duration-200 hover:scale-105 hover:shadow-[0_4px_16px_-2px_rgba(168,85,247,0.6)] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100"
          >
            {saving ? "Saving…" : "Add audio"}
          </button>
          <button
            type="button"
            onClick={() => navigate("/audio")}
            className="rounded-full px-5 py-2 text-sm text-[var(--color-sub)] transition hover:text-[var(--color-text)]"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
