import { useEffect, useMemo, useRef, useState } from "react";
import { Said } from "../ui/Said";
import { api, ApiError, fileUrl } from "../lib/api";
import type { Feel, Job, Living, LivingAuto, LivingLoop, LivingRender, Project, Transition } from "../lib/types";
import { useSong } from "../state/song";
import { usePlayer } from "../state/player";
import { Button, Disclosure, Segmented, TextArea } from "../ui/controls";
import { machine } from "../lib/machine";
import { choiceLabel, okToSpend, type PictureChoice } from "../lib/pictures";
import { Doer, doer, useWho } from "../state/who";

const LETTER = { a: "A", b: "B", c: "C", d: "D" } as Record<string, string>;
const SHAPE_NAME = { square: "Square", story: "9:16", wide: "16:9" } as const;
const VERDICT: Record<string, string> = { calm: "Calm", lively: "Lively", "too much": "Moves a lot", cuts: "Cuts" };
const FEEL: Record<Feel, { label: string; line: string }> = {
  still: { label: "Barely", line: "Only the slightest motion: at a glance it looks still, and on a second look it breathes." },
  subtle: { label: "A little", line: "Small, slow motion: the picture quietly alive." },
  gentle: { label: "Gentle", line: "A little more life, still slow and never sudden." },
};
const TRANSITION: Record<Transition, { label: string; line: string }> = {
  seamless: { label: "Seamless", line: "As a loop comes round, the next one blends in over a second: too gentle to notice." },
  dissolve: { label: "Dissolve", line: "A soft cross-fade of a second and a half." },
  slow: { label: "Slow dissolve", line: "A long four-second blend: one motion melts into the next." },
  dark: { label: "Dip to dark", line: "A soft dip halfway into shadow and back, between loops." },
};
const DEFAULT: Living = {
  settings: { count: 2, seconds: 6, feel: "subtle", keepPeople: false, transition: "seamless", shape: "square" },
  loops: [], renders: [],
};
const RUNNING: LivingAuto["status"][] = ["deciding", "painting", "writing", "animating", "finishing"];
const MOVES: Record<Feel, string> = { still: "Barely moving", subtle: "Moves a little", gentle: "Gentle movement" };

type Act = (what: string, fn: () => Promise<unknown>) => Promise<void>;
type Save = (b: { settings?: Partial<Living["settings"]>; motions?: Record<string, string>; mode?: "auto" | "direct"; keep?: boolean }) => Promise<void>;
// words that ask for a person to move (and a held person can't)
const ABOUT_PEOPLE = /\b(she|her|he|his|him|woman|man|girl|boy|person|people|figure|dancer|singer|face|body|arms?|hands?|hair)\b/i;

/** Living Album Cover: the song's cover, gently alive for as long as the song plays. Two ways to make it: Claude
 *  makes the whole thing (and you keep it, ask for another idea, or take over), or you direct three steps yourself:
 *  the picture, how it moves, and the video (which makes itself when the loops are ready). */
export function LivingAlbum({ project }: { project: Project }) {
  const roles = useWho((w) => w.roles);
  const jobs = useSong((s) => s.jobs);
  const lv: Living = { ...DEFAULT, ...(project.living ?? {}), settings: { ...DEFAULT.settings, ...(project.living?.settings ?? {}) } };
  const coverN = project.cover?.n;
  const chosen = lv.picture !== undefined && lv.picture === coverN;
  const loops = lv.loops.slice(0, lv.settings.count);
  const made = loops.filter((l) => l.video && l.cover === coverN).length;
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [changing, setChanging] = useState(false);
  const [shown, setShown] = useState<string | null>(null);
  // switching from "I'll direct it" back to Claude starts a fresh idea rather than showing the last one as current
  const [fresh, setFresh] = useState(false);
  const mode = lv.mode ?? (lv.loops.some((l) => l.video) || lv.picture !== undefined ? "direct" : "choose");
  const auto = lv.auto ?? null;
  const autoRunning = !!auto && RUNNING.includes(auto.status);

  const act: Act = async (what, fn) => {
    setBusy(what);
    setError(null);
    try {
      const r = await fn();
      if (r && typeof r === "object" && "kind" in (r as Job)) useSong.getState().onJob(r as Job);
      if (r && typeof r === "object" && "rev" in (r as Project)) useSong.getState().onProject(r as Project);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    } finally {
      setBusy(null);
    }
  };
  const save: Save = (body) => act("save", () => api.put(`/api/projects/${project.id}/living`, body));
  const startAuto = (note: string, again: boolean, resume?: string) => act("auto", async () => {
    const r = await api.post(`/api/projects/${project.id}/living/auto`, { note, again, resume });
    setFresh(false);
    return r;
  });
  const toMode = (m: "auto" | "direct") => {
    if (m === "auto" && !autoRunning) setFresh(true);
    void save({ mode: m });
  };

  const pictureJob = Object.values(jobs).find((j) => j.kind.startsWith("cover.") && j.projectId === project.id &&
    (j.status === "queued" || j.status === "running"));
  useEffect(() => {
    if (chosen) setChanging(false);
  }, [chosen, coverN]);

  // while Claude makes it, only loops of the new idea are shown (not the ones it's replacing)
  const current_ = (l: LivingLoop) => !!l.video && (mode !== "auto" || (l.madeWith === l.motion && l.status === "ready"));
  const showing = loops.find((l) => l.id === shown && current_(l)) ?? (chosen ? loops.find((l) => current_(l) && l.cover === coverN) : undefined);
  const step = !chosen || changing ? 1 : made === 0 ? 2 : 3;
  // Claude's finish in code, when there is one, is the video; the plain one stays beside it
  const current = lv.renders.find((r) => r.shape === lv.settings.shape && r.finish && r.finish === auto?.finished?.id) ??
    lv.renders.find((r) => r.shape === lv.settings.shape && !r.finish);
  // Claude's finished video plays in the monitor, with the song
  const finished = mode === "auto" && !fresh && auto?.status === "done" && current ? current : undefined;

  return (
    <div className="la">
      <section className="la-monitor" aria-label="Preview">
        <div className={`la-frame${finished ? ` sh-${finished.shape}` : ""}`}>
          {finished ? (
            <video key={finished.file} className="la-final" src={fileUrl(project.id, finished.file)} controls playsInline
              preload="metadata" onPlay={() => usePlayer.getState().stop()} />
          ) : showing ? (
            <LoopVideo key={showing.video} src={fileUrl(project.id, showing.video!)} />
          ) : project.cover ? (
            <img src={`/api/projects/${project.id}/living/picture.jpg?n=${coverN}`} alt="" />
          ) : <div className="la-empty">No picture yet</div>}
          {project.cover && !finished && (
            <img className="la-layer" src={`/api/projects/${project.id}/living/layer.png?k=${encodeURIComponent(`${coverN}-${project.title}-${project.cover.artist ?? ""}`)}`} alt="" />
          )}
          {pictureJob && <div className="la-working"><span className="ln-spin" aria-hidden="true" />{pictureJob.message ?? "Making the picture"}</div>}
        </div>
        <p className="la-caption">
          {finished ? <>Your living cover, with the song. {SHAPE_NAME[finished.shape]}, {Math.floor(finished.seconds / 60)}:{String(Math.round(finished.seconds % 60)).padStart(2, "0")}.</> : showing ? <>Loop {LETTER[showing.id]} on repeat, under the title and logos the video will have.</> :
            chosen ? "The picture to animate. Loops play here as they're made." : project.cover ? "Your song's cover." : "The picture appears here."}
        </p>
        {!finished && loops.filter((l) => l.video).length > 1 && (
          <div className="la-pick" role="group" aria-label="Show a loop">
            {loops.map((l) => (
              <button key={l.id} type="button" disabled={!l.video} className={showing?.id === l.id ? "on" : ""}
                onClick={() => setShown(l.id)}>{LETTER[l.id]}</button>
            ))}
          </div>
        )}
      </section>

      <section className="la-side">
        {mode !== "choose" && (
          <Segmented size="sm" label="Who makes it" value={mode} onChange={toMode} options={[
            { value: "auto", label: `${Doer(roles, "direct")} makes it`, hint: `${Doer(roles, "direct")} decides everything; you keep it or change it` },
            { value: "direct", label: "I'll direct it", hint: "Choose the picture, the motion and the video yourself" },
          ]} />
        )}
        {mode === "direct" ? (
          <>
            <ol className="la-flow" aria-label="Steps">
              {["The picture", "The motion", "The video"].map((name, i) => (
                <li key={name} className={step === i + 1 ? "on" : step > i + 1 ? "done" : ""}><span>{step > i + 1 ? "✓" : i + 1}</span>{name}</li>
              ))}
            </ol>

            <PictureStep project={project} chosen={chosen && !changing} job={pictureJob} busy={busy} act={act}
              onChange={() => setChanging(true)} onCancel={chosen ? () => setChanging(false) : undefined} />

            <MotionStep project={project} lv={lv} loops={loops} locked={!chosen || changing} jobs={jobs} busy={busy} act={act}
              save={save} onShow={setShown} />

            <VideoStep project={project} lv={lv} loops={loops} locked={!chosen || changing || made === 0} jobs={jobs} busy={busy}
              act={act} save={save} />
          </>
        ) : (
          <AutoPanel project={project} lv={lv} loops={loops} jobs={jobs} busy={busy} fresh={fresh || !auto}
            onStart={startAuto} onDirect={() => toMode("direct")} onKeep={() => void save({ keep: true })} current={current} />
        )}
        {error && <p className="ie-err">{error}</p>}
      </section>
    </div>
  );
}

/** The first sentence or two of Claude's own notes, for a quick read. */
const firstSentences = (text: string, n: number) => (text.match(/[^.!?]+[.!?]+/g) ?? [text]).slice(0, n).join(" ").trim();

/** Where a stopped run can carry on from (older stops didn't record it: one with a brief stopped at the picture). */
const stoppedAt = (a: LivingAuto) => a.failedAt ?? (a.coverJob && a.brief ? "paint" : "decide");

/* ---- Claude makes it ------------------------------------------------------------------------------------------- */

function AutoPanel({ project, lv, loops, jobs, busy, fresh, current, onStart, onDirect, onKeep }: {
  project: Project; lv: Living; loops: LivingLoop[]; jobs: Record<string, Job>; busy: string | null; fresh: boolean;
  current?: LivingRender; onStart: (note: string, again: boolean, resume?: string) => Promise<void>;
  onDirect: () => void; onKeep: () => void;
}) {
  const roles = useWho((w) => w.roles);
  const auto = lv.auto;
  const [note, setNote] = useState("");
  const running = !!auto && RUNNING.includes(auto.status);

  if (!auto || (fresh && !running) || auto.status === "failed" || auto.status === "stopped") {
    return (
      <div className="la-step la-now la-auto">
        <h3>Let {doer(roles, "direct")} make it</h3>
        <p className="la-lead">{Doer(roles, "direct")} reads the song and makes the whole thing: it paints a new cover designed to move, picks
          what moves and how much, and puts the video together.</p>
        {(auto?.status === "failed" || auto?.status === "stopped") && (
          <div className="la-stopped">
            <p className="ie-err">The last try stopped{auto.error ? `: ${auto.error.replace(/\.+$/, "")}` : ""}.</p>
            {auto.idea && (stoppedAt(auto) === "paint" || stoppedAt(auto) === "motion") && (
              <>
                <p className="la-note">The idea is kept: {auto.idea}</p>
                <div className="la-choice">
                  {stoppedAt(auto) === "paint" ? (
                    <>
                      <Button kind="primary" busy={busy === "auto"} disabled={!!busy} onClick={() => void onStart("", false, "same")}>
                        Try the picture again
                      </Button>
                      <Button disabled={!!busy} onClick={() => void onStart("", false, "local")} title={`Krea 2 on ${machine()}, free`}>
                        Paint it on {machine()} instead
                      </Button>
                    </>
                  ) : (
                    <Button kind="primary" busy={busy === "auto"} disabled={!!busy} onClick={() => void onStart("", false, "same")}>
                      Carry on from there
                    </Button>
                  )}
                </div>
                <div className="la-or"><span>or start over</span></div>
              </>
            )}
          </div>
        )}
        {fresh && auto?.idea && !running && <p className="la-note">Last time: {auto.idea}</p>}
        <input className="in" value={note} placeholder="Anything to steer it? Optional: “a rainy window at night”, “neon city”, “barely moving”…"
          onChange={(e) => setNote(e.target.value)} />
        <div className="la-go">
          <Button kind="primary" busy={busy === "auto"} disabled={!!busy} onClick={() => void onStart(note, !!auto?.idea && fresh)}>
            Make my living cover
          </Button>
          <span>About 5 minutes. The new picture is made the way Settings says for album covers; the animation is on {machine()}.</span>
        </div>
        <p className="la-note">You'll see the idea, then the video. Keep it, ask for another idea, or change any part yourself.
          The new picture becomes the song's cover too; the earlier ones stay to go back to.</p>
        {lv.mode === undefined && (
          <Button size="sm" kind="ghost" onClick={onDirect}>Or direct it yourself, step by step →</Button>
        )}
      </div>
    );
  }

  const count = auto.choices?.count ?? loops.length;
  const coverN = project.cover?.n;
  const madeNow = loops.filter((l) => l.video && l.cover === coverN && l.madeWith === l.motion && l.status === "ready").length;
  const rendering = Object.values(jobs).find((j) => j.kind === "living.render" && j.projectId === project.id &&
    (j.status === "queued" || j.status === "running"));
  const coverJob = auto.coverJob ? jobs[auto.coverJob] : undefined;
  const making = loops.filter((l) => l.status === "queued" || l.status === "making");
  const failedLoop = loops.find((l) => l.error && l.status !== "queued" && l.status !== "making");
  const now = auto.status === "deciding" ? "decide" : auto.status === "painting" ? "paint" : auto.status === "writing" ? "motion" :
    auto.status === "animating" ? (madeNow < count ? "animate" : "video") : auto.status === "finishing" ? "finish" : "done";
  const order = ["decide", ...(auto.picture === "keep" ? [] : ["paint"]), "motion", "animate", "video", "finish", "done"];
  const finishJob = auto.finishJob ? jobs[auto.finishJob] : undefined;
  const at = order.indexOf(now);
  const loopJob = making.map((l) => (l.jobId ? jobs[l.jobId] : undefined)).find((j) => j?.status === "running");
  const steps = [
    { key: "decide", label: `${Doer(roles, "direct")} listens and decides`, detail: auto.status === "deciding" ? "Looking at the cover, reading the song" : null },
    ...(auto.picture === "keep" ? [] : [{ key: "paint", label: "Painting a new cover, made to move", detail: coverJob?.message ?? null }]),
    { key: "motion", label: "Choosing what moves", detail: null },
    { key: "animate", label: `Animating ${count === 1 ? "the loop" : `${count} loops`}`,
      detail: now === "animate" ? `${madeNow} of ${count} made${loopJob?.message ? ` · ${loopJob.message}` : ""}` : null,
      progress: now === "animate" ? (madeNow + (loopJob?.progress ?? 0)) / count : undefined },
    { key: "video", label: "Putting the video together", detail: rendering?.message ?? null,
      progress: now === "video" ? rendering?.progress ?? 0 : undefined },
    ...(auto.finish || auto.status === "deciding" ? [{ key: "finish", label: "The finish, written in code",
      detail: now === "finish" ? finishJob?.message ?? "Waiting its turn" : null }] : []),
  ];
  const c = auto.choices;

  return (
    <div className="la-step la-now la-auto">
      <h3>{running ? `${Doer(roles, "direct")} is making it` : "The living cover"}</h3>
      {auto.idea ? (
        <div className="la-idea">
          <p>{auto.idea}</p>
          {auto.why && <p className="la-note">{auto.why}</p>}
          {auto.finish && !auto.finished && (
            <p className="la-note"><strong>The finish:</strong> {firstSentences(auto.finish, 2)}</p>
          )}
          {auto.finished?.about && <p className="la-note"><strong>About the finish:</strong> <Said text={auto.finished.about} /></p>}
          {loops.filter((l) => l.usable === false).map((l) => (
            <p key={l.id} className="la-note la-left">Loop {LETTER[l.id]} isn't in the video: H3 cut away to a different shot in every try.</p>
          ))}
          {Object.entries(auto.finished?.leftOut ?? {}).filter(([id]) => !loops.find((l) => l.id === id && l.usable === false)).map(([id, why]) => (
            <p key={id} className="la-note la-left">The finish left out loop {LETTER[id] ?? id}: {why}</p>
          ))}
          {c && (
            <div className="la-chips">
              <span>{c.count === 1 ? "1 loop" : `${c.count} loops`}</span>
              <span>{MOVES[c.feel]}</span>
              <span>{c.seconds} s each</span>
              {c.count > 1 && <span>{TRANSITION[c.transition].label}</span>}
            </div>
          )}
        </div>
      ) : auto.note ? <p className="la-note">You asked: {auto.note}</p> : null}

      {running && (
        <ol className="la-progress">
          {steps.map((st) => {
            const i = order.indexOf(st.key);
            const state = i < at ? "done" : i === at ? "on" : "";
            return (
              <li key={st.key} className={state}>
                <span className="la-dot">{state === "done" ? "✓" : state === "on" ? <span className="ln-spin" aria-hidden="true" /> : ""}</span>
                <div>
                  <strong>{st.label}</strong>
                  {state === "on" && st.detail && <span>{st.detail}</span>}
                  {state === "on" && st.progress !== undefined && (
                    <div className="la-bar"><i style={{ width: `${Math.round(Math.min(1, st.progress) * 100)}%` }} /></div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {running && failedLoop && !making.length && (
        <p className="ie-err">A loop didn't work: {failedLoop.error}. Try another idea, or direct it yourself.</p>
      )}

      {auto.status === "done" && auto.finishError && (
        <p className="la-note">The finish in code didn't work ({auto.finishError.replace(/\.+$/, "")}), so this is the
          animated cover without it.</p>
      )}
      {auto.status === "done" && current && (
        <>
          <div className="la-render-meta">
            <strong>{SHAPE_NAME[current.shape]}</strong>
            <span>{Math.floor(current.seconds / 60)}:{String(Math.round(current.seconds % 60)).padStart(2, "0")} · {(current.bytes / 1e6).toFixed(0)} MB</span>
            <a href={fileUrl(project.id, current.file)} download={`${project.title} (${SHAPE_NAME[current.shape]}).mp4`}>Download</a>
          </div>
          {auto.kept ? (
            <p className="la-kept">✓ Kept: this is the song's living cover.</p>
          ) : (
            <div className="la-choice">
              <Button kind="primary" disabled={!!busy} onClick={onKeep}>Keep it</Button>
              <Button disabled={!!busy} busy={busy === "auto"} onClick={() => void onStart(note, true)}>Another idea</Button>
              <Button kind="ghost" disabled={!!busy} onClick={onDirect}>Change it myself</Button>
            </div>
          )}
          <input className="in" value={note} placeholder="Steer the next idea, if you like: “warmer colors”, “a city at night”, “slower”"
            onChange={(e) => setNote(e.target.value)} />
          {auto.kept && (
            <div className="la-choice">
              <Button size="sm" disabled={!!busy} busy={busy === "auto"} onClick={() => void onStart(note, true)}>Another idea</Button>
              <Button size="sm" kind="ghost" disabled={!!busy} onClick={onDirect}>Change it myself</Button>
            </div>
          )}
          <p className="la-note">Another idea paints a new cover and replaces this video. Change it myself opens the three steps
            with everything that was chosen filled in.</p>
        </>
      )}
    </div>
  );
}

/* ---- 1 · the picture ---------------------------------------------------------------------------------------------- */

function PictureStep({ project, chosen, job, busy, act, onChange, onCancel }: {
  project: Project; chosen: boolean; job?: Job; busy: string | null; act: Act; onChange: () => void; onCancel?: () => void;
}) {
  const roles = useWho((w) => w.roles);
  const [how, setHow] = useState<"moving" | "describe" | "upload">("moving");
  const [steer, setSteer] = useState("");
  const [words, setWords] = useState("");
  const [exact, setExact] = useState(false);
  const [engine, setEngine] = useState("local");
  const [choices, setChoices] = useState<PictureChoice[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const cover = project.cover;
  const earlier = (project.covers ?? []).filter((c) => c.n !== cover?.n).slice(-6).reverse();
  const madeBy = !cover ? "" : cover.made.engine === "upload" ? "your picture" : cover.made.model;

  useEffect(() => {
    void api.get<{ engine: string; choices: PictureChoice[] }>("/api/covers/settings")
      .then((s) => { setEngine(s.engine); setChoices(s.choices); }).catch(() => undefined);
  }, []);

  if (chosen && cover) {
    return (
      <div className="la-step la-done">
        <div className="la-step-head">
          <h3><span className="mk-n">1</span>The picture</h3>
          <Button size="sm" kind="ghost" onClick={onChange}>Change</Button>
        </div>
        <p className="la-note">Animating {cover.n === 1 ? "the song's cover" : `picture ${cover.n}`}, made with {madeBy}
          {cover.made.moving ? ", designed to move" : ""}.</p>
      </div>
    );
  }
  const make = () => okToSpend(choices.find((c) => c.id === engine)) && act("picture", () => api.post(`/api/projects/${project.id}/cover`, how === "moving"
    ? { engine, note: steer, moving: true, forLiving: true }
    : exact ? { engine, prompt: words, forLiving: true } : { engine, note: words, moving: true, forLiving: true }));
  const upload = (file: File) => act("picture", async () => {
    const form = new FormData();
    form.append("file", file);
    form.append("forLiving", "true");
    const r = await fetch(`/api/projects/${project.id}/cover/upload`, { method: "POST", body: form });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new ApiError(body.detail ?? "The picture didn't upload.", r.status);
    return body;
  });

  return (
    <div className="la-step la-now">
      <div className="la-step-head">
        <h3><span className="mk-n">1</span>The picture</h3>
        {onCancel && <Button size="sm" kind="ghost" onClick={onCancel}>Keep the current one</Button>}
      </div>
      {cover ? (
        <>
          <p className="la-lead">This is the cover made with your song. Animate it as it is, or start from a new picture.</p>
          <Button kind="primary" busy={busy === "use"} disabled={!!busy || !!job}
            onClick={() => void act("use", () => api.post(`/api/projects/${project.id}/living/picture`))}>
            Use this cover
          </Button>
          <div className="la-or"><span>or start from a new picture</span></div>
        </>
      ) : (
        <p className="la-lead">This song has no cover yet. Make a picture to animate: it becomes the song's cover too.</p>
      )}
      <Segmented size="sm" label="A new picture" value={how} onChange={setHow} options={[
        { value: "moving", label: "Made to move", hint: `${Doer(roles, "chores")} designs one that animates well` },
        { value: "describe", label: "Describe it", hint: "Your idea, as much or as little as you like" },
        { value: "upload", label: "Upload", hint: "A picture of your own" },
      ]} />
      {how === "moving" && (
        <div className="la-form">
          <p className="la-note">{Doer(roles, "chores")} designs a new picture for the song where light, mist, water or fabric can drift gently, and
            nobody is caught mid-action (those animate badly).</p>
          <input className="in" value={steer} placeholder="Steer it, if you like: “a rainy window at night”, “keep the chapel”…"
            onChange={(e) => setSteer(e.target.value)} />
        </div>
      )}
      {how === "describe" && (
        <div className="la-form">
          <TextArea minRows={3} value={words} placeholder="What should the picture be? A few words or a full description."
            onChange={(e) => setWords(e.target.value)} />
          <label className="la-check">
            <input type="checkbox" checked={exact} onChange={(e) => setExact(e.target.checked)} />
            <span><strong>Use my words exactly.</strong> Otherwise {doer(roles, "chores")} turns them into a full picture description, made to move.</span>
          </label>
        </div>
      )}
      {how === "upload" ? (
        <div className="la-form">
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
          <Button busy={busy === "picture"} disabled={!!busy || !!job} onClick={() => fileRef.current?.click()}>Choose a picture…</Button>
          <span className="la-note">PNG, JPEG or WebP. The middle square is used, brought up to 3000 px.</span>
        </div>
      ) : (
        <div className="la-form la-make">
          <Segmented size="sm" label="Made with" value={engine} onChange={setEngine}
            options={choices.map((c) => ({ value: c.id, label: choiceLabel(c), hint: c.note }))} />
          <Button busy={busy === "picture" || !!job} disabled={!!busy || !!job || (how === "describe" && !words.trim())} onClick={() => void make()}>
            Make it
          </Button>
        </div>
      )}
      <p className="la-note">A new picture becomes the song's cover too (the earlier ones stay here to go back to).</p>

      {earlier.length > 0 && (
        <div className="la-earlier">
          <span>Earlier pictures</span>
          <div>
            {earlier.map((c) => (
              <button key={c.n} type="button" title={c.by?.concept ?? c.made?.model ?? `Picture ${c.n}`} disabled={!!busy || !!job}
                onClick={() => void act("use", () => api.post(`/api/projects/${project.id}/cover/use`, { n: c.n, forLiving: true }))}>
                <img src={`/api/projects/${project.id}/covers/${c.n}/thumb.jpg`} alt={`Picture ${c.n}`} loading="lazy" />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---- 2 · the motion ----------------------------------------------------------------------------------------------- */

function MotionStep({ project, lv, loops, locked, jobs, busy, act, save, onShow }: {
  project: Project; lv: Living; loops: LivingLoop[]; locked: boolean; jobs: Record<string, Job>; busy: string | null;
  act: Act; save: Save; onShow: (id: string) => void;
}) {
  const roles = useWho((w) => w.roles);
  const s = lv.settings;
  const [steer, setSteer] = useState(lv.steer ?? "");
  const written = loops.length > 0 && loops.every((l) => l.motion.trim());
  const working = loops.some((l) => l.status === "queued" || l.status === "making");
  const coverN = project.cover?.n;
  const todo = loops.filter((l) => l.motion.trim() && (!l.video || l.cover !== coverN || l.madeWith !== l.motion ||
    (l.madeFeel ?? s.feel) !== s.feel || (l.madeSeconds ?? s.seconds) !== s.seconds || (l.madeHold ?? s.keepPeople) !== s.keepPeople ||
    l.way !== "forward"));
  const minutes = Math.max(1, Math.round(todo.length * (s.seconds > 8 ? 2.2 : 1.3)));
  const make = async () => {
    for (const l of todo) if (l.status !== "queued" && l.status !== "making")
      await act(`make-${l.id}`, () => api.post(`/api/projects/${project.id}/living/loops/${l.id}/make`));
  };

  if (locked) {
    return (
      <div className="la-step la-locked">
        <h3><span className="mk-n">2</span>The motion</h3>
        <p className="la-note">Once the picture is chosen: how much it moves, and what.</p>
      </div>
    );
  }
  return (
    <div className="la-step la-now">
      <h3><span className="mk-n">2</span>The motion</h3>
      <div className="la-row">
        <span>How much movement</span>
        <Segmented size="sm" label="How much movement" value={s.feel} onChange={(feel) => void save({ settings: { feel } })}
          options={(Object.keys(FEEL) as Feel[]).map((k) => ({ value: k, label: FEEL[k].label }))} />
      </div>
      <p className="la-note la-tight">{FEEL[s.feel].line}</p>
      <div className="la-row">
        <span>Loops</span>
        <Segmented size="sm" label="Loops" value={s.count} onChange={(count) => void save({ settings: { count } })}
          options={[1, 2, 3, 4].map((n) => ({ value: n, label: String(n) }))} />
      </div>
      <p className="la-note la-tight">{s.count === 1 ? "One motion for the whole song." : `${s.count} different small motions that take turns through the song.`}</p>

      <div className="la-steer">
        <input className="in" value={steer} placeholder="Steer it, if you like: “only the candle flames”, “slow rain on the window”"
          onChange={(e) => setSteer(e.target.value)} />
        <Button size="sm" kind={written ? "ghost" : "primary"} busy={busy === "plan"} disabled={!!busy || working}
          onClick={() => void act("plan", () => api.post(`/api/projects/${project.id}/living/plan`, { note: steer }))}>
          {written ? "Write again" : `Let ${doer(roles, "direct")} decide`}
        </Button>
      </div>
      {busy === "plan" && <p className="la-note">{Doer(roles, "direct")} is looking at the picture and choosing what can move…</p>}
      {!written && busy !== "plan" && <p className="la-note">{Doer(roles, "direct")} looks at the picture and picks what can move for each loop. You can change any of it before
        animating, or write the motion yourself in the boxes.</p>}
      {lv.plan?.risk && <p className="la-risk">{lv.plan.risk}</p>}

      <div className="la-loops">
        {loops.map((l) => (
          <LoopCard key={l.id} loop={l} job={l.jobId ? jobs[l.jobId] : undefined} coverN={coverN} projectId={project.id}
            feel={s.feel} seconds={s.seconds} keepPeople={s.keepPeople} onShow={() => onShow(l.id)} onText={(t) => void save({ motions: { [l.id]: t } })}
            onAgain={() => void act(`make-${l.id}`, () => api.post(`/api/projects/${project.id}/living/loops/${l.id}/make`))}
            busy={busy === `make-${l.id}`} />
        ))}
      </div>

      {todo.length > 0 && (
        <div className="la-go">
          <Button kind="primary" disabled={!!busy || working} onClick={() => void make()}>
            {todo.length === loops.length ? `Animate ${loops.length === 1 ? "it" : `the ${loops.length} loops`}` : `Animate ${todo.length === 1 ? "the changed loop" : `${todo.length} changed loops`}`}
          </Button>
          <span>About {minutes} min on {machine()}; the video makes itself when they're done.</span>
        </div>
      )}
      <Disclosure id="living-more" title="More" hint="loop length, people">
        <div className="la-row">
          <span>Each loop lasts</span>
          <Segmented size="sm" label="Seconds per loop" value={s.seconds} onChange={(seconds) => void save({ settings: { seconds } })}
            options={[4, 6, 8, 12].map((n) => ({ value: n, label: `${n} s`, hint: n > 8 ? "Made from 6 s pieces" : undefined }))} />
        </div>
        <label className="la-check">
          <input type="checkbox" checked={s.keepPeople} onChange={(e) => void save({ settings: { keepPeople: e.target.checked } })} />
          <span><strong>Freeze people exactly as painted.</strong> Off, they hold their pose and only breathe, which looks most
            natural. On, they're kept perfectly still while the world around them moves (it can look odd).</span>
        </label>
      </Disclosure>
    </div>
  );
}

function LoopCard({ loop, job, coverN, projectId, feel, seconds, keepPeople, busy, onShow, onText, onAgain }: {
  loop: LivingLoop; job?: Job; coverN?: number; projectId: string; feel: Feel; seconds: number; keepPeople: boolean; busy: boolean;
  onShow: () => void; onText: (t: string) => void; onAgain: () => void;
}) {
  const hold = keepPeople;
  const [text, setText] = useState(loop.motion);
  const focused = useRef(false);
  useEffect(() => {
    if (!focused.current) setText(loop.motion);
  }, [loop.motion]);
  const working = loop.status === "queued" || loop.status === "making";
  const why = !loop.video ? null : loop.cover !== coverN ? "made from another picture" :
    loop.madeWith !== loop.motion ? "the words have changed" :
    loop.way !== "forward" ? "made the old way (it can look like it plays back on itself)" :
    (loop.madeFeel ?? feel) !== feel || (loop.madeSeconds ?? seconds) !== seconds || (loop.madeHold ?? hold) !== hold ? "made with other settings" : null;
  return (
    <article className={`la-loop st-${loop.status}`}>
      <div className="la-loop-head">
        <span className="la-letter">{LETTER[loop.id]}</span>
        {loop.video && (
          <button type="button" className="la-thumb" onClick={onShow} aria-label={`Show loop ${LETTER[loop.id]}`}>
            <LoopVideo src={fileUrl(projectId, loop.video)} />
          </button>
        )}
        <span className="la-state">
          {working ? (job?.message ?? "Waiting its turn") :
            loop.video ? <>{VERDICT[loop.verdict ?? "calm"]} · {loop.seconds?.toFixed(1)} s{loop.held ? " · people held" : ""}</> :
            loop.error ? <em>{loop.error}</em> : "Not made yet"}
          {why && !working && <em> · {why}</em>}
        </span>
        {loop.video && !working && (
          <Button size="sm" kind="ghost" busy={busy} disabled={busy || !text.trim()} onClick={onAgain} title="Make this loop again (another take)">
            Again
          </Button>
        )}
      </div>
      {working && <div className="la-bar"><i style={{ width: `${Math.round((job?.progress ?? 0) * 100)}%` }} /></div>}
      <TextArea minRows={2} value={text} placeholder="What moves, and how little: “dust drifts slowly through the beam of light…”"
        onFocus={() => (focused.current = true)}
        onBlur={() => { focused.current = false; if (text.trim() !== loop.motion) onText(text); }}
        onChange={(e) => setText(e.target.value)} />
      {loop.usable === false && loop.unusable && !working && <span className="la-warn">{loop.unusable}</span>}
      {hold && ABOUT_PEOPLE.test(text) && (
        <span className="la-warn">These words ask a person to move, but people are frozen (under More): untick it to let them.</span>
      )}
    </article>
  );
}

/* ---- 3 · the video ------------------------------------------------------------------------------------------------ */

function VideoStep({ project, lv, loops, locked, jobs, busy, act, save }: {
  project: Project; lv: Living; loops: LivingLoop[]; locked: boolean; jobs: Record<string, Job>; busy: string | null;
  act: Act; save: Save;
}) {
  const s = lv.settings;
  const rendering = Object.values(jobs).find((j) => j.kind === "living.render" && j.projectId === project.id &&
    (j.status === "queued" || j.status === "running"));
  const failed = Object.values(jobs).filter((j) => j.kind === "living.render" && j.projectId === project.id)
    .sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0];
  const current = lv.renders.find((r) => r.shape === s.shape && !r.finish);
  const others = lv.renders.filter((r) => r.shape !== s.shape || r.finish);
  const ready = loops.filter((l) => l.video);
  const stale = !!current && (current.transition !== s.transition || current.cover !== project.cover?.n ||
    ready.some((l) => current.made?.[l.id] !== l.rev) || ready.length !== Object.keys(current.made ?? {}).length);

  if (locked) {
    return (
      <div className="la-step la-locked">
        <h3><span className="mk-n">3</span>The video</h3>
        <p className="la-note">Made by itself once the loops are ready: they take turns through the whole song, under the title and logos.</p>
      </div>
    );
  }
  return (
    <div className="la-step la-now">
      <h3><span className="mk-n">3</span>The video</h3>
      <p className="la-note">The loops take turns through the whole song, changing at its sections, with the title and logos
        on top and your take as the sound. It's remade by itself when a loop or these settings change.</p>
      <div className="la-row">
        <span>Between loops</span>
        <Segmented size="sm" label="Transition" value={s.transition} onChange={(transition) => void save({ settings: { transition } })}
          options={(Object.keys(TRANSITION) as Transition[]).map((k) => ({ value: k, label: TRANSITION[k].label }))} />
      </div>
      <p className="la-note la-tight">{loops.length > 1 ? TRANSITION[s.transition].line : "With one loop there's nothing to change between."}</p>
      <div className="la-row">
        <span>Shape</span>
        <Segmented size="sm" label="Shape" value={s.shape} onChange={(shape) => void save({ settings: { shape } })}
          options={[{ value: "square", label: "Square", hint: "1080 × 1080, like the cover" },
            { value: "story", label: "9:16", hint: "1080 × 1920: the cover over a soft, dark copy of itself" },
            { value: "wide", label: "16:9", hint: "1920 × 1080: the cover over a soft, dark copy of itself" }]} />
      </div>

      {rendering ? (
        <div className="la-making">
          <span><span className="ln-spin" aria-hidden="true" /> {rendering.message ?? "Putting the video together"}</span>
          <div className="la-bar"><i style={{ width: `${Math.round((rendering.progress ?? 0) * 100)}%` }} /></div>
        </div>
      ) : (!current || stale) && (
        <div className="la-go">
          <Button kind="primary" busy={busy === "render"} disabled={!!busy}
            onClick={() => void act("render", () => api.post(`/api/projects/${project.id}/living/render`, {}))}>
            {current ? "Update the video" : `Make the ${SHAPE_NAME[s.shape].toLowerCase()} video`}
          </Button>
          <span>About half a minute.</span>
        </div>
      )}
      {failed?.status === "failed" && !rendering && <p className="ie-err">The last try didn't work: {failed.message}</p>}
      {current && <RenderCard r={current} projectId={project.id} title={project.title} stale={stale} />}
      {others.length > 0 && (
        <div className="la-others">
          <span>Other shapes</span>
          {others.map((r) => <RenderCard key={r.id} r={r} projectId={project.id} title={project.title} small />)}
        </div>
      )}
    </div>
  );
}

function RenderCard({ r, projectId, title, stale, small }: { r: LivingRender; projectId: string; title: string; stale?: boolean; small?: boolean }) {
  const when = useMemo(() => new Date(r.at * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }), [r.at]);
  return (
    <article className={`la-render sh-${r.shape}${small ? " small" : ""}`}>
      {!small && <video src={fileUrl(projectId, r.file)} controls playsInline preload="metadata" onPlay={() => usePlayer.getState().stop()} />}
      <div className="la-render-meta">
        <strong>{SHAPE_NAME[r.shape]}{r.finish ? " · with its finish in code" : ""}</strong>
        <span>{Math.floor(r.seconds / 60)}:{String(Math.round(r.seconds % 60)).padStart(2, "0")} · {(r.bytes / 1e6).toFixed(0)} MB · {when}
          {stale ? " · older than your changes" : ""}</span>
        <a href={fileUrl(projectId, r.file)} download={`${title} (${SHAPE_NAME[r.shape]}).mp4`}>Download</a>
      </div>
    </article>
  );
}

/** A silent loop that starts by itself. Browsers only autoplay video that is muted when it starts, and React sets
 *  `muted` as a property after the element exists, so it is set here and play() asked for explicitly. */
function LoopVideo({ src }: { src: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    v.muted = true;
    const go = () => void v.play().catch(() => undefined);
    go();
    v.addEventListener("canplay", go);
    return () => v.removeEventListener("canplay", go);
  }, [src]);
  return <video ref={ref} src={src} loop muted playsInline preload="auto" />;
}
