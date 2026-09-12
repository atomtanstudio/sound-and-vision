import { useEffect, useRef, useState, type RefObject } from "react";
import {
  ArrowLeft,
  Check,
  Film,
  LoaderCircle,
  Plus,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { ApiError, request } from "../music-studio/api";
import { type Track } from "../music-studio/model";
import { FilmReview, type FilmState } from "./FilmReview";
import { FilmSetup, ConceptFields } from "./FilmSetup";
import { StoryboardRerender } from "./StoryboardRerender";
import { StoryboardFrameActions } from "./StoryboardFrameActions";
import { SceneVideo } from "./SceneVideo";
import type { FilmSetupPayload } from "./film-concept";
import "./directed-video.css";
import { sceneVoiceLabel } from "./scene-voice";


const active = (state: string) =>
  ["queued", "running", "waiting-for-resource"].includes(state);
const stamp = (s: number) =>
  `${Math.floor(s / 60)}:${Math.floor(s % 60)
    .toString()
    .padStart(2, "0")}`;
type Project = Omit<FilmState, "scenes"> & {
  scenes: (FilmState["scenes"][number] & { action?: string })[];
};

type StoryboardEdit = { action:string; framing:string; continuity:string };
function StoryboardEditor({scene,busy,save}:{scene:Project['scenes'][number];busy:boolean;save:(edit:StoryboardEdit)=>Promise<void>}) {
  const [edit,setEdit]=useState<StoryboardEdit>({action:scene.story!.action,framing:scene.story!.framing,continuity:scene.story!.continuity});
  return <details className="film-scene-plan"><summary>Edit this storyboard frame</summary><div>
    <label>Physical action<textarea rows={3} minLength={20} maxLength={2000} disabled={busy} value={edit.action} onChange={(e)=>setEdit({...edit,action:e.target.value})}/></label>
    <label>Framing and camera<textarea rows={2} minLength={10} maxLength={700} disabled={busy} value={edit.framing} onChange={(e)=>setEdit({...edit,framing:e.target.value})}/></label>
    <label>Continuity<textarea rows={2} minLength={10} maxLength={1500} disabled={busy} value={edit.continuity} onChange={(e)=>setEdit({...edit,continuity:e.target.value})}/></label>
    <button className="secondary-button" disabled={busy || edit.action.trim().length<20 || edit.framing.trim().length<10 || edit.continuity.trim().length<10}
      onClick={()=>void save(edit)}>Update storyboard frame</button>
    <p>Checks the revision against the story, then creates one replacement image. The cast and cut points stay fixed.</p>
  </div></details>;
}

function SceneCutEditor({ end, index, busy, save }: {
  end: number; index: number; busy: boolean; save: (seconds: number) => void;
}) {
  const [value, setValue] = useState(end.toFixed(3));
  useEffect(() => setValue(end.toFixed(3)), [end]);
  return <form className="directed-cut-editor" onSubmit={(e) => { e.preventDefault(); save(Number(value)); }}>
    <label>Cut after scene {index + 1} (song seconds)
      <input type="number" min="0.042" max="900" step="0.001" required
        aria-label={`Cut after scene ${index + 1} in seconds`} value={value}
        onChange={(e) => setValue(e.target.value)} />
    </label>
    <button className="secondary-button" disabled={busy || !value || Math.abs(Number(value)-end) < .0006}>Apply cut</button>
  </form>;
}

export function DirectedVideoWorkspace({
  track,
  tracks,
  chooseSource,
  audioRef,
  language,
}: {
  track: Track;
  tracks: Track[];
  chooseSource: (id: string) => void;
  audioRef: RefObject<HTMLAudioElement | null>;
  language: string;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [rerenderIndex,setRerenderIndex]=useState<number|null>(null);
  const [loaded, setLoaded] = useState(false),
    [busy, setBusy] = useState(false);
  const [error, setError] = useState(""),
    [review, setReview] = useState(false),
    [trash, setTrash] = useState(false);
  const createRequest = useRef<{ id: string; payload: string } | null>(null);
  const pending = useRef(new Map<string, { id: string; revision: number }>());
  const selection = useRef<string | null>(null);
  useEffect(() => {
    let alive = true;
    request<{ films: Project[] }>("/films?include_deleted=true")
      .then(({ films }) => {
        if (!alive) return;
        setProjects(films);
        const saved = new URLSearchParams(location.search).get("film");
        const found = saved === "new" ? undefined :
          films.find((f) => f.takeId === track.id && f.id === saved) ||
          films.find((f) => !f.deletedAt && f.takeId === track.id);
        selection.current = found?.id || null;
        setProject(found || null);
        setLoaded(true);
      })
      .catch((e) => {
        if (alive) {
          setError(e.message);
          setLoaded(true);
        }
      });
    return () => {
      alive = false;
      selection.current = null;
    };
  }, [track.id]);
  const projectId = project?.id;
  useEffect(() => {
    if (!projectId || review || project?.deletedAt) return;
    let alive = true;
    const timer = setInterval(() => {
      if (busy) return;
      request<Project>(`/films/${projectId}`)
        .then((f) => {
          if (alive) {
            update(f);
            setError("");
          }
        })
        .catch((e) => {
          if (alive) void handleError(e, projectId, () => alive);
        });
    }, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [projectId, project?.deletedAt, busy, review]);
  async function handleError(e: Error, id = project?.id, current = () => true) {
    if (!current()) return;
    setError(e.message);
    if (!(e instanceof ApiError) || e.status !== 404 || !id) return;
    if (selection.current !== id) return;
    // Stop offering operations immediately, even if the follow-up list fails.
    pending.current.clear();
    setProject(null);
    setReview(false);
    try {
      const { films } = await request<{ films: Project[] }>(
        "/films?include_deleted=true",
      );
      // Another project may have been selected while the list was loading.
      if (selection.current !== id) return;
      const found = films.find((f) => f.id === id && f.takeId === track.id);
      setProjects(films);
      setProject(found || null);
      if (found) setError("");
    } catch {
      /* Keep the original error and the render controls removed. */
    }
  }
  function update(f: Project) {
    selection.current = f.id;
    setProject(f);
    setProjects((old) => [...old.filter((p) => p.id !== f.id), f]);
  }
  function select(f: Project | null) {
    selection.current = f?.id || null;
    setProject(f);
    setReview(false);
    setRerenderIndex(null);
    setError("");
    const url = new URL(location.href);
    if (f) url.searchParams.set("film", f.id);
    else url.searchParams.set("film", "new");
    history.replaceState({}, "", url);
  }
  async function act(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      await handleError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  async function create(draft: FilmSetupPayload) {
    await act(async () => {
      const payload = { ...draft, workflow: "short-film", takeId: track.id, language };
      const text = JSON.stringify(payload);
      if (createRequest.current?.payload !== text)
        createRequest.current = { id: crypto.randomUUID(), payload: text };
      const f = await request<Project>("/films", { ...payload, requestId: createRequest.current.id });
      update(f); select(f); createRequest.current = null;
    });
  }
  async function generate(indices: number[]) {
    if (!project || project.deletedAt) return;
    await act(async () => {
      let latest = await request<Project>(`/films/${project.id}`);
      for (const index of indices) {
        const actionKey = `${project.id}:${index}`;
        let intent = pending.current.get(actionKey);
        if (!intent) {
          intent = { id: crypto.randomUUID(), revision: latest.revision };
          pending.current.set(actionKey, intent);
        }
        try {
          latest = await request<Project>(
            `/films/${project.id}/scenes/${index}/generate`,
            { requestId: intent.id, revision: intent.revision },
          );
        } catch (error) {
          // A rejected revision is safe to retry with fresh inputs; an ambiguous
          // connection failure must keep its original idempotency key.
          if (
            !(error instanceof ApiError) ||
            error.status !== 409 ||
            !error.message.includes("The film changed.")
          )
            throw error;
          latest = await request<Project>(`/films/${project.id}`);
          intent = { ...intent, revision: latest.revision };
          pending.current.set(actionKey, intent);
          latest = await request<Project>(
            `/films/${project.id}/scenes/${index}/generate`,
            { requestId: intent.id, revision: intent.revision },
          );
        }
        pending.current.delete(actionKey);
        update(latest);
      }
    });
  }
  async function jobAction(id: string, action: string) {
    if (!project) return;
    await act(async () =>
      update(
        await request<Project>(`/films/${project.id}/jobs/${id}/${action}`, {}),
      ),
    );
  }
  async function rerenderVideo(index:number) {
    if(!project)return;
    const key=`${project.id}:${index}:video-rerender`;
    setBusy(true);
    try {
      const latest=await request<Project>(`/films/${project.id}`);
      let intent=pending.current.get(key);
      if(!intent){intent={id:crypto.randomUUID(),revision:latest.revision};pending.current.set(key,intent);}
      update(await request<Project>(`/films/${project.id}/scenes/${index}/rerender`,{
        requestId:intent.id,revision:intent.revision,
      }));
      pending.current.delete(key);
    } catch(error) {if(error instanceof ApiError && error.status===409)pending.current.delete(key);throw error;}
    finally {setBusy(false);}
  }
  async function acceptVideo(index:number,takeId:string) {
    if(!project)return;
    await act(async()=>{
      const latest=await request<Project>(`/films/${project.id}`);
      update(await request<Project>(`/films/${project.id}/scenes/${index}/takes/${takeId}/accept`,{revision:latest.revision}));
    });
  }
  async function reviseStoryboard(index:number,edit:StoryboardEdit) {
    if(!project)return;
    await act(async()=>{
      const key=`${project.id}:${index}:storyboard:${JSON.stringify(edit)}`;
      let intent=pending.current.get(key);
      if(!intent){intent={id:crypto.randomUUID(),revision:project.revision};pending.current.set(key,intent);}
      try {
        update(await request<Project>(`/films/${project.id}/scenes/${index}/storyboard`,{
          ...edit,revision:intent.revision,requestId:intent.id,
        }));
        pending.current.delete(key);
      } catch(error){if(error instanceof ApiError && error.status===409)pending.current.delete(key);throw error;}
    });
  }
  async function rerenderStoryboard(index:number,prompt:string,revision:number) {
    if(!project)return;
    const key=`${project.id}:${index}:rerender:${prompt}`;
    let intent=pending.current.get(key);
    if(!intent){intent={id:crypto.randomUUID(),revision};pending.current.set(key,intent);}
    setBusy(true);
    try {
      update(await request<Project>(`/films/${project.id}/scenes/${index}/storyboard/rerender`,{
        prompt,revision:intent.revision,requestId:intent.id,
      }));
      pending.current.delete(key);
    } catch(error){if(error instanceof ApiError && error.status===409)pending.current.delete(key);throw error;}
    finally{setBusy(false);}
  }
  async function updateVocalTiming() {
    if (!project) return;
    await act(async () => {
      const key = `${project.id}:vocal-timing`;
      let intent = pending.current.get(key);
      if (!intent) {
        intent = { id: crypto.randomUUID(), revision: project.revision };
        pending.current.set(key, intent);
      }
      update(await request<Project>(`/films/${project.id}/vocal-timing`, {
        requestId: intent.id, revision: intent.revision,
      }));
      pending.current.delete(key);
    });
  }
  async function prepareCast() {
    if (!project) return;
    await act(async () => {
      const key = `${project.id}:character-sheets`;
      let intent = pending.current.get(key);
      if (!intent) {
        intent = { id: crypto.randomUUID(), revision: project.revision };
        pending.current.set(key, intent);
      }
      try {
        update(await request<Project>(`/films/${project.id}/character-sheets`, {
          requestId: intent.id, revision: intent.revision,
        }));
        pending.current.delete(key);
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) pending.current.delete(key);
        throw error;
      }
    });
  }
  async function remove() {
    if (!project) return;
    await act(async () => {
      const f = await request<Project>(
        `/films/${project.id}`,
        { revision: project.revision },
        "DELETE",
      );
      setProjects((old) => old.map((p) => (p.id === f.id ? f : p)));
      select(null);
    });
  }
  async function restore(f: Project) {
    await act(async () => {
      const restored = await request<Project>(`/films/${f.id}/restore`, {
        revision: f.revision,
      });
      pending.current.clear();
      setProjects((old) => old.map((p) => (p.id === f.id ? restored : p)));
      if (restored.takeId === track.id) select(restored);
    });
  }
  const sameSong = projects.filter(
    (f) => !f.deletedAt && f.takeId === track.id,
  );
  const ready =
    project?.scenes.filter((s) =>
      s.takes.some((t) => t.id === s.selected && t.state === "ready"),
    ).length || 0;
  const timingNeedsUpdate = project?.workflow === "vrgdg-h3-turbo" &&
    (project.vocalTiming?.version || 0) < 2;
  const castNeedsPreparation = !!project?.scenes.length && !project.characterSheetVersion;
  const preparing = !!project?.jobs.some((j) => j.kind === "prepare" && active(j.state));
  const waiting =
    project?.scenes.filter(
      (s) => !s.takes.some((t) => t.state === "ready" || active(t.state)),
    ) || [];
  const allReady = !!project?.scenes.length && ready === project.scenes.length;
  const jobs =
    project?.jobs.filter((j) => {
      if (active(j.state)) return true;
      if (j.state !== "failed") return false;
      if (j.index != null && project.jobs.filter((other) => other.index === j.index).at(-1)?.id !== j.id) return false;
      const failedExport = project.exports.find((e) => e.id === j.id);
      return (
        !failedExport ||
        !project.exports.some(
          (e) => e.state === "ready" && e.revision >= failedExport.revision,
        )
      );
    }) || [];
  if (review && project && !project.deletedAt)
    return (
      <>
        <button className="secondary-button" onClick={() => setReview(false)}>
          <ArrowLeft size={15} /> Storyboard
        </button>
        <FilmReview
          key={project.id}
          takeId={track.id}
          initialFilmId={project.id}
          audioRef={audioRef}
          onPlay={() => audioRef.current?.pause()}
        />
      </>
    );
  return (
    <div className="directed-video">
      {project && rerenderIndex!==null && project.scenes[rerenderIndex]?.storyboardUrl && <StoryboardRerender
        key={`${project.id}:${rerenderIndex}`} filmId={project.id} index={rerenderIndex}
        name={project.scenes[rerenderIndex].name} imageUrl={project.scenes[rerenderIndex].storyboardUrl!}
        close={()=>setRerenderIndex(null)} submit={(prompt,revision)=>rerenderStoryboard(rerenderIndex,prompt,revision)}/>}
      <div className="directed-source">
        {track.cover && <img src={track.cover} alt="" />}
        <label>
          Song
          <select
            aria-label="Music video song"
            value={track.id}
            onChange={(e) => {
              history.replaceState({}, "", "/video");
              chooseSource(e.target.value);
            }}
          >
            {tracks
              .filter((t) => !t.deletedAt && (t.audio || t.audioUrl))
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title}
                  {t.take ? ` · Take ${t.take}` : ""}
                </option>
              ))}
          </select>
        </label>
        <span>{project?.workflow === "vrgdg-h3-turbo"
          ? `16:9 · ${project.output?.join(" × ") || "Native output"} · 24 fps`
          : "16:9 · 1080p · 24 fps"}</span>
      </div>
      <div className="directed-project-bar">
        <label className="sr-only" htmlFor="film-project">
          Video project
        </label>
        <select
          id="film-project"
          value={project?.id || ""}
          onChange={(e) =>
            select(sameSong.find((f) => f.id === e.target.value) || null)
          }
        >
          <option value="">New music video</option>
          {project?.deletedAt && (
            <option value={project.id}>{project.title} · In Trash</option>
          )}
          {sameSong.map((f) => (
            <option key={f.id} value={f.id}>
              {f.title} ·{" "}
              {f.scenes.length ? `${f.scenes.length} scenes` : "Preparing"}
            </option>
          ))}
        </select>
        <button
          className="secondary-button"
          disabled={busy}
          onClick={() => select(null)}
        >
          <Plus size={15} /> New project
        </button>
        <button className="secondary-button" onClick={() => setTrash(!trash)}>
          <Trash2 size={14} /> Trash
        </button>
      </div>
      {error && (
        <p className="directed-error" role="alert">
          {error}
        </p>
      )}
      {trash && (
        <div className="directed-trash">
          {projects.filter((f) => f.deletedAt).length ? (
            projects
              .filter((f) => f.deletedAt)
              .map((f) => (
                <div key={f.id}>
                  <span>{f.title}</span>
                  <button
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => void restore(f)}
                  >
                    Restore
                  </button>
                </div>
              ))
          ) : (
            <p>Trash is empty.</p>
          )}
        </div>
      )}
      {!loaded ? (
        <p role="status">Loading projects…</p>
      ) : project?.deletedAt ? (
        <section className="directed-setup" aria-label="Video project in Trash">
          <div>
            <h2>{project.title}</h2>
            <p>
              This project is in Trash. Restore it to continue with its existing
              scenes and visual reference.
            </p>
          </div>
          <div>
            <button
              className="primary-button"
              disabled={busy}
              onClick={() => void restore(project)}
            >
              <RotateCcw size={16} /> Restore project
            </button>
          </div>
        </section>
      ) : !project ? (
        <FilmSetup key={track.id} track={track} busy={busy} onCreate={create}/>
      ) : (
        <>
          <div className="directed-summary">
            <div>
              <h2>{project.title}</h2>
              {project.workflow === "short-film"
                ? <p>Review the characters and storyboard, then animate your scenes.</p>
                : project.workflow === "vrgdg-h3-turbo" && <p>Earlier music video project</p>}
              {project.vocalTiming?.firstVocal != null && <p>Vocal timing follows the recording, including instrumental rests.</p>}
              <p>
                {project.scenes.length
                  ? `${ready} of ${project.scenes.length} scenes ready · ${stamp(project.duration)}`
                  : "Preparing the storyboard and character sheets"}
              </p>
            </div>
            <div className="directed-actions">
              {ready > 0 && (
                <button
                  className="primary-button"
                  onClick={() => setReview(true)}
                >
                  <Check size={15} />{" "}
                  {allReady ? "Review & export" : "Review scenes"}
                </button>
              )}
              {!!waiting.length && (
                <button
                  className="primary-button"
                  disabled={busy || timingNeedsUpdate || castNeedsPreparation || preparing}
                  onClick={() => void generate(waiting.map((s) => s.index))}
                >
                  Animate remaining {waiting.length} scenes
                </button>
              )}
              <button
                className="icon-button"
                aria-label="Delete video project"
                title="Move project to Trash"
                disabled={busy || jobs.some((j) => active(j.state))}
                onClick={() => void remove()}
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
          {project.concept && <details className="film-storyboard-intro">
            <summary>The film concept · {project.creation?.treatment === "performance" ? "performance treatment" : "introduction to resolution"}</summary>
            <ConceptFields concept={project.concept} performance={project.creation?.treatment === "performance"}/>
          </details>}
          {castNeedsPreparation && <div className="directed-job" role="status">
            <div><strong>Prepare the cast before new renders</strong><p>Create a multi-view sheet for each character and use Singularity for future takes. Existing video takes remain available.</p></div>
            <button className="secondary-button" disabled={busy || project.jobs.some((j) => active(j.state)) || timingNeedsUpdate}
              onClick={() => void prepareCast()}>Prepare character sheets</button>
          </div>}
          {timingNeedsUpdate && <div className="directed-job" role="status">
            <div><strong>Vocal timing needs correction</strong><p>This older Audio Drive board did not locate the vocals. Update its scene directions and timing while keeping the character, cuts and existing takes.</p></div>
            <button className="secondary-button" disabled={busy || project.jobs.some((j) => active(j.state))}
              onClick={() => void updateVocalTiming()}>Update vocal timing</button>
          </div>}
          {jobs.map((j) => (
            <div key={j.id} className="directed-job" role="status">
              {active(j.state) && (
                <LoaderCircle className="directed-spinner" size={16} />
              )}
              <div>
                <strong>
                  {j.sceneIndex != null
                    ? `Storyboard frame ${j.sceneIndex + 1}`
                    : j.index == null
                    ? j.kind === "prepare"
                      ? "Storyboard"
                      : "Film export"
                    : `Scene ${j.index + 1}`}{" "}
                  ·{" "}
                  {j.state === "queued" && j.index != null
                    ? `Queue ${j.queuePosition || "…"}`
                    : j.phase}
                </strong>
                {j.error && <p>{j.error}</p>}
              </div>
              {j.state === "queued" && (
                <button
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void jobAction(j.id, "cancel")}
                >
                  Remove from queue
                </button>
              )}
              {j.state === "failed" && (
                <button
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void jobAction(j.id, "recover")}
                >
                  Recover run
                </button>
              )}
            </div>
          ))}
          {!!project.scenes.length && (
            <div className={`directed-board${project.workflow === "short-film" ? " film-illustrated-board" : ""}`}>
              <aside>
                {project.cast?.length ? <div className="directed-cast">
                  <h3>Character sheets</h3>
                  <p>Front · left · right · full body</p>
                  {project.cast.map((character) => <figure key={character.id}>
                    <a href={character.sheetUrl} target="_blank" rel="noreferrer">
                      <img src={character.sheetUrl} alt={`${character.name}: front, left, right and full-body views`} />
                    </a>
                    <figcaption><strong>{character.name}</strong><span>{character.role}</span></figcaption>
                    <details><summary>Fixed appearance</summary><p>{character.appearance}</p></details>
                  </figure>)}
                </div> : <><img
                  src={project.scenes[0].referenceUrl}
                  alt="Shared visual reference"
                />
                <h3>Visual reference</h3></>}
                <p>{project.continuity}</p>
              </aside>
              <div className="directed-scenes">
                {project.scenes.map((s) => {
                  const hasVideo = s.takes.some(t=>t.state==='ready');
                  const job = project.jobs.find(
                    (j) => j.index === s.index && active(j.state),
                  );
                  const frameJob = project.jobs.filter(
                    (j) => j.sceneIndex === s.index && ['storyboard-rerender', 'storyboard-frame'].includes(j.operation || ''),
                  ).at(-1);
                  const lastJob=project.jobs.filter(j=>j.index===s.index).at(-1);
                  return (
                    <article
                      key={s.index}
                      className={job || (frameJob && active(frameJob.state)) ? "is-rendering" : ""}
                    >
                      <div className="directed-scene-heading">
                        <span>
                          {String(s.index + 1).padStart(2, "0")} ·{" "}
                          {stamp(s.start)}–{stamp(s.end)}
                        </span>
                        <span>
                          {sceneVoiceLabel(s)}
                        </span>
                      </div>
                      <h3>{s.name}</h3>
                      {s.storyboardUrl && <a href={s.storyboardUrl} target="_blank" rel="noreferrer">
                        <img className="film-board-image" src={s.storyboardUrl} alt={`Storyboard scene ${s.index+1}: ${s.name}`}/>
                      </a>}
                      {s.storyboardUrl && <StoryboardFrameActions job={frameJob}
                        busy={busy || project.jobs.some(j=>active(j.state))}
                        open={()=>setRerenderIndex(s.index)} recover={id=>void jobAction(id, 'recover')}/>}
                      <p>{s.action || s.continuity}</p>
                      {s.story && <>
                        <p className="film-scene-purpose"><strong>{s.story.beat.replaceAll("-"," ")}:</strong> {s.story.purpose}</p>
                        <details className="film-scene-plan"><summary>Why this scene happens</summary>
                          <div><p>{s.story.cause}</p><p>{s.story.characterReason}</p>
                            <p><strong>Starts:</strong> {s.story.startState}</p><p><strong>Ends:</strong> {s.story.endState}</p></div>
                        </details>
                        {!s.takes.length && <StoryboardEditor key={`${project.id}:${s.index}:${s.storyboardFrame?.sha256}`} scene={s}
                          busy={busy || project.jobs.some((j)=>active(j.state))} save={(edit)=>reviseStoryboard(s.index,edit)}/>}
                      </>}
                      {!!s.castIds?.length && <p className="directed-scene-cast">Cast: {s.castIds.map((id) => project.cast?.find((c) => c.id === id)?.name || id).join(" · ")}
                        {s.vocalistId && <> · Vocals: {project.cast?.find((c) => c.id === s.vocalistId)?.name || s.vocalistId}</>}
                      </p>}
                      {["vrgdg-h3-turbo", "short-film"].includes(project.workflow || "") && s.index < project.scenes.length - 1 &&
                        !project.scenes.some((scene) => scene.takes.length) &&
                        !project.jobs.some((j) => active(j.state)) &&
                        <SceneCutEditor end={s.end} index={s.index} busy={busy}
                          save={(endSeconds) => void act(async () => update(await request<Project>(
                            `/films/${project.id}/scenes/${s.index}/cut`,
                            { revision: project.revision, endSeconds }, "PATCH")))} />}
                      {hasVideo ? (
                        <SceneVideo key={`${project.id}:${s.index}`} scene={s} job={job} lastJob={lastJob}
                          busy={busy || timingNeedsUpdate || castNeedsPreparation || preparing}
                          rerender={()=>rerenderVideo(s.index)} accept={id=>void acceptVideo(s.index,id)}
                          recover={id=>void jobAction(id,'recover')} onPlay={()=>audioRef.current?.pause()}/>
                      ) : (
                        <button
                          className="secondary-button"
                          disabled={busy || !!job || timingNeedsUpdate || castNeedsPreparation || preparing}
                          onClick={() => void generate([s.index])}
                        >
                          {job
                            ? job.state === "queued"
                              ? `Queued · ${job.queuePosition || "…"}`
                              : "Rendering…"
                            : "Animate scene"}
                        </button>
                      )}
                    </article>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
