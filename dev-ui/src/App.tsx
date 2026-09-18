import { useEffect, Suspense, lazy, useState } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { List } from "lucide-react";
import { Sidebar } from "./components/Sidebar";
import { HomePage } from "./pages/HomePage";
import { useAppStore } from "./stores/useAppStore";
import { MobileDrawer } from "./components/MobileDrawer";
import { SkipLink } from "./components/SkipLink";
import { Logo } from "./components/Logo";

const ChatPage = lazy(() => import("./pages/ChatPage").then(m => ({ default: m.ChatPage })));
const VoiceCallPage = lazy(() => import("./pages/VoiceCallPage").then(m => ({ default: m.VoiceCallPage })));
const GameEditorPage = lazy(() => import("./pages/GameEditorPage").then(m => ({ default: m.GameEditorPage })));
const GameBuilderPage = lazy(() => import("./pages/GameBuilderPage").then(m => ({ default: m.GameBuilderPage })));
const TranscriptImportPage = lazy(() => import("./pages/TranscriptImportPage").then(m => ({ default: m.TranscriptImportPage })));
const ExplorePage = lazy(() => import("./pages/ExplorePage").then(m => ({ default: m.ExplorePage })));
const LibraryPage = lazy(() => import("./pages/LibraryPage").then(m => ({ default: m.LibraryPage })));
const ArchivesPage = lazy(() => import("./pages/ArchivesPage").then(m => ({ default: m.ArchivesPage })));
const StudioPage = lazy(() => import("./pages/StudioPage").then(m => ({ default: m.StudioPage })));
const TagsPage = lazy(() => import("./pages/TagsPage").then(m => ({ default: m.TagsPage })));
const SkillsPage = lazy(() => import("./pages/SkillsPage").then(m => ({ default: m.SkillsPage })));
const AudioPage = lazy(() => import("./pages/AudioPage").then(m => ({ default: m.AudioPage })));
const AudioCreatePage = lazy(() => import("./pages/AudioCreatePage").then(m => ({ default: m.AudioCreatePage })));
const ProfilePage = lazy(() => import("./pages/ProfilePage").then(m => ({ default: m.ProfilePage })));

function LoadingFallback() {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <div className="animate-shimmer h-14 w-2/3 rounded-2xl" />
    </div>
  );
}

export default function App() {
  const loadAll = useAppStore((s) => s.loadAll);
  const location = useLocation();
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    setMobileDrawerOpen(false);
  }, [location.pathname]);

  return (
    <div className="relative flex h-screen w-screen bg-[var(--color-bg)] text-[var(--color-text)]">
      <SkipLink />
      <div className="bg-grain pointer-events-none fixed inset-0 z-50" />
      <Sidebar setMobileDrawerOpen={setMobileDrawerOpen} />
      <MobileDrawer isOpen={mobileDrawerOpen} onClose={() => setMobileDrawerOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {!location.pathname.startsWith("/chat/") && (
          <header className="flex shrink-0 items-center justify-between border-b border-[var(--color-border-soft)] px-4 py-3 lg:hidden">
            <span className="flex items-center gap-2">
              <Logo size={26} />
              <span className="font-heading text-[15px] font-bold tracking-tight">Roleplay</span>
            </span>
            <button
              onClick={() => setMobileDrawerOpen(true)}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-[var(--color-sub-dim)] transition-colors hover:text-[var(--color-text)]"
              aria-label="Open menu"
              aria-expanded={mobileDrawerOpen}
            >
              <List size={20} />
            </button>
          </header>
        )}
        {/* @container: establishes a CSS container-query context sized to
            this element's own actual width (viewport minus the sidebar's
            current width) - pages with a master/detail layout (Skills,
            Audio) key their detail rail's visibility off this via @5xl:,
            not a viewport media query, so it reacts live as the sidebar
            collapses/expands instead of only ever seeing total viewport
            width. */}
        <main id="main-content" className="@container flex flex-1 flex-col overflow-hidden min-w-0">
          <Suspense fallback={<LoadingFallback />}>
            <Routes location={location}>
              <Route path="/" element={<HomePage />} />
              <Route path="/chat/:sessionId" element={<ChatPage />} />
              <Route path="/chat/:sessionId/voice" element={<VoiceCallPage />} />
              <Route path="/games/new" element={<GameEditorPage />} />
              <Route path="/games/:gameId/edit" element={<GameEditorPage />} />
              <Route path="/games/builder" element={<GameBuilderPage />} />
              <Route path="/games/from-transcript" element={<TranscriptImportPage />} />
              <Route path="/explore" element={<ExplorePage />} />
              <Route path="/library" element={<LibraryPage />} />
              <Route path="/archives" element={<ArchivesPage />} />
              <Route path="/studio" element={<StudioPage />} />
              <Route path="/tags" element={<TagsPage />} />
              <Route path="/skills" element={<SkillsPage />} />
              <Route path="/audio" element={<AudioPage />} />
              <Route path="/audio/new" element={<AudioCreatePage />} />
              <Route path="/profile" element={<ProfilePage />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  );
}
