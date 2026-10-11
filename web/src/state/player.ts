import { create } from "zustand";
import { fileUrl } from "../lib/api";
import type { Take } from "../lib/types";
import { machine } from "../lib/machine";

/** The one player for the whole app: a single audio element, so starting one take stops another.
 * "Listen to" swaps the source between the mix and a stem while keeping the position. */
const audio = new Audio();
audio.preload = "auto";

export type Source = "mix" | "vocals" | "drums" | "bass" | "guitar" | "piano" | "other" | "instrumental";

interface PlayerState {
  error: string | null;
  take: Take | null;
  title: string;
  source: Source;
  playing: boolean;
  duration: number;
  play: (take: Take, title: string, at?: number) => void;
  toggle: () => void;
  seek: (t: number) => void;
  listenTo: (source: Source, fresh?: Take) => void;
  stop: () => void;
}

function srcFor(take: Take, source: Source): string | null {
  if (source === "mix") return take.files ? fileUrl(take.projectId, take.files.audio) : null;
  const stem = take.analysis?.stems?.[source];
  return stem ? fileUrl(take.projectId, stem) : null;
}

export const usePlayer = create<PlayerState>((set, get) => ({
  error: null,
  take: null,
  title: "",
  source: "mix",
  playing: false,
  duration: 0,

  play(take, title, at) {
    const same = get().take?.id === take.id;
    const source = same ? get().source : "mix";
    const src = srcFor(take, source);
    if (!src) return;
    if (!same || !audio.src.endsWith(src)) {
      audio.src = src;
      audio.currentTime = at ?? 0;
    } else if (at !== undefined) {
      audio.currentTime = at;
    }
    set({ take, title, source, duration: take.duration ?? 0, error: null });
    void audio.play().catch(() => undefined); // a failure arrives as the element's error event
  },

  toggle() {
    if (!get().take) return;
    if (get().error && audio.src) {
      // try the file again (the line may have been down when it first loaded)
      const at = audio.currentTime;
      audio.load();
      audio.addEventListener("loadedmetadata", () => { audio.currentTime = at; void audio.play().catch(() => undefined); }, { once: true });
      set({ error: null });
      return;
    }
    if (audio.paused) void audio.play().catch(() => undefined);
    else audio.pause();
  },

  seek(t) {
    audio.currentTime = Math.max(0, Math.min(t, (audio.duration || get().duration) - 0.05));
  },

  listenTo(source, fresh) {
    // the caller passes the take as it is now: its stems may have arrived after it started playing
    const take = fresh ?? get().take;
    if (!take) return set({ source });
    const src = srcFor(take, source);
    if (!src) return;
    const at = audio.currentTime;
    const was = !audio.paused;
    audio.src = src;
    // the position can only be set once the new file's length is known
    audio.addEventListener("loadedmetadata", () => {
      audio.currentTime = at;
      if (was) void audio.play();
    }, { once: true });
    set({ source, take });
  },

  stop() {
    audio.pause();
    set({ playing: false });
  },
}));

audio.addEventListener("play", () => usePlayer.setState({ playing: true, error: null }));
audio.addEventListener("error", () =>
  usePlayer.setState({ playing: false, error: `This take's audio didn't load. Check the connection to ${machine()}, then press play again.` }),
);
audio.addEventListener("pause", () => usePlayer.setState({ playing: false }));
audio.addEventListener("ended", () => usePlayer.setState({ playing: false }));
audio.addEventListener("loadedmetadata", () => usePlayer.setState({ duration: audio.duration }));

/** The playhead, read every animation frame while playing (no React re-render per frame unless subscribed). */
export const clock = {
  now: () => audio.currentTime,
  paused: () => audio.paused,
  onFrame(cb: (t: number) => void): () => void {
    let raf = 0;
    const tick = () => {
      cb(audio.currentTime);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  },
};
