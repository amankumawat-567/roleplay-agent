import { Gamepad2 } from "lucide-react";
import { useAppStore } from "../stores/useAppStore";
import { ProfileAvatar } from "./ProfileAvatar";

/** The games-count badge + user avatar shown top-right of a content page
 * (Home, Library, ...). Absolutely positioned within the page's own
 * `relative` container, so it stays anchored to that container's actual
 * top-right corner - and therefore reflows correctly - as the sidebar
 * collapses/expands and the container resizes, with no extra handling. */
export function TopBar() {
  const games = useAppStore((s) => s.games);

  return (
    <div className="animate-fade-up absolute right-6 top-6 z-10 flex items-center gap-3">
      <span className="flex items-center gap-1.5 rounded-full border border-white/[0.06] bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-[var(--color-sub)] backdrop-blur-md">
        <Gamepad2 size={13} />
        {games.length} Games
      </span>
      <ProfileAvatar size={34} />
    </div>
  );
}
