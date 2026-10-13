import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { linkTo } from "../lib/router";
import type { Checkpoint, InfluenceRun, Project, RunSong } from "../lib/types";
import { useRuns } from "../state/runs";
import { usePlayer } from "../state/player";
import { Button, TextArea } from "../ui/controls";
import { machine } from "../lib/machine";
import { Doer, useWho } from "../state/who";

const STAGES: { key: string; label: string; on: InfluenceRun["status"][] }[] = [
  { key: "research", label: "Research", on: ["researching"] },
  { key: "gather", label: "Gather", on: ["planned", "gathering"] },
  { key: "listen", label: "Listen", on: ["listening"] },
  { key: "train", label: "Train", on: ["training"] },
  { key: "choose", label: "Choose", on: ["choosing"] },
  { key: "keep", label: "Kept", on: ["kept"] },
];
const ORDER = ["researching", "planned", "gathering", "listening", "training", "choosing", "kept"];

function mins(s?: number | null) {
  if (!s) return "";
  const m = Math.round(s / 60);
  return m < 1 ? "under a minute" : m === 1 ? "about a minute" : `about ${m} minutes`;
}

function clock(s?: number) {
  if (!s) return "";
  return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

/** "What should your songs have more of?" — starts the research. Prefilled from a take's "Needs more influence". */
export function NewRun({ projectId, takeId, songTitle }: { projectId?: string; takeId?: string; songTitle?: string }) {
  const roles = useWho((w) => w.roles);
  const [finder, setFinder] = useState<string | null>(null);
  useEffect(() => {
    void api.get<{ name: string | null }>("/api/song-finder").then((r) => setFinder(r.name), () => setFinder(null));
  }, []);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const run = await api.post<InfluenceRun>("/api/influence-runs", { text, projectId, takeId });
      useRuns.getState().onRun(run);
      setText("");
      document.getElementById(`run-${run.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="ie-new">
      <label htmlFor="ie-ask">
        {songTitle ? <>What should <strong>{songTitle}</strong> have more of?</> : "What should your songs have more of?"}
      </label>
      <TextArea
        id="ie-ask"
        minRows={2}
        value={text}
        placeholder="A genre, a style or an artist's sound: “80s synthwave with gated drums”, “Delta blues slide guitar”, “more like Portishead”…"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && text.trim()) void start();
        }}
      />
      <div className="ie-new-row">
        <p>
          {Doer(roles, "research")} picks the artists and songs that define it. Songs in your music folder are used;{" "}
          {finder ? <>{finder} gets the rest, and you add the audio for any it can't find.</> : <>for the rest you add the audio yourself, from music you own.</>}{" "}
          You check the list before anything trains.
        </p>
        <Button kind="primary" busy={busy} disabled={!text.trim() || busy} onClick={() => void start()}>
          Research it
        </Button>
      </div>
      {error && <p className="ie-err">{error}</p>}
    </div>
  );
}

function Steps({ run }: { run: InfluenceRun }) {
  const at = ORDER.indexOf(run.status);
  const failedAt = run.status === "failed" || run.status === "stopped";
  return (
    <ol className="ie-steps" aria-label="Stages">
      {STAGES.map((s, i) => {
        const here = s.on.includes(run.status);
        const done = !failedAt && at >= 0 && ORDER.indexOf(s.on[s.on.length - 1]) < at;
        return (
          <li key={s.key} className={here ? "on" : done ? "done" : ""}>
            <span>{i + 1}</span>
            {s.label}
          </li>
        );
      })}
    </ol>
  );
}

/** Has its audio, or will: the run's song finder counts as having it */
const HAS_AUDIO = (s: RunSong) => s.source === "library" || s.source === "yours" || s.source === "finder" || s.state === "ready";

function SongRow({ s, finder, editable, onToggle, onAdd }: { s: RunSong; finder: string; editable: boolean; onToggle: () => void; onAdd: (f: File) => void }) {
  const pick = useRef<HTMLInputElement>(null);
  const state = !s.use && !editable ? s.note || "Left out" :
    s.state === "ready" ? "Ready" : s.state === "failed" ? s.note || "Couldn't use it" : s.state === "copying" ? "Getting it ready…" :
    s.state === "downloading" ? `Getting it with ${finder}…` :
    s.source === "library" ? "In your music" : s.source === "yours" ? "Added" : s.source === "finder" ? `${finder} will get it` : "Needs its audio";
  return (
    <li className={`ie-song${s.use ? "" : " off"} st-${s.state} src-${HAS_AUDIO(s) ? s.source : "needed"}`}>
      {editable ? (
        <input type="checkbox" checked={s.use} onChange={onToggle} aria-label={`Use ${s.title}`} />
      ) : (
        <span className="ie-dot" aria-hidden="true" />
      )}
      <span className="ie-song-name">
        <strong>{s.title}</strong>
        <span>{s.artist}{s.seconds ? ` · ${clock(s.seconds)}` : ""}{s.source === "yours" && s.file ? ` · ${s.file}` : ""}{s.instead ? ` · instead of ${s.instead}` : ""}</span>
      </span>
      {editable && !HAS_AUDIO(s) ? (
        <>
          <button type="button" className="ie-add" onClick={() => pick.current?.click()}>Add audio</button>
          <input ref={pick} type="file" accept="audio/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) onAdd(f); e.target.value = ""; }} />
        </>
      ) : (
        <span className="ie-song-state">{state}</span>
      )}
    </li>
  );
}

type Added = { run: InfluenceRun; added: string[]; unmatched: string[] };

/** Audio for a run's songs: one file for one song, or many matched to the list by their tags or names. XHR, so a
 *  folder of songs can show how far it's got. */
function sendAudio(rid: string, files: File[], song: string | undefined, onSent: (part: number) => void): Promise<Added> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  if (song) form.append("song", song);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/influence-runs/${rid}/audio`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onSent(e.loaded / e.total);
    xhr.onload = () => {
      let body: Partial<Added> & { detail?: string } = {};
      try {
        body = JSON.parse(xhr.responseText);
      } catch { /* not JSON: said below */ }
      if (xhr.status >= 200 && xhr.status < 300 && body.run) resolve(body as Added);
      else reject(new Error(body.detail ?? `The audio didn't reach ${machine()}. Try again.`));
    };
    xhr.onerror = () => reject(new Error(`The audio didn't reach ${machine()}. Try again.`));
    xhr.send(form);
  });
}

/** One shared preview player for the checkpoints, so comparing them is one click each. */
const preview = new Audio();
preview.preload = "none";

function Previews({ run, onKeep, keeping }: { run: InfluenceRun; onKeep: (step: number) => void; keeping: number | null }) {
  const [playing, setPlaying] = useState<string | null>(null);
  const [pos, setPos] = useState(0);
  const [songs, setSongs] = useState<Project[]>([]);
  const [target, setTarget] = useState(run.ask.projectId ?? "");
  const [trying, setTrying] = useState<number | null>(null);
  const [tried, setTried] = useState<Record<number, string>>({});
  const [tryError, setTryError] = useState<string | null>(null);
  useEffect(() => {
    if (run.status !== "choosing" && run.status !== "kept") return;
    void api.get<Project[]>("/api/projects").then((ps) => {
      const sung = ps.filter((p) => (p.sections?.length ?? 0) > 0);
      setSongs(sung);
      setTarget((t) => t || sung[0]?.id || "");
    });
  }, [run.status]);
  const tryOn = async (step: number) => {
    setTrying(step);
    setTryError(null);
    try {
      await api.post(`/api/influence-runs/${run.id}/try`, { step, projectId: target, strength: 0.7 });
      setTried((t) => ({ ...t, [step]: target }));
    } catch (e) {
      setTryError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    } finally {
      setTrying(null);
    }
  };
  useEffect(() => {
    const tick = () => setPos(preview.duration ? preview.currentTime / preview.duration : 0);
    const end = () => setPlaying(null);
    preview.addEventListener("timeupdate", tick);
    preview.addEventListener("ended", end);
    preview.addEventListener("pause", end);
    return () => {
      preview.removeEventListener("timeupdate", tick);
      preview.removeEventListener("ended", end);
      preview.removeEventListener("pause", end);
      preview.pause();
    };
  }, []);
  const toggle = (c: Checkpoint) => {
    if (playing === c.preview) {
      preview.pause();
      return;
    }
    usePlayer.getState().stop();
    const t = preview.src.endsWith(c.preview) ? preview.currentTime : 0;
    preview.src = c.preview;
    preview.currentTime = t;
    void preview.play().then(() => setPlaying(c.preview)).catch(() => setPlaying(null));
  };
  const rows = [...(run.train?.baseline ? [run.train.baseline] : []), ...(run.train?.checkpoints || [])];
  if (!rows.length) return null;
  const choosing = run.status === "choosing" || run.status === "kept";
  return (
    <div className="ie-previews">
      <p className="ie-hint">
        Each preview sings the same test song with the same seed, so only the training differs. Early steps barely move;
        late ones can start copying the training songs. Pick the one that sounds most like what you want.
      </p>
      {choosing && songs.length > 0 && (
        <div className="ie-try">
          <label htmlFor={`try-${run.id}`}>Try a checkpoint on</label>
          <select id={`try-${run.id}`} className="in" value={target} onChange={(e) => setTarget(e.target.value)}>
            {songs.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
          </select>
          <span>one YuE2 take with your words and sound, the checkpoint at 70%.</span>
        </div>
      )}
      {tryError && <p className="ie-err">{tryError}</p>}
      <ul>
        {rows.map((c) => (
          <li key={c.step} className={run.kept?.step === c.step ? "kept" : ""}>
            <button type="button" className={`ie-play${playing === c.preview ? " on" : ""}`} onClick={() => toggle(c)}
              aria-label={`${playing === c.preview ? "Pause" : "Play"} ${c.step ? `step ${c.step}` : "the untrained model"}`}>
              {playing === c.preview ? "❚❚" : "▶"}
            </button>
            <span className="ie-step-name">
              <strong>{c.step ? `Step ${c.step}` : "Before training"}</strong>
              <span>{c.step ? `${clock(c.seconds)}` : "for comparison"}</span>
            </span>
            <span className="ie-bar" aria-hidden="true">
              <i style={{ width: `${playing === c.preview ? pos * 100 : 0}%` }} />
            </span>
            {choosing && c.step > 0 && (
              tried[c.step] ? (
                <a className="ie-link ie-tried" {...linkTo(`/music/${tried[c.step]}`)}>Take started →</a>
              ) : (
                <Button size="sm" kind="ghost" busy={trying === c.step} disabled={!target || trying !== null}
                  onClick={() => void tryOn(c.step)}>Try</Button>
              )
            )}
            {choosing && c.step > 0 && (
              run.kept?.step === c.step ? (
                <span className="ie-kept">Kept</span>
              ) : (
                <Button size="sm" kind={run.kept ? "ghost" : "plain"} busy={keeping === c.step} disabled={keeping !== null}
                  onClick={() => onKeep(c.step)}>
                  {run.kept ? "Keep this instead" : "Keep this one"}
                </Button>
              )
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RunCard({ run }: { run: InfluenceRun }) {
  const job = useRuns((s) => (run.jobId ? s.jobs[run.jobId] : undefined));
  const [drop, setDrop] = useState<Set<string>>(new Set(run.songs.filter((s) => !s.use).map((s) => s.id)));
  const [busy, setBusy] = useState<string | null>(null);
  const [keeping, setKeeping] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(run.status !== "kept");
  const ref = useRef<HTMLElement>(null);
  const editable = run.status === "planned";
  const running = job && (job.status === "queued" || job.status === "running");
  const usable = run.songs.filter((s) => !drop.has(s.id) && (editable || s.state !== "failed"));
  const withAudio = usable.filter(HAS_AUDIO);
  const needAudio = usable.length - withAudio.length;
  const finder = run.finder || "The song finder";
  const fromFinder = usable.filter((s) => s.source === "finder" && s.state !== "ready").length;
  const [sent, setSent] = useState<number | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const many = useRef<HTMLInputElement>(null);
  const addAudio = async (files: File[], song?: string) => {
    if (!files.length) return;
    setError(null);
    setAdded(null);
    setSent(0);
    try {
      const r = await sendAudio(run.id, files, song, setSent);
      useRuns.getState().onRun(r.run);
      if (song) setDrop((d) => { const n = new Set(d); n.delete(song); return n; });
      else {
        setDrop((d) => { const n = new Set(d); r.added.forEach((id) => n.delete(id)); return n; });
        setAdded(`Matched ${r.added.length} of ${files.length}.` + (r.unmatched.length ? ` Not on the list: ${r.unmatched.slice(0, 4).join(", ")}${r.unmatched.length > 4 ? "…" : ""}` : ""));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSent(null);
    }
  };
  const minutes = useMemo(() => Math.round(usable.reduce((a, s) => a + (s.seconds || 210), 0) / 60), [usable]);

  const act = async (what: string, call: () => Promise<InfluenceRun | unknown>) => {
    setBusy(what);
    setError(null);
    try {
      const r = await call();
      if (r && typeof r === "object" && "id" in r && "status" in r) useRuns.getState().onRun(r as InfluenceRun);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    } finally {
      setBusy(null);
    }
  };
  const keep = async (step: number) => {
    setKeeping(step);
    await act("keep", () => api.post(`/api/influence-runs/${run.id}/keep`, { step }));
    setKeeping(null);
  };
  const progress = job?.progress ?? (run.status === "training" && run.train ? run.train.step / run.train.steps : undefined);
  // keeping or trying a checkpoint went wrong: the run is still in Choose, with the reason
  const problem = !running && (run.status === "choosing" || run.status === "kept") && !!run.message?.startsWith("Couldn't");

  return (
    <article className={`ie-run st-${run.status}`} id={`run-${run.id}`} ref={ref}>
      <header className="ie-run-head">
        <button type="button" className="ie-run-title" onClick={() => setOpen(!open)} aria-expanded={open}>
          <span className="ie-kind">{run.kind || "New"}</span>
          <strong>{run.name || "Researching…"}</strong>
          <span className="ie-ask">“{run.ask.text}”</span>
        </button>
        <Steps run={run} />
      </header>
      {open && (
        <div className="ie-run-body">
          {(running || run.status === "failed" || run.status === "stopped" || run.status === "kept" || problem) && (
            <div className={`ie-status${run.status === "failed" || problem ? " bad" : ""}`} role="status">
              {running && <span className="ln-spin" aria-hidden="true" />}
              <span>{job?.message && running ? job.message : run.message}</span>
              {run.status === "training" && run.train?.eta ? <span className="ie-sub">{mins(run.train.eta)} of training left</span> : null}
              {running && run.status !== "researching" && (
                <Button size="sm" kind="ghost" busy={busy === "stop"} onClick={() => void act("stop", () => api.post(`/api/influence-runs/${run.id}/stop`))}>
                  Stop
                </Button>
              )}
              {(run.status === "failed" || run.status === "stopped") && run.songs.length > 0 && (
                <Button size="sm" busy={busy === "start"} onClick={() => void act("start", () => api.post(`/api/influence-runs/${run.id}/start`, { drop: [...drop] }))}>
                  Carry on
                </Button>
              )}
              {run.status === "kept" && (
                <a className="ie-link" {...linkTo(run.ask.projectId ? `/music/${run.ask.projectId}` : "/music")}>
                  {run.ask.projectId ? "Back to the song →" : "Use it in a song →"}
                </a>
              )}
              {running && progress !== undefined && (
                <span className="ie-progress" aria-hidden="true"><i style={{ width: `${Math.round(progress * 100)}%` }} /></span>
              )}
            </div>
          )}

          {run.howMany && (
            <section className="ie-plan">
              <p className="ie-about">{run.about}</p>
              <p className="ie-why"><strong>Why this many:</strong> {run.howMany}</p>
              <details className="ie-artists">
                <summary>{run.artists.length} artists, and why each one</summary>
                <ul>
                  {run.artists.map((a) => (
                    <li key={a.name}><strong>{a.name}</strong> {a.inLibrary && <span className="ie-lib">in your music</span>} — {a.why}</li>
                  ))}
                </ul>
              </details>
            </section>
          )}

          {run.songs.length > 0 && run.status !== "choosing" && run.status !== "kept" && (
            <section className="ie-songs">
              <h3>
                {usable.length} songs · about {minutes} minutes
                {editable && needAudio > 0 && <span> · {needAudio} need their audio</span>}
              </h3>
              {editable && run.musicNote && <p className="ie-note">Your music couldn't be read ({run.musicNote}), so every song needs its audio added.</p>}
              {editable && run.finderNote && <p className="ie-note">{finder} couldn't be asked ({run.finderNote}), so the songs that aren't in your music need their audio added.</p>}
              {editable && (
                <div className={`ie-drop${over ? " over" : ""}`}
                  onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
                  onDrop={(e) => { e.preventDefault(); setOver(false); void addAudio([...e.dataTransfer.files]); }}>
                  <span>
                    {sent !== null ? `Sending… ${Math.round(sent * 100)}%` :
                      <>Drop audio files here, or <button type="button" onClick={() => many.current?.click()}>choose them</button>: each one is matched to the list by its tags or its name.</>}
                  </span>
                  {added && <span className="ie-sub">{added}</span>}
                  <input ref={many} type="file" accept="audio/*" multiple hidden onChange={(e) => { void addAudio([...(e.target.files ?? [])]); e.target.value = ""; }} />
                </div>
              )}
              <ul>
                {run.songs.map((s) => (
                  <SongRow key={s.id} s={{ ...s, use: !drop.has(s.id) }} finder={finder} editable={editable}
                    onToggle={() => setDrop((d) => { const n = new Set(d); if (n.has(s.id)) n.delete(s.id); else n.add(s.id); return n; })}
                    onAdd={(f) => void addAudio([f], s.id)} />
                ))}
              </ul>
            </section>
          )}

          {editable && (
            <div className="ie-go">
              <p>
                {fromFinder > 0 ? <>{finder} gets {fromFinder === 1 ? "one song" : `${fromFinder} songs`} first. </> : null}
                {needAudio > 0 ? <>Songs still without their audio are left out (your music is looked through once more first). </> : null}
                {withAudio.length < 8 ? <>Add the audio for at least {8 - withAudio.length} more to start. </> : null}
                Training takes about 30–40 minutes on {machine()} and holds the GPU, so new songs wait until it's done.
              </p>
              <Button kind="primary" busy={busy === "start"} disabled={withAudio.length < 8 || !!busy || sent !== null}
                onClick={() => void act("start", () => api.post(`/api/influence-runs/${run.id}/start`, { drop: [...drop] }))}>
                Gather {withAudio.length} songs and train
              </Button>
            </div>
          )}

          {(run.status === "training" || (run.train?.checkpoints?.length ?? 0) > 0) && (
            <Previews run={run} onKeep={(s) => void keep(s)} keeping={keeping} />
          )}

          {error && <p className="ie-err">{error}</p>}
          {!running && run.status !== "training" && (
            <div className="ie-foot">
              {["choosing", "kept", "failed", "stopped"].includes(run.status) && run.trigger && run.songs.length > 0 && (
                <Button size="sm" kind="ghost" busy={busy === "again"}
                  title="A new run with these songs: change the list, then train it again"
                  onClick={() => void act("again", async () => {
                    const fresh = await api.post<InfluenceRun>(`/api/influence-runs/${run.id}/again`, {});
                    useRuns.getState().onRun(fresh);
                    setTimeout(() => document.getElementById(`run-${fresh.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
                    return null;
                  })}>
                  Train again with changes
                </Button>
              )}
              <Button size="sm" kind="ghost" busy={busy === "del"}
                onClick={() => { if (confirm("Delete this run? A kept influence stays in your library.")) void act("del", () => api.del(`/api/influence-runs/${run.id}`).then(() => useRuns.getState().onRun({ ...run, deleted: true }))); }}>
                Delete run
              </Button>
            </div>
          )}
        </div>
      )}
    </article>
  );
}
