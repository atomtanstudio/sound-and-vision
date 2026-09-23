import { StudioProvider, useStudio } from "./context";
import { TopBar } from "./components/TopBar";
import { PlayerDock } from "./components/PlayerDock";
import { SettingsModal } from "./components/SettingsModal";
import { HomePage } from "./pages/HomePage";
import { MusicPage } from "./pages/MusicPage";
import { LibraryPage } from "./pages/LibraryPage";
import { VideoPage } from "./pages/VideoPage";
import { cn } from "./ui";

export function MusicStudio() {
  return (
    <StudioProvider>
      <Shell />
    </StudioProvider>
  );
}

function Shell() {
  const { page, toasts } = useStudio();
  return (
    <div className="app-shell">
      <div className="ambient" aria-hidden="true">
        <i className="glow glow-a" />
        <i className="glow glow-b" />
        <i className="glow glow-c" />
        <div className="grain" />
      </div>
      <TopBar />
      <main className="page" key={page}>
        {page === "home" ? <HomePage /> : null}
        {page === "music" ? <MusicPage /> : null}
        {page === "video" ? <VideoPage /> : null}
        {page === "library" ? <LibraryPage /> : null}
      </main>
      <PlayerDock />
      <SettingsModal />
      <div className="toasts" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={cn("toast", `toast-${toast.tone}`)}>
            {toast.message}
          </div>
        ))}
      </div>
    </div>
  );
}
