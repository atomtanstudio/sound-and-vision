import { useEffect, useMemo, useRef, useState } from "react";
import { Image as ImageIcon, Pause, Play, Radio, Waves } from "lucide-react";
import { createRequestId, request } from "../../music-studio/api";
import { readLocal, writeLocal } from "../../music-studio/model";
import type { Track } from "../../music-studio/model";
import {
  alignedCues,
  currentLyricAlignment,
  makeDraft,
  makePlacements,
  type VideoDraft,
} from "../../video/timeline";
import type { Alignment } from "../../video/production";
import { VisualizerCanvas } from "../../video/visualizers/VisualizerCanvas";
import { SONG_REACTIVE_LABEL } from "../../video/visualizers/library";
import { useSongArtwork } from "../../video/visualizers/useSongArtwork";
import { mediaUrl, playable, useStudio } from "../context";
import { CoverArt } from "../components/CoverArt";
import {
  Btn,
  Empty,
  Field,
  Kicker,
  Modal,
  Segmented,
  TextInput,
  Toggle,
  cn,
} from "../ui";
import { useProduction } from "./video/useProduction";
import { LyricStage, StageBackground } from "./video/LyricStage";
import { VisualizerMode } from "./video/VisualizerMode";
import { KineticMode } from "./video/KineticMode";
import { CinematicMode } from "./video/CinematicMode";

type Kind = "visualizer" | "kinetic" | "cinematic";
const cinematicEnabled = import.meta.env.VITE_ENABLE_MUSIC_VIDEO === "true";

export function VideoPage() {
  const {
    tracks,
    videoSource,
    setVideoSource,
    navigate,
    playing,
    progress,
    duration: playerDuration,
    audioRef,
    status,
  } = useStudio();
  const track =
    tracks.find((t) => t.id === videoSource && !t.deletedAt) || null;
  const artwork = useSongArtwork(track?.id || "", !!track?.source);
  const [draft, setDraft] = useState<VideoDraft | null>(null);
  const [picking, setPicking] = useState(false);
  const [analysis, setAnalysis] = useState<{
    ready: boolean;
    progress: number;
    error?: string;
  }>({ ready: false, progress: 0 });
  const [visualError, setVisualError] = useState("");
  const draftKey = track ? `sv-video-draft-v1:${track.id}` : null;
  useEffect(() => {
    if (!track) return setDraft(null);
    const stored = draftKey
      ? readLocal<Partial<VideoDraft> | null>(draftKey, null)
      : null;
    const base = {
      ...makeDraft(track),
      kind: "visualizer" as const,
      reactiveMode: "song" as const,
      showLyrics: false,
      shade: 0,
    };
    setAnalysis({ ready: false, progress: 0 });
    setVisualError("");
    setDraft(
      stored
        ? {
            ...base,
            ...stored,
            reactiveMode:
              stored.reactiveMode ||
              (stored.visualizer && stored.visualizer !== "8"
                ? "classic"
                : "song"),
            cueEdits: stored.cueEdits || base.cueEdits,
            prompts: stored.prompts || base.prompts,
            wordEdits: stored.wordEdits || base.wordEdits,
          }
        : base,
    );
  }, [track?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const update = (part: Partial<VideoDraft>) =>
    setDraft((old) => {
      if (!old) return old;
      const next = { ...old, ...part };
      if (draftKey) writeLocal(draftKey, next);
      return next;
    });

  const prod = useProduction(track?.id || "", !!track?.source);
  const { current, playTrack, toggle } = useStudio();
  const activeSource =
    !!track && current === track.id ? playerDuration : track?.duration || 0;
  const duration = Math.max(1, activeSource || 0);
  const alignment = useMemo(() => {
    if (!draft || !track) return undefined;
    const job = [...prod.jobs]
      .reverse()
      .find((j) => j.kind === "lyric-alignment" && j.state === "succeeded");
    return currentLyricAlignment(
      draft,
      job ? (job.result as Alignment) : undefined,
    );
  }, [prod.jobs, draft, track]);
  const cues = useMemo(
    () => (draft ? alignedCues(alignment, draft) : []),
    [alignment, draft],
  );
  const placements = useMemo(
    () => (draft ? makePlacements(duration, draft) : []),
    [duration, draft],
  );
  const urls = useMemo(
    () =>
      draft
        ? Array.from(
            {
              length:
                draft.background === "images"
                  ? draft.imageCount
                  : draft.clipCount,
            },
            (_, slot) => {
              const j = [...prod.jobs]
                .reverse()
                .find(
                  (job) =>
                    job.kind === "video-image" &&
                    job.state === "succeeded" &&
                    job.input.slot === slot,
                );
              return j ? `/api/video/jobs/${j.id}/media` : undefined;
            },
          )
        : [],
    [prod.jobs, draft],
  );
  const scenes = artwork.jobs.filter(
    (j) =>
      j.state === "succeeded" &&
      j.input.aspect === draft?.aspect &&
      j.input.takeId === track?.id,
  );
  const scene =
    (scenes.find((j) => j.id === draft?.reactiveArtworkId) || scenes.at(-1))
      ?.result || undefined;
  const analyzesSong =
    draft?.reactiveMode !== "classic" ? !!scene && !scene.renderer : draft?.visualizer === "8";
  if (!track || !draft)
    return (
      <div className="video">
        <header className="page-head">
          <div>
            <Kicker>video suite</Kicker>
            <h1>Music video</h1>
          </div>
        </header>
        <Empty
          icon={<Radio size={22} />}
          title="Pick a soundtrack"
          body="Turn a finished song into a Song Reactive Visualizer, a kinetic lyric video, or a generated cinematic."
          action={
            <Btn variant="primary" onClick={() => setPicking(true)}>
              Choose a song
            </Btn>
          }
        />
        <SoundtrackPicker
          open={picking}
          tracks={tracks}
          onPick={(t) => {
            setVideoSource(t.id);
            setPicking(false);
          }}
          onClose={() => setPicking(false)}
          navigate={navigate}
        />
      </div>
    );

  const kind = draft.kind === "directed" ? "cinematic" : (draft.kind as Kind);
  const time = current === track.id ? progress : 0;
  const photographic = kind === "visualizer" && draft.reactiveMode !== "classic" && scene?.renderer === "reference-player-v1";
  return (
    <div className="video">
      <header className="page-head video-head">
        <button className="soundtrack" onClick={() => setPicking(true)}>
          <CoverArt track={track} className="soundtrack-cover" />
          <span>
            <strong>{track.title || "Untitled"}</strong>
            <small>{track.subtitle || "soundtrack"} · change</small>
          </span>
        </button>
        <div className="video-mode-row">
          <Segmented
            ariaLabel="Video kind"
            options={[
              { value: "visualizer", label: SONG_REACTIVE_LABEL },
              {
                value: "kinetic",
                label: "Kinetic",
                title: "Generated backgrounds + timed lyrics",
              },
              ...(cinematicEnabled
                ? [
                    {
                      value: "cinematic" as Kind,
                      label: "Cinematic",
                      title: "Guided AI music video",
                    },
                  ]
                : []),
            ]}
            value={kind === "cinematic" && !cinematicEnabled ? "kinetic" : kind}
            onChange={(next) => update({ kind: next })}
          />
          <Segmented
            ariaLabel="Aspect ratio"
            size="sm"
            options={[
              { value: "16:9", label: "16:9" },
              { value: "9:16", label: "9:16" },
            ]}
            value={draft.aspect}
            onChange={(aspect) => update({ aspect })}
          />
        </div>
      </header>

      <div className="video-grid">
        <section className="stage-col">
          <div
            className={cn("stage", draft.aspect === "9:16" && "portrait")}
            style={{ containerType: "inline-size" }}
          >
            {kind === "visualizer" ? (
              draft.reactiveMode !== "classic" && !scene ? (
                <div className="song-scene-empty">
                  <CoverArt track={track} />
                  <p>
                    Your song’s scene starts with its story.
                    <small>
                      Create artwork to preview the reactive composition.
                    </small>
                  </p>
                </div>
              ) : photographic ? (
                <img className="song-artwork-still" src={scene.artworkUrl} alt={scene.concept}
                  style={{ filter: `brightness(${1-.0085*draft.shade})` }} />
              ) : (
                <VisualizerCanvas
                  scene={draft.reactiveMode !== "classic" ? scene : undefined}
                  audioRef={audioRef}
                  analysisUrl={
                    mediaUrl(track, track.source ? "flac" : "mp3") || undefined
                  }
                  active={current === track.id}
                  playing={playing}
                  time={time}
                  preset={0}
                  selection={draft.visualizer}
                  duration={duration}
                  strength={draft.visualizerStrength}
                  onAnalysis={setAnalysis}
                  onError={setVisualError}
                  onReady={() => setVisualError("")}
                />
              )
            ) : (
              <StageBackground
                draft={draft}
                cues={cues}
                time={time}
                placements={placements}
                urls={urls}
              />
            )}
            {!photographic && <LyricStage
              draft={draft}
              cues={cues}
              time={time}
              title={track.title}
              aligned={!!alignment}
            />}
            {!photographic && <div className="stage-badge">
              <Kicker>
                {kind === "visualizer"
                  ? SONG_REACTIVE_LABEL
                  : kind === "kinetic"
                    ? "Kinetic backgrounds"
                    : "Cinematic"}
              </Kicker>
            </div>}
            <button
              className={cn(
                "stage-play",
                playing && current === track.id && "on",
              )}
              aria-label={
                playing && current === track.id ? "Pause" : photographic ? "Play soundtrack" : "Play preview"
              }
              onClick={() => {
                if (current === track.id) toggle();
                else playTrack(track);
              }}
            >
              {playing && current === track.id ? (
                <Pause size={22} fill="currentColor" />
              ) : (
                <Play size={22} fill="currentColor" />
              )}
            </button>
          </div>
          {photographic && <p className="small muted">Artwork preview. Use “Preview motion” to watch an 8-second sample before rendering the full song.</p>}
          <div className="video-controls">
            <Waves size={15} aria-hidden="true" />
            <span className="mono">{mmss(time)}</span>
            <input
              type="range"
              aria-label="Video timeline"
              min={0}
              max={duration}
              step={0.5}
              value={Math.min(time, duration)}
              onChange={(e) => {
                const audio = audioRef.current;
                if (audio && current === track.id)
                  audio.currentTime = Number(e.target.value);
              }}
            />
            <span className="mono">{mmss(duration)}</span>
          </div>
          <Toggle
            label="Show lyrics"
            checked={draft.showLyrics}
            onChange={(showLyrics) => update({ showLyrics })}
          />
          {kind === "kinetic" ? (
            <div className="bg-toggle">
              <Segmented
                ariaLabel="Backgrounds"
                size="sm"
                options={[
                  { value: "images", label: "Image series" },
                  { value: "motion", label: "Motion clips" },
                ]}
                value={draft.background}
                onChange={(background) => update({ background })}
              />
              <label className="inline-text">
                <Kicker>Palette / treatment</Kicker>
                <TextInput
                  value={draft.brief}
                  placeholder={track.form?.style || track.title}
                  onChange={(e) => update({ brief: e.target.value })}
                />
              </label>
            </div>
          ) : null}
        </section>

        <aside className="video-panels">
          {!status?.connected ? (
            <div className="panel offline-panel">
              <Kicker>Engine</Kicker>
              <p>
                The music engine is offline. You can still preview visualizers
                against demo soundtracks.
              </p>
            </div>
          ) : null}
          {kind === "visualizer" &&
            (visualError || (analyzesSong && analysis.error)) && (
              <p role="alert" className="small muted">
                {visualError || analysis.error}
              </p>
            )}
          {kind === "visualizer" &&
            analyzesSong &&
            !analysis.ready &&
            !analysis.error && (
              <p role="status" className="small muted">
                Reading your song… {Math.round(analysis.progress * 100)}%
              </p>
            )}
          {kind === "visualizer" ? (
            <VisualizerMode
              track={track}
              draft={draft}
              update={update}
              duration={duration}
              cues={cues}
              artwork={artwork}
              scene={scene}
              pauseSoundtrack={() => { if (playing) toggle(); }}
            />
          ) : kind === "kinetic" ? (
            <KineticMode
              track={track}
              draft={draft}
              update={update}
              duration={duration}
              prod={prod}
              cues={cues}
              alignment={alignment}
            />
          ) : (
            <CinematicMode
              track={track}
              duration={duration}
              aspect={draft.aspect}
              lyrics={draft.lyrics || track.form?.lyrics || ""}
              language={draft.language}
              cues={cues}
            />
          )}
        </aside>
      </div>
      <SoundtrackPicker
        open={picking}
        tracks={tracks}
        onPick={(t) => {
          setVideoSource(t.id);
          setPicking(false);
        }}
        onClose={() => setPicking(false)}
        navigate={navigate}
      />
    </div>
  );
}

const mmss = (s: number) =>
  `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

function SoundtrackPicker({
  open,
  tracks,
  onPick,
  onClose,
  navigate,
}: {
  open: boolean;
  tracks: Track[];
  onPick: (t: Track) => void;
  onClose: () => void;
  navigate: (p: "music") => void;
}) {
  const finished = tracks.filter((t) => playable(t) && !t.deletedAt);
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Soundtrack"
      subtitle="Pick any finished song to build a video around."
    >
      {finished.length ? (
        <div className="picker-list">
          {finished.map((t) => (
            <button key={t.id} className="picker-row" onClick={() => onPick(t)}>
              <CoverArt track={t} className="picker-cover" />
              <span>
                <strong>{t.title || "Untitled"}</strong>
                <small>
                  {t.project} · {t.subtitle || "demo session"}
                </small>
              </span>
              <ImageIcon size={15} aria-hidden="true" />
            </button>
          ))}
        </div>
      ) : (
        <Empty
          icon={<Play size={20} />}
          title="No finished songs yet"
          body="Import audio or generate a take, then return."
          action={
            <Btn variant="primary" onClick={() => navigate("music")}>
              To the console
            </Btn>
          }
        />
      )}
    </Modal>
  );
}
