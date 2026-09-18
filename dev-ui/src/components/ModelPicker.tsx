import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown } from "lucide-react";
import { api } from "../services/api";
import type { ProviderModels } from "../types";

function providerLabel(provider: string): string {
  return provider === "ollama" ? "Ollama" : provider[0].toUpperCase() + provider.slice(1);
}

interface ModelPickerProps {
  provider: string;
  model: string;
  onChange: (provider: string, model: string) => void;
  disabled?: boolean;
}

/** A live provider/model picker (docs/roadmap.md section D) - grouped by
 * provider, sourced from `GET /api/models` instead of a hardcoded list, so
 * it only ever offers a model that's actually usable right now (Ollama
 * reachable, or a hosted provider with its key configured) - never a
 * disabled/greyed-out entry for one that isn't. Scrolls once a provider
 * has more models than fit; the trigger shows just the model id (the
 * provider is implied by the group it lives in). The panel is portaled to
 * <body> and positioned from the trigger's own bounding rect, since a
 * backdrop-blur/transform ancestor would otherwise trap an
 * absolutely-positioned panel behind later same-page content no matter how
 * high its z-index is set. */
export function ModelPicker({ provider, model, onChange, disabled = false }: ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState({ top: 0, right: 0 });
  const [providers, setProviders] = useState<ProviderModels[] | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .getModels()
      .then((res) => setProviders(res.providers))
      .catch(() => setProviders([]));
  }, []);

  function openMenu() {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) {
      setCoords({ top: rect.bottom + 8, right: window.innerWidth - rect.right });
    }
    setOpen(true);
  }

  function close() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") {
        close();
        return;
      }
      // Keep Tab cycling within the menu instead of letting focus escape
      // into the page behind this still-open portal.
      if (e.key === "Tab") {
        const items = menuRef.current?.querySelectorAll<HTMLElement>('button[type="button"]:not(:disabled)');
        if (!items || items.length === 0) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    setTimeout(() => {
      const firstItem = menuRef.current?.querySelector('button[type="button"]') as HTMLElement;
      firstItem?.focus();
    }, 0);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  const label = model || (providers === null ? "Loading models…" : providers.length === 0 ? "No models available" : "Select model");

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => (open ? close() : openMenu())}
        disabled={disabled || providers?.length === 0}
        aria-label={disabled ? "Model selection not available yet" : "Select model"}
        aria-expanded={open}
        aria-haspopup="listbox"
        className="flex shrink-0 items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.03] py-1.5 pl-3 pr-2.5 text-xs text-[var(--color-sub)] transition-colors hover:border-white/20 hover:text-[var(--color-text)] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {label}
        <ChevronDown size={11} className="text-[var(--color-sub-dim)]" aria-hidden="true" />
      </button>

      {open &&
        providers &&
        !disabled &&
        createPortal(
          <>
            <div className="fixed inset-0 z-[100]" onClick={close} />
            <div
              ref={menuRef}
              className="fixed z-[110] max-h-56 w-52 overflow-y-auto rounded-xl border border-white/[0.08] bg-[#14121e] py-2 shadow-xl"
              style={{ top: coords.top, right: coords.right }}
              role="listbox"
            >
              {providers.map((group) => (
                <div key={group.provider} className="px-2 py-1">
                  <p className="px-1.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-sub-dim)]" aria-hidden="true">
                    {providerLabel(group.provider)}
                  </p>
                  <div className="ml-1.5 flex flex-col gap-0.5 border-l border-white/[0.08] pl-2.5">
                    {group.models.map((m) => {
                      const active = group.provider === provider && m.id === model;
                      return (
                        <button
                          key={m.id}
                          type="button"
                          role="option"
                          aria-selected={active}
                          onClick={() => {
                            onChange(group.provider, m.id);
                            close();
                          }}
                          className={`truncate rounded-lg border px-2.5 py-1.5 text-left text-xs transition-colors ${
                            active
                              ? "border-[var(--color-accent)] bg-white/[0.06] text-[var(--color-text)]"
                              : "border-transparent text-[var(--color-sub)] hover:bg-white/[0.05] hover:text-[var(--color-text)]"
                          }`}
                        >
                          {m.id}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </>,
          document.body,
        )}
    </div>
  );
}
