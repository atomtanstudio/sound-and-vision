import { useEffect, useMemo, useRef, useState } from "react";
import {
  Clapperboard,
  Download,
  ExternalLink,
  LayoutGrid,
  List,
  RotateCcw,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { request } from "../../music-studio/api";
import { projects as defaultProjects, readLocal, writeLocal, type Track } from "../../music-studio/model";
import { playable, timeLabel, useStudio } from "../context";
import { CoverArt } from "../components/CoverArt";
import { TrackDetail, statusLabel } from "../components/TrackDetail";
import {
  Btn,
  Empty,
  ErrorNote,
  IconBtn,
  Segmented,
  Select,
  TextInput,
  cn,
} from "../ui";

type LibraryVideo = {
  id: string;
  kind: "music-video" | "film" | "visualizer";
  takeId?: string | null;
  title: string;
  duration?: number;
  created?: number;
  videoUrl: string;
  downloadUrl?: string;
};

export function LibraryPage() {
  const { tracks, navigate, playTrack, current, playing, pushToast, refresh, setVideoSource } =
    useStudio();
  const [tab, setTab] = useState<"all" | "songs" | "videos">("all");
  const [query, setQuery] = useState("");
  const [project, setProject] = useState("all");
  const [filter, setFilter] = useState<"all" | "favorites" | "trash">("all");
  const [layout, setLayout] = useState<"grid" | "list">(() =>
    readLocal<"grid" | "list">("sv-studio-layout", readLocal<"grid" | "list">("sv-nova-layout", "grid")),
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<Track | null>(null);
  const [error, setError] = useState("");
  const [videos, setVideos] = useState<LibraryVideo[]>([]);
  const [showMore, setShowMore] = useState(48);
  writeLocal("sv-studio-layout", layout);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      const [backend, renderer] = await Promise.allSettled([
        request<{ videos: LibraryVideo[]; missingFiles?: number }>("/library/videos").then((r) => r.videos),
        fetch("/local-api/visualizer-renders", { signal: AbortSignal.timeout(10000) })
          .then((r) => (r.ok ? r.json() : Promise.reject("renderer offline")))
          .then((r) =>
            (r.jobs as { id: string; takeId?: string; state: string; videoUrl?: string; downloadUrl?: string; title?: string; created?: number; duration?: number; preview?: boolean }[])
              .filter((j) => j.state === "succeeded" && j.videoUrl && !j.preview)
              .map((j) => ({
                id: `visualizer:${j.id}`,
                kind: "visualizer" as const,
                takeId: j.takeId ?? null,
                title: j.title || "Visualizer",
                created: j.created,
                duration: j.duration,
                videoUrl: j.videoUrl!,
                downloadUrl: j.downloadUrl || undefined,
              })),
          ),
      ]);
      if (cancelled) return;
      setVideos([
        ...new Map(
          [...(backend.status === "fulfilled" ? backend.value : []), ...(renderer.status === "fulfilled" ? (renderer.value as LibraryVideo[]) : [])].map((v) => [v.id, v]),
        ).values(),
      ]);
      timer = setTimeout(poll, 10000);
    };
    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  const projects = useMemo(
    () => [...new Set([...defaultProjects, ...readLocal<string[]>("sv-projects-v2", []), ...tracks.map((t) => t.project)])],
    [tracks],
  );
  const trackById = useMemo(
    () => new Map(tracks.map((track) => [track.id, track])),
    [tracks],
  );
  const songs = tracks.filter((track) => {
    if (filter === "trash" ? !track.deletedAt : !!track.deletedAt) return false;
    if (filter === "favorites" && !track.favorite) return false;
    if (project !== "all" && track.project !== project) return false;
    const q = query.trim().toLowerCase();
    return !q || `${track.title} ${track.subtitle} ${track.project}`.toLowerCase().includes(q);
  });
  const visibleVideos = filter === "all" ? videos.filter((video) => {
    const take = video.takeId ? trackById.get(video.takeId) : undefined;
    if (project !== "all" && take?.project !== project) return false;
    const q = query.trim().toLowerCase();
    return !q || `${video.title} ${video.kind} ${take?.title || ""} ${take?.project || ""}`.toLowerCase().includes(q);
  }) : [];
  const toggleSelect = (id: string, on: boolean) =>
    setSelected((old) => {
      const next = new Set(old);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  const action = async (kind: "move" | "trash" | "restore", projectName?: string) => {
    setError("");
    try {
      await request("/library/actions", { ids: [...selected], action: kind, ...(projectName === undefined ? {} : { project: projectName }) });
      pushToast(`Updated ${selected.size} ${selected.size === 1 ? "song" : "songs"}`);
      setSelected(new Set());
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="library">
      <header className="page-head">
        <div>
          <KickerBack />
          <h1>Library</h1>
        </div>
        <Segmented
          ariaLabel="Library section"
          options={[
            { value: "all", label: `All ${songs.length + visibleVideos.length}` },
            { value: "songs", label: `Songs ${songs.length}` },
            { value: "videos", label: `Videos ${visibleVideos.length}` },
          ]}
          value={tab}
          onChange={(next) => {
            setTab(next);
            if (next === "all") setFilter("all");
          }}
        />
      </header>

      {tab !== "videos" ? (
        <>
          <div className="lib-toolbar">
            <div className="lib-search">
              <Search size={14} aria-hidden="true" />
              <TextInput placeholder="Search songs, videos, projects…" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <label className="lib-filter">
              <span className="filter-label">Project</span>
              <Select value={project} onChange={(e) => setProject(e.target.value)} aria-label="Project filter">
                <option value="all">All projects</option>
                {projects.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </Select>
            </label>
            <Select
              className="lib-filter-select"
              value={filter}
              onChange={(e) => setFilter(e.target.value as "all" | "favorites" | "trash")}
              aria-label="Library filter"
            >
              <option value="all">Filter</option>
              <option value="favorites">Favorites</option>
              <option value="trash">Trash</option>
            </Select>
            <ImportButton onDone={refresh} onError={setError} />
            <div className="lib-layout-toggle">
              <IconBtn label="Grid" className={cn(layout === "grid" && "on")} onClick={() => setLayout("grid")}>
                <LayoutGrid size={15} />
              </IconBtn>
              <IconBtn label="List" className={cn(layout === "list" && "on")} onClick={() => setLayout("list")}>
                <List size={15} />
              </IconBtn>
            </div>
          </div>
          {selected.size ? (
            <div className="lib-selection-bar">
              <strong>{selected.size} selected</strong>
              {filter !== "trash" ? (
                <>
                  <Select aria-label="Move to project" defaultValue="" onChange={(e) => e.target.value && void action("move", e.target.value)}>
                    <option value="" disabled>
                      Move to project…
                    </option>
                    {projects.filter((p) => p !== "Loose tracks").map((p) => <option key={p}>{p}</option>)}
                    <option>Loose tracks</option>
                  </Select>
                  <Btn size="sm" variant="quiet" onClick={() => void action("trash")}>
                    <Trash2 size={14} /> Trash
                  </Btn>
                </>
              ) : (
                <Btn size="sm" onClick={() => void action("restore")}>
                  <RotateCcw size={14} /> Restore
                </Btn>
              )}
              <button className="text-link" onClick={() => setSelected(new Set())}>
                Clear
              </button>
              <ErrorNote>{error}</ErrorNote>
            </div>
          ) : null}
          {songs.length ? (
            <div className={cn("lib-grid", layout === "list" && "lib-list")}>
              {songs.slice(0, showMore).map((track) =>
                layout === "grid" ? (
                  <SongCard key={track.id} track={track} selected={selected.has(track.id)} onSelect={toggleSelect} onPlay={playTrack} isCurrent={current === track.id} playing={playing} onOpen={setDetail} />
                ) : (
                  <SongRow key={track.id} track={track} selected={selected.has(track.id)} onSelect={toggleSelect} onPlay={playTrack} isCurrent={current === track.id} playing={playing} onOpen={setDetail} />
                ),
              )}
            </div>
          ) : tab === "songs" ? (
            <Empty
              icon={<Clapperboard size={22} />}
              title={filter === "trash" ? "Trash is empty" : "No songs match"}
              body={filter === "trash" ? undefined : "Everything you generate lands here."}
              action={filter !== "trash" && !query ? <Btn variant="primary" onClick={() => navigate("music")}>Make the first one</Btn> : undefined}
            />
          ) : null}
          {songs.length > showMore ? (
            <button className="more-link" onClick={() => setShowMore((n) => n + 48)}>
              Show more
            </button>
          ) : null}
          {tab === "all" ? (
            <section className="lib-all-section">
              <header className="lib-subhead">
                <h2>Videos</h2>
                <span>{visibleVideos.length} saved</span>
              </header>
              <VideosTab videos={visibleVideos} tracks={tracks} setVideoSource={setVideoSource} navigate={navigate} />
            </section>
          ) : null}
        </>
      ) : (
        <VideosTab videos={visibleVideos} tracks={tracks} setVideoSource={setVideoSource} navigate={navigate} />
      )}
      {detail ? <TrackDetail track={detail} onClose={() => setDetail(null)} /> : null}
    </div>
  );
}

const KickerBack = () => {
  const { navigate } = useStudio();
  return (
    <button className="kicker kicker-link" onClick={() => navigate("home")}>
      home
    </button>
  );
};

function SongCard({
  track,
  selected,
  onSelect,
  onPlay,
  isCurrent,
  playing,
  onOpen,
}: {
  track: Track;
  selected: boolean;
  onSelect: (id: string, on: boolean) => void;
  onPlay: (t: Track) => void;
  isCurrent: boolean;
  playing: boolean;
  onOpen: (t: Track) => void;
}) {
  const live = !!track.status && !["succeeded", "failed", "cancelled"].includes(track.status);
  return (
    <article className={cn("song-card", selected && "selected")}>
      <label className="song-check">
        <input type="checkbox" checked={selected} onChange={(e) => onSelect(track.id, e.target.checked)} aria-label={`Select ${track.title}`} />
      </label>
      <button className="song-art" onClick={() => onOpen(track)}>
        <CoverArt track={track} className="song-cover" ring={live} />
        {playable(track) ? (
          <span className={cn("song-play", isCurrent && playing && "on")} role="presentation" onClick={(e) => { e.preventDefault(); e.stopPropagation(); onPlay(track); }}>
            <HeartPlay playing={isCurrent && playing} />
          </span>
        ) : null}
      </button>
      <div className="song-meta">
        <button className="song-title" onClick={() => onOpen(track)}>{track.title || "Untitled"}</button>
        <span className="song-sub">{track.subtitle || track.project}</span>
        <span className={cn("song-status", live && "live")}>{statusLabel(track)}{track.duration ? ` · ${timeLabel(track.duration)}` : ""}</span>
      </div>
    </article>
  );
}
const HeartPlay = ({ playing }: { playing: boolean }) =>
  playing ? <PauseGlyph /> : <PlayGlyph />;
const PlayGlyph = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M8 5.5v13l11-6.5z" />
  </svg>
);
const PauseGlyph = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M7 5h3.5v14H7zm6.5 0H17v14h-3.5z" />
  </svg>
);

function SongRow({
  track,
  selected,
  onSelect,
  onPlay,
  isCurrent,
  playing,
  onOpen,
}: {
  track: Track;
  selected: boolean;
  onSelect: (id: string, on: boolean) => void;
  onPlay: (t: Track) => void;
  isCurrent: boolean;
  playing: boolean;
  onOpen: (t: Track) => void;
}) {
  return (
    <div className={cn("song-row", isCurrent && "on", selected && "selected")}>
      <input type="checkbox" checked={selected} onChange={(e) => onSelect(track.id, e.target.checked)} aria-label={`Select ${track.title}`} />
      <button className="row-play" onClick={() => onPlay(track)} aria-label="Play" disabled={!playable(track)}>
        {isCurrent && playing ? <PauseGlyph /> : <PlayGlyph />}
      </button>
      <CoverArt track={track} className="row-cover" />
      <button className="row-title" onClick={() => onOpen(track)}>
        {track.title || "Untitled"}
      </button>
      <span className="row-sub">{track.project}</span>
      <span className={cn("row-status", track.status && !["succeeded", "failed", "cancelled"].includes(track.status) && "live")}>
        {statusLabel(track)}
      </span>
      <span className="row-time">{track.duration ? timeLabel(track.duration) : ""}</span>
    </div>
  );
}

function ImportButton({ onDone, onError }: { onDone: () => void; onError: (m: string) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <input
        ref={ref}
        type="file"
        accept="audio/*"
        hidden
        onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          setBusy(true);
          onError("");
          try {
            await fetch("/api/songs/import", {
              method: "POST",
              headers: { "X-Filename": file.name, "Content-Type": "application/octet-stream" },
              body: file,
              signal: AbortSignal.timeout(120000),
            }).then(async (r) => {
              const data = await r.json();
              if (!r.ok) throw Error(data.detail || "Import failed.");
              return data;
            });
            onDone();
          } catch (err) {
            onError((err as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      />
      <Btn size="sm" onClick={() => ref.current?.click()} loading={busy}>
        <Upload size={14} /> Import
      </Btn>
    </>
  );
}

function VideosTab({
  videos,
  tracks,
  setVideoSource,
  navigate,
}: {
  videos: LibraryVideo[];
  tracks: Track[];
  setVideoSource: (id: string | null) => void;
  navigate: (p: "video") => void;
}) {
  const byId = new Map(tracks.map((t) => [t.id, t]));
  return (
    <div className="videos-grid">
      {videos.length ? (
        videos.map((video) => {
          const take = video.takeId ? byId.get(video.takeId) : undefined;
          return (
            <article className="video-card" key={video.id}>
              <video src={video.videoUrl} controls preload="metadata" playsInline />
              <div className="video-card-meta">
                <strong>{video.title || "Untitled video"}</strong>
                <span>
                  {video.kind === "visualizer" ? "Song Reactive Visualizer" : video.kind === "film" ? "Film" : "Music video"}
                  {take ? ` · ${take.title}` : ""}
                </span>
                <div className="video-card-actions">
                  {video.downloadUrl ? (
                    <a className="btn btn-ghost btn-sm" href={video.downloadUrl} download>
                      <Download size={14} /> MP4
                    </a>
                  ) : null}
                  {video.takeId ? (
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        setVideoSource(video.takeId!);
                        navigate("video");
                      }}
                    >
                      <ExternalLink size={14} /> Open editor
                    </button>
                  ) : null}
                </div>
              </div>
            </article>
          );
        })
      ) : (
        <Empty
          icon={<Clapperboard size={22} />}
          title="No finished videos yet"
          body="Visualizers, lyric videos and films appear here once rendered."
        />
      )}
    </div>
  );
}
