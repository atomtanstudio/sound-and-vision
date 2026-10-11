import { useEffect, useState } from "react";
import { Wordmark } from "../brand/Wordmark";
import { api } from "../lib/api";
import { linkTo, usePath } from "../lib/router";
import { useLine } from "../state/events";
import { ThemeToggle } from "../ui/ThemeToggle";
import { Settings } from "./Settings";
import { settingsChanged } from "../lib/pictures";
import "./topbar.css";
import { Machine, machine } from "../lib/machine";
import { useWho } from "../state/who";

const TABS = [
  { path: "/", label: "Home" },
  { path: "/music", label: "Music" },
  { path: "/video", label: "Video" },
  { path: "/influences", label: "Influence Engine" },
  { path: "/library", label: "Library" },
  { path: "/share", label: "Share" },
];

interface Working { id: string; kind: string; status: "running" | "queued"; message: string; projectId?: string | null; title: string }
interface Health {
  comfy: { ok: boolean; busy?: boolean; slow?: boolean; vramFreeMiB?: number; vramTotalMiB?: number; error?: string };
  queue: number;
  working?: Working[];
}

/** What a job is, in a few words. */
function whatItIs(kind: string): string {
  if (kind.startsWith("song.import")) return "Bringing in a song";
  if (kind === "quick") return "Writing a song";
  if (kind === "title") return "Naming a song";
  if (kind === "share.clip") return "A clip to share";
  if (kind.startsWith("song.")) return "Singing a song";
  if (kind === "analysis") return "Listening to a song";
  if (kind.startsWith("cover.")) return "Painting a cover";
  if (kind.startsWith("living.")) return "Living Album Cover";
  if (kind === "kinetic.film") return "Motion Graphics film";
  if (kind === "music.film") return "Music video";
  if (kind.startsWith("influence")) return "Influence Engine";
  return "Working";
}
function whereItIs(w: Working): string | null {
  if (!w.projectId) return w.kind.startsWith("influence") ? "/influences" : null;
  if (w.kind === "kinetic.film") return `/video/${w.projectId}?kind=kinetic`;
  if (w.kind === "music.film") return `/video/${w.projectId}?kind=music`;
  if (w.kind.startsWith("living.")) return `/video/${w.projectId}`;
  if (w.kind === "share.clip") return "/share";
  return `/music/${w.projectId}`;
}

/** The server's state, checked every 15 s: green when the GPU server answers, with the queue length. */
function useHealth() {
  const [h, setH] = useState<Health | null>(null);
  const [down, setDown] = useState(false);
  useEffect(() => {
    let live = true;
    let id = 0;
    const tick = () =>
      api.get<Health>("/api/health").then((x) => {
        if (!live) return;
        setH(x);
        setDown(false);
        // every 5 s while something's being made, so the light follows the work; every 15 s otherwise
        window.clearTimeout(id);
        id = window.setTimeout(tick, x.working?.some((w) => w.status === "running") ? 5000 : 15000);
      }).catch(() => {
        if (!live) return;
        setDown(true);
        window.clearTimeout(id);
        id = window.setTimeout(tick, 15000);
      });
    tick();
    return () => {
      live = false;
      window.clearTimeout(id);
    };
  }, []);
  return { h, down };
}

export function TopBar() {
  const path = usePath();
  const { h, down } = useHealth();
  const [settings, setSettings] = useState(false);
  useEffect(() => {  // "Change in Settings", from a panel that shows a choice made there
    const show = () => setSettings(true);
    window.addEventListener("sv-open-settings", show);
    return () => window.removeEventListener("sv-open-settings", show);
  }, []);
  const [open, setOpen] = useState(false);
  const line = useLine((s) => s.state);
  const unreachable = down || line === "lost";
  const working = h?.working ?? [];
  const running = working.filter((w) => w.status === "running");
  const tone = unreachable ? "down" : !h ? "" : !h.comfy.ok ? "down" : running.length || h.comfy.busy ? "work" : "ok";
  const gb = (m?: number) => Math.round((m ?? 0) / 1024);
  const label = unreachable ? `Can't reach ${machine()} right now (reconnecting)` : !h ? `Checking ${machine()}…` :
    !h.comfy.ok ? `${Machine()} is up, but its ComfyUI isn't answering` :
    tone === "work" ? `${Machine()} is making ${running.length === 1 ? "something" : `${running.length} things`}` +
      (h.queue > running.length ? ` · ${h.queue - running.length} waiting` : "") + " (click to see what)" :
    `${Machine()} ready · ${gb(h.comfy.vramFreeMiB)} of ${gb(h.comfy.vramTotalMiB)} GB free` + (h.queue ? ` · ${h.queue} waiting` : "");
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!(e.target as HTMLElement).closest(".tb-statuswrap")) setOpen(false); };
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [open]);
  return (
    <header className="tb">
      <a className="tb-home" {...linkTo("/")} aria-label="Sound / Vision home">
        <Wordmark size={19} animate />
      </a>
      <nav className="tb-nav" aria-label="Main">
        {TABS.map((t) => (
          <a key={t.path} className="tb-link" aria-current={(t.path === "/" ? path === "/" : path.startsWith(t.path) ||
            (t.path === "/music" && path.startsWith("/song")) || (t.path === "/share" && path.startsWith("/brand"))) ? "page" : undefined}
            {...linkTo(t.path)}>
            {t.label}
          </a>
        ))}
      </nav>
      <div className="tb-right">
        <span className="tb-statuswrap">
          <button type="button" className={"tb-status" + (tone ? ` tb-${tone}` : "")} title={label} aria-label={label}
            aria-expanded={working.length ? open : undefined} onClick={() => working.length && setOpen(!open)}>
            {tone === "work" ? (
              <span className="tb-eq" aria-hidden="true"><i /><i /><i /></span>
            ) : <span className="tb-dot" />}
            {tone === "work" ? "Working" : Machine()}
            {h?.queue ? <span className="tb-q">{h.queue}</span> : null}
          </button>
          {open && working.length > 0 && (
            <div className="tb-jobs" role="dialog" aria-label={`What ${machine()} is making`}>
              <strong>{Machine()} is making</strong>
              {working.map((w) => {
                const href = whereItIs(w);
                const body = (
                  <>
                    <span className={"tb-work-dot" + (w.status === "running" ? " on" : "")} />
                    <span className="tb-work-text">
                      <b>{whatItIs(w.kind)}{w.title ? ` · ${w.title}` : ""}</b>
                      <span>{w.status === "running" ? (w.message || "Working") : "Waiting its turn"}</span>
                    </span>
                  </>
                );
                return href ? <a key={w.id} className="tb-work-row" {...linkTo(href, () => setOpen(false))}>{body}</a> :
                  <div key={w.id} className="tb-work-row">{body}</div>;
              })}
            </div>
          )}
        </span>
        <ThemeToggle />
        <button className="tb-icon" type="button" aria-label="Settings" title="Settings" onClick={() => setSettings(true)}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
          </svg>
        </button>
      </div>
      {settings && <Settings onClose={() => { setSettings(false); void useWho.getState().load(); settingsChanged(); }} />}
    </header>
  );
}
