import { Home, Moon, Settings2, Sun, Video, Disc3, ListMusic } from "lucide-react";
import { useStudio } from "../context";
import { cn, IconBtn } from "../ui";
import type { Page } from "../../music-studio/model";

const nav: { page: Page; label: string; icon: typeof Home }[] = [
  { page: "home", label: "Home", icon: Home },
  { page: "music", label: "Music", icon: Disc3 },
  { page: "video", label: "Video", icon: Video },
  { page: "library", label: "Library", icon: ListMusic },
];

export function TopBar() {
  const { page, navigate, online, status, theme, setTheme, setSettingsOpen } =
    useStudio();
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <button
          className="wordmark"
          onClick={() => navigate("home")}
          aria-label="Sound Vision home"
        >
          <span className="wordmark-sound">SOUND</span>
          <span className="wordmark-vision">vision</span>
        </button>
        <nav className="mainnav" aria-label="Primary">
          {nav.map(({ page: target, label, icon: Icon }) => (
            <button
              key={target}
              className={cn("mainnav-item", page === target && "on")}
              onClick={() => navigate(target)}
            >
              <Icon size={15} strokeWidth={1.9} aria-hidden="true" />
              {label}
            </button>
          ))}
        </nav>
        <div className="topbar-right">
          <span
            className={cn("engine-chip", online ? "live" : "off")}
            title={
              online
                ? `${status?.model || "engine"} connected`
                : "Engine offline — demo mode"
            }
          >
            <i aria-hidden="true" />
            {online ? "Engine live" : "Offline"}
          </span>
          <IconBtn
            label={theme === "dark" ? "Switch to daylight" : "Switch to midnight"}
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </IconBtn>
          <IconBtn label="AI setup" onClick={() => setSettingsOpen(true)}>
            <Settings2 size={16} />
          </IconBtn>
        </div>
      </div>
    </header>
  );
}
