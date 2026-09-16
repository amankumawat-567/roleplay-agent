import { useEffect } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { HomePage } from "./pages/HomePage";
import { ChatPage } from "./pages/ChatPage";
import { VoiceCallPage } from "./pages/VoiceCallPage";
import { GameEditorPage } from "./pages/GameEditorPage";
import { GameBuilderPage } from "./pages/GameBuilderPage";
import { TranscriptImportPage } from "./pages/TranscriptImportPage";
import { ExplorePage } from "./pages/ExplorePage";
import { LibraryPage } from "./pages/LibraryPage";
import { ArchivesPage } from "./pages/ArchivesPage";
import { StudioPage } from "./pages/StudioPage";
import { TagsPage } from "./pages/TagsPage";
import { SkillsPage } from "./pages/SkillsPage";
import { AudioPage } from "./pages/AudioPage";
import { ProfilePage } from "./pages/ProfilePage";
import { useAppStore } from "./stores/useAppStore";

export default function App() {
  const loadAll = useAppStore((s) => s.loadAll);
  const location = useLocation();

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  return (
    <div className="relative flex h-screen w-screen overflow-hidden bg-[var(--color-bg)] text-[var(--color-text)]">
      <div className="bg-grain pointer-events-none fixed inset-0 z-50" />
      <Sidebar />
      {/* @container: establishes a CSS container-query context sized to
          this element's own actual width (viewport minus the sidebar's
          current width) - pages with a master-detail layout (Skills,
          Audio) key their detail rail's visibility off this via @5xl:,
          not a viewport media query, so it reacts live as the sidebar
          collapses/expands instead of only ever seeing total viewport
          width. */}
      <main className="@container flex flex-1 flex-col overflow-hidden">
        <div key={location.pathname} className="animate-fade-up flex flex-1 flex-col overflow-hidden">
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
            <Route path="/profile" element={<ProfilePage />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
