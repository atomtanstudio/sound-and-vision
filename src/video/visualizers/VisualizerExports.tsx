import { useEffect, useRef, useState } from "react";
import { Download, Film, X } from "lucide-react";
import type { Track } from "../../music-studio/model";
import { timingIssues, type VideoDraft, type LyricCue } from "../timeline";
import { originalVisualizerPresets } from "./library";
import { presetNumber } from "./schedule";

type ExportJob = {
  id: string;
  state: string;
  title: string;
  phase: string;
  error: string | null;
  frames: number;
  totalFrames: number;
  queuePosition: number | null;
  created: number;
  selection: string;
  aspect: string;
  lyrics: boolean;
  downloadUrl: string | null;
  videoUrl: string | null;
  renderHost?: string;
  framesPerSecond?: number | null;
  remainingSeconds?: number | null;
};
async function api<T>(path = "", body?: unknown): Promise<T> {
  const response = await fetch(`/local-api/visualizer-renders${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  });
  const data = await response.json();
  if (!response.ok)
    throw Error(data.detail || "Could not reach the local video renderer");
  return data;
}
export function VisualizerExports({
  track,
  draft,
  cues,
  duration,
}: {
  track: Track;
  draft: VideoDraft;
  cues: LyricCue[];
  duration: number;
}) {
  const [jobs, setJobs] = useState<ExportJob[]>([]),
    [available, setAvailable] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const [renderer, setRenderer] = useState("renderer");
  const [error, setError] = useState(""),
    [submitting, setSubmitting] = useState(false);
  const pending = useRef<{ signature: string; id: string } | null>(null);
  useEffect(() => {
    let disposed = false,
      timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await api<{
          available: boolean;
          jobs: ExportJob[];
          renderer?: string;
        }>(`?takeId=${track.id}`);
        if (!disposed) {
          setJobs(result.jobs);
          setAvailable(result.available);
          setConnectionError("");
          setRenderer(result.renderer || "Mac");
        }
      } catch (error) {
        if (!disposed) {
          setAvailable(false);
          setConnectionError(
            `Render status unavailable: ${(error as Error).message}`,
          );
        }
      }
      if (!disposed) timer = setTimeout(poll, 2000);
    };
    if (!!track.source) void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [track.id, track.source]);
  const active = jobs.some((j) => ["queued", "running"].includes(j.state));
  const timingProblems = timingIssues(cues, duration);
  const missingWords = cues.reduce(
    (n, c) =>
      n +
      (c.words?.filter((w) => w.start == null || w.end == null).length ?? 0),
    0,
  );
  const lyricIssue =
    draft.showLyrics && draft.lyrics.trim() && !cues.length
      ? "Align lyrics first, or turn off Show lyrics to render just the visualizer."
      : draft.showLyrics && (timingProblems.length || missingWords)
        ? missingWords
          ? `${missingWords} words have no complete timestamp. Set their times in Word timing, or turn off Show lyrics.`
          : `${timingProblems[0]} Adjust it in Word timing, or turn off Show lyrics.`
        : "";
  const issue =
    !track.source || track.status !== "succeeded"
      ? "Choose a finished song from your library to render."
      : lyricIssue;
  async function render() {
    setSubmitting(true);
    setError("");
    const body = {
      takeId: track.id,
      duration,
      draft,
      cues: draft.showLyrics ? cues : [],
    };
    const signature = JSON.stringify(body);
    if (pending.current?.signature !== signature)
      pending.current = { signature, id: crypto.randomUUID() };
    try {
      const job = await api<ExportJob>("", {
        ...body,
        requestId: pending.current.id,
      });
      setJobs((old) => [job, ...old.filter((j) => j.id !== job.id)]);
      pending.current = null;
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setSubmitting(false);
    }
  }
  async function cancel(job: ExportJob) {
    try {
      await api(`/${job.id}/cancel`, {});
      setError("");
    } catch (error) {
      setError((error as Error).message);
    }
  }
  return (
    <section
      className="visualizer-exports"
      aria-label="Visualizer video exports"
    >
      <div className="visualizer-export-heading">
        <div>
          <strong>Render your video</strong>
          <p>
            {draft.visualizer === "all"
              ? "All eight styles, equal time across the full song"
              : originalVisualizerPresets[presetNumber(draft.visualizer)].name}
            {` · ${draft.aspect} · 1080p · 24 fps`}
          </p>
        </div>
        <button
          className="primary-button"
          disabled={!!issue || !available || submitting || active}
          onClick={() => void render()}
        >
          <Film size={16} />
          {submitting
            ? "Submitting…"
            : active
              ? "Render in progress"
              : "Render video"}
        </button>
      </div>
      <p className="video-field-note">
        {issue ||
          (renderer === "Legion"
            ? "Renders on Legion. You can close the editor; the video keeps rendering and the finished MP4 appears here when you return."
            : "Renders in the background on this computer. Keep the local server running; the finished MP4 appears here.")}
      </p>
      {(error || connectionError) && (
        <p className="form-error" role="alert">
          {error || connectionError}
        </p>
      )}
      {jobs.length > 0 && (
        <ol className="visualizer-export-jobs">
          {jobs.slice(0, 6).map((job) => (
            <li key={job.id}>
              <div>
                <strong>
                  {job.state === "queued"
                    ? `Queued · position ${job.queuePosition ?? "…"}`
                    : job.phase}
                </strong>
                <span>
                  {job.selection === "all"
                    ? "All eight styles"
                    : originalVisualizerPresets[presetNumber(job.selection)]
                        .name}{" "}
                  · {job.aspect} · {job.lyrics ? "With lyrics" : "No lyrics"} ·{" "}
                  {job.renderHost || "Mac"}
                </span>
                {job.state === "running" &&
                  job.totalFrames > 0 &&
                  job.frames > 0 && (
                    <>
                      <progress
                        aria-label="Frames rendered"
                        value={job.frames}
                        max={job.totalFrames}
                      />
                      <small>
                        {job.frames.toLocaleString()} /{" "}
                        {job.totalFrames.toLocaleString()} frames
                        {job.framesPerSecond && job.remainingSeconds != null
                          ? ` · ${job.framesPerSecond.toFixed(1)} fps · about ${Math.max(1, Math.ceil(job.remainingSeconds / 60))} min remaining`
                          : ""}
                      </small>
                    </>
                  )}
                {job.error && <p className="form-error">{job.error}</p>}
              </div>
              {job.downloadUrl ? (
                <a className="secondary-button" href={job.downloadUrl}>
                  <Download size={15} />
                  Download MP4
                </a>
              ) : ["running", "queued"].includes(job.state) ? (
                <button
                  className="secondary-button"
                  onClick={() => void cancel(job)}
                >
                  <X size={14} />
                  Cancel render
                </button>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
