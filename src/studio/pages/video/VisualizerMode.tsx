import { useState } from "react";
import type { Track } from "../../../music-studio/model";
import type { LyricCue, VideoDraft } from "../../../video/timeline";
import { classicVisualizerPresets } from "../../../video/visualizers/library";
import type { SongScene } from "../../../video/visualizers/scene";
import type { SongArtworkController } from "../../../video/visualizers/useSongArtwork";
import { presetNumber } from "../../../video/visualizers/schedule";
import { Btn, Field, Modal, Slider, TextArea, cn } from "../../ui";
import { RenderCard } from "./RenderCard";
import { localApi, useLocalRenders, type ExportJob } from "./export-api";

export function VisualizerMode({
  track,
  draft,
  update,
  duration,
  cues,
  artwork,
  scene,
  pauseSoundtrack,
}: {
  track: Track;
  draft: VideoDraft;
  update: (part: Partial<VideoDraft>) => void;
  duration: number;
  cues: LyricCue[];
  artwork: SongArtworkController;
  scene?: SongScene;
  pauseSoundtrack: () => void;
}) {
  const renders = useLocalRenders(
    "visualizer-renders",
    track.id,
    !!track.source,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [watching, setWatching] = useState<ExportJob | null>(null);
  const songMode = draft.reactiveMode !== "classic";
  const photographic = songMode && scene?.renderer === "reference-player-v1";
  const genre =
    draft.reactiveGenre ??
    (track.form?.style || track.form?.description || track.form?.genre || "");
  const latest = artwork.jobs.at(-1);
  const selectedJob = artwork.jobs.find(
    (j) => j.result?.artworkJobId === scene?.artworkJobId,
  );
  const changed =
    selectedJob &&
    (selectedJob.input.song.genre.trim() !== genre.trim() ||
      selectedJob.input.song.lyrics.trim() !== draft.lyrics.trim() ||
      selectedJob.input.song.notes !== (draft.reactiveNotes || ""));
  const selection =
    draft.visualizer === "all" ? "all" : String(presetNumber(draft.visualizer));
  const pick = (value: string) =>
    update({
      visualizer: value as VideoDraft["visualizer"],
      reactiveMode: "classic",
    });
  const issue =
    !track.source || track.status !== "succeeded"
      ? "Choose a finished song from your library to render."
      : songMode && !scene
        ? "Create your song’s artwork before rendering."
        : songMode && changed
          ? "The song details have changed. Create new artwork to use them."
          : photographic && !renders.referencePlayer
            ? "The photographic player renderer needs its matching server update."
          : photographic && draft.showLyrics
            ? "Turn off Show lyrics for this photographic player. Your lyric sheet still guides the artwork."
          : songMode && !renders.songScenes
            ? "The renderer needs the matching song-artwork update before exporting this scene."
            : !renders.available
              ? "The video renderer is offline."
              : draft.showLyrics && draft.lyrics.trim() && !cues.length
                ? "Align the lyrics first, or turn “Show lyrics” off to render just the visualizer."
                : "";
  async function render(preview = false) {
    setBusy(true);
    setError("");
    const body = {
      takeId: track.id,
      duration,
      ...(preview ? { preview: true } : {}),
      draft: songMode
        ? {
            ...draft,
            visualizer: "8",
            reactiveMode: "song",
            reactiveArtworkId: scene?.artworkJobId,
          }
        : draft,
      cues: draft.showLyrics ? cues : [],
    };
    try {
      const job = await localApi<ExportJob>("visualizer-renders", "", {
        ...body,
        requestId: renders.requestIdFor(body),
      });
      renders.mergeJob(job);
      renders.rememberDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <section className="panel mode-panel">
        <h2>A scene for your song</h2>
        <p className="muted small">
          Your genre, lyrics, and mood guide the artwork and where the motion
          belongs. The recording drives the animation.
        </p>
        {!songMode && (
          <Btn
            variant="quiet"
            onClick={() =>
              update({ reactiveMode: "song", visualizer: "8", shade: 0 })
            }
          >
            Create a scene for this song
          </Btn>
        )}
        {songMode && (
          <>
            <Field
              label="Genre & mood"
              hint="Starts with your saved song description. Add anything the artwork should understand."
            >
              <TextArea
                rows={4}
                value={genre}
                onChange={(e) => update({ reactiveGenre: e.target.value })}
                placeholder="Describe the song’s genre and atmosphere…"
              />
            </Field>
            <Field
              label="Lyric sheet"
              hint="Used to understand the song, even when lyrics are hidden in the video."
            >
              <TextArea
                rows={5}
                value={draft.lyrics}
                onChange={(e) => update({ lyrics: e.target.value })}
                placeholder="Lyrics give the scene its story…"
              />
            </Field>
            <Field
              label="Anything to include or avoid?"
              hint="Optional creative guidance."
            >
              <TextArea
                rows={2}
                value={draft.reactiveNotes || ""}
                onChange={(e) => update({ reactiveNotes: e.target.value })}
                placeholder="A place, memory, color, or detail that matters…"
              />
            </Field>
            <Btn
              variant="primary"
              loading={artwork.submitting || artwork.active}
              disabled={
                !artwork.available ||
                artwork.submitting ||
                artwork.active ||
                (!genre.trim() && !draft.lyrics.trim())
              }
              onClick={() => {
                update({
                  reactiveArtworkId: undefined,
                  visualizer: "8",
                  shade: 0,
                });
                void artwork.create({
                  aspect: draft.aspect,
                  genre,
                  lyrics: draft.lyrics,
                  notes: draft.reactiveNotes || "",
                });
              }}
            >
              {scene ? "Create another version" : "Create song artwork"}
            </Btn>
            {artwork.active && (
              <p role="status" className="small muted">
                {latest?.result?.phase || "Preparing your song’s scene…"}
              </p>
            )}
            {(artwork.error || latest?.error) && (
              <p role="alert" className="error-note">
                {artwork.error || latest?.error}
              </p>
            )}
            {scene && (
              <div className="song-scene-reason">
                <strong>{scene.concept}</strong>
                <p className="small muted">{scene.reasoning}</p>
                <details>
                  <summary>Why this fits the song</summary>
                  <ul>
                    {scene.evidence.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                </details>
              </div>
            )}
            {artwork.jobs.filter(
              (j) => j.state === "succeeded" && j.input.aspect === draft.aspect,
            ).length > 1 && (
              <details className="song-art-history">
                <summary>Previous artwork</summary>
                {artwork.jobs
                  .filter(
                    (j) =>
                      j.state === "succeeded" &&
                      j.input.aspect === draft.aspect,
                  )
                  .map((j, i) => (
                    <button
                      key={j.id}
                      className={cn(
                        "preset",
                        scene?.artworkJobId === j.id && "on",
                      )}
                      onClick={() =>
                        update({
                          reactiveArtworkId: j.id,
                          reactiveGenre: j.input.song.genre,
                          lyrics: j.input.song.lyrics,
                          reactiveNotes: j.input.song.notes,
                        })
                      }
                    >
                      <strong>Version {i + 1}</strong>
                      <span>{j.result?.concept}</span>
                    </button>
                  ))}
              </details>
            )}
          </>
        )}
        <details className="classic-styles" open={!songMode || undefined}>
          <summary>
            Classic collection <span>8 styles</span>
          </summary>
          <div className="preset-grid">
            <button
              className={cn("preset", !songMode && selection === "all" && "on")}
              onClick={() => pick("all")}
              aria-pressed={!songMode && selection === "all"}
            >
              <em>full journey</em>
              <strong>All eight classics</strong>
              <span>Equal time across the song</span>
            </button>
            {classicVisualizerPresets.map((preset) => (
              <button
                key={preset.id}
                className={cn(
                  "preset",
                  !songMode && selection === String(preset.id) && "on",
                )}
                onClick={() => pick(String(preset.id))}
                aria-pressed={!songMode && selection === String(preset.id)}
              >
                <strong>{preset.name}</strong>
                <span>{preset.description}</span>
              </button>
            ))}
          </div>
        </details>
        <Slider
          label="Reactivity"
          min={0.25}
          max={2}
          step={0.05}
          value={draft.visualizerStrength}
          display={`${Math.round(draft.visualizerStrength * 100)}%`}
          onChange={(visualizerStrength) => update({ visualizerStrength })}
        />
        {!songMode && (
          <Field
            label="Lyric sheet"
            hint="Used when “Show lyrics” is on. Paste lyrics, then align them on the Kinetic tab for word-perfect timing."
          >
            <TextArea
              rows={3}
              placeholder={track.form?.lyrics || "Optional lyrics…"}
              value={draft.lyrics}
              onChange={(e) => update({ lyrics: e.target.value })}
            />
          </Field>
        )}
      </section>
      <RenderCard
        title="Export"
        summary={
          songMode
            ? `Song artwork · ${draft.aspect} · 1080p · ${photographic ? 30 : 24} fps`
            : selection === "all"
              ? "Classic collection · 1080p · 24 fps"
              : `${classicVisualizerPresets[Math.min(7, presetNumber(selection))].name} · ${draft.aspect} · 1080p · 24 fps`
        }
        note={
          !renders.available
            ? "Renderer offline — start the local app to queue MP4 exports."
            : `Renders in the background on ${renders.renderer}. The finished MP4 appears here and in your Library.`
        }
        issue={issue}
        busy={busy || renders.active}
        error={error || renders.connectionError}
        onRender={() => void render()}
        onPreview={photographic ? () => void render(true) : undefined}
        onPlay={(job) => { pauseSoundtrack(); setWatching(job); }}
        jobs={renders.jobs}
        onCancel={(job) =>
          void renders.cancel(job).catch((e) => setError((e as Error).message))
        }
      />
      <Modal open={!!watching} onClose={() => setWatching(null)} title={watching?.preview ? "Motion preview" : "Rendered video"}
        subtitle={watching?.title}>
        {watching?.videoUrl && <video key={watching.id} className="song-motion-preview" src={watching.videoUrl} controls playsInline />}
      </Modal>
    </>
  );
}
