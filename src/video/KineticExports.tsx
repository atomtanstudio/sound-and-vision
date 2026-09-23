import { useEffect, useRef, useState } from "react";
import { Download, Film, X } from "lucide-react";
import { createRequestId } from "../music-studio/api";
import type { Track } from "../music-studio/model";
import { timingIssues, type LyricCue, type VideoDraft } from "./timeline";

type KineticAsset = {
  id: string;
  name: string;
  kind: "images" | "motion";
  slot: number;
  url: string;
  blob?: Blob;
  generated?: boolean;
};
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
  background: string;
  aspect: string;
  lyrics: boolean;
  downloadUrl: string | null;
  videoUrl: string | null;
  renderHost?: string;
  framesPerSecond?: number | null;
  remainingSeconds?: number | null;
};

async function api<T>(path = "", body?: unknown, method?: string): Promise<T> {
  const response = await fetch(`/local-api/kinetic-renders${path}`, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(body === undefined ? 15000 : 30000),
  });
  const data = await response.json();
  if (!response.ok)
    throw Error(data.detail || "Could not reach the video renderer");
  return data;
}

function minimalDraft(draft: VideoDraft) {
  return {
    aspect: draft.aspect,
    background: draft.background,
    imageCount: draft.imageCount,
    imageCycles: draft.imageCycles,
    clipCount: draft.clipCount,
    clipSeconds: draft.clipSeconds,
    pan: draft.pan,
    transition: draft.transition,
    shade: draft.shade,
    font: draft.font,
    textSize: draft.textSize,
    placement: draft.placement,
    lyricMotion: draft.lyricMotion,
    intensity: draft.intensity,
    textColor: draft.textColor,
    highlightColor: draft.highlightColor,
    lyrics: draft.lyrics,
    language: draft.language,
    audioFade: draft.audioFade,
  };
}

export function KineticExports({
  track,
  draft,
  assets,
  cues,
  duration,
}: {
  track: Track;
  draft: VideoDraft;
  assets: KineticAsset[];
  cues: LyricCue[];
  duration: number;
}) {
  const [jobs, setJobs] = useState<ExportJob[]>([]);
  const [available, setAvailable] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const [renderer, setRenderer] = useState("renderer");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const pending = useRef<{ signature: string; id: string } | null>(null);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await api<{
          available: boolean;
          jobs: ExportJob[];
          renderer?: string;
        }>(`?takeId=${encodeURIComponent(track.id)}`);
        if (!disposed) {
          setJobs(result.jobs);
          setAvailable(result.available);
          setRenderer(result.renderer || "Mac");
          setConnectionError("");
        }
      } catch (pollError) {
        if (!disposed) {
          setAvailable(false);
          setConnectionError(
            `Render status unavailable: ${(pollError as Error).message}`,
          );
        }
      }
      if (!disposed) timer = setTimeout(poll, 2000);
    };
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [track.id]);

  const active = jobs.some((job) => ["queued", "running"].includes(job.state));
  const requiredCount =
    draft.background === "images" ? draft.imageCount : draft.clipCount;
  const selectedAssets = Array.from({ length: requiredCount }, (_, slot) =>
    assets.find(
      (asset) => asset.kind === draft.background && asset.slot === slot,
    ),
  );
  const missingAssets = selectedAssets.reduce((missing, asset, slot) => {
    if (!asset) missing.push(slot + 1);
    return missing;
  }, [] as number[]);
  const timingProblems = timingIssues(cues, duration);
  const missingWords = cues.reduce(
    (total, cue) =>
      total +
      (cue.words?.filter((word) => word.start == null || word.end == null)
        .length ?? 0),
    0,
  );
  const lyricIssue =
    draft.lyrics.trim() && !cues.length
      ? "Align lyrics first, or remove the lyric sheet to render a background-only video."
      : missingWords
        ? `${missingWords} words have no complete timestamp. Set their times in Edit lyric timing.`
        : timingProblems[0] || "";
  const issue =
    !track.source || track.status !== "succeeded"
      ? "Choose a finished song from your library to render."
      : missingAssets.length
        ? `Generate or add background ${missingAssets[0]} before rendering.`
        : lyricIssue;

  async function uploadAsset(requestId: string, asset: KineticAsset) {
    let source: Blob;
    if (asset.blob) source = asset.blob;
    else {
      source = await fetch(new URL(asset.url, window.location.href), {
        signal: AbortSignal.timeout(120000),
      }).then((response) => {
        if (!response.ok)
          throw Error(`Could not read background ${asset.slot + 1}.`);
        return response.blob();
      });
    }
    const response = await fetch(
      `/local-api/kinetic-renders/assets/${encodeURIComponent(requestId)}/${asset.kind}/${asset.slot}`,
      {
        method: "PUT",
        headers: { "Content-Type": source.type || "application/octet-stream" },
        body: source,
        signal: AbortSignal.timeout(10 * 60 * 1000),
      },
    );
    const data = await response.json();
    if (!response.ok)
      throw Error(
        data.detail || `Could not upload background ${asset.slot + 1}.`,
      );
  }

  async function render() {
    if (issue || submitting) return;
    setSubmitting(true);
    setError("");
    const body = {
      takeId: track.id,
      title: track.title,
      duration,
      draft: minimalDraft(draft),
      cues,
      assets: selectedAssets.map((asset) => ({
        kind: asset!.kind,
        slot: asset!.slot,
        name: asset!.name,
      })),
    };
    const signature = JSON.stringify(body);
    if (pending.current?.signature !== signature)
      pending.current = { signature, id: createRequestId() };
    const requestId = pending.current.id;
    try {
      await api("/assets", {
        requestId,
        takeId: body.takeId,
        assets: body.assets,
      });
      for (let index = 0; index < selectedAssets.length; index++) {
        setStatus(
          `Uploading background ${index + 1} of ${selectedAssets.length}…`,
        );
        await uploadAsset(requestId, selectedAssets[index]!);
      }
      setStatus("Submitting the full-song render…");
      const job = await api<ExportJob>("", { ...body, requestId });
      setJobs((old) => [job, ...old.filter((item) => item.id !== job.id)]);
      pending.current = null;
      setStatus("");
    } catch (renderError) {
      setError((renderError as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function cancel(job: ExportJob) {
    try {
      await api(`/${job.id}/cancel`, {}, "POST");
      setError("");
    } catch (cancelError) {
      setError((cancelError as Error).message);
    }
  }

  return (
    <section className="visualizer-exports" aria-label="Kinetic video exports">
      <div className="visualizer-export-heading">
        <div>
          <strong>Render your kinetic video</strong>
          <p>
            {draft.background === "images" ? "Slideshow" : "H3 clips"} · {draft.aspect} · 1080p · 24 fps · original soundtrack
          </p>
        </div>
        <button
          className="primary-button"
          disabled={!!issue || !available || submitting || active}
          onClick={() => void render()}
        >
          <Film size={16} />
          {submitting
            ? "Preparing…"
            : active
              ? "Render in progress"
              : "Render video"}
        </button>
      </div>
      <p className="video-field-note">
        {issue ||
          (renderer === "Legion"
            ? "Renders on Legion. You can leave the editor; the finished MP4 will appear here."
            : "Renders in the background. Keep the local app running until the MP4 is ready.")}
      </p>
      {status && (
        <p className="video-field-note" role="status">
          {status}
        </p>
      )}
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
                  {job.background === "images" ? "Slideshow" : "H3 clips"} · {job.aspect} · {job.lyrics ? "With lyrics" : "Title only"} · {job.renderHost || "renderer"}
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
                        {job.frames.toLocaleString()} / {job.totalFrames.toLocaleString()} frames
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
