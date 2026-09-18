import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { X, Home, Compass, Library, Archive, Tag, Wand2, Puzzle, AudioLines, Settings } from "lucide-react";
import { ProfileAvatar } from "./ProfileAvatar";

const MOBILE_BREAKPOINT = 1024; // lg breakpoint

interface MobileDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export function MobileDrawer({ isOpen, onClose }: MobileDrawerProps) {
  const location = useLocation();
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    function checkMobile() {
      setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    }
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  useEffect(() => {
    onClose();
  }, [location.pathname, onClose]);

  if (!isMobile) return null;

  const navItems = [
    { to: "/", icon: Home, label: "Home" },
    { to: "/explore", icon: Compass, label: "Explore" },
    { to: "/library", icon: Library, label: "Library" },
    { to: "/archives", icon: Archive, label: "Archives" },
    { to: "/tags", icon: Tag, label: "Tags" },
    { to: "/studio", icon: Wand2, label: "Studio" },
    { to: "/skills", icon: Puzzle, label: "Skills" },
    { to: "/audio", icon: AudioLines, label: "Audio" },
    { to: "/profile#settings", icon: Settings, label: "Settings" },
  ];

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside
        className={`fixed inset-y-0 right-0 z-50 w-[280px] max-w-full bg-[var(--color-bg-soft)] shadow-[0_30px_60px_-20px_rgba(0,0,0,0.8)] transform transition-transform duration-300 ease-[var(--ease-out-expo)] lg:hidden ${isOpen ? "translate-x-0" : "translate-x-full"}`}
        role="navigation"
        aria-label="Mobile navigation"
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between px-4 pt-4 pb-3 border-b border-[var(--color-border)]">
            <Link to="/" className="flex items-center gap-2" onClick={onClose}>
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)]">
                <span className="text-white font-bold text-lg">R</span>
              </div>
              <span className="font-heading text-lg font-bold tracking-tight">Roleplay</span>
            </Link>
            <button
              onClick={onClose}
              className="flex h-10 w-10 items-center justify-center rounded-lg text-[var(--color-sub)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-text)]"
              aria-label="Close menu"
            >
              <X size={20} />
            </button>
          </div>

          <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1" role="list">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname.startsWith(item.to.split("#")[0]) && item.to !== "/";
              const isHomeActive = location.pathname === "/" && item.to === "/";
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  onClick={onClose}
                  role="listitem"
                  className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-base transition-colors ${
                    isActive || isHomeActive
                      ? "bg-white/[0.06] text-[var(--color-text)]"
                      : "text-[var(--color-sub)] hover:bg-white/[0.04] hover:text-[var(--color-text)]"
                  }`}
                >
                  <Icon size={20} className="shrink-0" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          <div className="border-t border-[var(--color-border)] p-4">
            <ProfileAvatar size={40} ringClassName="ring-sky-400/60" />
          </div>
        </div>
      </aside>
    </>
  );
}