import { Download, Film, Play, X } from "lucide-react";
import { Btn, Kicker, cn } from "../../ui";
import type { ExportJob } from "./export-api";

export function RenderCard({
  title,
  summary,
  note,
  issue,
  busy,
  onRender,
  onPreview,
  onPlay,
  error,
  jobs,
  onCancel,
}: {
  title: string;
  summary: string;
  note: string;
  issue?: string;
  busy: boolean;
  onRender: () => void;
  onPreview?: () => void;
  onPlay?: (job: ExportJob) => void;
  error?: string;
  jobs: ExportJob[];
  onCancel: (job: ExportJob) => void;
}) {
  return (
    <section className="panel render-card">
      <header className="render-head">
        <div>
          <Kicker>{title}</Kicker>
          <strong>{summary}</strong>
        </div>
        {onPreview && <Btn variant="quiet" disabled={!!issue || busy} onClick={onPreview}>
          <Play size={16} /> Preview motion
        </Btn>}
        <Btn variant="primary" disabled={!!issue || busy} loading={busy} onClick={onRender}>
          <Film size={16} /> Render video
        </Btn>
      </header>
      <p className={cn("render-note", issue && "warn")}>{issue || note}</p>
      {error ? <p className="error-note">{error}</p> : null}
      {jobs.length ? (
        <ol className="render-jobs">
          {jobs.slice(0, 5).map((job) => (
            <li key={job.id}>
              <div>
                <strong>
                  {job.state === "queued"
                    ? `Queued · position ${job.queuePosition ?? "…"}`
                    : job.state === "succeeded"
                      ? job.preview ? "Preview ready" : "Finished"
                      : job.state === "failed"
                        ? "Failed"
                        : job.phase || job.state}
                </strong>
                <span>
                  {job.aspect} · {job.lyrics ? "with lyrics" : "no lyrics"} ·{" "}
                  {job.renderHost || "renderer"}
                </span>
                {job.state === "running" && job.totalFrames > 0 ? (
                  <>
                    <span className="render-progress">
                      <i style={{ width: `${(job.frames / job.totalFrames) * 100}%` }} />
                    </span>
                    <small>
                      {job.frames.toLocaleString()} / {job.totalFrames.toLocaleString()} frames
                      {job.framesPerSecond && job.remainingSeconds != null
                        ? ` · ${job.framesPerSecond.toFixed(1)} fps · ~${Math.max(1, Math.ceil(job.remainingSeconds / 60))} min left`
                        : ""}
                    </small>
                  </>
                ) : null}
                {job.error ? <p className="error-note">{job.error}</p> : null}
              </div>
              {job.videoUrl && onPlay && <Btn variant="quiet" size="sm" onClick={() => onPlay(job)}>
                <Play size={14} /> {job.preview ? "Watch preview" : "Watch video"}
              </Btn>}
              {job.downloadUrl ? (
                <a className="btn btn-ghost btn-sm" href={job.downloadUrl} download>
                  <Download size={14} /> MP4
                </a>
              ) : ["running", "queued"].includes(job.state) ? (
                <Btn size="sm" variant="quiet" onClick={() => onCancel(job)}>
                  <X size={13} /> Cancel
                </Btn>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
