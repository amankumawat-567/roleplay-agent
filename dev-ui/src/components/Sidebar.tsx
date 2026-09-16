import { useState } from "react";
import type { KeyboardEvent, MouseEvent, ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  Archive,
  AudioLines,
  Check,
  Compass,
  Home,
  Library,
  MessageSquare,
  PanelLeft,
  Pencil,
  Plus,
  Puzzle,
  Tag,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import { useHealthStatus } from "../hooks/useHealthStatus";
import { useStartChat } from "../hooks/useStartChat";
import { useAppStore } from "../stores/useAppStore";
import { timeAgoGroup } from "../utils/richText";
import { Logo } from "./Logo";
import type { SessionSummary } from "../types";

function NavGroup({ label, collapsed, children }: { label: string; collapsed: boolean; children: ReactNode }) {
  if (collapsed) return <div className="mt-5 flex flex-col items-center gap-1">{children}</div>;
  return (
    <div className="mt-5 px-5">
      <p className="mb-2 text-xs text-[var(--color-sub-dim)]">{label}</p>
      <div className="flex flex-col gap-0.5">{children}</div>
    </div>
  );
}

function NavItem({
  to,
  icon,
  label,
  collapsed,
  trailing,
}: {
  to: string;
  icon: ReactNode;
  label: string;
  collapsed: boolean;
  trailing?: ReactNode;
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        `flex items-center gap-2.5 rounded-xl text-left text-[13.5px] transition-all duration-150 active:scale-[0.98] ${
          collapsed ? "justify-center p-1.5" : "py-1.5 pl-1.5 pr-2.5"
        } ${isActive ? "bg-white/[0.06] text-[var(--color-text)]" : "text-[var(--color-sub)] hover:text-[var(--color-text)]"}`
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-all duration-150 ${
              isActive
                ? "bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] text-white shadow-[0_2px_10px_-2px_rgba(168,85,247,0.6)]"
                : "text-[var(--color-sub)]"
            }`}
          >
            {icon}
          </span>
          {!collapsed && <span className="truncate">{label}</span>}
          {!collapsed && trailing}
        </>
      )}
    </NavLink>
  );
}

/** Pulls the session id out of both `/chat/:sessionId` and
 * `/chat/:sessionId/voice` - a plain `slice("/chat/".length)` leaves the
 * `/voice` suffix attached on the voice route, which matches no session and
 * silently breaks anything keyed off it (see useCurrentGameId below). */
function currentSessionIdFromPath(pathname: string): string | null {
  return pathname.match(/^\/chat\/([^/]+)/)?.[1] ?? null;
}

/** The game_id of the session currently open in chat - lets "New game"
 * restart with the same persona instead of sending you to a picker. Only
 * meaningful in chat mode, but harmless to compute elsewhere. */
function useCurrentGameId(): string | null {
  const location = useLocation();
  const sessions = useAppStore((s) => s.sessions);
  const sessionId = currentSessionIdFromPath(location.pathname);
  if (!sessionId) return null;
  return sessions.find((s) => s.id === sessionId)?.game_id ?? null;
}

function NewGameButton({ collapsed }: { collapsed: boolean }) {
  const navigate = useNavigate();
  const startChat = useStartChat();
  const gameId = useCurrentGameId();
  const [starting, setStarting] = useState(false);

  async function handleClick() {
    if (!gameId) {
      navigate("/");
      return;
    }
    setStarting(true);
    try {
      await startChat(gameId);
    } finally {
      setStarting(false);
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={starting}
      title={gameId ? "Start a fresh session with this persona" : "Pick a persona to chat with"}
      className={`flex shrink-0 items-center gap-2.5 rounded-xl border border-dashed border-white/15 text-[13.5px] font-medium text-[var(--color-text)] transition-all duration-150 hover:border-white/25 hover:bg-white/[0.05] active:scale-[0.98] disabled:opacity-50 ${
        collapsed ? "justify-center p-1.5" : "py-2 pl-2 pr-3"
      }`}
    >
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] text-white">
        <Plus size={15} />
      </span>
      {!collapsed && <span className="truncate">New game</span>}
    </button>
  );
}

/** One row in RecentChats - a plain link, or (mid-rename) an inline text
 * input replacing the title in place, same interaction shape most
 * chat-history sidebars use (see docs/roadmap.md A3). */
function ChatRow({
  session,
  active,
  deleting,
  archiving,
  onDelete,
  onArchive,
}: {
  session: SessionSummary;
  active: boolean;
  deleting: boolean;
  archiving: boolean;
  onDelete: (e: MouseEvent) => void;
  onArchive: (e: MouseEvent) => void;
}) {
  const renameSession = useAppStore((s) => s.renameSession);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(session.title);
  const [saving, setSaving] = useState(false);

  function startRename(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDraft(session.title);
    setRenaming(true);
  }

  function cancelRename(e: MouseEvent | KeyboardEvent) {
    e.preventDefault();
    e.stopPropagation();
    setRenaming(false);
  }

  async function commitRename(e: MouseEvent | KeyboardEvent) {
    e.preventDefault();
    e.stopPropagation();
    const title = draft.trim();
    if (!title || title === session.title) {
      setRenaming(false);
      return;
    }
    setSaving(true);
    try {
      await renameSession(session.id, title);
      setRenaming(false);
    } finally {
      setSaving(false);
    }
  }

  if (renaming) {
    return (
      <div className="flex items-center gap-1 rounded-xl py-1 pl-2.5 pr-1.5">
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename(e);
            if (e.key === "Escape") cancelRename(e);
          }}
          disabled={saving}
          className="min-w-0 flex-1 rounded-lg border border-white/15 bg-white/[0.06] px-1.5 py-0.5 text-[13px] text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
        />
        <button
          onClick={commitRename}
          disabled={saving}
          title="Save"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[var(--color-sub-dim)] transition-colors hover:bg-white/[0.08] hover:text-[var(--color-text)] disabled:opacity-50"
        >
          <Check size={12} />
        </button>
        <button
          onClick={cancelRename}
          disabled={saving}
          title="Cancel"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[var(--color-sub-dim)] transition-colors hover:bg-white/[0.08] hover:text-[var(--color-text)] disabled:opacity-50"
        >
          <X size={12} />
        </button>
      </div>
    );
  }

  return (
    <Link
      to={`/chat/${session.id}`}
      title={session.title}
      className={`group flex items-center gap-2 rounded-xl py-1.5 pl-2.5 pr-1.5 text-[13px] transition-colors duration-150 ${
        active
          ? "bg-white/[0.06] text-[var(--color-text)]"
          : "text-[var(--color-sub)] hover:bg-white/[0.04] hover:text-[var(--color-text)]"
      }`}
    >
      <span className="min-w-0 flex-1 truncate">{session.title}</span>
      <span className="flex shrink-0 items-center gap-0.5 opacity-0 transition-all duration-150 group-hover:opacity-100">
        <button
          onClick={startRename}
          title="Rename chat"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[var(--color-sub-dim)] transition-all duration-150 hover:bg-white/[0.08] hover:text-[var(--color-text)]"
        >
          <Pencil size={12} />
        </button>
        <button
          onClick={onArchive}
          disabled={archiving}
          title="Archive chat"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[var(--color-sub-dim)] transition-all duration-150 hover:bg-white/[0.08] hover:text-[var(--color-text)] disabled:opacity-50"
        >
          <Archive size={12} />
        </button>
        <button
          onClick={onDelete}
          disabled={deleting}
          title="Delete chat"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[var(--color-sub-dim)] transition-all duration-150 hover:bg-rose-500/15 hover:text-rose-400 disabled:opacity-50"
        >
          <Trash2 size={12} />
        </button>
      </span>
    </Link>
  );
}

/** Groups the *current persona's* sessions (Library already covers "browse
 * everything across every persona" - see docs/roadmap.md A1) into
 * Today/Yesterday/Earlier buckets, most recent first within each - the
 * same shape a ChatGPT/Claude-style sidebar history list uses. Each row
 * reveals rename/archive/delete on hover; archiving or deleting the
 * session that's currently open kicks the user back to Library rather
 * than leaving them stranded on a chat page whose session no longer
 * shows up here (see docs/roadmap.md A4 - archived sessions live on in
 * the Archives view, just not in this list). */
function RecentChats({ collapsed }: { collapsed: boolean }) {
  const sessions = useAppStore((s) => s.sessions);
  const deleteSession = useAppStore((s) => s.deleteSession);
  const archiveSession = useAppStore((s) => s.archiveSession);
  const location = useLocation();
  const navigate = useNavigate();
  const currentGameId = useCurrentGameId();
  const activeId = currentSessionIdFromPath(location.pathname);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [archivingId, setArchivingId] = useState<string | null>(null);

  const scoped = currentGameId ? sessions.filter((s) => s.game_id === currentGameId) : sessions;
  const groups: { label: string; items: SessionSummary[] }[] = [];
  for (const session of [...scoped].sort((a, b) => b.created_at - a.created_at)) {
    const label = timeAgoGroup(session.created_at);
    const group = groups.find((g) => g.label === label);
    if (group) group.items.push(session);
    else groups.push({ label, items: [session] });
  }

  async function handleDelete(session: SessionSummary, e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm(`Delete "${session.title}"? This can't be undone.`)) return;
    setDeletingId(session.id);
    try {
      await deleteSession(session.id);
      if (activeId === session.id) navigate("/library");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleArchive(session: SessionSummary, e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setArchivingId(session.id);
    try {
      await archiveSession(session.id);
      if (activeId === session.id) navigate("/library");
    } finally {
      setArchivingId(null);
    }
  }

  return (
    <div className="mt-5 flex min-h-0 flex-1 flex-col px-5">
      {!collapsed && groups.length > 0 && (
        <>
          <p className="mb-2 text-xs text-[var(--color-sub-dim)]">Recent chats</p>
          <div className="no-scrollbar flex-1 space-y-3 overflow-y-auto pb-2">
            {groups.map((group) => (
              <div key={group.label}>
                <p className="mb-1 px-1.5 text-[10px] font-medium uppercase tracking-wide text-[var(--color-sub-dim)]/70">
                  {group.label}
                </p>
                <div className="flex flex-col gap-0.5">
                  {group.items.map((session) => (
                    <ChatRow
                      key={session.id}
                      session={session}
                      active={activeId === session.id}
                      deleting={deletingId === session.id}
                      archiving={archivingId === session.id}
                      onDelete={(e) => handleDelete(session, e)}
                      onArchive={(e) => handleArchive(session, e)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const health = useHealthStatus();
  const healthDotClass =
    health === "online" ? "bg-emerald-400" : health === "offline" ? "bg-rose-400" : "bg-amber-400";
  const isChatMode = location.pathname.startsWith("/chat/");

  return (
    <aside
      className={`relative z-10 flex h-full shrink-0 flex-col bg-[var(--color-bg-soft)] transition-[width] duration-200 ${
        collapsed ? "w-[76px]" : "w-64"
      }`}
    >
      <div className={`flex items-center pt-5 ${collapsed ? "flex-col gap-3 px-3" : "justify-between px-5"}`}>
        <NavLink to="/" className="relative flex items-center gap-2.5">
          <div className="relative flex h-8 w-8 shrink-0 items-center justify-center">
            <Logo size={30} />
            <span
              title="Backend status"
              className={`absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full ring-2 ring-[var(--color-bg-soft)] ${healthDotClass}`}
            />
          </div>
          {!collapsed && <span className="text-[17px] font-bold tracking-tight">Roleplay</span>}
        </NavLink>
        <button
          onClick={() => setCollapsed((v) => !v)}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[var(--color-sub-dim)] transition-colors hover:text-[var(--color-text)]"
        >
          <PanelLeft size={15} />
        </button>
      </div>

      {isChatMode ? (
        <>
          <div className={collapsed ? "mt-5 flex flex-col items-center gap-2" : "mt-5 flex flex-col gap-2 px-5"}>
            <NewGameButton collapsed={collapsed} />
            <NavItem to="/library" icon={<Library size={15} />} label="Library" collapsed={collapsed} />
            <NavItem to="/archives" icon={<Archive size={15} />} label="Archives" collapsed={collapsed} />
          </div>
          <RecentChats collapsed={collapsed} />
        </>
      ) : (
        <>
          <div className={collapsed ? "mt-5 flex flex-col items-center" : "mt-5 px-5"}>
            <NavItem to="/" icon={<Home size={15} />} label="Home" collapsed={collapsed} />
          </div>

          <NavGroup label="Discover" collapsed={collapsed}>
            <NavItem to="/explore" icon={<Compass size={15} />} label="Explore" collapsed={collapsed} />
            <NavItem to="/library" icon={<Library size={15} />} label="Library" collapsed={collapsed} />
            <NavItem to="/archives" icon={<Archive size={15} />} label="Archives" collapsed={collapsed} />
            <NavItem to="/tags" icon={<Tag size={15} />} label="Tags" collapsed={collapsed} />
          </NavGroup>

          <NavGroup label="Create" collapsed={collapsed}>
            <NavItem to="/studio" icon={<Wand2 size={15} />} label="Studio" collapsed={collapsed} />
            <NavItem to="/skills" icon={<Puzzle size={15} />} label="Skills" collapsed={collapsed} />
            <NavItem to="/audio" icon={<AudioLines size={15} />} label="Audio" collapsed={collapsed} />
          </NavGroup>

          <div className="flex-1" />
        </>
      )}

      <div className={collapsed ? "flex flex-col items-center gap-1 pb-3" : "flex flex-col gap-0.5 px-5 pb-3"}>
        <span
          title="Coming soon"
          className={`flex items-center gap-2.5 text-[13.5px] text-[var(--color-sub)] ${collapsed ? "justify-center p-1.5" : "py-1.5"}`}
        >
          <MessageSquare size={15} className="shrink-0" />
          {!collapsed && <span className="truncate">Feedback</span>}
        </span>
      </div>
    </aside>
  );
}
