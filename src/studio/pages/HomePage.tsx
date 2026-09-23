import { useEffect, useState } from "react";
import {
  ArrowRight,
  Clapperboard,
  Disc3,
  Library as LibraryIcon,
  Play,
  Sparkles,
} from "lucide-react";
import { request } from "../../music-studio/api";
import { playable, useStudio } from "../context";
import { CoverArt } from "../components/CoverArt";
import { Btn, cn } from "../ui";
import type { Track } from "../../music-studio/model";

export function HomePage() {
  const { tracks, navigate, playTrack, current, playing } = useStudio();
  const [videos, setVideos] = useState(0);
  const [styles, setStyles] = useState(0);
  useEffect(() => {
    request<{ videos: unknown[] }>("/library/videos")
      .then((r) => setVideos(r.videos.length))
      .catch(() => {});
    request<{ groups: unknown[] }>("/loras")
      .then((r) => setStyles(r.groups.length))
      .catch(() => {});
  }, []);
  const recent = tracks
    .filter((t) => !t.deletedAt && (t.source || playable(t)))
    .slice(0, 6);
  const projects = [
    ...new Set(tracks.filter((t) => !t.deletedAt).map((t) => t.project)),
  ].slice(0, 6);
  const hour = new Date().getHours();
  const greeting =
    hour < 5
      ? "Still awake"
      : hour < 12
        ? "Good morning"
        : hour < 18
          ? "Good afternoon"
          : "Good evening";
  return (
    <div className="home">
      <section className="hero">
        <h1>{greeting}.</h1>
        <p>
          Describe a feeling. Sound &amp; Vision writes the song, paints the cover,
          and dresses it in a music video. All on your own hardware.
        </p>
        <div className="hero-actions">
          <Btn variant="primary" size="lg" onClick={() => navigate("music")}>
            <Disc3 size={17} /> Create a new song
          </Btn>
          <Btn size="lg" onClick={() => navigate("video")}>
            <Clapperboard size={17} /> Make a Music Video
          </Btn>
        </div>
      </section>

      <section className="stats" aria-label="Studio stats">
        {[
          {
            label: "Songs",
            value: tracks.filter((t) => !t.deletedAt && t.source).length || "—",
            icon: Disc3,
          },
          { label: "Videos", value: videos || "—", icon: Clapperboard },
          { label: "Trained styles", value: styles || "—", icon: Sparkles },
          { label: "Projects", value: projects.length, icon: LibraryIcon },
        ].map(({ label, value, icon: Icon }) => (
          <div className="stat" key={label}>
            <span className="stat-icon">
              <Icon size={16} />
            </span>
            <strong>{value}</strong>
            <span>{label}</span>
          </div>
        ))}
      </section>

      <section className="home-section">
        <header className="section-head">
          <h2>Latest sessions</h2>
          <button className="text-link" onClick={() => navigate("library")}>
            Library <ArrowRight size={14} />
          </button>
        </header>
        <div className="session-rail">
          {recent.length ? (
            recent.map((track) => (
              <SessionCard
                key={track.id}
                track={track}
                onPlay={playTrack}
                active={current === track.id}
                playing={playing}
              />
            ))
          ) : (
            <p className="muted">Nothing recorded yet — start with a feeling.</p>
          )}
        </div>
      </section>

      {projects.length ? (
        <section className="home-section">
          <header className="section-head">
            <h2>Projects</h2>
          </header>
          <div className="project-chips">
            {projects.map((project) => (
              <button
                key={project}
                className="chip"
                onClick={() => navigate("library")}
              >
                {project}
                <span className="chip-count">
                  {tracks.filter((t) => t.project === project && !t.deletedAt).length}
                </span>
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function SessionCard({
  track,
  onPlay,
  active,
  playing,
}: {
  track: Track;
  onPlay: (t: Track) => void;
  active: boolean;
  playing: boolean;
}) {
  const isLive =
    !!track.status && !["succeeded", "failed", "cancelled"].includes(track.status);
  return (
    <article className={cn("session", active && "on")}>
      <div className="session-cover">
        <CoverArt track={track} className="session-art" ring={isLive} />
        {playable(track) ? (
          <button
            className="session-play"
            aria-label={`Play ${track.title}`}
            onClick={() => onPlay(track)}
          >
            {active && playing ? (
              <Play size={16} fill="currentColor" />
            ) : (
              <Play size={16} fill="currentColor" />
            )}
          </button>
        ) : null}
      </div>
      <div className="session-meta">
        <strong>{track.title || "Untitled"}</strong>
        <span>
          {isLive ? track.stage || "Generating…" : track.subtitle || track.project}
        </span>
      </div>
    </article>
  );
}
