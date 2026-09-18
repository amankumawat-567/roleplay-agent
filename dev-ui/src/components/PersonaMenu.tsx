import { useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { Copy, MoreVertical, Pencil, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { api } from "../services/api";
import { useAppStore } from "../stores/useAppStore";

const menuItemClass =
  "flex items-center gap-2 px-3 py-2 text-left text-xs text-[var(--color-sub)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-text)] disabled:cursor-not-allowed disabled:opacity-40";

interface PersonaMenuProps {
  // Only `id` is ever used below - a narrower shape than the full Game so
  // any list-level type with an id (LibraryEntry included) can be passed
  // straight through without carrying fields this menu never touches.
  game: { id: string };
  /** Called after a successful delete, on top of the list refresh every
   * call site gets for free - ChatPage uses this to navigate away from the
   * now-gone persona's chat (see docs/ARCHITECTURE.md's "manage this
   * persona" menu). */
  onDeleted?: () => void;
  /** Overrides the trigger button's own chrome - each surface (a card's
   * corner icon, ChatPage's header) matches its own existing style. */
  triggerClassName?: string;
  iconSize?: number;
}

/** The one shared "manage this persona" control (docs/ARCHITECTURE.md,
 * originally roadmap section B) - Edit / Edit with AI / Duplicate /
 * Refresh research / Delete, reused across GameCard, GameTile, and
 * ChatPage's header instead of each surface reinventing its own hover
 * icons. */
export function PersonaMenu({ game, onDeleted, triggerClassName, iconSize = 14 }: PersonaMenuProps) {
  const navigate = useNavigate();
  const loadAll = useAppStore((s) => s.loadAll);
  const researching = useAppStore((s) => s.researchingGameId === game.id);
  const refreshResearch = useAppStore((s) => s.refreshResearch);

  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const [busy, setBusy] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function close() {
    setOpen(false);
    setConfirmingDelete(false);
    setError(null);
    triggerRef.current?.focus();
  }

  function toggle(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (open) {
      close();
      return;
    }
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) setCoords({ top: rect.bottom + 6, left: Math.max(8, rect.right - 200) });
    setOpen(true);
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
    // Focus first menu item
    setTimeout(() => {
      const firstItem = menuRef.current?.querySelector('button[type="button"]') as HTMLElement;
      firstItem?.focus();
    }, 0);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  function handleEdit(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    close();
    navigate(`/games/${game.id}/edit`);
  }

  async function handleEditWithAi(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setBusy(true);
    try {
      const detail = await api.getGame(game.id);
      navigate("/games/builder", {
        state: {
          gameId: game.id,
          existingGame: {
            title: detail.title,
            tags: detail.tags.join(", "),
            persona: detail.persona,
            user_role: detail.user_role,
            script: detail.script,
            research_query: detail.research_query,
          },
        },
      });
      close();
    } catch {
      setError("Failed to load this persona");
      setBusy(false);
    }
  }

  async function handleDuplicate(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setBusy(true);
    try {
      const detail = await api.getGame(game.id);
      navigate("/games/new", {
        state: {
          draft: {
            title: `${detail.title} (copy)`,
            character_name: detail.character_name,
            tags: detail.tags,
            provider: detail.provider,
            model: detail.model,
            starter: detail.starter,
            persona: detail.persona,
            user_role: detail.user_role,
            script: detail.script,
            research_query: detail.research_query,
            num_ctx: detail.num_ctx,
            memory_recall: detail.memory_recall,
            skills: detail.skills,
            voice: detail.voice,
          },
        },
      });
      close();
    } catch {
      setError("Failed to load this persona");
      setBusy(false);
    }
  }

  function handleResearch(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    refreshResearch(game.id);
    close();
  }

  async function handleDelete(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirmingDelete) {
      setConfirmingDelete(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.deleteGame(game.id);
      await loadAll();
      setOpen(false);
      setConfirmingDelete(false);
      onDeleted?.();
    } catch {
      setError("Failed to delete this persona");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative inline-flex" onClick={(e) => e.stopPropagation()}>
      <button
        ref={triggerRef}
        type="button"
        onClick={toggle}
        aria-label="Manage this persona"
        aria-expanded={open}
        aria-haspopup="menu"
        className={
          triggerClassName ??
          "flex h-7 w-7 items-center justify-center rounded-full text-[var(--color-sub)] transition hover:bg-white/[0.08] hover:text-[var(--color-text)]"
        }
      >
        <MoreVertical size={iconSize} />
      </button>
      {open &&
        createPortal(
          <>
            <div className="fixed inset-0 z-[100]" onClick={close} />
            <div
              ref={menuRef}
              className="fixed z-[110] flex w-48 flex-col overflow-hidden rounded-xl border border-white/[0.08] bg-[#14121e] py-1 shadow-xl"
              style={{ top: coords.top, left: coords.left }}
              role="menu"
            >
              <button
                type="button"
                role="menuitem"
                onClick={handleEdit}
                className={menuItemClass}
              >
                <Pencil size={13} aria-hidden="true" /> Edit
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={handleEditWithAi}
                disabled={busy}
                className={menuItemClass}
              >
                <Sparkles size={13} aria-hidden="true" /> Edit with AI
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={handleDuplicate}
                disabled={busy}
                className={menuItemClass}
              >
                <Copy size={13} aria-hidden="true" /> Duplicate
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={handleResearch}
                className={menuItemClass}
              >
                <RefreshCw size={13} className={researching ? "animate-spin" : ""} aria-hidden="true" /> Refresh research
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={handleDelete}
                disabled={busy}
                className={`${menuItemClass} text-rose-400 hover:bg-rose-500/10 hover:text-rose-300`}
              >
                <Trash2 size={13} aria-hidden="true" /> {confirmingDelete ? "Confirm delete?" : "Delete"}
              </button>
              {error && <p className="px-3 py-1.5 text-[11px] text-rose-400">{error}</p>}
            </div>
          </>,
          document.body,
        )}
    </div>
  );
}
