import { create } from "zustand";
import { useSong } from "./song";
import { useRuns } from "./runs";
import type { InfluenceRun, Job, Project, Take } from "../lib/types";

/** The live line to the server: one WebSocket for the whole window. It reconnects by itself (backing
 * off up to 10 s), and after any gap it re-reads the open song, so a take that finished while the
 * line was down never stays stuck. */

export type LineState = "connecting" | "live" | "lost";

export const useLine = create<{ state: LineState; since: number; drops: number }>(() => ({
  state: "connecting",
  since: Date.now(),
  drops: 0,
}));

let ws: WebSocket | null = null;
let wait = 1000;
let timer: number | undefined;
let everLive = false;

function open() {
  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/live`;
  ws = new WebSocket(url);
  ws.onmessage = (e) => {
    const { kind, data } = JSON.parse(e.data as string) as { kind: string; data: unknown };
    if (kind === "hello") {
      const wasLost = everLive && useLine.getState().state !== "live";
      everLive = true;
      wait = 1000;
      useLine.setState({ state: "live", since: Date.now() });
      if (wasLost) {
        void useSong.getState().resync();
        if (useRuns.getState().loaded) void useRuns.getState().load();
      }
    } else if (kind === "take") useSong.getState().onTake(data as Take);
    else if (kind === "job") {
      useSong.getState().onJob(data as Job);
      useRuns.getState().onJob(data as Job);
    } else if (kind === "influenceRun") useRuns.getState().onRun(data as InfluenceRun);
    else if (kind === "project") useSong.getState().onProject(data as Project);
    else if (kind === "influences") void useSong.getState().refreshLibrary();
  };
  ws.onclose = () => {
    ws = null;
    const s = useLine.getState();
    if (s.state !== "lost") useLine.setState({ state: "lost", since: Date.now(), drops: s.drops + 1 });
    window.clearTimeout(timer);
    timer = window.setTimeout(open, wait);
    wait = Math.min(wait * 2, 10000);
  };
}

export function connectEvents() {
  if (ws) return;
  open();
  // a laptop waking up or a tab coming back: try at once instead of waiting out the backoff
  const now = () => {
    if (useLine.getState().state !== "live" && (!ws || ws.readyState === WebSocket.CLOSED)) {
      window.clearTimeout(timer);
      wait = 1000;
      open();
    }
  };
  window.addEventListener("online", now);
  document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && now());
}
