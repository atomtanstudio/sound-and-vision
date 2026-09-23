import { useMemo, useState } from "react";
import { Check, Mic, Sparkles, Waves } from "lucide-react";
import type { Track } from "../../../music-studio/model";
import type { Alignment } from "../../../video/production";
import {
  backgroundPrompt,
  FPS,
  framesFor,
  makePlacements,
  timingIssues,
  type LyricCue,
  type VideoDraft,
} from "../../../video/timeline";
import { busyJob, type useProduction } from "./useProduction";
import { timeLabel } from "../../context";
import {
  Btn,
  ErrorNote,
  Field,
  Kicker,
  Segmented,
  Select,
  Slider,
  TextArea,
  TextInput,
  cn,
} from "../../ui";
import { RenderCard } from "./RenderCard";
import { localApi, useLocalRenders, type ExportJob } from "./export-api";

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

export function KineticMode({
  track,
  draft,
  update,
  duration,
  prod,
  cues,
  alignment,
}: {
  track: Track;
  draft: VideoDraft;
  update: (part: Partial<VideoDraft>) => void;
  duration: number;
  prod: ReturnType<typeof useProduction>;
  cues: LyricCue[];
  alignment: Alignment | undefined;
}) {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const renders = useLocalRenders("kinetic-renders", track.id, true);

  const latest = (kind: string) =>
    [...prod.jobs].reverse().find((j) => j.kind === kind);
  const transcription = latest("lyric-transcription");
  const alignmentJob = latest("lyric-alignment");
  const placements = useMemo(() => makePlacements(duration, draft), [duration, draft]);
  const assetUrl = (slot: number) => {
    const job = [...prod.jobs]
      .reverse()
      .find(
        (j) =>
          j.kind === "video-image" &&
          j.state === "succeeded" &&
          j.input.slot === slot,
      );
    return job ? `/api/video/jobs/${job.id}/media` : undefined;
  };
  const missingAssets = Array.from(
    { length: draft.imageCount },
    (_, slot) => slot,
  ).filter((slot) => !assetUrl(slot));
  const timingProblems = timingIssues(cues, duration);
  const missingWords = cues.reduce(
    (n, c) => n + (c.words?.filter((w) => w.start == null || w.end == null).length ?? 0),
    0,
  );
  const issue =
    !track.source || track.status !== "succeeded"
      ? "Choose a finished song to render."
      : missingAssets.length
        ? `Generate or wait for background ${missingAssets[0] + 1} before rendering.`
        : draft.lyrics.trim() && !cues.length
          ? "Align lyrics first, or clear the lyric sheet to render a background-only video."
          : missingWords
            ? `${missingWords} words have no complete timestamp — re-align or fix them.`
            : timingProblems[0] || "";

  async function transcribe() {
    setError("");
    await prod.submit([
      {
        kind: "transcription",
        slot: 0,
        aspect: draft.aspect,
        seconds: duration,
        prompt: "",
        lyrics: "",
        language: draft.language,
      },
    ]);
  }
  async function align() {
    setError("");
    await prod.submit([
      {
        kind: "alignment",
        slot: 0,
        aspect: draft.aspect,
        seconds: duration,
        prompt: "",
        lyrics: draft.lyrics,
        language: draft.language,
      },
    ]);
  }
  async function generateSeries() {
    setError("");
    const inputs = Array.from({ length: draft.imageCount }, (_, slot) => ({
      kind: "images" as const,
      slot,
      aspect: draft.aspect,
      seconds: duration,
      prompt: backgroundPrompt(track, draft, slot),
      lyrics: draft.lyrics,
      language: draft.language,
    }));
    await prod.submit(inputs);
  }
  async function render() {
    setBusy(true);
    setError("");
    const selectedAssets = Array.from({ length: draft.imageCount }, (_, slot) => ({
      kind: "images" as const,
      slot,
      name: `background-${slot + 1}.png`,
      url: assetUrl(slot)!,
    }));
    const body = {
      takeId: track.id,
      title: track.title,
      duration,
      draft: minimalDraft(draft),
      cues,
      assets: selectedAssets.map(({ kind, slot, name }) => ({ kind, slot, name })),
    };
    const requestId = renders.requestIdFor(body);
    try {
      setStatus("Registering assets…");
      await localApi("kinetic-renders", "/assets", { requestId, takeId: track.id, assets: body.assets });
      for (const asset of selectedAssets) {
        setStatus(`Uploading background ${asset.slot + 1} of ${selectedAssets.length}…`);
        const source = await fetch(new URL(asset.url, window.location.href), {
          signal: AbortSignal.timeout(120000),
        }).then((r) => {
          if (!r.ok) throw Error(`Could not read background ${asset.slot + 1}.`);
          return r.blob();
        });
        const put = await fetch(
          `/local-api/kinetic-renders/assets/${encodeURIComponent(requestId)}/${asset.kind}/${asset.slot}`,
          {
            method: "PUT",
            headers: { "Content-Type": source.type || "application/octet-stream" },
            body: source,
            signal: AbortSignal.timeout(10 * 60 * 1000),
          },
        );
        if (!put.ok) {
          const data = await put.json().catch(() => ({}));
          throw Error(data.detail || `Could not upload background ${asset.slot + 1}.`);
        }
      }
      setStatus("Submitting the render…");
      const job = await localApi<ExportJob>("kinetic-renders", "", {
        ...body,
        requestId,
      });
      renders.mergeJob(job);
      renders.rememberDone();
      setStatus("");
    } catch (e) {
      setError((e as Error).message);
      setStatus("");
    } finally {
      setBusy(false);
    }
  }
  const runningJob = prod.jobs.find(busyJob);
  return (
    <>
      <section className="panel mode-panel">
        <h2>
          <Mic size={15} /> Lyrics & timing
        </h2>
        <div className="kinetic-lyric-row">
          <TextArea
            rows={5}
            value={draft.lyrics}
            placeholder="Lyrics appear here after transcription, or paste your own…"
            onChange={(e) => update({ lyrics: e.target.value })}
          />
          <div className="kinetic-lyric-actions">
            <Btn
              disabled={busyJob(transcription || ({} as never)) || prod.submitting}
              loading={transcription ? busyJob(transcription) : false}
              onClick={() => void transcribe()}
            >
              <Waves size={15} /> Transcribe
            </Btn>
            {transcription?.state === "succeeded" && transcription.result?.lyrics ? (
              <Btn
                size="sm"
                variant="quiet"
                onClick={() => {
                  update({ lyrics: transcription.result!.lyrics!, lyricRevision: undefined });
                  void align();
                }}
              >
                <Check size={14} /> Use transcription
              </Btn>
            ) : null}
            <Btn
              variant="primary"
              disabled={!draft.lyrics.trim() || prod.submitting || busyJob(alignmentJob || ({} as never))}
              loading={alignmentJob ? busyJob(alignmentJob) : false}
              onClick={() => void align()}
            >
              Align to audio
            </Btn>
          </div>
        </div>
        {runningJob ? (
          <p className="kinetic-job-live" role="status">
            <i /> {runningJob.input.kind} · {runningJob.result?.phase || runningJob.state}
          </p>
        ) : null}
        {prod.error ? <ErrorNote>{prod.error}</ErrorNote> : null}
        {alignment ? (
          <p className="muted small">
            {alignment.method} · {alignment.wordCount} words
            {alignment.reviewCount ? ` · ${alignment.reviewCount} flagged for review` : ""} ·{" "}
            {cues.length} timed lines
          </p>
        ) : null}
        {cues.length ? (
          <details className="cue-editor" open={draft.cueEdits && Object.keys(draft.cueEdits).length > 0}>
            <summary>
              <Kicker>Line timing</Kicker> <span>fine-tune start / end</span>
            </summary>
            <ol>
              {cues.map((cue, i) => (
                <li key={cue.id}>
                  <span className="cue-index">{i + 1}</span>
                  <span className="cue-text">{cue.text}</span>
                  <label>
                    in
                    <input
                      type="number"
                      step="0.05"
                      min={0}
                      max={duration}
                      value={(cue.startFrame / FPS).toFixed(2)}
                      onChange={(e) =>
                        update({
                          cueEdits: {
                            ...draft.cueEdits,
                            [cue.id]: {
                              startFrame: Math.max(0, Math.round(Number(e.target.value) * FPS)),
                              endFrame: cue.endFrame,
                            },
                          },
                        })
                      }
                    />
                  </label>
                  <label>
                    out
                    <input
                      type="number"
                      step="0.05"
                      min={0}
                      max={duration}
                      value={(cue.endFrame / FPS).toFixed(2)}
                      onChange={(e) =>
                        update({
                          cueEdits: {
                            ...draft.cueEdits,
                            [cue.id]: {
                              startFrame: cue.startFrame,
                              endFrame: Math.min(framesFor(duration), Math.round(Number(e.target.value) * FPS)),
                            },
                          },
                        })
                      }
                    />
                  </label>
                </li>
              ))}
            </ol>
          </details>
        ) : null}
        <div className="kinetic-style">
          <Field label="Word motion">
            <Select
              value={draft.lyricMotion}
              onChange={(e) => update({ lyricMotion: e.target.value as VideoDraft["lyricMotion"] })}
            >
              {["auto", "pop", "slam", "rise", "highlight", "reveal", "calm"].map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </Select>
          </Field>
          <Field label="Type">
            <Segmented
              ariaLabel="Lyric type style"
              size="sm"
              options={[
                { value: "bold", label: "Bold" },
                { value: "soft", label: "Soft" },
                { value: "editorial", label: "Editorial" },
              ]}
              value={draft.font}
              onChange={(font) => update({ font })}
            />
          </Field>
          <Slider label="Text size" min={60} max={160} value={draft.textSize} display={`${draft.textSize}%`} onChange={(textSize) => update({ textSize })} />
          <Slider label="Intensity" min={0.25} max={2} step={0.05} value={draft.intensity} display={draft.intensity.toFixed(2)} onChange={(intensity) => update({ intensity })} />
        </div>
      </section>

      <section className="panel mode-panel">
        <h2>
          <Sparkles size={15} /> Background series
        </h2>
        <Field label="Visual brief" hint="Interpreted as inspiration per slot — a coordinated series keeps one palette.">
          <TextInput value={draft.brief} onChange={(e) => update({ brief: e.target.value })} placeholder={track.form?.style || track.title} />
        </Field>
        <div className="kinetic-series-row">
          <Slider label="Images" min={2} max={24} value={draft.imageCount} onChange={(imageCount) => update({ imageCount })} />
          <Btn variant="primary" disabled={prod.submitting || renders.active} onClick={() => void generateSeries()}>
            {draft.imageCount} prompts · Generate
          </Btn>
        </div>
        <div className="asset-strip">
          {Array.from({ length: draft.imageCount }, (_, slot) => {
            const url = assetUrl(slot);
            const job = prod.jobs.find((j) => j.kind === "video-image" && j.input.slot === slot);
            return (
              <div key={slot} className={cn("asset-tile", !url && job && "pending")}>
                {url ? <img src={url} alt={`Background ${slot + 1}`} /> : <span>{slot + 1}</span>}
              </div>
            );
          })}
        </div>
        <p className="muted small">
          Placements: {placements.length} segments across {timeLabel(duration)} ·{" "}
          {draft.transition === "dissolve" ? "dissolves" : "hard cuts"} ·{" "}
          {draft.pan ? "slow pan" : "static frame"}
        </p>
      </section>

      <RenderCard
        title="Export"
        summary={`${draft.imageCount} backgrounds · ${draft.aspect} · 1080p · 24 fps · original soundtrack`}
        note={status || (!renders.available
          ? "Renderer offline — start the local app to queue MP4 exports."
          : `Renders on ${renders.renderer}. Keep the local app running until the MP4 is ready.`)}
        issue={issue}
        busy={busy || renders.active}
        error={error || prod.error}
        onRender={() => void render()}
        jobs={renders.jobs}
        onCancel={(job) => void renders.cancel(job).catch((e) => setError((e as Error).message))}
      />
    </>
  );
}
