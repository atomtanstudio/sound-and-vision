import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type RefObject,
} from "react";
import {
  Type,
  AudioLines,
  Clapperboard,
  Image as ImageIcon,
  Film,
  Monitor,
  Smartphone,
  Play,
  Pause,
  Upload,
  Download,
  ChevronDown,
  Check,
  Undo2,
  Redo2,
  X,
  MoveLeft,
  MoveRight,
  Music2,
} from "lucide-react";
import { readLocal, writeLocal, type Track } from "../music-studio/model";
import {
  FPS,
  makeDraft,
  makePlacements,
  alignedCues,
  cueAt,
  placementAt,
  timeLabel,
  backgroundPrompt,
  videoManifest,
  timingIssues,
  framesFor,
  type VideoDraft,
} from "./timeline";
import {
  loadAssets,
  saveAssets,
  removeAsset,
  type ImportedAsset,
} from "./assets";
import "./video.css";
import { useVideoProduction, busyJob, type Alignment } from "./production";
import { wordMotion } from "./kinetics";
import { WordTimingEditor } from "./WordTimingEditor";
import { VisualizerCanvas } from "./visualizers/VisualizerCanvas";
import { LyricOverlay } from "./visualizers/LyricOverlay";
import { VisualizerExports } from "./visualizers/VisualizerExports";
import {
  presetNumber,
  visualizerFrame,
  visualizerSchedule,
} from "./visualizers/schedule";
import { DirectedVideoWorkspace } from "./DirectedVideoWorkspace";
import {
  originalVisualizerPresets,
  visualizerPreviewUrl,
} from "./visualizers/library";
import "@fontsource-variable/newsreader/wght-italic.css";

type AssetPreview = Omit<ImportedAsset, "blob"> & {
  url: string;
  blob?: Blob;
  generated?: boolean;
};
type Props = {
  imported: (track: Track) => void;
  tracks: Track[];
  sourceId: string;
  chooseSource: (id: string) => void;
  currentId: string;
  playing: boolean;
  progress: number;
  audioRef: RefObject<HTMLAudioElement | null>;
  play: (track: Track) => void;
  seek: (track: Track, seconds: number) => void;
};
const playable = (track: Track) =>
  !track.deletedAt && !!(track.audio || track.audioUrl);
const length = (track: Track) => (track.source ? track.duration || 0 : 240);
const musicVideoAvailable = import.meta.env.VITE_ENABLE_MUSIC_VIDEO === "true";

const options = [
  {
    id: "kinetic",
    title: "Kinetic lyric video",
    note: "Animated words over images or clips",
    icon: Type,
  },
  {
    id: "visualizer",
    title: "Visualizer video",
    note: "Audio-reactive visuals, optional lyrics",
    icon: AudioLines,
  },
  {
    id: "directed",
    title: "Music video",
    note: musicVideoAvailable
      ? "A treatment, storyboard and scenes"
      : "Coming soon",
    icon: Clapperboard,
  },
] as const;

export function VideoWorkspace(props: Props) {
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState("");
  async function importSong(file?: File) {
    if (!file || importing) return;
    if (file.size > 100 * 1024 * 1024) {
      setImportError("Choose a song smaller than 100 MB.");
      return;
    }
    setImporting(true);
    setImportError("");
    try {
      const response = await fetch("/api/songs/import", {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-Filename": encodeURIComponent(file.name),
        },
        body: file,
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Song import failed.",
        );
      props.imported(data);
    } catch (e) {
      setImportError((e as Error).message);
    } finally {
      setImporting(false);
    }
  }
  const importer = (
    <div className="song-import-bar">
      <label className="secondary-button">
        {importing ? "Importing song…" : "Import song"}
        <input
          aria-label="Import song"
          type="file"
          accept=".wav,.flac,.mp3,.m4a,.ogg"
          disabled={importing}
          onChange={(e) => {
            void importSong(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </label>
      <span>
        Use your own audio · WAV, FLAC, MP3, M4A, OGG · up to 100 MB / 10
        minutes
      </span>
      {importError && <p role="alert">{importError}</p>}
    </div>
  );
  const tracks = props.tracks.filter(playable);
  const track = tracks.find((t) => t.id === props.sourceId) || tracks[0];
  if (!track)
    return (
      <div className="video-empty">
        <Clapperboard size={32} />
        <h1>Make a video</h1>
        <p>Import an existing song or choose a finished song from Music.</p>
        {importer}
      </div>
    );
  return (
    <>
      <div>{importer}</div>
      <VideoEditor key={track.id} {...props} tracks={tracks} track={track} />
    </>
  );
}
function restoreDraft(track: Track): VideoDraft {
  const base = makeDraft(track),
    saved = readLocal<Partial<VideoDraft>>(`sv-video-draft-v1:${track.id}`, {});
  if (saved.version !== 1) return base;
  const draft = { ...base, ...saved };
  for (const key of [
    "imageCount",
    "imageCycles",
    "clipCount",
    "clipSeconds",
    "intro",
    "outro",
    "textSize",
    "shade",
  ] as const)
    if (!Number.isFinite(draft[key])) draft[key] = base[key];
  draft.imageCount = Math.max(1, Math.min(100, Math.round(draft.imageCount)));
  draft.imageCycles = Math.max(1, Math.min(8, Math.round(draft.imageCycles)));
  draft.clipCount = Math.max(1, Math.min(24, Math.round(draft.clipCount)));
  draft.clipSeconds = Math.max(4, Math.min(15, draft.clipSeconds));
  draft.kind = ["kinetic", "visualizer", "directed"].includes(draft.kind)
    ? draft.kind
    : base.kind;
  draft.aspect = draft.aspect === "9:16" ? "9:16" : "16:9";
  draft.background = draft.background === "motion" ? "motion" : "images";
  draft.lyrics = typeof draft.lyrics === "string" ? draft.lyrics : base.lyrics;
  draft.brief = typeof draft.brief === "string" ? draft.brief : base.brief;
  draft.prompts =
    draft.prompts && typeof draft.prompts === "object" ? draft.prompts : {};
  draft.cueEdits =
    draft.cueEdits && typeof draft.cueEdits === "object" ? draft.cueEdits : {};
  draft.wordEdits =
    draft.wordEdits && typeof draft.wordEdits === "object"
      ? draft.wordEdits
      : {};
  draft.intensity = Number.isFinite(draft.intensity)
    ? Math.max(0.5, Math.min(1.5, draft.intensity))
    : 1;
  draft.visualizerStrength = Number.isFinite(draft.visualizerStrength)
    ? Math.max(0.25, Math.min(2, draft.visualizerStrength))
    : 1;
  if (!saved.motionVersion) {
    draft.lyricMotion = "auto";
    draft.motionVersion = 2;
  }
  return draft;
}
function VideoEditor({
  track,
  tracks,
  sourceId,
  chooseSource,
  currentId,
  playing,
  progress,
  audioRef,
  play,
  seek,
}: Props & { track: Track }) {
  const [draft, setDraft] = useState(() => {
    const restored = restoreDraft(track);
    if (new URLSearchParams(location.search).has("film"))
      restored.kind = "directed";
    return restored;
  });
  const production = useVideoProduction(track.id);
  const alignmentJob = [...production.jobs]
    .reverse()
    .find(
      (j) =>
        j.kind === "lyric-alignment" &&
        j.state === "succeeded" &&
        j.input.lyrics.trim() === draft.lyrics.trim() &&
        j.input.language === draft.language,
    );
  const alignment = alignmentJob?.result as Alignment | undefined;
  const alignmentBusy = production.jobs.some(
    (j) => j.kind === "lyric-alignment" && busyJob(j),
  );
  const transcription = [...production.jobs]
    .reverse()
    .find(
      (j) =>
        j.kind === "lyric-transcription" &&
        j.state === "succeeded" &&
        j.input.language === draft.language,
    );
  const transcriptionBusy = production.jobs.some(
    (j) => j.kind === "lyric-transcription" && busyJob(j),
  );
  const [reviewLyrics, setReviewLyrics] = useState("");
  useEffect(() => {
    setReviewLyrics(transcription?.result?.lyrics || "");
  }, [transcription?.id, transcription?.result?.lyrics]);
  const [status, setStatus] = useState("Draft saved in this browser");
  const history = useRef<{ past: VideoDraft[]; future: VideoDraft[] }>({
    past: [],
    future: [],
  });
  const [, setHistoryTick] = useState(0);
  const [assets, setAssets] = useState<AssetPreview[]>([]);
  const urls = useRef<string[]>([]),
    alive = useRef(true);
  const [assetBusy, setAssetBusy] = useState(false),
    [assetError, setAssetError] = useState("");
  const [selectedAsset, setSelectedAsset] = useState(0),
    [showGuides, setShowGuides] = useState(false);
  const [clock, setClock] = useState(currentId === track.id ? progress : 0);
  const [measuredDuration, setMeasuredDuration] = useState<number | null>(null);
  const [reduceMotion, setReduceMotion] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const input = useRef<HTMLInputElement>(null),
    replaceSlot = useRef<number | null>(null);
  const duration = measuredDuration || length(track);
  const active = currentId === track.id;
  const previewPlaying = active && playing;
  const visualizerPreset = presetNumber(draft.visualizer);
  const position = active ? clock : 0;
  const frame = Math.min(
    visualizerFrame(position, FPS),
    Math.max(0, framesFor(duration) - 1),
  );
  const remoteAssets = new Map<string, AssetPreview>();
  for (const job of production.jobs) {
    if (
      job.state === "succeeded" &&
      job.result?.assetUrl &&
      job.input.aspect === draft.aspect
    ) {
      const kind = job.input.kind as "images" | "motion";
      remoteAssets.set(`${kind}:${job.input.slot}`, {
        id: job.id,
        trackId: track.id,
        kind,
        slot: job.input.slot,
        name: job.result.name || "Generated background",
        url: job.result.assetUrl,
        generated: true,
        created: job.created,
      });
    }
  }
  const combinedAssets = new Map(remoteAssets);
  for (const asset of assets) {
    const key = `${asset.kind}:${asset.slot}`;
    if (
      !combinedAssets.has(key) ||
      (asset.created || 0) > (combinedAssets.get(key)?.created || 0)
    )
      combinedAssets.set(key, asset);
  }
  const allAssets = [...combinedAssets.values()];
  const placements = makePlacements(duration, draft),
    cues = alignedCues(alignment, draft);
  const reviewCount =
    alignment?.cues.reduce(
      (n, line) =>
        n +
        line.words.filter(
          (w, i) =>
            w.review &&
            !(
              draft.wordEdits[`${line.id}:${i}`]?.start != null &&
              draft.wordEdits[`${line.id}:${i}`]?.end != null
            ),
        ).length,
      0,
    ) || 0;
  const missingWordCount =
    alignment?.cues.reduce(
      (n, line) =>
        n +
        line.words.filter((word, i) => {
          const w = draft.wordEdits[`${line.id}:${i}`] ?? word;
          return w.start == null || w.end == null;
        }).length,
      0,
    ) ?? 0;
  const timingErrors = timingIssues(cues, duration);
  const placementIndex = placementAt(placements, frame);
  const currentPlacement = placements[Math.max(0, placementIndex)];
  const currentAsset = currentPlacement?.assetIndex || 0;
  const assetCount =
    draft.background === "images" ? draft.imageCount : draft.clipCount;
  const displaySlot = Math.min(selectedAsset, assetCount - 1);
  const currentMedia = allAssets.find(
    (a) => a.kind === draft.background && a.slot === currentAsset,
  );
  const cue = cueAt(cues, frame);
  const cueProgress = cue
    ? Math.max(
        0,
        Math.min(
          1,
          (frame - cue.startFrame) / Math.max(1, cue.endFrame - cue.startFrame),
        ),
      )
    : 0;
  const words = cue?.text.split(/\s+/) || [];
  const wordIndex =
    cue?.words?.findIndex(
      (w) =>
        w.start !== null &&
        w.end !== null &&
        position >= w.start &&
        position < w.end,
    ) ?? -1;
  const effect =
    draft.lyricMotion === "auto"
      ? ["pop", "slam", "rise"][Number(cue?.id.split("-")[1] || 0) % 3]
      : draft.lyricMotion;
  const elapsedInPlacement =
    (frame - (currentPlacement?.startFrame || 0)) / FPS;
  const visualLyrics =
    draft.kind === "kinetic" ||
    (draft.kind === "visualizer" && draft.showLyrics);
  const nextPlacement = placements[placementIndex + 1];
  const nextMedia = allAssets.find(
    (a) => a.kind === draft.background && a.slot === nextPlacement?.assetIndex,
  );
  const fadeFrames =
    draft.transition === "dissolve" && nextPlacement
      ? Math.min(
          14,
          Math.floor(
            ((currentPlacement?.endFrame || 0) -
              (currentPlacement?.startFrame || 0)) /
              3,
          ),
        )
      : 0;
  const fade = fadeFrames
    ? Math.max(
        0,
        Math.min(
          1,
          (frame - ((currentPlacement?.endFrame || 0) - fadeFrames)) /
            fadeFrames,
        ),
      )
    : 0;
  const previous = placements[placementIndex - 1];
  const sourceOffset =
    draft.transition === "dissolve" && previous
      ? Math.min(
          14,
          Math.floor((previous.endFrame - previous.startFrame) / 3),
        ) / FPS
      : 0;

  useEffect(() => {
    setStatus(
      writeLocal(`sv-video-draft-v1:${track.id}`, draft)
        ? "Draft saved in this browser"
        : "Draft could not be saved. Download a copy.",
    );
  }, [draft, track.id]);
  useEffect(() => {
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setReduceMotion(mq.matches);
    mq.addEventListener("change", change);
    return () => mq.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    setClock(active ? progress : 0);
    if (!active || !playing) return;
    let request = 0;
    const tick = () => {
      setClock(audioRef.current?.currentTime || 0);
      request = requestAnimationFrame(tick);
    };
    request = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(request);
  }, [active, playing, progress, audioRef]);
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !active) return;
    const update = () => {
      if (Number.isFinite(audio.duration) && audio.duration > 0)
        setMeasuredDuration(audio.duration);
    };
    update();
    audio.addEventListener("loadedmetadata", update);
    return () => audio.removeEventListener("loadedmetadata", update);
  }, [active, audioRef]);
  async function refreshAssets() {
    const files = await loadAssets(track.id);
    if (!alive.current) return;
    const next = files.map((file) => ({
      ...file,
      url: URL.createObjectURL(file.blob),
    }));
    const old = urls.current;
    urls.current = next.map((file) => file.url);
    setAssets(next);
    old.forEach((url) => URL.revokeObjectURL(url));
  }
  useEffect(() => {
    alive.current = true;
    void refreshAssets().catch(() =>
      setAssetError(
        "This browser could not open saved media. Your editing controls still work.",
      ),
    );
    return () => {
      alive.current = false;
      urls.current.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [track.id]);
  function change(patch: Partial<VideoDraft>) {
    if (patch.kind && patch.kind !== "directed") {
      const url = new URL(location.href);
      url.searchParams.delete("film");
      window.history.replaceState(null, "", url);
    }
    if (sourceId !== track.id) chooseSource(track.id);
    history.current.past.push(draft);
    if (history.current.past.length > 40) history.current.past.shift();
    history.current.future = [];
    setHistoryTick((n) => n + 1);
    setDraft({ ...draft, ...patch });
  }
  function undo(redo = false) {
    const from = redo ? history.current.future : history.current.past,
      to = redo ? history.current.past : history.current.future;
    const next = from.pop();
    if (!next) return;
    to.push(draft);
    setDraft(next);
    setHistoryTick((n) => n + 1);
  }
  async function importMedia(files: FileList | null) {
    if (!files?.length) return;
    if (sourceId !== track.id) chooseSource(track.id);
    setAssetError("");
    setAssetBusy(true);
    try {
      const kind = draft.background,
        start =
          replaceSlot.current ??
          allAssets
            .filter((a) => a.kind === kind)
            .reduce((max, a) => Math.max(max, a.slot + 1), 0);
      const selected = replaceSlot.current === null ? [...files] : [files[0]];
      if (start + selected.length > 100)
        throw new Error("Import up to 100 background assets per song.");
      if (
        selected.some((file) =>
          kind === "images"
            ? !/^image\/(png|jpeg|webp)$/.test(file.type)
            : !/^video\/(mp4|webm|quicktime)$/.test(file.type),
        )
      )
        throw new Error(
          kind === "images"
            ? "Use PNG, JPG or WebP images."
            : "Use MP4, WebM or MOV clips supported by your browser.",
        );
      if (
        selected.some(
          (file) => file.size > (kind === "images" ? 25 : 150) * 1024 * 1024,
        )
      )
        throw new Error(
          kind === "images"
            ? "Keep each image under 25 MB."
            : "Keep each preview clip under 150 MB.",
        );
      await saveAssets(
        selected.map((file, index) => ({
          id: `${track.id}:${kind}:${start + index}`,
          trackId: track.id,
          kind,
          slot: start + index,
          name: file.name,
          blob: file,
          created: Date.now(),
        })),
      );
      if (!alive.current) return;
      if (start + selected.length > assetCount)
        change(
          kind === "images"
            ? { imageCount: start + selected.length }
            : { clipCount: start + selected.length },
        );
      await refreshAssets();
    } catch (error) {
      if (alive.current) setAssetError((error as Error).message);
    } finally {
      if (alive.current) setAssetBusy(false);
      if (input.current) input.current.value = "";
      replaceSlot.current = null;
    }
  }
  function downloadPlan() {
    const manifest = videoManifest(
      track,
      draft,
      duration,
      allAssets.map(({ id, name, kind, slot, generated, url }) => ({
        id,
        name,
        kind,
        slot,
        generated,
        ...(generated ? { url } : {}),
      })),
      alignment,
    );
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(manifest, null, 2)], {
        type: "application/json",
      }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${track.title.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-video-plan.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const selectedPromptKey = `${draft.background}-${displaySlot}`;
  const prompt =
    draft.prompts[selectedPromptKey] ??
    backgroundPrompt(track, draft, displaySlot);
  const selectedMedia = allAssets.find(
    (a) => a.kind === draft.background && a.slot === displaySlot,
  );
  const backgroundBusy = production.jobs.some(
    (j) => j.input.kind === draft.background && busyJob(j),
  );
  async function generateBackgrounds(onlySlot?: number) {
    const slots =
      onlySlot === undefined
        ? Array.from({ length: assetCount }, (_, i) => i).filter(
            (i) =>
              !allAssets.some(
                (a) => a.kind === draft.background && a.slot === i,
              ),
          )
        : [onlySlot];
    await production.submit(
      slots.map((slot) => ({
        kind: draft.background,
        slot,
        aspect: draft.aspect,
        seconds: draft.clipSeconds,
        lyrics: draft.lyrics,
        language: draft.language,
        prompt:
          draft.prompts[`${draft.background}-${slot}`] ??
          backgroundPrompt(track, draft, slot),
      })),
    );
  }
  async function alignLyrics() {
    change({ wordEdits: {}, cueEdits: {} });
    await production.submit([
      {
        kind: "alignment",
        slot: 0,
        aspect: draft.aspect,
        seconds: 8,
        lyrics: draft.lyrics,
        prompt: "",
        language: draft.language,
      },
    ]);
  }
  const latestJobs = new Map<string, (typeof production.jobs)[number]>();
  for (const job of production.jobs)
    if (job.input.aspect === draft.aspect || job.kind === "lyric-alignment")
      latestJobs.set(`${job.kind}:${job.input.slot}`, job);
  const visibleJobs = [...latestJobs.values()].filter(
    (j) => busyJob(j) || j.state === "failed",
  );
  const perImage = duration / Math.max(1, draft.imageCount * draft.imageCycles);
  if (["directed"].includes(draft.kind))
    return (
      <div className="video-workspace">
        <div className="video-heading">
          <div>
            <h1>Music video</h1>
            <p>
              {track.title} <span>/</span> Scenes, review, and export
            </p>
          </div>
        </div>
        <fieldset className="video-kind-switch">
          <legend className="sr-only">Video type</legend>
          {options.map(({ id, title, note, icon: Icon }) => (
            <label key={id} className={draft.kind === id ? "chosen" : ""}>
              <input
                type="radio"
                name="video-kind"
                aria-label={title}
                disabled={id === "directed" && !musicVideoAvailable}
                checked={draft.kind === id}
                onChange={() => change({ kind: id })}
              />
              <Icon size={21} />
              <span>
                <strong>{title}</strong>
                <small>{note}</small>
              </span>
              <span className="video-radio-dot" />
            </label>
          ))}
        </fieldset>
        {!musicVideoAvailable ? (
          <section
            className="video-coming-soon"
            aria-label="Music video coming soon"
          >
            <Clapperboard size={32} />
            <h2>
              Music video <span className="coming-soon-tag">Coming soon</span>
            </h2>
            <p>
              We’re refining scene generation and character consistency.
              Existing projects are saved and will be available when this
              feature returns.
            </p>
            <button
              className="secondary-button"
              onClick={() => change({ kind: "kinetic" })}
            >
              Make a kinetic lyric video
            </button>
          </section>
        ) : (
          <DirectedVideoWorkspace
            track={track}
            tracks={tracks}
            chooseSource={(id) => {
              const selected = tracks.find((item) => item.id === id);
              if (selected)
                writeLocal(`sv-video-draft-v1:${id}`, {
                  ...restoreDraft(selected),
                  kind: "directed",
                });
              chooseSource(id);
            }}
            audioRef={audioRef}
            language={draft.language}
          />
        )}
      </div>
    );
  return (
    <div className="video-workspace">
      <div className="video-heading">
        <div>
          <h1>New video</h1>
          <p>
            {track.project === "Loose tracks" ? "Unsorted" : track.project}{" "}
            <span>/</span> {track.title}
          </p>
        </div>
        <div className="video-heading-actions">
          <span className="video-save-status" role="status">
            <Check size={13} />
            {status}
          </span>
          <button
            className="icon-button"
            aria-label="Undo video edit"
            title="Undo"
            disabled={!history.current.past.length}
            onClick={() => undo()}
          >
            <Undo2 size={16} />
          </button>
          <button
            className="icon-button"
            aria-label="Redo video edit"
            title="Redo"
            disabled={!history.current.future.length}
            onClick={() => undo(true)}
          >
            <Redo2 size={16} />
          </button>
          <button className="secondary-button" onClick={downloadPlan}>
            <Download size={15} />
            Download plan
          </button>
        </div>
      </div>
      <div className="video-generation-bar">
        <div>
          <strong>
            {alignment
              ? `${alignment.wordCount - missingWordCount} / ${alignment.wordCount} words timed`
              : draft.kind === "visualizer"
                ? "Play your song. Choose a visualizer."
                : "Align the vocal. Generate the backgrounds."}
          </strong>
          <small>
            {alignment
              ? missingWordCount
                ? `${missingWordCount} words have no complete timestamp. Open Word timing to set their times.`
                : reviewCount
                  ? `${reviewCount} confidence flags. Review while listening; these flags do not block rendering.`
                  : "Audio-derived word timing · review while listening"
              : "Your song and lyrics stay together throughout the video."}
          </small>
        </div>
        <button
          className="secondary-button"
          disabled={
            production.submitting ||
            alignmentBusy ||
            !draft.lyrics.trim() ||
            !production.installed
          }
          onClick={() => void alignLyrics()}
        >
          {alignmentBusy
            ? "Aligning lyrics…"
            : alignment
              ? "Align lyrics again"
              : "Align lyrics"}
        </button>
        {draft.kind === "kinetic" && (
          <button
            className="primary-button"
            disabled={
              production.submitting ||
              backgroundBusy ||
              Array.from({ length: assetCount }, (_, i) => i).every((i) =>
                allAssets.some(
                  (a) => a.kind === draft.background && a.slot === i,
                ),
              )
            }
            onClick={() => void generateBackgrounds()}
          >
            {backgroundBusy
              ? "Generating…"
              : draft.background === "images"
                ? "Generate images"
                : "Generate clips"}
          </button>
        )}
      </div>
      {production.error && (
        <p className="form-error" role="alert">
          {production.error}
        </p>
      )}
      {draft.kind === "visualizer" && assetError && (
        <p className="form-error" role="alert">
          {assetError}
        </p>
      )}
      {draft.kind === "visualizer" && (
        <VisualizerExports
          key={track.id}
          track={track}
          draft={draft}
          cues={cues}
          duration={duration}
        />
      )}
      {visibleJobs.length > 0 && (
        <div
          className="video-generation-jobs"
          aria-label="Video generation progress"
        >
          {visibleJobs.map((job) => (
            <div key={job.id}>
              <span>
                {job.kind === "lyric-alignment"
                  ? "Lyrics"
                  : `${job.input.kind === "images" ? "Image" : "Clip"} ${job.input.slot + 1}`}
              </span>
              <small role="status">
                {job.error ||
                  job.result?.phase ||
                  (job.state === "queued" ? "Queued" : job.state)}
              </small>
              {job.state === "failed" ? (
                <button
                  className="quiet-button"
                  onClick={() => void production.action(job, "retry")}
                >
                  Retry
                </button>
              ) : (
                <button
                  className="quiet-button"
                  disabled={
                    job.kind === "video-motion" && job.state === "running"
                  }
                  title={
                    job.kind === "video-motion"
                      ? "A running clip finishes safely; queued clips can be cancelled."
                      : undefined
                  }
                  onClick={() => void production.action(job, "cancel")}
                >
                  Cancel
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      <fieldset className="video-kind-switch">
        <legend className="sr-only">Video type</legend>
        {options.map(({ id, title, note, icon: Icon }) => (
          <label key={id} className={draft.kind === id ? "chosen" : ""}>
            <input
              type="radio"
              name="video-kind"
              aria-label={title}
              disabled={id === "directed" && !musicVideoAvailable}
              checked={draft.kind === id}
              onChange={() => change({ kind: id })}
            />
            <Icon size={21} />
            <span>
              <strong>{title}</strong>
              <small>{note}</small>
            </span>
            <span className="video-radio-dot" />
          </label>
        ))}
      </fieldset>
      <div className="video-workbench">
        <section className="video-settings" aria-label="Video settings">
          <label>
            Soundtrack
            <select
              aria-label="Soundtrack"
              value={track.id}
              onChange={(event) => chooseSource(event.target.value)}
            >
              {tracks.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.title} ·{" "}
                  {item.source === "imported"
                    ? "Imported song"
                    : item.source === "yue2"
                      ? `Take ${item.take || 1}`
                      : item.audio === 1
                        ? "Amber take"
                        : "Dusk take"}
                </option>
              ))}
            </select>
          </label>
          <div className="video-song-summary">
            {track.cover ? (
              <img src={track.cover} alt="" />
            ) : (
              <Music2 size={26} />
            )}
            <div>
              <strong>{track.title}</strong>
              <span>{timeLabel(duration)} · Original soundtrack</span>
            </div>
          </div>
          <fieldset className="video-control-section">
            <legend>Frame</legend>
            <div className="video-choice-row">
              {(["16:9", "9:16"] as const).map((aspect, index) => (
                <label
                  className={draft.aspect === aspect ? "chosen" : ""}
                  key={aspect}
                >
                  <input
                    type="radio"
                    name="video-aspect"
                    aria-label={aspect}
                    checked={draft.aspect === aspect}
                    onChange={() => change({ aspect })}
                  />
                  {index === 0 ? (
                    <Monitor size={17} />
                  ) : (
                    <Smartphone size={17} />
                  )}
                  <span>
                    {aspect}
                    <small>{index === 0 ? "Landscape" : "Portrait"}</small>
                  </span>
                </label>
              ))}
            </div>
            <p className="video-field-note">
              {draft.aspect === "9:16" ? "1080 × 1920" : "1920 × 1080"} · 24 fps
              {draft.kind === "visualizer" ? "MP4 output" : "output plan"}
            </p>
          </fieldset>
          {draft.kind === "directed" ? (
            <>
              <fieldset className="video-control-section">
                <legend>Treatment</legend>
                <label className="sr-only" htmlFor="video-treatment">
                  Music video treatment
                </label>
                <select
                  id="video-treatment"
                  value={draft.treatment}
                  onChange={(event) =>
                    change({
                      treatment: event.target.value as VideoDraft["treatment"],
                    })
                  }
                >
                  <option value="concept">Abstract / concept</option>
                  <option value="narrative">Narrative</option>
                  <option value="performance">Performance</option>
                  <option value="mixed">Mixed</option>
                </select>
                <label>
                  Direction
                  <textarea
                    rows={5}
                    value={draft.direction}
                    onChange={(event) =>
                      change({ direction: event.target.value })
                    }
                    placeholder="Visual story, locations, recurring characters…"
                  />
                </label>
              </fieldset>
              <p className="video-field-note">
                Storyboard and shot generation come in the music-video phase.
                This treatment is saved with your song.
              </p>
            </>
          ) : (
            <>
              {draft.kind === "visualizer" && (
                <fieldset className="video-control-section">
                  <legend>Visualizer</legend>
                  <label>
                    Visual style
                    <select
                      aria-label="Visual style"
                      value={
                        draft.visualizer === "all"
                          ? "all"
                          : String(visualizerPreset)
                      }
                      onChange={(event) =>
                        change({
                          visualizer: event.target
                            .value as VideoDraft["visualizer"],
                        })
                      }
                    >
                      <option value="all">
                        All visualizers — equal time across the song
                      </option>
                      {originalVisualizerPresets.map((preset) => (
                        <option key={preset.id} value={String(preset.id)}>
                          {preset.name} — {preset.description}
                        </option>
                      ))}
                    </select>
                  </label>
                  {draft.visualizer === "all" && (
                    <p className="video-field-note">
                      Each of the eight styles plays once, in list order, for
                      about {timeLabel(duration / 8)}. Changes are equally
                      spaced across the song.
                    </p>
                  )}
                  <label>
                    Response strength ·{" "}
                    {Math.round(draft.visualizerStrength * 100)}%
                    <input
                      type="range"
                      min={0.25}
                      max={2}
                      step={0.05}
                      value={draft.visualizerStrength}
                      onChange={(event) =>
                        change({
                          visualizerStrength: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                  <label className="video-checkbox">
                    <input
                      type="checkbox"
                      checked={draft.showLyrics}
                      onChange={(event) =>
                        change({ showLyrics: event.target.checked })
                      }
                    />
                    Show lyrics
                  </label>
                  <p className="video-field-note">
                    Play the song to see its bass, percussion and upper
                    frequencies drive the visuals.{" "}
                    <a
                      href={visualizerPreviewUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Browse all eight
                    </a>
                  </p>
                </fieldset>
              )}
              {draft.kind !== "visualizer" && (
                <fieldset className="video-control-section">
                  <legend>Background</legend>
                  <div className="video-choice-row">
                    {(["images", "motion"] as const).map((kind) => (
                      <label
                        className={draft.background === kind ? "chosen" : ""}
                        key={kind}
                      >
                        <input
                          type="radio"
                          name="video-background"
                          aria-label={
                            kind === "images"
                              ? "Image slideshow"
                              : "H3 animation loops"
                          }
                          checked={draft.background === kind}
                          onChange={() => {
                            change({ background: kind });
                            setSelectedAsset(0);
                          }}
                        />
                        {kind === "images" ? (
                          <ImageIcon size={17} />
                        ) : (
                          <Film size={17} />
                        )}
                        <span>
                          {kind === "images" ? "Slideshow" : "Animation loops"}
                          <small>
                            {kind === "images"
                              ? "Generated images"
                              : "MiniMax H3"}
                          </small>
                        </span>
                      </label>
                    ))}
                  </div>
                  <label>
                    Visual theme
                    <textarea
                      rows={3}
                      value={draft.brief}
                      onChange={(event) =>
                        change({ brief: event.target.value })
                      }
                      placeholder="Describe the atmosphere, places and color palette…"
                    />
                  </label>
                  <p className="video-field-note">
                    Background prompts include your song and its lyrics. Keep
                    the center quiet for the words.
                  </p>
                  {draft.background === "images" ? (
                    <div className="video-field-pair">
                      <label>
                        Images
                        <input
                          type="number"
                          aria-label="Number of images"
                          min={1}
                          max={100}
                          step={1}
                          value={draft.imageCount}
                          onChange={(event) => {
                            if (event.target.value)
                              change({
                                imageCount: Math.max(
                                  1,
                                  Math.min(
                                    100,
                                    Math.round(Number(event.target.value)),
                                  ),
                                ),
                              });
                          }}
                        />
                      </label>
                      <label>
                        Sequence
                        <select
                          aria-label="Slideshow repetitions"
                          value={draft.imageCycles}
                          onChange={(event) =>
                            change({ imageCycles: Number(event.target.value) })
                          }
                        >
                          <option value={1}>Once across song</option>
                          <option value={2}>Repeat twice</option>
                          <option value={3}>Repeat 3 times</option>
                          <option value={4}>Repeat 4 times</option>
                        </select>
                      </label>
                    </div>
                  ) : (
                    <div className="video-field-pair">
                      <label>
                        Clips
                        <input
                          type="number"
                          aria-label="Number of animation clips"
                          min={1}
                          max={24}
                          value={draft.clipCount}
                          onChange={(event) => {
                            if (event.target.value)
                              change({
                                clipCount: Math.max(
                                  1,
                                  Math.min(
                                    24,
                                    Math.round(Number(event.target.value)),
                                  ),
                                ),
                              });
                          }}
                        />
                      </label>
                      <label>
                        Clip length
                        <select
                          aria-label="Animation clip length"
                          value={draft.clipSeconds}
                          onChange={(event) =>
                            change({ clipSeconds: Number(event.target.value) })
                          }
                        >
                          {[4, 6, 8, 10, 12, 15].map((s) => (
                            <option key={s} value={s}>
                              {s} seconds
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                  )}
                  <div className="video-timing-summary" aria-live="polite">
                    {draft.background === "images" ? (
                      <>
                        <strong>{perImage.toFixed(1)} seconds per image</strong>
                        <span>
                          {draft.imageCount} images ·{" "}
                          {draft.imageCycles === 1
                            ? "one full-song sequence"
                            : `${draft.imageCycles} equal cycles`}
                        </span>
                      </>
                    ) : (
                      <>
                        <strong>
                          {draft.clipCount * draft.clipSeconds}-second loop
                          sequence
                        </strong>
                        <span>
                          {draft.clipCount} × {draft.clipSeconds}s clips ·
                          repeat and trim to {timeLabel(duration)}
                        </span>
                      </>
                    )}
                  </div>
                  <div className="video-field-pair">
                    <label>
                      Transitions
                      <select
                        value={draft.transition}
                        onChange={(event) =>
                          change({
                            transition: event.target
                              .value as VideoDraft["transition"],
                          })
                        }
                      >
                        <option value="dissolve">Soft dissolve</option>
                        <option value="cut">Clean cut</option>
                      </select>
                    </label>
                    {draft.background === "images" && (
                      <label className="video-checkbox">
                        <input
                          type="checkbox"
                          checked={draft.pan}
                          onChange={(event) =>
                            change({ pan: event.target.checked })
                          }
                        />
                        Slow pan & zoom
                      </label>
                    )}
                  </div>
                </fieldset>
              )}
              {draft.kind !== "visualizer" && draft.background === "motion" && (
                <fieldset className="video-motion-content">
                  <legend>H3 animation</legend>
                  <label>
                    Content
                    <select
                      value={draft.motionStyle}
                      onChange={(e) =>
                        change({
                          motionStyle: e.target
                            .value as VideoDraft["motionStyle"],
                        })
                      }
                    >
                      <option value="scene">Thematic scenes</option>
                      <option value="graphics">Motion graphics</option>
                      <option value="typography">Animated text</option>
                      <option value="mixed">Scenes + animated text</option>
                    </select>
                  </label>
                  {(draft.motionStyle === "typography" ||
                    draft.motionStyle === "mixed") && (
                    <label>
                      Short text
                      <input
                        type="text"
                        maxLength={80}
                        value={draft.motionText}
                        onChange={(e) => change({ motionText: e.target.value })}
                      />
                    </label>
                  )}
                  <p className="video-field-note">
                    H3 lettering is part of the clip. Sung lyrics keep their
                    separate, editable timing.
                  </p>
                </fieldset>
              )}
              <details className="video-disclosure">
                <summary>
                  Lyrics & timing{" "}
                  <span>
                    {cues.length ? `${cues.length} lines` : "Add lyrics"}
                  </span>
                  <ChevronDown size={15} />
                </summary>
                <div>
                  <button
                    className="secondary-button"
                    disabled={
                      !production.installed ||
                      production.submitting ||
                      transcriptionBusy ||
                      alignmentBusy
                    }
                    onClick={() =>
                      void production.submit([
                        {
                          kind: "transcription",
                          slot: 0,
                          aspect: draft.aspect,
                          seconds: 8,
                          lyrics: "",
                          language: draft.language,
                          prompt: "",
                        },
                      ])
                    }
                  >
                    {transcriptionBusy
                      ? "Transcribing song…"
                      : "Transcribe lyrics from song"}
                  </button>
                  <p className="video-field-note">
                    Transcribe the recorded vocal, review the draft, then align
                    the corrected lyrics. Requires the local lyric-alignment
                    runtime.
                  </p>
                  {transcription && (
                    <div>
                      <label>
                        Review transcribed lyrics
                        <textarea
                          rows={7}
                          aria-label="Review transcribed lyrics"
                          value={reviewLyrics}
                          onChange={(e) => setReviewLyrics(e.target.value)}
                        />
                      </label>
                      <p className="video-field-note">
                        Transcription can mishear singing or invent words during
                        instrumental passages. Listen and correct the draft
                        before using it.
                      </p>
                      {!transcription.result?.lyrics?.trim() && (
                        <p>
                          No words were recognized. You can type the lyrics
                          below.
                        </p>
                      )}
                      <button
                        className="secondary-button"
                        disabled={!reviewLyrics.trim()}
                        onClick={() =>
                          change({
                            lyrics: reviewLyrics,
                            cueEdits: {},
                            wordEdits: {},
                          })
                        }
                      >
                        Use reviewed lyrics
                        {draft.lyrics.trim() ? " (replace current lyrics)" : ""}
                      </button>
                    </div>
                  )}
                  <label>
                    Video lyrics
                    <textarea
                      rows={7}
                      aria-label="Video lyrics"
                      value={draft.lyrics}
                      onChange={(event) =>
                        change({
                          lyrics: event.target.value,
                          cueEdits: {},
                          wordEdits: {},
                        })
                      }
                      placeholder="Paste the lyrics you want to show. Section labels stay out of the video."
                    />
                  </label>
                  <label>
                    Lyric language
                    <select
                      value={draft.language}
                      onChange={(e) =>
                        change({ language: e.target.value, wordEdits: {} })
                      }
                    >
                      <option value="en">English</option>
                      <option value="es">Spanish</option>
                      <option value="fr">French</option>
                      <option value="de">German</option>
                      <option value="it">Italian</option>
                      <option value="pt">Portuguese</option>
                    </select>
                  </label>
                  <p className="video-field-note">
                    Align lyrics reads the recorded vocal. Editing the lyrics or
                    language requires a new alignment. Uncertain words are
                    flagged below.
                  </p>
                </div>
              </details>
              <details className="video-disclosure">
                <summary>
                  Type & motion
                  <ChevronDown size={15} />
                </summary>
                <div>
                  <div className="video-field-pair">
                    <label>
                      Typography
                      <select
                        value={draft.font}
                        onChange={(event) =>
                          change({
                            font: event.target.value as VideoDraft["font"],
                          })
                        }
                      >
                        <option value="bold">Bold</option>
                        <option value="soft">Soft</option>
                        <option value="editorial">Editorial</option>
                      </select>
                    </label>
                    <label>
                      Lyric motion
                      <select
                        value={draft.lyricMotion}
                        onChange={(event) =>
                          change({
                            lyricMotion: event.target
                              .value as VideoDraft["lyricMotion"],
                          })
                        }
                      >
                        <option value="auto">
                          Automatic · varied entrances
                        </option>
                        <option value="pop">Word pop</option>
                        <option value="slam">Slam</option>
                        <option value="rise">Rise</option>
                        <option value="highlight">Word highlight</option>
                        <option value="reveal">Line reveal</option>
                        <option value="calm">Calm</option>
                      </select>
                    </label>
                  </div>
                  <label>
                    Motion strength · {Math.round(draft.intensity * 100)}%
                    <input
                      type="range"
                      min={50}
                      max={150}
                      value={Math.round(draft.intensity * 100)}
                      onChange={(e) =>
                        change({ intensity: Number(e.target.value) / 100 })
                      }
                    />
                  </label>
                  <label>
                    Text size · {draft.textSize}%
                    <input
                      type="range"
                      min={60}
                      max={150}
                      value={draft.textSize}
                      onChange={(event) =>
                        change({ textSize: Number(event.target.value) })
                      }
                    />
                  </label>
                  <label>
                    Position
                    <select
                      value={draft.placement}
                      onChange={(event) =>
                        change({
                          placement: event.target
                            .value as VideoDraft["placement"],
                        })
                      }
                    >
                      <option value="center">Center</option>
                      <option value="lower">Lower third</option>
                    </select>
                  </label>
                  <div className="video-field-pair">
                    <label>
                      Text
                      <input
                        type="color"
                        value={draft.textColor}
                        onChange={(event) =>
                          change({ textColor: event.target.value })
                        }
                      />
                    </label>
                    <label>
                      Highlight
                      <input
                        type="color"
                        value={draft.highlightColor}
                        onChange={(event) =>
                          change({ highlightColor: event.target.value })
                        }
                      />
                    </label>
                  </div>
                  <label>
                    Background shade · {draft.shade}%
                    <input
                      type="range"
                      min={0}
                      max={85}
                      value={draft.shade}
                      onChange={(event) =>
                        change({ shade: Number(event.target.value) })
                      }
                    />
                  </label>
                  {reduceMotion && (
                    <p className="video-field-note">
                      Reduced-motion preference is active in the preview.
                    </p>
                  )}
                </div>
              </details>
            </>
          )}
        </section>
        <section className="video-preview-column" aria-label="Video preview">
          <div className="video-preview-sticky">
            <div className="video-preview-heading">
              <span>
                {draft.kind === "kinetic"
                  ? "Kinetic lyric video preview"
                  : draft.kind === "visualizer"
                    ? "Visualizer video preview"
                    : "Music video treatment"}
              </span>
              <label className="video-checkbox">
                <input
                  type="checkbox"
                  checked={showGuides}
                  onChange={(event) => setShowGuides(event.target.checked)}
                />
                Safe area
              </label>
            </div>
            <div
              className={`video-stage-wrap ${draft.aspect === "9:16" ? "portrait" : "landscape"}`}
            >
              <div
                className={`video-stage font-${draft.font} position-${draft.placement}`}
                style={
                  {
                    aspectRatio: draft.aspect.replace(":", "/"),
                    "--video-text": draft.textColor,
                    "--video-highlight": draft.highlightColor,
                  } as CSSProperties
                }
                data-aspect={draft.aspect}
                data-preview-frame={frame}
              >
                {draft.kind === "visualizer" ? (
                  <VisualizerCanvas
                    audioRef={audioRef}
                    active={active}
                    playing={previewPlaying}
                    time={position}
                    preset={visualizerPreset}
                    selection={draft.visualizer}
                    duration={duration}
                    strength={draft.visualizerStrength}
                    reduceMotion={reduceMotion}
                    onError={setAssetError}
                  />
                ) : (
                  <BackgroundMedia
                    key={`${currentMedia?.url || track.cover}-current`}
                    asset={currentMedia}
                    fallback={track.cover}
                    seconds={elapsedInPlacement + sourceOffset}
                    playing={previewPlaying}
                    pan={
                      draft.background === "images" &&
                      draft.pan &&
                      !reduceMotion
                    }
                    progress={
                      (frame - (currentPlacement?.startFrame || 0)) /
                      Math.max(
                        1,
                        (currentPlacement?.endFrame || 1) -
                          (currentPlacement?.startFrame || 0),
                      )
                    }
                    error={setAssetError}
                  />
                )}
                {draft.kind !== "visualizer" && fade > 0 && (
                  <div className="video-blend-layer" style={{ opacity: fade }}>
                    <BackgroundMedia
                      key={`${nextMedia?.url || track.cover}-next`}
                      asset={nextMedia}
                      fallback={track.cover}
                      seconds={(fade * fadeFrames) / FPS}
                      playing={previewPlaying}
                      pan={
                        draft.background === "images" &&
                        draft.pan &&
                        !reduceMotion
                      }
                      progress={0}
                      error={setAssetError}
                    />
                  </div>
                )}
                <div
                  className="video-shade"
                  style={{ opacity: draft.shade / 100 }}
                />
                {showGuides && (
                  <div className="video-safe-area" aria-hidden="true" />
                )}
                {draft.kind === "visualizer" && draft.showLyrics ? (
                  <LyricOverlay
                    draft={draft}
                    cues={cues}
                    time={position}
                    title={track.title}
                    aligned={!!alignment}
                    reduceMotion={reduceMotion}
                  />
                ) : draft.kind === "kinetic" ? (
                  <div
                    className="kinetic-words"
                    style={{
                      fontSize: `${(draft.aspect === "9:16" ? 10 : 7) * (draft.textSize / 100)}cqw`,
                      opacity:
                        !reduceMotion && draft.lyricMotion === "reveal" && cue
                          ? Math.min(1, cueProgress * 9)
                          : 1,
                      transform:
                        !reduceMotion && draft.lyricMotion === "reveal" && cue
                          ? `translateY(${(1 - Math.min(1, cueProgress * 9)) * 12}px)`
                          : undefined,
                    }}
                  >
                    {cue ? (
                      words.map((word, index) => (
                        <span
                          key={`${cue.id}-${index}`}
                          style={wordMotion(
                            effect,
                            cue.words?.[index]?.start == null
                              ? -1
                              : position - cue.words[index].start!,
                            index,
                            draft.intensity,
                            reduceMotion,
                          )}
                          className={index === wordIndex ? "current-word" : ""}
                          data-word-start={
                            cue.words?.[index]?.start ?? undefined
                          }
                        >
                          {word}{" "}
                        </span>
                      ))
                    ) : (
                      <span className="video-title-frame">
                        {!alignment
                          ? track.title
                          : frame < (cues[0]?.startFrame || 0)
                            ? track.title
                            : ""}
                      </span>
                    )}
                  </div>
                ) : draft.kind === "directed" ? (
                  <div className="video-future-preview">
                    <span>Storyboard preview comes next</span>
                    <strong>{track.title}</strong>
                  </div>
                ) : null}
                {draft.kind !== "visualizer" && !currentMedia && (
                  <span className="video-preview-source">
                    Cover art preview
                  </span>
                )}
              </div>
            </div>
            <div className="video-preview-transport">
              <button
                className="video-preview-play"
                aria-label={
                  previewPlaying ? "Pause video preview" : "Play video preview"
                }
                onClick={() => {
                  chooseSource(track.id);
                  play(track);
                }}
              >
                {previewPlaying ? (
                  <Pause size={17} fill="currentColor" />
                ) : (
                  <Play size={17} fill="currentColor" />
                )}
              </button>
              <span>{timeLabel(position)}</span>
              <input
                aria-label="Video preview position"
                type="range"
                min={0}
                max={duration}
                step={1 / FPS}
                value={position}
                onChange={(event) => seek(track, Number(event.target.value))}
              />
              <span>{timeLabel(duration)}</span>
            </div>
            {draft.kind === "visualizer" && draft.visualizer === "all" && (
              <>
                <div className="video-timeline-heading">
                  <span>Equal-time visualizer sequence</span>
                  <span>8 styles</span>
                </div>
                <div
                  className="video-timeline"
                  aria-label="Visualizer sequence"
                >
                  {visualizerSchedule(duration, "all").map((segment) => (
                    <button
                      key={segment.preset}
                      className={
                        frame >= segment.startFrame && frame < segment.endFrame
                          ? "current"
                          : ""
                      }
                      title={`${originalVisualizerPresets[segment.preset].name}: ${timeLabel(segment.startFrame / FPS)}–${timeLabel(segment.endFrame / FPS)}`}
                      onClick={() => seek(track, segment.startFrame / FPS)}
                    >
                      {originalVisualizerPresets[segment.preset].name}
                    </button>
                  ))}
                </div>
              </>
            )}
            {draft.kind !== "visualizer" && (
              <>
                <div className="video-timeline-heading">
                  <span>Background sequence</span>
                  <span>
                    {placements.length}{" "}
                    {draft.background === "images"
                      ? "slides"
                      : "clip placements"}
                  </span>
                </div>
                <div
                  className="video-timeline"
                  aria-label="Background timeline"
                >
                  {placements.map((placement, index) => (
                    <button
                      key={index}
                      title={`${draft.background === "images" ? "Image" : "Clip"} ${placement.assetIndex + 1}: ${timeLabel(placement.startFrame / FPS)}–${timeLabel(placement.endFrame / FPS)}`}
                      aria-label={`Preview ${draft.background === "images" ? "image" : "clip"} ${placement.assetIndex + 1}, placement ${index + 1}`}
                      className={index === placementIndex ? "current" : ""}
                      style={{
                        flex: placement.endFrame - placement.startFrame,
                      }}
                      onClick={() => {
                        setSelectedAsset(placement.assetIndex);
                        seek(track, placement.startFrame / FPS);
                      }}
                    >
                      {placements.length <= 16 ? placement.assetIndex + 1 : ""}
                    </button>
                  ))}
                </div>
                <div className="video-timeline-labels">
                  <span>0:00</span>
                  <span>{timeLabel(duration / 2)}</span>
                  <span>{timeLabel(duration)}</span>
                </div>
              </>
            )}
            <p className="video-preview-note">
              {visualLyrics
                ? cues.length
                  ? alignment
                    ? reviewCount
                      ? `${reviewCount} words need review`
                      : "Audio-aligned lyrics"
                    : "Align lyrics to preview the words"
                  : "Add your lyrics to preview the typography"
                : "Original song stays as the soundtrack"}
            </p>
            <div className="video-render-status">
              <span>Editor preview</span>
              <p>
                {draft.kind === "visualizer"
                  ? "Live audio-reactive preview. Render video exports the full song and your saved visual settings to MP4."
                  : "Generate backgrounds above; finished assets appear in the sequence automatically. MP4 export is not connected yet."}
              </p>
            </div>
          </div>
        </section>
      </div>
      {draft.kind === "kinetic" && (
        <section className="video-background-plan" aria-label="Background plan">
          <div className="video-section-heading">
            <div>
              <h2>
                {draft.background === "images"
                  ? "Slideshow images"
                  : "Animation clips"}
              </h2>
              <p>
                {draft.background === "images"
                  ? "Generate the missing images from these prompts. Each result joins the slideshow automatically."
                  : "Short, quiet motion. Clips repeat at normal speed; the song keeps its original audio."}
              </p>
            </div>
            <button
              className="secondary-button"
              disabled={assetBusy}
              onClick={() => {
                replaceSlot.current = null;
                input.current?.click();
              }}
            >
              <Upload size={15} />
              {assetBusy
                ? "Importing…"
                : draft.background === "images"
                  ? "Add images"
                  : "Add clips"}
            </button>
            <input
              ref={input}
              type="file"
              className="sr-only"
              aria-label="Import video backgrounds"
              accept={
                draft.background === "images"
                  ? "image/png,image/jpeg,image/webp"
                  : "video/mp4,video/webm,video/quicktime"
              }
              multiple
              onChange={(event) => void importMedia(event.target.files)}
            />
          </div>
          {assetError && (
            <p className="form-error" role="alert">
              {assetError}
            </p>
          )}
          <div className="video-asset-strip">
            {Array.from({ length: assetCount }, (_, index) => {
              const asset = allAssets.find(
                (a) => a.kind === draft.background && a.slot === index,
              );
              return (
                <button
                  type="button"
                  key={index}
                  aria-label={`Edit ${draft.background === "images" ? "image" : "clip"} ${index + 1} prompt`}
                  aria-pressed={displaySlot === index}
                  className={displaySlot === index ? "chosen" : ""}
                  onClick={() => setSelectedAsset(index)}
                >
                  {asset ? (
                    asset.kind === "images" ? (
                      <img src={asset.url} alt="" />
                    ) : (
                      <Film size={24} />
                    )
                  ) : draft.background === "images" ? (
                    <ImageIcon size={24} />
                  ) : (
                    <Film size={24} />
                  )}
                  <span>{index + 1}</span>
                  <small>
                    {asset
                      ? asset.generated
                        ? "Generated"
                        : "Imported"
                      : "Planned"}
                  </small>
                </button>
              );
            })}
          </div>
          <div className="video-prompt-editor">
            <div>
              <strong>
                {draft.background === "images" ? "Image" : "Clip"}{" "}
                {displaySlot + 1}
              </strong>
              <span>
                {selectedMedia?.name || "Prompt ready for generation"}
              </span>
              <button
                className="icon-button"
                aria-label="Previous background prompt"
                disabled={displaySlot === 0}
                onClick={() => setSelectedAsset(displaySlot - 1)}
              >
                <MoveLeft size={16} />
              </button>
              <button
                className="icon-button"
                aria-label="Next background prompt"
                disabled={displaySlot === assetCount - 1}
                onClick={() => setSelectedAsset(displaySlot + 1)}
              >
                <MoveRight size={16} />
              </button>
            </div>
            <label className="sr-only" htmlFor="background-prompt">
              Background prompt
            </label>
            <textarea
              id="background-prompt"
              rows={4}
              value={prompt}
              onChange={(event) =>
                change({
                  prompts: {
                    ...draft.prompts,
                    [selectedPromptKey]: event.target.value,
                  },
                })
              }
            />
            <div className="video-prompt-actions">
              <button
                className="primary-button"
                disabled={production.submitting || backgroundBusy}
                onClick={() => void generateBackgrounds(displaySlot)}
              >
                {selectedMedia ? "Regenerate" : "Generate"}{" "}
                {draft.background === "images" ? "image" : "clip"}{" "}
                {displaySlot + 1}
              </button>
              <button
                className="secondary-button"
                disabled={assetBusy}
                onClick={() => {
                  replaceSlot.current = displaySlot;
                  input.current?.click();
                }}
              >
                <Upload size={14} />
                {selectedMedia ? "Replace media" : "Add media here"}
              </button>
              {selectedMedia && !selectedMedia.generated && (
                <button
                  className="quiet-button"
                  disabled={assetBusy}
                  onClick={() => {
                    void removeAsset(selectedMedia.id)
                      .then(refreshAssets)
                      .catch((error) => setAssetError(error.message));
                  }}
                >
                  <X size={14} />
                  Remove
                </button>
              )}
              <button
                className="quiet-button"
                onClick={() => {
                  const prompts = { ...draft.prompts };
                  delete prompts[selectedPromptKey];
                  change({ prompts });
                }}
              >
                Reset prompt
              </button>
            </div>
          </div>
          {draft.background === "motion" && (
            <p className="video-field-note">
              Matching first and last frames is a generation goal, not a
              guaranteed seamless loop. Review the seams before export.
            </p>
          )}
        </section>
      )}
      {visualLyrics && alignment && (
        <WordTimingEditor
          alignment={alignment}
          draft={draft}
          duration={duration}
          change={change}
          seek={(seconds) => seek(track, seconds)}
        />
      )}
      {timingErrors.length > 0 && (
        <p className="form-error">{timingErrors[0]}</p>
      )}
    </div>
  );
}

function BackgroundMedia({
  asset,
  fallback,
  seconds,
  playing,
  pan,
  progress,
  error,
}: {
  asset?: AssetPreview;
  fallback?: string;
  seconds: number;
  playing: boolean;
  pan: boolean;
  progress: number;
  error: (text: string) => void;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    const sync = () => {
      if (!Number.isFinite(video.duration) || video.duration <= 0) return;
      const target = seconds % video.duration;
      if (Math.abs(video.currentTime - target) > (playing ? 0.18 : 0.025))
        video.currentTime = target;
      if (playing) void video.play().catch(() => {});
      else video.pause();
    };
    sync();
    video.addEventListener("loadedmetadata", sync);
    return () => video.removeEventListener("loadedmetadata", sync);
  }, [asset?.url, seconds, playing]);
  if (asset?.kind === "motion")
    return (
      <video
        ref={ref}
        className="video-background"
        src={asset.url}
        muted
        loop
        playsInline
        preload="metadata"
        onError={() =>
          error(
            "This clip cannot play in this browser. Try MP4 with H.264 video.",
          )
        }
      />
    );
  return (
    <img
      className="video-background"
      src={asset?.url || fallback || "/media/desert.jpg"}
      alt=""
      style={{
        transform: pan
          ? `scale(${1.025 + 0.055 * Math.min(1, progress)}) translateX(${(Math.min(1, progress) - 0.5) * 1.2}%)`
          : undefined,
      }}
    />
  );
}
