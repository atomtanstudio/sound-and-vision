import { useEffect, useRef, useState, type RefObject } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  Film,
  Flag,
  Play,
  RotateCcw,
  X,
  Trash2,
} from "lucide-react";
import { request } from "../music-studio/api";
import { readLocal, writeLocal } from "../music-studio/model";
import { reconcilePreviews, type FilmPreviews } from "./film-previews";
import {
  FilmCreditsEditor,
  defaultCredits,
  type FilmCredits,
} from "./FilmCredits";
import "./film-review.css";
import { sceneVoiceLabel } from "./scene-voice";

type Take = {
  id: string;
  label: string;
  state: string;
  correction?: string;
  timingOutdated?: boolean;
  error?: string;
  contextChanged?: boolean;
  baseTakeId?: string;
  method?: string;
  shiftFrames?: number;
  repairRange?: { startFrame: number; endFrame: number };
  smartPlan?: {
    intent: string;
    explanation: string;
    method: string;
    startSeconds: number;
    endSeconds: number;
    speechPolicy: string;
    cutPolicy: string;
    playbackSpeed?: number;
    sourceStartSeconds?: number;
    sourceEndSeconds?: number;
  };
  mediaUrl: string;
  posterUrl: string;
  contextUrl: string;
  checks?: {
    manualReview?: string[];
    possibleInternalCuts?: number[];
    manualFindings?: string[];
    continuityCompiler?: string;
    conditioningAudio?: string;
    aiReview?: {
      result: string;
      summary: string;
      findings: string[];
      coverage?: string;
    };
  };
};
type Scene = {
  index: number;
  name: string;
  type: string;
  action?: string;
  start: number;
  end: number;
  review: string;
  selected: string;
  correction: string;
  continuity: string;
  issue: string;
  referenceUrl: string;
  identityReferences: { role: string; url: string }[];
  castIds?: string[];
  vocalistId?: string | null;
  story?: import('./film-concept').StoryScene;
  storyboardUrl?: string;
  storyboardFrame?: { sha256:string };
  takes: Take[];
  timing: {
    source?: string;
    version?: number;
    leadingRest: number;
    uncertainWords: number;
    words: {
      text: string;
      start: number;
      end: number;
      review: string | null;
    }[];
    spans: { start: number; end: number }[];
  };
};
export type FilmState = {
  id: string;
  title: string;
  artist: string;
  credits?: FilmCredits;
  workflow?: "directed" | "vrgdg-h3-turbo" | "short-film";
  concept?: import('./film-concept').FilmConcept | null;
  storyboardVersion?: number;
  creation?: { treatment?:string };
  renderProfile?: string;
  characterSheetVersion?: number;
  cast?: { id: string; name: string; role: string; appearance: string; sheetUrl: string; views: string[] }[];
  vocalTiming?: { version: number; source: string; firstVocal: number | null; reviewCount: number };
  output?: number[];
  takeId: string;
  revision: number;
  cutRevision: number;
  duration: number;
  deletedAt?: number | null;
  fps: number;
  continuity: string;
  scenes: Scene[];
  exports: { id: string; state: string; revision: number; mediaUrl: string }[];
  jobs: {
    id: string;
    kind?: string;
    operation?: string;
    sceneIndex?: number;
    queuedAt?: number;
    index: number | null;
    state: string;
    phase: string;
    queuePosition?: number | null;
    error?: string;
  }[];
};
const active = (state: string) =>
  ["queued", "running", "waiting-for-resource"].includes(state);
const jobLabel = (job: FilmState["jobs"][number]) =>
  job.state === "queued"
    ? job.queuePosition === 1
      ? "Next"
      : `Queued · ${job.queuePosition || "…"}`
    : job.state === "waiting-for-resource"
      ? "Waiting for renderer"
      : "Rendering";
const stamp = (time: number) =>
  `${Math.floor(time / 60)}:${Math.floor(time % 60)
    .toString()
    .padStart(2, "0")}`;

export function FilmReview({
  takeId,
  initialFilmId,
  onPlay,
  audioRef,
}: {
  takeId: string;
  initialFilmId?: string;
  onPlay: () => void;
  audioRef: RefObject<HTMLAudioElement | null>;
}) {
  const [films, setFilms] = useState<FilmState[]>([]),
    [film, setFilm] = useState<FilmState | null>(null);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [index, setIndex] = useState(0);
  const [previews, setPreviews] = useState<FilmPreviews>({}),
    [mode, setMode] = useState<"film" | "scene" | "context">("film");
  const [correction, setCorrection] = useState(""),
    [continuity, setContinuity] = useState(""),
    [issue, setIssue] = useState("none"),
    [globalContext, setGlobalContext] = useState("");
  const [time, setTime] = useState(0),
    [notice, setNotice] = useState("");
  const [repairMethod, setRepairMethod] = useState<
      "smart" | "source-edit" | "timing" | "frame-regenerate"
    >("smart"),
    [shiftFrames, setShiftFrames] = useState(0);
  const [repairStart, setRepairStart] = useState(0),
    [repairEnd, setRepairEnd] = useState(0);
  const player = useRef<HTMLVideoElement>(null),
    pendingTime = useRef<number | null>(null),
    pendingPlay = useRef(false);
  const filmId = film?.id;
  const [creditDraft, setCreditDraft] = useState<FilmCredits>(
    defaultCredits(""),
  );
  useEffect(() => {
    if (film)
      setCreditDraft(film.credits || defaultCredits(film.title, film.artist));
    // Keep in-progress typing through job polling.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filmId]);
  const previewFilm = useRef<string | null>(null);
  useEffect(() => {
    if (!film) return;
    const key = `sv-film-previews-v1:${film.id}`;
    const saved = readLocal<FilmPreviews>(key, {});
    const next = reconcilePreviews(film.scenes, saved);
    const newlyReady =
      previewFilm.current === film.id &&
      saved[index]?.newestReadyId !== next[index]?.newestReadyId;
    previewFilm.current = film.id;
    setPreviews(next);
    writeLocal(key, next);
    if (newlyReady) {
      player.current?.pause();
      pendingTime.current = 0;
      pendingPlay.current = false;
      setMode("scene");
      setNotice("New take ready. It is selected for preview.");
    }
  }, [film, index]);
  function setTakeIdPreview(id: string) {
    if (!film) return;
    const next = { ...previews, [index]: { ...previews[index], takeId: id } };
    setPreviews(next);
    writeLocal(`sv-film-previews-v1:${film.id}`, next);
  }
  useEffect(() => {
    const audio = audioRef.current;
    audio?.pause();
    const pause = () => player.current?.pause();
    audio?.addEventListener("play", pause);
    return () => audio?.removeEventListener("play", pause);
  }, [audioRef]);
  useEffect(() => {
    let alive = true;
    request<{ films: FilmState[] }>("/films?include_deleted=true")
      .then((data) => {
        if (!alive) return;
        setFilms(data.films);
        const available = data.films.filter(
          (f) =>
            !f.deletedAt &&
            f.scenes.length &&
            f.scenes.some((s) =>
              s.takes.some((t) => t.id === s.selected && t.state === "ready"),
            ),
        );
        const saved =
          initialFilmId || new URLSearchParams(location.search).get("film");
        const chosen =
          available.find((f) => f.id === saved) ||
          available.find((f) => f.takeId === takeId) ||
          null;
        setFilm(chosen);
        setIndex(
          chosen?.scenes.findIndex((s) =>
            s.takes.some((t) => t.state === "ready"),
          ) ?? 0,
        );
      })
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [takeId, initialFilmId]);
  useEffect(() => {
    if (!filmId) return;
    let alive = true,
      timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await request<FilmState>(`/films/${filmId}`);
        if (alive) setFilm(data);
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
      if (alive) timer = setTimeout(poll, 3000);
    };
    timer = setTimeout(poll, 3000);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [filmId]);
  const scene = film?.scenes[index],
    take =
      scene?.takes.find((t) => t.id === previews[index]?.takeId) ||
      scene?.takes.filter((t) => t.state === "ready").at(-1) ||
      scene?.takes.find((t) => t.id === scene.selected) ||
      scene?.takes.at(-1);
  const sceneSeconds =
    scene && film
      ? Math.round((scene.end - scene.start) * film.fps) / film.fps
      : 0;
  const latestExport = film?.exports.filter((e) => e.state === "ready").at(-1);
  const currentExport = latestExport?.revision === film?.cutRevision;
  const complete =
    !!film?.scenes.length &&
    film.scenes.every((s) =>
      s.takes.some((t) => t.id === s.selected && t.state === "ready"),
    );
  const src =
    mode !== "film"
      ? take?.state === "ready"
        ? mode === "context"
          ? take.contextUrl
          : take.mediaUrl
        : undefined
      : latestExport?.mediaUrl;
  useEffect(() => {
    if (!scene) return;
    player.current?.pause();
    setMode("scene");
    pendingTime.current = 0;
    pendingPlay.current = false;
    setCorrection(scene.correction || "");
    setContinuity(scene.continuity || "");
    setIssue(scene.issue || "none");
    setRepairMethod("smart");
    setShiftFrames(0);
    setRepairStart(0);
    setRepairEnd(sceneSeconds);
    setNotice("");
    // Local typing survives polling; only switching scene/film resets the editor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filmId, index]);
  useEffect(() => {
    setGlobalContext(film?.continuity || "");
  }, [filmId]);
  useEffect(() => {
    if (player.current?.readyState && pendingTime.current !== null) {
      player.current.currentTime = pendingTime.current;
      pendingTime.current = null;
      if (pendingPlay.current) {
        pendingPlay.current = false;
        void player.current.play().catch((e) => setError(e.message));
      }
    }
  }, [src]);
  function chooseScene(next: number) {
    if (!film) return;
    next = Math.max(0, Math.min(film.scenes.length - 1, next));
    player.current?.pause();
    pendingPlay.current = false;
    setError("");
    if (!latestExport || !film.scenes[next].takes.some((t) => t.state === "ready")) {
      pendingTime.current = 0;
      setIndex(next);
      setMode("scene");
      return;
    }
    if (mode === "film" && player.current) {
      player.current.currentTime = film.scenes[next].start;
      setTime(film.scenes[next].start);
    } else pendingTime.current = film.scenes[next].start;
    setIndex(next);
    setMode("film");
  }
  function playScene() {
    if (!take || take.state !== "ready") return;
    pendingTime.current = 0;
    pendingPlay.current = true;
    setMode("scene");
    if (mode === "scene" && player.current) {
      player.current.currentTime = 0;
      pendingTime.current = null;
      pendingPlay.current = false;
      void player.current.play().catch((e) => setError(e.message));
    }
  }
  function playInFilm() {
    if (!scene || take?.state !== "ready") return;
    pendingTime.current = 0;
    pendingPlay.current = true;
    setMode("context");
    if (mode === "context" && player.current) {
      player.current.currentTime = pendingTime.current;
      pendingTime.current = null;
      pendingPlay.current = false;
      void player.current.play().catch((e) => setError(e.message));
    }
  }
  async function mutate(path: string, body: unknown, method = "POST") {
    if (!film) return null;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const data = await request<FilmState>(
        `/films/${film.id}${path}`,
        body,
        method,
      );
      setFilm(data);
      return data;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }
  async function renderMissing() {
    if (!film || !scene || scene.takes.some((t) => t.state === "ready")) return;
    const key = `sv-scene-generate:${film.id}:${index}`;
    const signature = String(film.revision);
    const saved = readLocal<{ signature: string; requestId: string } | null>(key, null);
    const requestId = saved?.signature === signature ? saved.requestId : crypto.randomUUID();
    writeLocal(key, { signature, requestId });
    const data = await mutate(`/scenes/${index}/generate`, { revision: film.revision, requestId });
    if (data) {
      localStorage.removeItem(key);
      setNotice("Scene queued with the saved storyboard, character reference and song excerpt.");
    }
  }
  async function rerender() {
    if (!scene || !film || take?.state !== "ready") return;
    // Retain the same ID across an uncertain response and page reload.
    const payload = {
      revision: film.revision,
      correction,
      continuity,
      issue,
      baseTakeId: take.id,
      method: film.workflow === "vrgdg-h3-turbo" ? "regenerate" : repairMethod,
      shiftFrames: film.workflow !== "vrgdg-h3-turbo" && repairMethod === "timing" ? shiftFrames : 0,
      ...(repairMethod === "frame-regenerate"
        ? {
            repairStartFrame: Math.round(repairStart * film.fps),
            repairEndFrame: Math.round(repairEnd * film.fps),
          }
        : {}),
    };
    const key = `sv-scene-submit:${film.id}:${index}`;
    let saved: { signature: string; requestId: string } | null = null;
    try {
      saved = JSON.parse(sessionStorage.getItem(key) || "null");
    } catch {}
    const signature = JSON.stringify(payload);
    const requestId =
      saved?.signature === signature ? saved.requestId : crypto.randomUUID();
    sessionStorage.setItem(key, JSON.stringify({ signature, requestId }));
    const data = await mutate(`/scenes/${index}/retry`, {
      ...payload,
      requestId,
    });
    if (data) {
      sessionStorage.removeItem(key);
      setNotice(
        film.workflow === "vrgdg-h3-turbo" ? "New scene take queued with the original character and song excerpt. Earlier takes are retained."
          : `Repair queued from ${take.label}. You can continue reviewing and queue another scene.`,
      );
    }
  }
  async function accept() {
    if (!film || !take || !scene) return;
    const changed = scene.selected !== take.id;
    const data = await mutate(`/scenes/${index}/takes/${take.id}/accept`, {
      revision: film.revision,
    });
    if (!data) return;
    if (changed && complete) {
      const exported = await mutate("/exports", {
        revision: data.revision,
        requestId: crypto.randomUUID(),
      });
      if (exported)
        setNotice(
          "Take selected. Rebuilding the full film with the original song.",
        );
    } else
      setNotice(
        changed
          ? "Take selected. Finish rendering the remaining scenes before building the film."
          : "Scene marked reviewed.",
      );
  }
  async function moveToTrash(target: FilmState, deleted: boolean) {
    setBusy(true);
    setError("");
    try {
      const changed = await request<FilmState>(
        `/films/${target.id}${deleted ? "" : "/restore"}`,
        { revision: target.revision },
        deleted ? "DELETE" : "POST",
      );
      const updated = films.map((f) => (f.id === changed.id ? changed : f));
      setFilms(updated);
      if (deleted && film?.id === target.id) {
        player.current?.pause();
        const next = updated.find((f) => !f.deletedAt) || null;
        setIndex(0);
        setFilm(next);
        const url = new URL(location.href);
        url.searchParams.delete("film");
        if (next) url.searchParams.set("film", next.id);
        history.replaceState(null, "", url);
      } else if (!deleted && !film) {
        setIndex(0);
        setFilm(changed);
      }
      setNotice(
        deleted
          ? `${target.title} moved to Trash.`
          : `${target.title} restored.`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const trash = films.filter((f) => f.deletedAt);
  const trashList = trash.length > 0 && (
    <details className="film-trash">
      <summary>Trash · {trash.length}</summary>
      {trash.map((f) => (
        <div key={f.id}>
          <span>
            {f.title} · {f.artist}
          </span>
          <button
            className="secondary-button"
            disabled={busy}
            aria-label={`Restore ${f.title}`}
            onClick={() => void moveToTrash(f, false)}
          >
            <RotateCcw size={13} />
            Restore
          </button>
        </div>
      ))}
    </details>
  );
  if (!film)
    return (
      <section className="film-review">
        <div className="film-empty">
          <Film size={28} />
          <h2>No video projects</h2>
          <p>
            {error ||
              notice ||
              "Completed music videos appear here for review."}
          </p>
          <a className="secondary-button" href="/music">
            Go to Music
          </a>
        </div>
        {trashList}
      </section>
    );
  if (!scene) return null;
  const contextLead =
    index > 0 &&
    film.scenes[index - 1].takes.some(
      (t) => t.id === film.scenes[index - 1].selected && t.state === "ready",
    )
      ? Math.min(2, film.scenes[index - 1].end - film.scenes[index - 1].start)
      : 0;
  const filmTime = mode === "context" ? scene.start - contextLead + time : time;
  const playingIndex =
    mode !== "scene"
      ? film.scenes.findIndex((s) => filmTime >= s.start && filmTime < s.end)
      : index;
  const running = film.jobs.find((j) => j.index === index && active(j.state));
  const repairPlan =
    scene.takes.find((t) => t.id === running?.id)?.smartPlan || take?.smartPlan;
  const exportJob = [...film.jobs]
    .reverse()
    .find((j) => j.index === null && active(j.state));
  const inProgress = film.jobs
    .filter((j) => j.index !== null && active(j.state))
    .sort((a, b) => (a.queuePosition ?? 0) - (b.queuePosition ?? 0));
  const newestReady = scene.takes.filter((t) => t.state === "ready").at(-1);
  const latestJob = film.jobs.filter((j) => j.index === index).at(-1);
  return (
    <section className="film-review" aria-label="Music video scene review">
      <header className="film-toolbar">
        <label>
          Film
          <select
            aria-label="Review film"
            value={film.id}
            onChange={(e) => {
              const chosen = films.find((f) => f.id === e.target.value);
              if (!chosen) return;
              player.current?.pause();
              setIndex(
                chosen.scenes.findIndex((s) =>
                  s.takes.some((t) => t.state === "ready"),
                ),
              );
              setFilm(chosen);
              const url = new URL(location.href);
              url.searchParams.set("film", chosen.id);
              history.replaceState(null, "", url);
            }}
          >
            {films
              .filter(
                (f) =>
                  !f.deletedAt &&
                  f.scenes.length &&
                  f.scenes.some((s) =>
                    s.takes.some(
                      (t) => t.id === s.selected && t.state === "ready",
                    ),
                  ),
              )
              .map((f) => (
                <option key={f.id} value={f.id}>
                  {f.title} · {f.artist}
                </option>
              ))}
          </select>
        </label>
        <div className="film-toolbar-actions">
          <span>
            {film.scenes.filter((s) => s.review === "approved").length} /{" "}
            {film.scenes.length} reviewed
          </span>
          <button
            className="secondary-button"
            disabled={busy || !complete || !!exportJob || currentExport}
            onClick={() =>
              void mutate("/exports", {
                revision: film.revision,
                requestId: crypto.randomUUID(),
              })
            }
          >
            {exportJob ? "Building film…" : "Build updated film"}
          </button>
          {latestExport && (
            <a
              className="secondary-button"
              href={latestExport.mediaUrl}
              download
            >
              <Download size={15} />
              Download film
            </a>
          )}
          <button
            className="secondary-button"
            disabled={busy || film.jobs.some((j) => active(j.state))}
            title={
              film.jobs.some((j) => active(j.state))
                ? "Finish or cancel pending jobs first"
                : "Move this video project to Trash"
            }
            onClick={() => void moveToTrash(film, true)}
          >
            <Trash2 size={15} />
            Delete project
          </button>
        </div>
      </header>
      {!!film.scenes.length && !film.characterSheetVersion && <div className="film-notice" role="status">
        <p>Prepare a front, left, right and full-body sheet for each character before making new takes. Future renders use Singularity’s first pass.</p>
        <button className="secondary-button" disabled={busy || film.jobs.some((j) => active(j.state))}
          onClick={() => void mutate("/character-sheets", { revision: film.revision, requestId: crypto.randomUUID() })}>
          Prepare character sheets
        </button>
      </div>}
      {film.workflow !== "vrgdg-h3-turbo" && <details className="film-credits-settings">
        <summary>Song credits</summary>
        <FilmCreditsEditor
          value={creditDraft}
          onChange={setCreditDraft}
          background={take?.posterUrl}
        />
        <button
          className="secondary-button"
          disabled={
            busy ||
            JSON.stringify(creditDraft) ===
              JSON.stringify(
                film.credits || defaultCredits(film.title, film.artist),
              )
          }
          onClick={async () => {
            const result = await mutate(
              "/credits",
              { revision: film.revision, credits: creditDraft },
              "PATCH",
            );
            if (result)
              setNotice("Credits saved. Build updated film to include them.");
          }}
        >
          Save credits
        </button>
      </details>}
      {trashList}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="film-notice" role="status">
          {notice}
        </p>
      )}
      {inProgress.length > 0 && (
        <div className="film-render-queue" aria-label="Render queue">
          <span>Render queue</span>
          <ol>
            {inProgress.map((j) => (
              <li key={j.id}>
                <button onClick={() => chooseScene(j.index!)} title={j.phase}>
                  <b>Scene {j.index! + 1}</b>
                  <span>{jobLabel(j)}</span>
                </button>
                {j.state === "queued" && (
                  <button
                    className="film-queue-remove"
                    aria-label={`Remove scene ${j.index! + 1} from queue`}
                    disabled={busy}
                    onClick={() => void mutate(`/jobs/${j.id}/cancel`, {})}
                  >
                    <X size={13} />
                  </button>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
      {exportJob && (
        <p className="film-notice" role="status">
          Film export: {exportJob.phase}
        </p>
      )}
      <div className="film-review-grid">
        <div className="film-viewer">
          <div className="film-player-heading">
            <div className="film-view-tabs">
              <button
                aria-pressed={mode === "film"}
                disabled={!latestExport}
                onClick={() => {
                  player.current?.pause();
                  setMode("film");
                }}
              >
                Full film
              </button>
              {mode === "context" && (
                <button aria-pressed="true">Across cuts</button>
              )}
              <button
                aria-pressed={mode === "scene"}
                onClick={() => {
                  player.current?.pause();
                  setMode("scene");
                }}
              >
                Selected scene
              </button>
            </div>
            <span>
              {mode === "film"
                ? `Scene ${Math.max(0, playingIndex) + 1}`
                : `Scene ${index + 1}${take ? ` · ${take.label}` : " · Not rendered"}`}
            </span>
          </div>
          {src ? (
            <video
              key={src}
              ref={player}
              src={src}
              controls
              playsInline
              preload="metadata"
              onPlay={onPlay}
              onLoadedMetadata={() => {
                const v = player.current;
                if (!v) return;
                if (pendingTime.current !== null) {
                  v.currentTime = pendingTime.current;
                  pendingTime.current = null;
                }
                if (pendingPlay.current) {
                  pendingPlay.current = false;
                  void v.play().catch((e) => setError(e.message));
                }
              }}
              onTimeUpdate={() => setTime(player.current?.currentTime || 0)}
              onError={() =>
                setError(
                  "This video could not load. The saved take is retained; refresh to reconnect.",
                )
              }
            />
          ) : (
            <div className="film-waiting">
              <Film size={32} />
              <p>
                {take?.error || latestJob?.error || (running
                  ? running.phase
                  : take ? "This take is unavailable. Recover the run or render a new take below."
                    : "This scene has not been rendered. You can render it from the scene controls.")}
              </p>
            </div>
          )}
          {mode === "film" && !currentExport && (
            <p className="film-warning">
              Showing the previous export.{" "}
              {exportJob
                ? "The updated cut is building."
                : "Build the updated film to include your selected takes."}
            </p>
          )}
          {mode === "context" && (
            <p className="film-help">
              Selected take with up to two seconds of each neighboring scene.
              The original song plays continuously across both cuts.
            </p>
          )}
          <div className="film-play-actions">
            <button
              className="secondary-button"
              onClick={playInFilm}
              disabled={take?.state !== "ready"}
            >
              <Play size={14} />
              Play across the cut
            </button>
            <button
              className="secondary-button"
              onClick={playScene}
              disabled={take?.state !== "ready"}
            >
              <Play size={14} />
              Play scene
            </button>
            <span>
              {stamp(scene.start)} – {stamp(scene.end)} ·{" "}
              {(scene.end - scene.start).toFixed(2)} s
            </span>
          </div>
          <div className="film-scene-strip" aria-label="Video scenes">
            {film.scenes.map((s) => {
              const selected =
                s.takes.find(
                  (t) =>
                    t.id === previews[s.index]?.takeId && t.state === "ready",
                ) ||
                s.takes.find((t) => t.id === s.selected) ||
                s.takes.find((t) => t.state === "ready");
              const job = inProgress.find((j) => j.index === s.index);
              const lastJob = film.jobs.filter((j) => j.index === s.index).at(-1);
              const failed = !job && lastJob?.state === "failed";
              const failureLabel = lastJob?.kind === "generate" ? "Render failed" : "Repair failed";
              return (
                <button
                  key={s.index}
                  className={`film-scene-card ${index === s.index ? "selected" : ""} ${playingIndex === s.index ? "playing" : ""}`}
                  aria-pressed={index === s.index}
                  aria-label={`Scene ${s.index + 1}: ${s.name}${job ? ` · ${jobLabel(job)}` : failed ? ` · ${failureLabel}` : ""}`}
                  onClick={() => chooseScene(s.index)}
                >
                  <div
                    className={`film-scene-thumbnail ${job ? "pending" : ""}`}
                  >
                    {selected?.state === "ready" ? (
                      <img src={selected.posterUrl} alt="" loading="lazy" />
                    ) : !job && !failed ? (
                      <span>Not rendered</span>
                    ) : null}
                    {job && (
                      <span
                        className={`film-render-overlay ${job.state === "running" ? "rendering" : ""}`}
                        title={job.phase}
                      >
                        <i aria-hidden="true" />
                        {jobLabel(job)}
                      </span>
                    )}
                    {failed && (
                      <span className="film-render-overlay">{failureLabel}</span>
                    )}
                  </div>
                  <span>
                    <b>{String(s.index + 1).padStart(2, "0")}</b>
                    {s.review === "approved" ? (
                      <Check size={14} />
                    ) : s.review === "flagged" ? (
                      <Flag size={13} />
                    ) : null}
                  </span>
                  <strong>{s.name}</strong>
                  <small>
                    {stamp(s.start)} ·{" "}
                    {sceneVoiceLabel(s)}
                  </small>
                </button>
              );
            })}
          </div>
        </div>
        <aside className="film-inspector" aria-label="Selected scene controls">
          <div className="film-inspector-title">
            <div>
              <small>SCENE {String(index + 1).padStart(2, "0")}</small>
              <h2>{scene.name}</h2>
            </div>
            <div>
              <button
                className="icon-button"
                aria-label="Previous scene"
                disabled={index === 0}
                onClick={() => chooseScene(index - 1)}
              >
                <ChevronLeft size={18} />
              </button>
              <button
                className="icon-button"
                aria-label="Next scene"
                disabled={index === film.scenes.length - 1}
                onClick={() => chooseScene(index + 1)}
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
          {!scene.takes.some((t) => t.state === "ready") && <div className="film-take-note">
            <p>{scene.action || scene.continuity}</p>
            <p className="film-help">{sceneVoiceLabel(scene)}</p>
            {latestJob?.error && !take?.error && <p className="form-error">{latestJob.error}</p>}
            {latestJob?.state === "failed" && !take?.error && <button
              className="secondary-button" disabled={busy || !!running}
              onClick={() => void mutate(`/jobs/${latestJob.id}/recover`, {})}>
              Recover existing run
            </button>}
            <button className="primary-button"
              disabled={busy || !!running || !film.characterSheetVersion || film.jobs.some((j) => j.kind === "prepare" && active(j.state)) ||
                (film.workflow === "vrgdg-h3-turbo" && (film.vocalTiming?.version || 0) < 2)}
              onClick={() => void renderMissing()}>
              {running ? jobLabel(running) : scene.takes.length ? "Render new take" : "Render scene"}
            </button>
            <p className="film-help">Uses this scene's saved storyboard direction, character reference and song excerpt. Earlier attempts are retained.</p>
          </div>}
          {take && <>
          <label>
            Take
            <select
              aria-label="Scene take"
              value={take.id}
              onChange={(e) => {
                player.current?.pause();
                setTakeIdPreview(e.target.value);
                setMode("scene");
                pendingTime.current = 0;
              }}
            >
              {scene.takes.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                  {t.id === scene.selected ? " · In film" : ""}
                  {t.state !== "ready" ? ` · ${t.state}` : ""}
                </option>
              ))}
            </select>
          </label>
          {take.timingOutdated && <p role="status" className="film-help">This take was made before the vocal timing was corrected. Its video is unchanged; regenerate the scene to test the corrected direction.</p>}
          {take.correction && (
            <details className="film-take-note">
              <summary>Requested change</summary>
              <p>{take.correction}</p>
            </details>
          )}
          {repairPlan && (
            <details className="film-take-note" open>
              <summary>Repair plan</summary>
              <p>{repairPlan.intent}</p>
              <p>{repairPlan.explanation}</p>
              <p className="film-help">
                {repairPlan.startSeconds.toFixed(2)}–
                {repairPlan.endSeconds.toFixed(2)} s ·{" "}
                {repairPlan.cutPolicy === "single-shot"
                  ? "One continuous shot"
                  : "Keep existing shots"}{" "}
                ·{" "}
                {repairPlan.speechPolicy === "silent"
                  ? "Silent character"
                  : "Original vocal performance"}
              </p>
            </details>
          )}
          {take.checks?.aiReview && (
            <div
              className={
                take.checks.aiReview.result === "no-obvious-issue"
                  ? "film-take-note"
                  : "film-warning"
              }
              role="status"
            >
              <strong>
                {take.checks.aiReview.result === "needs-review"
                  ? "Review found a concern"
                  : "Frame review"}
              </strong>
              <p>{take.checks.aiReview.summary}</p>
              {take.checks.aiReview.findings.length > 0 && (
                <ul>
                  {take.checks.aiReview.findings.map((finding, i) => (
                    <li key={i}>{finding}</li>
                  ))}
                </ul>
              )}
              <p className="film-help">
                {take.checks.aiReview.coverage ||
                  "Check the result in playback before using this take."}
              </p>
            </div>
          )}
          {!!take.checks?.manualFindings?.length && (
            <p className="film-warning">
              Visual review: {take.checks.manualFindings.join(" ")}
            </p>
          )}
          {!!take.checks?.possibleInternalCuts?.length && (
            <p className="film-warning">
              Possible internal cuts at{" "}
              {take.checks.possibleInternalCuts
                .map((t) => `+${t.toFixed(2)}s`)
                .join(", ")}
              . Check this take before using it.
            </p>
          )}
          {take.contextChanged && take.id !== "original" && (
            <p className="film-warning">
              The film has been edited since this take was requested. Check both
              neighboring cuts.
            </p>
          )}
          {take.error && (
            <p className="form-error">
              {take.error}
              {!take.error.startsWith("H3 rejected") && (
                <button
                  className="quiet-button"
                  disabled={busy || !!running}
                  onClick={() => void mutate(`/jobs/${take.id}/recover`, {})}
                >
                  Recover existing run
                </button>
              )}
            </p>
          )}
          {latestJob?.state === "failed" && latestJob.id !== take.id && (
            <p className="film-warning" role="status">
              Last repair failed: {latestJob.error} Your current take is still
              available.
            </p>
          )}
          <button
            className="secondary-button film-use-take"
            disabled={busy || take.state !== "ready"}
            onClick={() => void accept()}
          >
            <Check size={15} />
            {take.id === scene.selected
              ? "Mark scene reviewed"
              : "Use this take"}
          </button>
          {newestReady &&
            newestReady.id !== take.id &&
            newestReady.id !== "original" && (
              <button
                className="quiet-button"
                onClick={() => {
                  setTakeIdPreview(newestReady.id);
                  setMode("scene");
                }}
              >
                Review {newestReady.label}
              </button>
            )}
          {take.baseTakeId && (
            <p className="film-help">
              {take.method === "regenerate" ? "New render from the character reference" : take.smartPlan?.method === "reuse-shot"
                ? `Continuous section · ${take.smartPlan.sourceStartSeconds?.toFixed(2)}–${take.smartPlan.sourceEndSeconds?.toFixed(2)} s · ${Math.round((take.smartPlan.playbackSpeed || 1) * 100)}% speed`
                : take.smartPlan
                  ? `Smart repair · ${take.smartPlan.method === "frame-regenerate" ? "Rebuilt from a frame" : "Source video edit"}`
                  : take.method === "frame-regenerate" && take.repairRange
                    ? `Range replacement · ${(take.repairRange.startFrame / film.fps).toFixed(2)}–${(take.repairRange.endFrame / film.fps).toFixed(2)} s`
                    : take.method === "timing"
                      ? `Timing ${take.shiftFrames! > 0 ? "+" : ""}${take.shiftFrames} frames`
                      : "Source video edit"}
              {take.method === "regenerate" ? " · Compared with " : " · From "}
              {scene.takes.find((t) => t.id === take.baseTakeId)?.label ||
                "saved take"}
            </p>
          )}
          {take.state === "ready" && <>
          <label>
            Issue
            <select
              aria-label="Scene issue"
              value={issue}
              onChange={(e) => setIssue(e.target.value)}
            >
              <option value="none">No issue selected</option>
              <option value="lip-sync">Lip sync</option>
              <option value="identity">Person looks different</option>
              <option value="objects">Objects or continuity</option>
              <option value="motion">Movement or anatomy</option>
              <option value="other">Other</option>
            </select>
          </label>
          {film.workflow !== "vrgdg-h3-turbo" && <label>
            Repair method
            <select
              aria-label="Repair method"
              value={repairMethod}
              onChange={(e) =>
                setRepairMethod(
                  e.target.value as
                    "smart" | "source-edit" | "timing" | "frame-regenerate",
                )
              }
            >
              <option value="smart">Smart repair</option>
              <option value="source-edit">Edit whole take with H3</option>
              <option value="frame-regenerate">
                Replace motion from a frame
              </option>
              <option value="timing">
                Adjust timing · keep existing video
              </option>
            </select>
          </label>}
          <p className="film-help">
            Source: {take.label}.{" "}
              {film.workflow === "vrgdg-h3-turbo" ? (film.characterSheetVersion
                ? "Regenerates this scene from its assigned character sheets with Singularity. Only its designated singer follows the gated vocal excerpt; the full song remains the soundtrack."
                : "Regenerates this whole scene with the original shared character image and song excerpt.")
              : repairMethod === "smart"
              ? "Reads the scene frames and your note, chooses a repair method, then checks the result. Describe what looks wrong and what you want instead."
              : repairMethod === "timing"
                ? "For a consistent early or late mouth movement. Moves the video against the unchanged song; it cannot correct the wrong mouth shapes."
                : repairMethod === "frame-regenerate"
                  ? "Uses the first frame of your chosen range to create new motion. Frames outside that range stay intact. Check both joins before using the take."
                  : "Uses the whole video as a reference. H3 may change motion or shot order; use a range replacement to protect the rest of the scene."}
          </p>
          {repairMethod === "frame-regenerate" && (
            <fieldset className="film-repair-range">
              <legend>Replace part of this scene</legend>
              <label>
                From (seconds)
                <input
                  aria-label="Repair start seconds"
                  type="number"
                  min={0}
                  max={sceneSeconds - 2}
                  step={1 / film.fps}
                  value={repairStart}
                  onChange={(e) => setRepairStart(Number(e.target.value))}
                />
              </label>
              <label>
                To (seconds)
                <input
                  aria-label="Repair end seconds"
                  type="number"
                  min={2}
                  max={sceneSeconds}
                  step={1 / film.fps}
                  value={repairEnd}
                  onChange={(e) => setRepairEnd(Number(e.target.value))}
                />
              </label>
              <p className="film-help">
                At least 2 seconds. Times are relative to this scene.
              </p>
              {(take.checks?.possibleInternalCuts || [])
                .filter((t) => sceneSeconds - t >= 2)
                .map((t) => (
                  <button
                    key={t}
                    className="secondary-button"
                    onClick={() => {
                      setRepairStart(t);
                      setRepairEnd(sceneSeconds);
                    }}
                  >
                    From detected cut at {t.toFixed(2)} s
                  </button>
                ))}
            </fieldset>
          )}
          {repairMethod === "timing" && (
            <label>
              Video timing
              <div className="film-timing-adjust">
                <button
                  className="secondary-button"
                  aria-label="Move video one frame earlier"
                  disabled={shiftFrames <= -24}
                  onClick={() => setShiftFrames((n) => n - 1)}
                >
                  −
                </button>
                <output>
                  {shiftFrames > 0 ? "+" : ""}
                  {shiftFrames} frames · {(shiftFrames / film.fps).toFixed(3)} s
                </output>
                <button
                  className="secondary-button"
                  aria-label="Move video one frame later"
                  disabled={shiftFrames >= 24}
                  onClick={() => setShiftFrames((n) => n + 1)}
                >
                  +
                </button>
              </div>
              <span className="film-help">
                + makes the mouth movement later; − makes it earlier. Holds the
                first or last frame to keep the scene length. Create a preview
                take, then play across the cut.
              </span>
            </label>
          )}
          <label>
            What should change?
            <textarea
              aria-label="Scene correction"
              rows={4}
              maxLength={4000}
              placeholder="Describe the problem and the action you want instead."
              value={correction}
              onChange={(e) => setCorrection(e.target.value)}
            />
          </label>
          <label>
            Continuity for this scene
            <textarea
              aria-label="Scene continuity"
              rows={3}
              maxLength={6000}
              placeholder="Who is present, what each person holds, what must stay in place."
              value={continuity}
              onChange={(e) => setContinuity(e.target.value)}
            />
          </label>
          <div className="film-correction-actions">
            <button
              className="secondary-button"
              disabled={busy}
              onClick={async () => {
                const d = await mutate(
                  `/scenes/${index}`,
                  { revision: film.revision, correction, continuity, issue },
                  "PATCH",
                );
                if (d) setNotice("Scene notes saved.");
              }}
            >
              Save notes
            </button>
            <button
              className="primary-button"
              disabled={
                busy ||
                !!running ||
                take.state !== "ready" ||
                (repairMethod !== "timing" && !film.characterSheetVersion) ||
                film.jobs.some((j) => j.kind === "prepare" && active(j.state)) ||
                (repairMethod === "frame-regenerate" &&
                  (repairStart < 0 ||
                    repairEnd > sceneSeconds ||
                    repairEnd - repairStart < 2)) ||
                (repairMethod === "timing" ? !shiftFrames : !correction.trim())
              }
              onClick={() => void rerender()}
            >
              <RotateCcw size={15} />
              {running
                ? jobLabel(running)
                : inProgress.length
                  ? "Add to queue"
                  : repairMethod === "timing"
                    ? "Create timing preview"
                    : film.workflow === "vrgdg-h3-turbo" ? "Regenerate scene" : "Render repair"}
            </button>
          </div>
          {running && (
            <p className="film-help" role="status">
              {running.phase}. You can select another scene while this runs.
            </p>
          )}
          <p className="film-help">
            One new take per click. Original timing, song audio and earlier
            takes are retained. Review the result before using it.
          </p>
          </>}
          </>}
          <details open={scene.type === "performance"}>
            <summary>Vocal timing</summary>
            {take?.checks?.conditioningAudio === "isolated-vocal" && (
              <p>
                This take uses the isolated vocal for lip-sync guidance.
                Playback retains the full original song.
              </p>
            )}
            <p>
              {scene.type === "performance"
                ? `First aligned vocal: +${scene.timing.leadingRest.toFixed(3)} s. Rest times are included in the retry instructions.`
                : "This is a story scene. People should stay silent while the soundtrack plays."}
            </p>
            <div className="film-vocal-map">
              {scene.timing.spans.map((s, i) => (
                <span
                  key={i}
                  style={{
                    left: `${(100 * s.start) / (scene.end - scene.start)}%`,
                    width: `${(100 * (s.end - s.start)) / (scene.end - scene.start)}%`,
                  }}
                />
              ))}
            </div>
            <p className="film-word-timing">
              {scene.timing.words.map((w, i) => (
                <button
                  key={i}
                  title={`+${w.start.toFixed(3)} s${w.review ? " · " + w.review : ""}`}
                  className={w.review ? "uncertain" : ""}
                  onClick={() => {
                    if (player.current)
                      player.current.currentTime =
                        w.start +
                        (mode === "film"
                          ? scene.start
                          : mode === "context"
                            ? contextLead
                            : 0);
                  }}
                >
                  {w.text}
                </button>
              ))}
            </p>
            <small>
              {scene.timing.uncertainWords} words flagged for timing review.
              Exact audio cuts do not guarantee generated lip sync.
            </small>
          </details>
          <details>
            <summary>References and continuity</summary>
            <div className="film-reference-grid">
              <figure>
                <img
                  src={scene.referenceUrl}
                  alt="Original character and scene reference"
                />
                <figcaption>{scene.storyboardUrl ? "Storyboard opening frame" : film.cast?.find((c) => c.id === scene.castIds?.[0])?.name || "Identity / scene"}</figcaption>
              </figure>
              {scene.identityReferences.map((ref) => (
                <figure key={ref.url}>
                  <img src={ref.url} alt={ref.role} />
                  <figcaption>{ref.role}</figcaption>
                </figure>
              ))}
              {[index - 1, index + 1]
                .filter(
                  (i) =>
                    i >= 0 &&
                    i < film.scenes.length &&
                    film.scenes[i].takes.some(
                      (t) =>
                        t.id === film.scenes[i].selected && t.state === "ready",
                    ),
                )
                .map((i) => {
                  const s = film.scenes[i],
                    t = s.takes.find((t) => t.id === s.selected)!;
                  return (
                    <figure key={i}>
                      <img
                        src={
                          t.posterUrl +
                          (i < index ? "?edge=end" : "?edge=start")
                        }
                        alt={`Scene ${i + 1} boundary reference`}
                      />
                      <figcaption>
                        Scene {i + 1} · {s.name}
                      </figcaption>
                    </figure>
                  );
                })}
            </div>
            <p>
              Smart repair inspects the chosen take and uses the film's
              continuity to choose an editing method. Its plan shows which
              references or existing section it will use. The neighboring frames
              shown here help you review how the scenes join.
            </p>
            <label>
              Film continuity
              <textarea
                aria-label="Film continuity"
                rows={6}
                value={globalContext}
                maxLength={6000}
                onChange={(e) => setGlobalContext(e.target.value)}
              />
            </label>
            <button
              className="secondary-button"
              disabled={busy}
              onClick={async () => {
                const d = await mutate(
                  "/context",
                  { revision: film.revision, continuity: globalContext },
                  "PATCH",
                );
                if (d) setNotice("Film continuity saved for future retries.");
              }}
            >
              Save film continuity
            </button>
          </details>
          <details>
            <summary>Checks and review</summary>
            <p>
              {take?.state !== "ready" ? "No completed take is available for review yet."
                : take.checks ? "This take passed complete decoding and the exact frame-count check."
                  : "Original scene retained from the completed film."}
            </p>
            <p>
              Check the mouth through every sung phrase, each person's face and
              clothing, object count and ownership, and both cuts. These visual
              checks require review; retries never run automatically.
            </p>
          </details>
        </aside>
      </div>
    </section>
  );
}
