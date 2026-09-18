import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { Lightbulb, Mic, Paperclip, Send, Square } from "lucide-react";

interface ComposerProps {
  disabled: boolean;
  onSend: (text: string) => void;
  placeholder?: string;
  /** Section F0: hidden entirely (not merely disabled) once this persona's
   * model reports audio-input capability - voice mode is the better fit
   * for that persona, and browser dictation's transcribe-then-discard-tone
   * approximation shouldn't compete with it in text mode. */
  hideDictation?: boolean;
}

function PillButton({
  icon,
  label,
  onClick,
  disabled,
  active,
  title,
}: {
  icon: ReactNode;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  active?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-pressed={active}
      className={`flex items-center gap-1.5 rounded-full border px-3.5 py-2 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        active
          ? "border-[var(--color-accent-2)]/30 bg-[var(--color-accent-2)]/15 text-[var(--color-accent-2)]"
          : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-sub)] hover:bg-[var(--color-surface-hover)]"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

/** Minimal ambient shape for the non-standard SpeechRecognition API - no
 * @types package ships one, and we only touch a handful of members. */
interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

export function Composer({ disabled, onSend, placeholder, hideDictation }: ComposerProps) {
  const [value, setValue] = useState("");
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  const SpeechRecognitionCtor =
    (window as unknown as { SpeechRecognition?: new () => SpeechRecognitionLike; webkitSpeechRecognition?: new () => SpeechRecognitionLike })
      .SpeechRecognition ??
    (window as unknown as { webkitSpeechRecognition?: new () => SpeechRecognitionLike }).webkitSpeechRecognition;

  useEffect(() => {
    return () => recognitionRef.current?.stop();
  }, []);

  function submit() {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") submit();
  }

  function toggleVoice() {
    if (!SpeechRecognitionCtor) return;
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    const recognition = new SpeechRecognitionCtor();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) setValue((prev) => (prev ? `${prev} ${transcript}` : transcript));
    };
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }

  return (
    <div
      className="rounded-[28px] bg-gradient-to-r from-[var(--color-accent)]/40 via-[var(--color-border)] to-[var(--color-accent-2)]/40 p-[1.5px] shadow-lg shadow-black/20 transition-all duration-200 focus-within:from-[var(--color-accent)]/70 focus-within:to-[var(--color-accent-2)]/70"
    >
      <div className="flex flex-col gap-3 rounded-[26px] bg-[var(--color-panel)] px-5 pb-3 pt-4">
        <label htmlFor="composer-input" className="sr-only">
          Message
        </label>
        <input
          id="composer-input"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder ?? "Ask me anything…"}
          autoComplete="off"
          className="w-full bg-transparent text-[15px] text-[var(--color-text)] outline-none placeholder:text-[var(--color-sub-dim)]"
        />
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <PillButton icon={<Paperclip size={14} aria-hidden="true" />} label="Attach" disabled title="Not available yet" />
            <PillButton icon={<Lightbulb size={14} aria-hidden="true" />} label="Deep Think" disabled title="Not available yet" />
          </div>
          <div className="flex items-center gap-2">
            {!hideDictation && (
              <PillButton
                icon={listening ? <Square size={14} aria-hidden="true" /> : <Mic size={14} aria-hidden="true" />}
                label={listening ? "Stop" : "Voice"}
                active={listening}
                onClick={toggleVoice}
                disabled={!SpeechRecognitionCtor}
                title={
                  !SpeechRecognitionCtor
                    ? "Voice input isn't supported in this browser"
                    : listening
                      ? "Stop dictating"
                      : "Dictate a message"
                }
              />
            )}
            <button
              onClick={submit}
              disabled={disabled || !value.trim()}
              className="flex shrink-0 items-center gap-1.5 rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] px-5 py-2.5 text-sm font-medium text-white transition-all duration-200 enabled:hover:scale-[1.03] enabled:hover:shadow-[0_4px_16px_-2px_rgba(168,85,247,0.6)] disabled:cursor-not-allowed disabled:opacity-40 active:scale-95"
            >
              <Send size={14} aria-hidden="true" />
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
