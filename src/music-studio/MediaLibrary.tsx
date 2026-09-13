import { useEffect, useRef, useState } from "react";
import {
  AudioLines,
  Clapperboard,
  Download,
  Play,
  Pause,
  Search,
} from "lucide-react";
import type { Track } from "./model";
import "./media-library.css";

export type LibraryVideo = {
  id: string;
  kind: "music-video" | "visualizer" | "film";
  title: string;
  takeId?: string;
  filmId?: string;
  created: number;
  duration?: number;
  videoUrl: string;
  downloadUrl: string;
};
type RendererJob = {
  id: string;
  state: string;
  title: string;
  takeId: string;
  created: number;
  duration: number;
  videoUrl: string;
  downloadUrl: string;
};
const durationLabel = (seconds = 0) =>
  `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
const typeLabel = (kind: LibraryVideo["kind"]) =>
  kind === "visualizer" ? "Visualizer video" : "Music video";

export function MediaLibrary({
  tracks,
  currentId,
  playing,
  play,
  pauseMusic,
  openVideo,
}: {
  tracks: Track[];
  currentId: string;
  playing: boolean;
  play: (track: Track) => void;
  pauseMusic: () => void;
  openVideo: (
    takeId?: string,
    kind?: LibraryVideo["kind"],
    filmId?: string,
  ) => void;
}) {
  const [videos, setVideos] = useState<LibraryVideo[]>([]),
    [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]),
    [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all"),
    [limit, setLimit] = useState(48);
  const region = useRef<HTMLElement>(null);
  const previous = useRef<{
    backend: LibraryVideo[];
    renderer: LibraryVideo[];
  }>({ backend: [], renderer: [] });
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function get(path: string) {
      const response = await fetch(path, {
        signal: AbortSignal.any([
          controller.signal,
          AbortSignal.timeout(15000),
        ]),
      });
      if (!response.ok) throw new Error("History unavailable");
      return response.json();
    }
    async function poll() {
      const [backend, renderer] = await Promise.allSettled([
        get("/api/library/videos"),
        get("/local-api/visualizer-renders"),
      ]);
      if (controller.signal.aborted) return;
      const warnings: string[] = [];
      if (backend.status === "fulfilled") {
        previous.current.backend = backend.value.videos;
        if (backend.value.missingFiles)
          warnings.push(
            `${backend.value.missingFiles} saved exports have missing or unreadable files.`,
          );
      } else
        warnings.push(
          "Music-video history is unavailable. Showing any previously loaded videos.",
        );
      if (renderer.status === "fulfilled")
        previous.current.renderer = renderer.value.jobs
          .filter((j: RendererJob) => j.state === "succeeded" && j.videoUrl)
          .map((j: RendererJob) => ({
            ...j,
            id: `visualizer:${j.id}`,
            kind: "visualizer",
          }));
      else
        warnings.push(
          "Visualizer history is unavailable. Showing any previously loaded videos.",
        );
      setVideos([
        ...new Map(
          [...previous.current.backend, ...previous.current.renderer].map(
            (v) => [v.id, v],
          ),
        ).values(),
      ]);
      setErrors(warnings);
      setLoading(false);
      timer = setTimeout(() => void poll(), 10000);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, []);
  const pauseVideos = (except?: HTMLVideoElement) =>
    region.current?.querySelectorAll("video").forEach((video) => {
      if (video !== except) video.pause();
    });
  useEffect(() => {
    if (playing) pauseVideos();
  }, [playing, currentId]);
  useEffect(() => {
    setLimit(48);
  }, [filter, query]);
  const byId = new Map(tracks.map((track) => [track.id, track]));
  const songs = tracks.filter(
    (track) =>
      !track.deletedAt &&
      (track.audio || track.audioUrl) &&
      (!track.source || track.status === "succeeded"),
  );
  const savedVideos = videos.filter(
    (v) => !v.takeId || !byId.get(v.takeId)?.deletedAt,
  );
  const needle = query.trim().toLocaleLowerCase();
  const entries = [
    ...songs.map((song) => ({
      id: `song:${song.id}`,
      song,
      video: null as LibraryVideo | null,
      title: song.title,
      created: song.created || 0,
    })),
    ...savedVideos.map((video) => ({
      id: video.id,
      song: null as Track | null,
      video,
      title:
        video.kind === "visualizer"
          ? byId.get(video.takeId || "")?.title || video.title
          : video.title,
      created: video.created || 0,
    })),
  ]
    .filter(
      (item) =>
        (filter === "all" || (filter === "music" ? item.song : item.video)) &&
        `${item.title} ${item.song?.project || ""} ${item.video ? typeLabel(item.video.kind) : ""}`
          .toLocaleLowerCase()
          .includes(needle),
    )
    .sort((a, b) => b.created - a.created || a.id.localeCompare(b.id));
  return (
    <section ref={region} className="media-library" aria-label="Media library">
      <div className="section-heading">
        <div>
          <h1>Library</h1>
          <p>Your songs and finished videos, together.</p>
        </div>
        <span className="media-library-total">
          {songs.length} songs · {savedVideos.length} videos
        </span>
      </div>
      <div className="media-library-toolbar">
        <div className="media-library-filters" aria-label="Media type">
          {[
            ["all", "All"],
            ["music", "Music"],
            ["videos", "Videos"],
          ].map(([id, label]) => (
            <button
              key={id}
              aria-pressed={filter === id}
              onClick={() => setFilter(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="media-library-search">
          <Search size={16} />
          <input
            type="search"
            aria-label="Search library"
            placeholder="Search songs and videos"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      </div>
      {errors.map((error) => (
        <p className="media-library-notice" role="status" key={error}>
          {error}
        </p>
      ))}
      {loading && <p role="status">Loading saved videos…</p>}
      {!entries.length && !loading && (
        <div className="media-library-empty">
          <Clapperboard size={32} />
          <h2>
            {query
              ? "No matching media"
              : filter === "videos"
                ? "Your finished videos will appear here"
                : "Your library is ready"}
          </h2>
          <p>
            {query
              ? "Try another title or clear the search."
              : "Create a song, import audio, or finish a video to add it to your library."}
          </p>
        </div>
      )}
      <div className="media-library-grid">
        {entries.slice(0, limit).map(({ id, song, video, title }) => {
          const track = song || byId.get(video?.takeId || "");
          const cover = track?.cover;
          const isPlaying = !!song && currentId === song.id && playing;
          return (
            <article
              className="media-library-card"
              key={id}
              aria-label={`${video ? typeLabel(video.kind) : "Song"}: ${title}`}
            >
              {song ? (
                <button
                  className="media-library-cover"
                  aria-label={`${isPlaying ? "Pause" : "Play"} ${title}`}
                  onClick={() => {
                    pauseVideos();
                    play(song);
                  }}
                >
                  {cover ? (
                    <img src={cover} alt="" loading="lazy" />
                  ) : (
                    <AudioLines size={48} />
                  )}
                  <span className="media-library-play">
                    {isPlaying ? <Pause size={24} /> : <Play size={24} />}
                  </span>
                </button>
              ) : (
                <video
                  controls
                  playsInline
                  preload="none"
                  poster={cover}
                  src={video!.videoUrl}
                  aria-label={`Play video: ${title}`}
                  onPlay={(e) => {
                    pauseVideos(e.currentTarget);
                    pauseMusic();
                  }}
                />
              )}
              <div className="media-library-card-body">
                <div className="media-library-meta">
                  <span>
                    {song
                      ? song.source === "imported"
                        ? "Imported song"
                        : song.source
                          ? "Song"
                          : "Sample song"
                      : typeLabel(video!.kind)}
                  </span>
                  <span>
                    {durationLabel(
                      song ? song.duration || 240 : video?.duration,
                    )}
                  </span>
                </div>
                <h2>{title}</h2>
                <p>
                  {video
                    ? `Exported ${new Date(video.created).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`
                    : track?.project || "Music"}
                </p>
                <div className="media-library-card-actions">
                  <a
                    className="quiet-button"
                    download={`${title}.${song ? "mp3" : "mp4"}`}
                    href={
                      video
                        ? video.downloadUrl
                        : song!.source
                          ? `/api/takes/${song!.id}/files/audio.mp3`
                          : `/media/desert-afterglow-${song!.audio}.mp3`
                    }
                  >
                    <Download size={14} />
                    Download
                  </a>
                  {(track || video?.filmId) &&
                    (video?.kind !== "film" ||
                      import.meta.env.VITE_ENABLE_MUSIC_VIDEO === "1") && (
                      <button
                        className="quiet-button"
                        onClick={() =>
                          openVideo(track?.id, video?.kind, video?.filmId)
                        }
                      >
                        {song ? "Create video" : "Open editor"}
                      </button>
                    )}
                </div>
              </div>
            </article>
          );
        })}
      </div>
      {entries.length > limit && (
        <button
          className="secondary-button media-library-more"
          onClick={() => setLimit(limit + 48)}
        >
          Show more · {entries.length - limit} remaining
        </button>
      )}
    </section>
  );
}
