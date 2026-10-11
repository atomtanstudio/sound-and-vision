import { useEffect, useState } from "react";
import { ArtistField } from "./ArtistField";
import { api } from "../lib/api";
import { linkTo } from "../lib/router";
import { useSong } from "../state/song";
import { CoverThumb } from "./Cover";
import { MakePanel } from "./MakePanel";
import { TakesColumn } from "./Takes";
import "./song.css";

/** A song brought in from elsewhere: where it came from, how the listening is going, and the way to its videos. */
function Brought() {
  const { project, takes, jobs } = useSong();
  const [busy, setBusy] = useState(false);
  const take = takes.find((t) => t.id === project?.masterTake);
  const importing = Object.values(jobs).find((j) => j.kind === "song.import" && j.projectId === project?.id &&
    (j.status === "queued" || j.status === "running" || j.status === "failed"));
  const a = take?.analysis;
  const listening = a?.status === "queued" || a?.status === "running";
  const job = Object.values(jobs).find((j) => j.kind === "analysis" && j.takeId === take?.id && j.status === "running");
  if (!project) return null;
  const src = project.source!;
  return (
    <div className={"sp-reading sp-brought" + (importing?.status === "failed" ? " sp-reading-failed" : "")} role="status">
      {importing?.status === "failed" ? <>That didn't work: {importing.message}</> : importing ? (
        <><span className="ln-spin" aria-hidden="true" />Getting your song ready…</>
      ) : (
        <>
          {listening && <span className="ln-spin" aria-hidden="true" />}
          <span>
            Your song{src.artist ? ` by ${src.artist}` : ""}, brought in from <em>{src.file}</em>.{" "}
            {listening ? (job?.message ?? "The app is listening to it: stems, beat, sections and words.") + " A few minutes." :
              a?.status === "ready" ? "It's ready for its videos." : a?.status === "failed" ? `The listening didn't finish: ${a.error ?? "try again"}.` : ""}
          </span>
          {a?.status === "ready" && project.lyricsHeard && (
            <span className="sp-reading-sub">The words on the lyric sheet are what Whisper heard: check them, then time them again.</span>
          )}
          {take && (a?.status === "ready" || a?.status === "failed") && (
            <button type="button" className="sp-mini" disabled={busy}
              onClick={async () => { setBusy(true); try { await api.post(`/api/takes/${take.id}/listen`); } finally { setBusy(false); } }}>
              {a?.status === "failed" ? "Listen again" : "Time the words again"}
            </button>
          )}
          {a?.status === "ready" && <a className="sp-mini" {...linkTo(`/video/${project.id}`)}>Make a video →</a>}
        </>
      )}
    </div>
  );
}

export function SongPage({ id }: { id: string }) {
  const { project, error, load, setTitle, saving } = useSong();
  const reading = useSong((s) => Object.values(s.jobs).find((j) => j.kind === "quick" && j.projectId === id &&
    (j.status === "queued" || j.status === "running" || j.status === "failed")));

  useEffect(() => {
    void load(id);
  }, [id, load]);

  useEffect(() => {
    const flush = () => void useSong.getState().saveNow();
    window.addEventListener("pagehide", flush);
    return () => window.removeEventListener("pagehide", flush);
  }, []);

  if (error && !project) return <main className="sp-msg">{error}</main>;
  if (!project) return <main className="sp-msg sp-loading">Opening the song…</main>;

  return (
    <main className="sp">
      <header className="sp-head">
        <div className="sp-title">
          <CoverThumb />
          <div className="sp-names">
            <input
              className="sp-name"
              value={project.title}
              placeholder="Untitled song"
              aria-label="Song title"
              onChange={(e) => setTitle(e.target.value)}
              onFocus={(e) => project.title === "Untitled song" && e.target.select()}
            />
            <ArtistField project={project} />
          </div>
          <span className={`sp-saving sp-${saving}`}>
            {saving === "saving" ? "Saving…" : saving === "error" ? "Not saved, retrying" : saving === "pending" ? "" : "Saved"}
          </span>
        </div>
        <nav className="sp-steps" aria-label="Steps">
          <span className="sp-step sp-on">Song</span>
          <span className="sp-arrow">→</span>
          {project.masterTake ? (
            <a className="sp-step sp-step-link" {...linkTo(`/video/${project.id}`)} title="Make a video for this song">Video</a>
          ) : (
            <span className="sp-step" title="Choose a take first (Use this one)">Video</span>
          )}
          <span className="sp-arrow">→</span>
          <a className="sp-step sp-step-link" {...linkTo(`/share?song=${project.id}`)} title="Make clips of it for TikTok, Reels, Shorts and more">Share</a>
        </nav>
      </header>
      {project.source?.kind === "upload" && <Brought />}
      {reading && (
        <div className={"sp-reading" + (reading.status === "failed" ? " sp-reading-failed" : "")} role="status">
          {reading.status === "failed" ? (
            <>That didn't work: {reading.message}</>
          ) : (
            <>
              <span className="ln-spin" aria-hidden="true" />
              {reading.stage === "start" ? "Starting your songs…" : "Reading your idea and writing the song…"}
              <span className="sp-reading-sub">The words, the sound and two takes, all from what you typed.</span>
            </>
          )}
        </div>
      )}
      <div className="sp-body">
        <aside className="sp-make" aria-label="Make the song">
          <MakePanel />
        </aside>
        <section className="sp-takes" aria-label="Takes">
          <TakesColumn />
        </section>
      </div>
    </main>
  );
}
