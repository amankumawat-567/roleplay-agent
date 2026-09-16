import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, FileText, Link2, Sparkles } from "lucide-react";
import { api, ApiError } from "../services/api";

type Mode = "video" | "text";

function fieldClasses() {
  return "w-full rounded-xl border border-[var(--color-border)] bg-white/[0.03] px-3.5 py-2.5 text-sm outline-none transition-all duration-200 placeholder:text-[var(--color-sub-dim)] focus:border-[var(--color-accent)]/60 focus:bg-white/[0.05] focus:shadow-[0_0_0_4px_rgba(168,85,247,0.1)]";
}

export function TranscriptImportPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("video");
  const [url, setUrl] = useState("");
  const [transcript, setTranscript] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    try {
      const draft =
        mode === "video"
          ? await api.generateDraftFromVideo(url.trim())
          : await api.generateDraftFromTranscript(transcript.trim());
      navigate("/games/new", { state: { draft } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to generate a draft from this transcript.");
    } finally {
      setLoading(false);
    }
  }

  const canGenerate = (mode === "video" ? url : transcript).trim().length > 0;

  return (
    <div className="relative flex h-full flex-1 flex-col">
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-64 bg-[radial-gradient(ellipse_at_top,rgba(168,85,247,0.18),transparent_70%)]" />

      <header className="glass-panel relative z-10 flex items-center gap-3 border-b border-[var(--color-border-soft)] px-5 py-3.5">
        <button
          onClick={() => navigate("/studio")}
          className="flex h-8 w-8 items-center justify-center rounded-full text-[var(--color-sub)] transition-all duration-150 hover:bg-white/[0.06] hover:text-[var(--color-text)] active:scale-90"
        >
          <ArrowLeft size={16} />
        </button>
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)]">
          <FileText size={13} className="text-white" />
        </div>
        <span className="font-medium">Build a persona from a transcript</span>
      </header>

      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-5 overflow-y-auto px-5 py-8">
        <p className="animate-fade-up text-sm leading-relaxed text-[var(--color-sub)]">
          Point at a YouTube video with captions, or paste a transcript directly - either way, a
          draft persona gets generated from it for you to review and tweak before saving.
        </p>

        <div className="animate-fade-up flex w-fit gap-1 rounded-full border border-[var(--color-border)] bg-white/[0.03] p-1">
          <button
            type="button"
            onClick={() => setMode("video")}
            className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-medium transition-all duration-150 ${
              mode === "video" ? "bg-white/[0.08] text-[var(--color-text)]" : "text-[var(--color-sub)]"
            }`}
          >
            <Link2 size={12} /> Video URL
          </button>
          <button
            type="button"
            onClick={() => setMode("text")}
            className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-medium transition-all duration-150 ${
              mode === "text" ? "bg-white/[0.08] text-[var(--color-text)]" : "text-[var(--color-sub)]"
            }`}
          >
            <FileText size={12} /> Paste transcript
          </button>
        </div>

        {mode === "video" ? (
          <div className="animate-fade-up flex flex-col gap-1.5">
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
              className={fieldClasses()}
            />
            <p className="text-xs text-[var(--color-sub-dim)]">
              Only works for videos with captions (auto-generated is fine) - audio transcription
              isn't supported yet.
            </p>
          </div>
        ) : (
          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            placeholder="Paste a transcript here…"
            className={`animate-fade-up min-h-64 resize-y ${fieldClasses()}`}
          />
        )}

        {error && <p className="animate-fade-up text-xs text-rose-400">{error}</p>}

        <button
          onClick={handleGenerate}
          disabled={!canGenerate || loading}
          className="animate-fade-up flex items-center justify-center gap-1.5 self-start rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] px-4 py-2 text-sm font-medium text-white transition-all duration-200 enabled:hover:scale-105 enabled:hover:shadow-[0_4px_16px_-2px_rgba(168,85,247,0.6)] disabled:cursor-not-allowed disabled:opacity-30 active:scale-95"
        >
          <Sparkles size={14} className={loading ? "animate-pulse" : ""} />
          {loading ? "Generating draft…" : "Generate draft"}
        </button>
      </div>
    </div>
  );
}
