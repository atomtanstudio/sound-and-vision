/** Music Studio — global studio state: routing, engine health, library polling,
 * the single shared player, theme and toasts. Data contracts mirror the legacy
 * app exactly (same endpoints, same localStorage keys) so work carries over. */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { request, type BackendStatus } from "../music-studio/api";
import {
  initialTracks,
  pageFromPath,
  readLocal,
  uniqueTracks,
  writeLocal,
  type Page,
  type Track,
} from "../music-studio/model";

export function mediaUrl(
  track: Track,
  format: "mp3" | "wav" | "flac" = "mp3",
): string | null {
  if (!track.source)
    return track.audio
      ? `/media/desert-afterglow-${track.audio}.${format}`
      : null;
  return `/api/takes/${track.id}/files/audio.${format}`;
}
export const playable = (track: Track) =>
  !!mediaUrl(track) && (!track.status || track.status === "succeeded");
export const timeLabel = (seconds: number) => {
  if (!Number.isFinite(seconds) || seconds < 0) return "–:––";
  const m = Math.floor(seconds / 60),
    s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
};

export type Toast = { id: number; message: string; tone: "ok" | "err" };
type StudioValue = {
  page: Page;
  navigate: (page: Page) => void;
  status: BackendStatus | null;
  online: boolean;
  tracks: Track[];
  refresh: () => void;
  upsertLocal: (tracks: Track[]) => void;
  patchTrack: (id: string, patch: Partial<Track>) => void;
  removeLocal: (id: string) => void;
  audioRef: RefObject<HTMLAudioElement | null>;
  current: string | null;
  currentTrack: Track | null;
  playing: boolean;
  progress: number;
  duration: number;
  volume: number;
  setVolume: (v: number) => void;
  playTrack: (track: Track) => void;
  toggle: () => void;
  seek: (seconds: number) => void;
  step: (delta: number) => void;
  videoSource: string | null;
  setVideoSource: (id: string | null) => void;
  makeVideo: (track: Track) => void;
  theme: "dark" | "light";
  setTheme: (t: "dark" | "light") => void;
  toasts: Toast[];
  pushToast: (message: string, tone?: Toast["tone"]) => void;
  settingsOpen: boolean;
  setSettingsOpen: (open: boolean) => void;
};
const StudioContext = createContext<StudioValue | null>(null);
export const useStudio = () => {
  const value = useContext(StudioContext);
  if (!value) throw Error("useStudio must run inside StudioProvider");
  return value;
};

export function StudioProvider({ children }: { children: ReactNode }) {
  const [page, setPage] = useState<Page>(() =>
    pageFromPath(window.location.pathname),
  );
  const [status, setStatus] = useState<BackendStatus | null>(null);
  const [serverTracks, setServerTracks] = useState<Track[]>([]);
  const [localTracks, setLocalTracks] = useState<Track[]>(() =>
    readLocal<Track[]>("sv-library-v2", []),
  );
  const [current, setCurrent] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolumeState] = useState(() =>
    readLocal<number>("sv-volume", 0.8),
  );
  const [videoSource, setVideoSourceState] = useState<string | null>(() =>
    readLocal<string | null>("sv-video-source-v1", null),
  );
  const [theme, setThemeState] = useState<"dark" | "light">(() =>
    readLocal<"dark" | "light">("sv-studio-theme", readLocal<"dark" | "light">("sv-nova-theme", "dark")),
  );
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [tick, setTick] = useState(0);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  if (!audioRef.current) audioRef.current = new Audio();

  /* ------------------------------------------------------------ routing */
  const navigate = useCallback((next: Page) => {
    window.history.pushState({}, "", `/${next}`);
    setPage(next);
  }, []);
  useEffect(() => {
    const onPop = () => setPage(pageFromPath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  /* ------------------------------------------------------------- theme */
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    writeLocal("sv-studio-theme", theme);
  }, [theme]);
  const setTheme = useCallback((t: "dark" | "light") => setThemeState(t), []);

  /* -------------------------------------------------------- engine poll */
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const health = await request<BackendStatus>("/health");
        if (cancelled) return;
        setStatus(health);
        if (health.connected) {
          const library = await request<{ tracks: Track[] }>(
            "/library?include_deleted=true",
          );
          if (!cancelled) setServerTracks(library.tracks);
        }
      } catch {
        if (!cancelled) setStatus(null);
      }
      if (!cancelled) timer = setTimeout(poll, 3000);
    };
    let timer = setTimeout(poll, 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [tick]);
  const refresh = useCallback(() => setTick((n) => n + 1), []);

  const upsertLocal = useCallback((incoming: Track[]) => {
    setLocalTracks((old) => {
      const merged = uniqueTracks([...incoming, ...old]);
      writeLocal("sv-library-v2", merged);
      return merged;
    });
  }, []);
  const patchTrack = useCallback((id: string, patch: Partial<Track>) => {
    setLocalTracks((old) => {
      const merged = old.map((track) =>
        track.id === id ? { ...track, ...patch } : track,
      );
      writeLocal("sv-library-v2", merged);
      return merged;
    });
    setServerTracks((old) =>
      old.map((track) => (track.id === id ? { ...track, ...patch } : track)),
    );
  }, []);
  const removeLocal = useCallback((id: string) => {
    setLocalTracks((old) => {
      const merged = old.filter((track) => track.id !== id);
      writeLocal("sv-library-v2", merged);
      return merged;
    });
  }, []);

  const tracks = useMemo(() => {
    const sampleIds = new Set(initialTracks.map((t) => t.id));
    const merged = uniqueTracks([
      ...serverTracks,
      ...localTracks.filter((t) => !sampleIds.has(t.id)),
      ...initialTracks,
    ]);
    return [...merged].sort((a, b) => b.created - a.created);
  }, [serverTracks, localTracks]);
  // Seed samples once so first-run browsing always has something to love.
  useEffect(() => {
    const existing = readLocal<Track[]>("sv-library-v2", []);
    if (!existing.length) writeLocal("sv-library-v2", initialTracks);
  }, []);

  /* ------------------------------------------------------------ player */
  const audio = audioRef.current;
  useEffect(() => {
    if (!audio) return;
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onMeta = () => setDuration(audio.duration || 0);
    const onEnd = () => setPlaying(false);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("loadedmetadata", onMeta);
    audio.addEventListener("durationchange", onMeta);
    audio.addEventListener("ended", onEnd);
    return () => {
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("loadedmetadata", onMeta);
      audio.removeEventListener("durationchange", onMeta);
      audio.removeEventListener("ended", onEnd);
    };
  }, [audio]);
  useEffect(() => {
    if (!audio) return;
    let raf = 0;
    const loop = () => {
      if (!audio.paused && !audio.ended) setProgress(audio.currentTime);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [audio, playing]);
  useEffect(() => {
    if (audio) audio.volume = volume;
    writeLocal("sv-volume", volume);
  }, [audio, volume]);

  const playTrack = useCallback(
    (track: Track) => {
      const src = mediaUrl(track);
      if (!src || !audio) return;
      if (current !== track.id) {
        audio.src = src;
        setCurrent(track.id);
        setProgress(0);
      }
      void audio.play().catch(() => setPlaying(false));
    },
    [audio, current],
  );
  const toggle = useCallback(() => {
    if (!audio || !current) return;
    if (audio.paused) void audio.play().catch(() => {});
    else audio.pause();
  }, [audio, current]);
  const seek = useCallback(
    (seconds: number) => {
      if (!audio) return;
      audio.currentTime = Math.max(0, seconds);
      setProgress(seconds);
    },
    [audio],
  );
  const queue = useMemo(() => tracks.filter(playable), [tracks]);
  const step = useCallback(
    (delta: number) => {
      const index = queue.findIndex((track) => track.id === current);
      const next = queue[(index + delta + queue.length) % queue.length];
      if (next) playTrack(next);
    },
    [queue, current, playTrack],
  );

  const currentTrack = useMemo(
    () => tracks.find((track) => track.id === current) ?? null,
    [tracks, current],
  );

  /* ---------------------------------------------------------- hand-offs */
  const setVideoSource = useCallback((id: string | null) => {
    setVideoSourceState(id);
    writeLocal("sv-video-source-v1", id);
  }, []);
  const makeVideo = useCallback(
    (track: Track) => {
      setVideoSource(track.id);
      navigate("video");
    },
    [setVideoSource, navigate],
  );

  /* -------------------------------------------------------------- toasts */
  const pushToast = useCallback(
    (message: string, tone: Toast["tone"] = "ok") => {
      const id = Date.now() + Math.random();
      setToasts((old) => [...old.slice(-3), { id, message, tone }]);
      setTimeout(
        () => setToasts((old) => old.filter((toast) => toast.id !== id)),
        4200,
      );
    },
    [],
  );

  const value: StudioValue = {
    page,
    navigate,
    status,
    online: !!status?.connected,
    tracks,
    refresh,
    upsertLocal,
    patchTrack,
    removeLocal,
    audioRef,
    current,
    currentTrack,
    playing,
    progress,
    duration,
    volume,
    setVolume: setVolumeState,
    playTrack,
    toggle,
    seek,
    step,
    videoSource,
    setVideoSource,
    makeVideo,
    theme,
    setTheme,
    toasts,
    pushToast,
    settingsOpen,
    setSettingsOpen,
  };
  return (
    <StudioContext.Provider value={value}>{children}</StudioContext.Provider>
  );
}
