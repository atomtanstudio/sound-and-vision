import { useEffect, useMemo, useState } from "react";
import { Said } from "../ui/Said";
import { api, ApiError, fileUrl } from "../lib/api";
import { go as goTo, useQuery } from "../lib/router";
import type { KineticVideo, Project } from "../lib/types";
import { usePlayer } from "../state/player";
import { useSong } from "../state/song";
import { EFFORT_NAME } from "../shell/Settings";
import { Button, Disclosure, Segmented, TextArea } from "../ui/controls";
import { ThumbMaker } from "../library/ThumbMaker";
import "../library/library.css";
import "../shell/bring.css";
import { machine } from "../lib/machine";
import { okToSpend, onSettingsChanged, type PictureChoice, type Using } from "../lib/pictures";
import { Doer, doer, useWho } from "../state/who";

const SHAPE = { wide: "16:9", story: "9:16", square: "Square" } as const;
const EFFORTS = ["low", "medium", "high", "xhigh", "max"];
const WORKING = ["queued", "preparing", "running", "stopping"];

/** The request Claude gets unless you write your own: your own chat prompt, word for word (the server's OPENING). */
function defaultRequest(p: Project, lyrics: boolean) {
  const artist = p.cover?.artist || p.source?.artist || "";
  const by = artist ? ` by ${artist}` : "";
  return lyrics
    ? `Make a dynamic motion graphics music video with lyrics for "${p.title}"${by} that shows what an incredible motion designer ` +
      "you are, like it's your showreel for a résumé. Go all out. The song is song/song.m4a, and its lyrics, timed to the singing, " +
      "are in song/timing.json."
    : `Make a dynamic motion graphics music video for "${p.title}"${by}, using the song in song/song.m4a, that shows what an ` +
      "incredible motion designer you are. Go all out.";
}

/** What differs between the films Claude makes in its studio: Motion Graphics (all code) and Music Video (pictures
 *  made as Settings says, brought to life with H3). Both are one Claude conversation; notes continue it. */
type Mode = "kinetic" | "music";
const WORD: Record<Mode, string> = { kinetic: "motion graphics", music: "music video" };

/** Motion Graphics: Claude writes and renders a music video for the whole song in code, with the lyrics or without,
 *  with free rein: the way the films made in Claude Code chats were made. Notes continue the same conversation. */
export function KineticFilm({ project, mode = "kinetic" }: { project: Project; mode?: Mode }) {
  const k = project[mode] ?? { film: null, videos: [] };
  const film = k.film;
  const working = !!film && WORKING.includes(film.status);
  const [fresh, setFresh] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const current = k.videos.find((v) => v.id === film?.video) ?? (film ? k.videos.find((v) => v.film === film.id) : undefined) ?? k.videos[0];
  const asked = useQuery("v");  // ?v=<id>: an earlier version, opened from the Library or the list below
  const watching = (asked ? k.videos.find((v) => v.id === asked) : undefined) ?? current;
  const watchUrl = (vid?: string) => `/video/${project.id}?kind=${mode}${vid ? `&v=${vid}` : ""}`;

  const act = async (what: string, fn: () => Promise<unknown>) => {
    setBusy(what);
    setError(null);
    try {
      const r = await fn();
      if (r && typeof r === "object" && "rev" in (r as Project)) useSong.getState().onProject(r as Project);
      setFresh(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    } finally {
      setBusy(null);
    }
  };

  const showForm = !film || fresh;
  return (
    <div className="kt">
      <section className="kt-monitor" aria-label="The film">
        <Monitor project={project} mode={mode} working={working} current={showForm && !asked ? k.videos[0] : watching} stills={film?.status === "waiting" ? film.stills ?? [] : []} />
      </section>
      <section className="kt-side">
        {showForm ? (
          mode === "music" ? (
            <MusicStartForm project={project} busy={busy} onCancel={film ? () => setFresh(false) : undefined}
              onStart={(body) => act("start", () => api.post(`/api/projects/${project.id}/music`, body))} />
          ) : (
            <StartForm project={project} busy={busy} onCancel={film ? () => setFresh(false) : undefined}
              onStart={(body) => act("start", () => api.post(`/api/projects/${project.id}/kinetic`, body))} />
          )
        ) : (
          <FilmState project={project} mode={mode} busy={busy} current={current} onNew={() => setFresh(true)}
            onNote={(text, go) => act(go ? "go" : "note", () => api.post(`/api/projects/${project.id}/${mode}/note`, { text, go }))}
            onStop={() => act("stop", () => api.post(`/api/projects/${project.id}/${mode}/stop`))} />
        )}
        {error && <p className="ie-err">{error}</p>}
        {watching && current && watching.id !== current.id && (
          <p className="la-note">Watching version {watching.version}{watching.part ? `, ${fmt(watching.part.start)}–${fmt(watching.part.end)}` : watching.opening ? ", the opening" : ""}.{" "}
            <button type="button" className="kt-linkbtn" onClick={() => goTo(watchUrl(), true)}>Back to the newest</button></p>
        )}
        {k.videos.length > 1 && !working && (
          <div className="kt-versions">
            <span>Other versions</span>
            {k.videos.filter((v) => v.id !== watching?.id).map((v) => (
              <VersionRow key={v.id} v={v} project={project} mode={mode} onWatch={() => goTo(watchUrl(v.id === current?.id ? undefined : v.id), true)} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Monitor({ project, mode, working, current, stills }: { project: Project; mode: Mode; working: boolean; current?: KineticVideo; stills: string[] }) {
  const [peek, setPeek] = useState<{ file: string; at: number }[]>([]);
  useEffect(() => {
    if (!working) return;
    const load = () => api.get<{ file: string; at: number }[]>(`/api/projects/${project.id}/${mode}/peek`).then(setPeek).catch(() => undefined);
    void load();
    const id = window.setInterval(load, 15000);
    return () => window.clearInterval(id);
  }, [working, project.id, mode]);
  const shape = current?.shape ?? project[mode]?.film?.shape ?? "wide";
  if (working && peek.length) {
    const p = peek[0];
    return (
      <>
        <div className={`kt-frame sh-${shape}`}><img src={`${fileUrl(project.id, p.file)}?v=${Math.round(p.at)}`} alt="" /></div>
        <p className="la-caption">The latest {mode === "music" ? "picture it made" : "frame it drew"}, {new Date(p.at * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}.
          It looks at its work as it goes.</p>
      </>
    );
  }
  if (stills.length) {
    return (
      <>
        <div className="kt-stills">{stills.map((s) => <img key={s} src={fileUrl(project.id, s)} alt="" />)}</div>
        <p className="la-caption">Stills of key moments, from the idea.</p>
      </>
    );
  }
  if (current && !working) {
    return (
      <>
        <div className={`kt-frame sh-${current.shape}`}>
          <video key={current.file} src={fileUrl(project.id, current.file)} poster={current.poster ? fileUrl(project.id, current.poster) : undefined}
            controls playsInline preload="metadata" onPlay={() => usePlayer.getState().stop()} />
        </div>
        <p className="la-caption">Version {current.version}{current.part ? ` · ${fmt(current.part.start)}–${fmt(current.part.end)} of the song` : current.opening ? " · the opening" : ""} · {SHAPE[current.shape]} · {fmt(current.seconds)}</p>
      </>
    );
  }
  return (
    <div className={`kt-frame sh-${shape} kt-empty`}>
      <span>{working ? `Setting up. ${mode === "music" ? "Pictures" : "Frames"} appear here as they're made.` : `The ${mode === "music" ? "video" : "film"} plays here.`}</span>
    </div>
  );
}

/** The model that directs this film and how long it thinks: the models that can direct videos in code, as connected
 *  in Settings (none connected: says so, and the film can't start). */
function DirectorPick({ model, effort, setModel, setEffort }: {
  model: string; effort: string; setModel: (m: string) => void; setEffort: (e: string) => void;
}) {
  const films = useWho((w) => w.filmModels);
  if (!films.length) {
    return <p className="la-note kt-who-none">Videos made in code need a model that can direct in code: connect one in
      Settings.</p>;
  }
  return (
    <div className="kt-who">
      <select className="in" value={model} onChange={(e) => setModel(e.target.value)} aria-label="Model">
        {films.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        {!films.some((m) => m.id === model) && <option value={model}>{model}</option>}
      </select>
      <select className="in" value={effort} onChange={(e) => setEffort(e.target.value)} aria-label="Reasoning">
        <option value="">Reasoning: the model's default</option>
        {EFFORTS.map((x) => <option key={x} value={x}>Reasoning: {EFFORT_NAME[x]}</option>)}
      </select>
    </div>
  );
}

function StartForm({ project, busy, onStart, onCancel }: {
  project: Project; busy: string | null; onCancel?: () => void;
  onStart: (body: { request: string; feel: string; shape: string; ideaFirst: boolean; model: string; effort: string | null; lyrics: boolean }) => Promise<void>;
}) {
  const roles = useWho((w) => w.roles);
  const plan = useWho((w) => w.plan);
  const films = useWho((w) => w.filmModels);
  const hasWords = project.sung !== false && !!project.sections?.some((s) => s.text.trim());
  const [lyrics, setLyrics] = useState(hasWords);
  const base = useMemo(() => defaultRequest(project, lyrics), [project.title, project.cover?.artist, project.source?.artist, lyrics]);
  const [request, setRequest] = useState(base);
  const [edited, setEdited] = useState(false);
  useEffect(() => { if (!edited) setRequest(base); }, [base, edited]);
  const [feel, setFeel] = useState("");
  const [shape, setShape] = useState<"wide" | "story" | "square">("wide");
  const [ideaFirst, setIdeaFirst] = useState(false);
  const [model, setModel] = useState("claude-opus-5-5");
  const [effort, setEffort] = useState<string>("xhigh");
  useEffect(() => {  // the defaults from Settings → Who does what → Making videos in code
    api.get<{ who: Record<string, { model: string | null; effort?: string | null }[]> }>("/api/connections")
      .then((c) => { const f = c.who.film?.[0]; if (f?.model) setModel(f.model); setEffort(f?.effort ?? ""); }).catch(() => undefined);
  }, []);
  return (
    <div className="la-step la-now kt-form">
      <div className="la-step-head">
        <h3>Motion Graphics</h3>
        {onCancel && <Button size="sm" kind="ghost" onClick={onCancel}>Back to the film</Button>}
      </div>
      <p className="la-lead">{Doer(roles, "film", "The director")} designs, writes and renders a music video for the whole song in
        code, with free rein.</p>
      <div className="la-row">
        <span>Lyrics</span>
        <Segmented size="sm" label="Lyrics" value={lyrics ? "on" : "off"} onChange={(v) => setLyrics(v === "on")} options={[
          { value: "on", label: "With lyrics", hint: hasWords ? "The sung words, timed to the vocal, are in the folder" : "This song has no words yet" },
          { value: "off", label: "No lyrics", hint: "Pure motion graphics" }]} />
      </div>
      <label className="br-field"><span>Anything to steer it? (optional)</span>
        <TextArea minRows={2} value={feel} placeholder={`“Brutalist and loud”, “a slow-burn noir”, “make the chorus explode”… or leave it to ${doer(roles, "film", "the director")}`}
          onChange={(e) => setFeel(e.target.value)} />
      </label>
      <div className="la-row">
        <span>Shape</span>
        <Segmented size="sm" label="Shape" value={shape} onChange={setShape} options={[
          { value: "wide", label: "16:9", hint: "1920 × 1080, 60 fps" }, { value: "story", label: "9:16", hint: "1080 × 1920, 60 fps" },
          { value: "square", label: "Square", hint: "1080 × 1080, 60 fps" }]} />
      </div>
      <DirectorPick model={model} effort={effort} setModel={setModel} setEffort={setEffort} />
      <label className="la-check">
        <input type="checkbox" checked={ideaFirst} onChange={(e) => setIdeaFirst(e.target.checked)} />
        <span><strong>Show me the idea first.</strong> {Doer(roles, "film", "The director")} writes a one-page idea with a few stills and waits for your go
          before it builds the film.</span>
      </label>
      <Disclosure id="kt-request" title="The request" hint="as simple as your own">
        <TextArea minRows={3} value={request} onChange={(e) => { setRequest(e.target.value); setEdited(true); }} />
        <p className="la-note">This is all the director is asked, plus your steer above. Its folder has the song, its stems and
          timed words, and the app's measurements, with no style rules. It can use the web and install whatever it needs.</p>
        {request !== base && <Button size="sm" kind="ghost" onClick={() => { setRequest(base); setEdited(false); }}>Back to the default</Button>}
      </Disclosure>
      <div className="la-go">
        <Button kind="primary" busy={busy === "start"} disabled={!!busy || !project.masterTake || !films.length}
          onClick={() => void onStart({ request: request === base ? "" : request, feel, shape, ideaFirst, model, effort: effort || null, lyrics })}>
          Make the film
        </Button>
        <span>Usually one to two hours on {machine()}, on your {plan ? `${plan} ` : ""}plan. You can leave this page; it carries on.</span>
      </div>
    </div>
  );
}

const MV_KINDS = [
  { id: "performance", name: "Performance", line: "An original performer or band singing the whole song, lip-synced, on a stage or anywhere.", singing: true },
  { id: "hybrid", name: "Hybrid", line: "Lip-sync woven through a story or striking imagery, like the Dub Pistols' “Rapture”.", singing: true },
  { id: "surreal", name: "Surreal", line: "Not a conventional video: a visual treat of impossible images, only loosely tied to the song.", singing: false },
] as const;
type MvKind = (typeof MV_KINDS)[number]["id"];

function MusicStartForm({ project, busy, onStart, onCancel }: {
  project: Project; busy: string | null; onCancel?: () => void;
  onStart: (body: { request: string; feel: string; kind: string; opening: boolean; part: Part | null; model: string; effort: string | null }) => Promise<void>;
}) {
  const roles = useWho((w) => w.roles);
  const plan = useWho((w) => w.plan);
  const films = useWho((w) => w.filmModels);
  const [kind, setKind] = useState<MvKind>("surreal");
  // who makes this video's pictures (Settings → Pictures for music videos), so the form can say it, and ask if it's paid
  const [pictures, setPictures] = useState<PictureChoice | undefined>();
  const [clips, setClips] = useState<PictureChoice | undefined>();
  const [using, setUsing] = useState<Using>({}); // the model and settings chosen on an MCP server, by role
  const [madeWith, setMadeWith] = useState<Using>({}); // exactly what Settings chose, in words
  useEffect(() => {  // (read again whenever Settings closes)
    const read = () => void api.get<{ scenes: string; choices: PictureChoice[]; motion: string; motionChoices: PictureChoice[];
                                       using?: Using; madeWith?: Using }>("/api/covers/settings")
      .then((s) => {
        setPictures(s.choices.find((c) => c.id === s.scenes));
        setClips(s.motionChoices.find((c) => c.id === s.motion));
        setUsing(s.using ?? {});
        setMadeWith(s.madeWith ?? {});
      }).catch(() => undefined);
    read();
    return onSettingsChanged(read);
  }, []);
  const named = (c: PictureChoice | undefined, role: "scenes" | "motion") => madeWith[role] || c?.name;
  const [first, setFirst] = useState<"opening" | "part" | "whole">("opening");
  const parts = useParts(project.id);
  const [partAt, setPartAt] = useState(0);
  const part = first === "part" ? parts[partAt] ?? null : null;
  const [base, setBase] = useState("");
  const [request, setRequest] = useState("");
  useEffect(() => {  // the request for this kind, as the server words it
    void api.get<{ request: string }>(`/api/projects/${project.id}/music/request?kind=${kind}`).then((r) => {
      setBase(r.request);
      setRequest(r.request);
    }).catch(() => undefined);
  }, [project.id, kind]);
  const singing = MV_KINDS.find((k) => k.id === kind)!.singing;
  const [feel, setFeel] = useState("");
  const [model, setModel] = useState("claude-opus-5-5");
  const [effort, setEffort] = useState<string>("xhigh");
  useEffect(() => {  // the defaults from Settings → Who does what → Making videos in code
    api.get<{ who: Record<string, { model: string | null; effort?: string | null }[]> }>("/api/connections")
      .then((c) => { const f = c.who.film?.[0]; if (f?.model) setModel(f.model); setEffort(f?.effort ?? ""); }).catch(() => undefined);
  }, []);
  return (
    <div className="la-step la-now kt-form">
      <div className="la-step-head">
        <h3>Music Video</h3>
        {onCancel && <Button size="sm" kind="ghost" onClick={onCancel}>Back to the video</Button>}
      </div>
      <p className="la-lead">{Doer(roles, "film", "The director")} directs a music video for the whole song: it makes the pictures with {named(pictures, "scenes") ?? "the source in Settings"},
        brings them to life with {singing ? `MiniMax H3 on ${machine()}` : named(clips, "motion") ?? `MiniMax H3 on ${machine()}`}, and cuts and finishes it to the music.{singing ? " The singing goes through VRGameDevGirl's Video Builder, with the song locked into each scene so the mouths follow the real vocal." : ""}</p>
      <div className="mv-kinds" role="radiogroup" aria-label="Kind of music video">
        {MV_KINDS.map((k) => (
          <button key={k.id} type="button" role="radio" aria-checked={k.id === kind}
            className={"mv-kind" + (k.id === kind ? " on" : "")} onClick={() => setKind(k.id)}>
            <strong>{k.name}{k.singing && <em>Lip-synced</em>}</strong>
            <span>{k.line}</span>
          </button>
        ))}
      </div>
      <label className="br-field"><span>Anything to steer it? (optional)</span>
        <TextArea minRows={2} value={feel} placeholder={`“Cold and minimal”, “like a dream underwater”, “painted, not photographed”… or leave it to ${doer(roles, "film", "the director")}`}
          onChange={(e) => setFeel(e.target.value)} />
      </label>
      <DirectorPick model={model} effort={effort} setModel={setModel} setEffort={setEffort} />
      <div className="mv-first">
        <Segmented size="sm" label="Start with" value={first} onChange={setFirst}
          options={[{ value: "opening", label: "The first 30 seconds" }, { value: "part", label: "A part of the song" }, { value: "whole", label: "The whole song" }]} />
        {first === "opening" && <p className="la-note">It plans the whole video, makes the opening with its title screen, and waits for
          your go before it makes the rest.</p>}
        {first === "part" && (
          <>
            <select className="in" value={partAt} onChange={(e) => setPartAt(Number(e.target.value))} aria-label="Which part">
              {parts.map((x, i) => <option key={i} value={i}>{x.label} · {fmt(x.start)}–{fmt(x.end)}</option>)}
            </select>
            <p className="la-note">It plans the whole video, then makes just this part, with no title screen, so it can stand on its
              own (a trailer, a clip). Make the rest carries on from there.</p>
          </>
        )}
      </div>
      <Disclosure id="mv-request" title="The request" hint="your words">
        <TextArea minRows={4} value={request} onChange={(e) => setRequest(e.target.value)} />
        <p className="la-note">This is what the director is asked, plus your steer above. Its folder has the song, its stems and timed
          words, the app's measurements, the way to make pictures, H3, and your MCP servers, with no style rules.</p>
        {request !== base && <Button size="sm" kind="ghost" onClick={() => setRequest(base)}>Back to the default</Button>}
      </Disclosure>
      <div className="la-go">
        <Button kind="primary" busy={busy === "start"} disabled={!!busy || !project.masterTake || !films.length}
          onClick={() => okToSpend(pictures, "this video's pictures", using.scenes) && (singing || okToSpend(clips, "this video's clips", using.motion)) && void onStart({ request: request === base ? "" : request, feel, kind, opening: first !== "whole", part, model, effort: effort || null })}>
          Make the video
        </Button>
        <span>{singing
          ? `The Video Builder takes about 5–6 minutes a scene, so 30 seconds takes about 45 minutes and the whole song six to eight hours, on your ${plan ? `${plan} ` : ""}plan. You can leave this page.`
          : `H3 takes about 90 seconds a shot, so the opening takes around half an hour and the whole song a few hours, on your ${plan ? `${plan} ` : ""}plan. You can leave this page.`}</span>
      </div>
    </div>
  );
}

function FilmState({ project, mode, busy, current, onNew, onNote, onStop }: {
  project: Project; mode: Mode; busy: string | null; current?: KineticVideo; onNew: () => void;
  onNote: (text: string, go: boolean) => Promise<void>; onStop: () => void;
}) {
  const roles = useWho((w) => w.roles);
  const films = useWho((w) => w.filmModels);
  const film = project[mode]!.film!;
  const opening = film.status === "waiting" && !!current?.opening && current.film === film.id;
  const [thumb, setThumb] = useState(false);
  const name = mode === "music" ? "video" : "film";
  const [note, setNote] = useState("");
  const working = WORKING.includes(film.status);
  const since = useSince(film.runAt ?? film.at, working);
  const lines = (film.lines ?? []).slice(-6);
  return (
    <div className="la-step la-now kt-state">
      <div className="la-step-head">
        <h3>{working ? `${Doer(roles, "film", "The director")} is making the ${name}` : opening ? (current?.part ? "The part" : "The opening") : film.status === "waiting" ? (film.concept ? "The idea" : "It replied") :
          film.status === "done" ? `The ${name}` : film.status === "stopped" ? "Stopped" : "It stopped"}</h3>
        <span className="la-note">{films.find((m) => m.id === film.model)?.name ?? film.model} · {film.effort ? EFFORT_NAME[film.effort] : "default"} reasoning</span>
      </div>

      {working && (
        <>
          <p className="kt-now"><span className="ln-spin" aria-hidden="true" /> <Said text={film.message ?? "Working"} /></p>
          <p className="la-note">{since}. Every {name} is its own, so it takes as long as it takes; you can leave this page.</p>
        </>
      )}
      {lines.length > 0 && (
        <div className="kt-lines">
          {lines.map((l, i) => <p key={i}><Said text={l.text} /></p>)}
        </div>
      )}
      {film.status === "waiting" && film.concept && <div className="kt-concept"><Said text={film.concept} /></div>}
      {!working && film.reply && film.status !== "done" && !film.concept && <p className="kt-reply"><Said text={film.reply} /></p>}
      {opening && current && (
        <div className="la-render-meta">
          <strong>{current.part ? `${fmt(current.part.start)}–${fmt(current.part.end)} of the song` : `The first ${fmt(current.seconds)}`}</strong>
          <a href={fileUrl(project.id, current.file)} download={`${project.title} (${WORD[mode]}, opening).mp4`}>Download</a>
        </div>
      )}
      {(film.status === "failed" || film.status === "stopped") && film.error && <p className="ie-err">{film.error}</p>}
      {film.status === "done" && current && (
        <>
          {current.about && <p className="la-note"><strong>About it:</strong> <Said text={current.about} /></p>}
          <div className="la-render-meta">
            <strong>Version {current.version}</strong>
            <span>{SHAPE[current.shape]} · {fmt(current.seconds)} · {(current.bytes / 1e6).toFixed(0)} MB</span>
            <a href={fileUrl(project.id, current.file)} download={`${project.title} (${WORD[mode]}, v${current.version}).mp4`}>Download</a>
            <button type="button" className="kt-linkbtn" onClick={() => setThumb(true)}>Thumbnail</button>
            {current.share && <a href={fileUrl(project.id, current.share)} download={`${project.title} (${WORD[mode]}, v${current.version}, share).mp4`}>Smaller copy</a>}
          </div>
        </>
      )}

      {thumb && current && (
        <ThumbMaker onClose={() => setThumb(false)} onSaved={() => undefined} item={{
          key: `v:${project.id}:${mode === "music" ? "music" : "motion"}:${current.id}`, type: "video", kind: mode === "music" ? "music" : "motion",
          kindName: mode === "music" ? "Music Video" : "Motion Graphics", pid: project.id, vid: current.id, title: project.title,
          artist: project.cover?.artist || project.source?.artist || "", file: current.file, shape: current.shape,
          aspect: current.shape === "wide" ? 16 / 9 : current.shape === "story" ? 9 / 16 : 1, seconds: current.seconds, at: current.at, created: current.at,
        }} />
      )}
      {working ? (
        <div className="la-choice"><Button kind="ghost" busy={busy === "stop" || film.status === "stopping"} disabled={!!busy} onClick={onStop}>Stop</Button></div>
      ) : (
        <>
          {film.status === "waiting" && (film.concept || opening) && (
            <div className="la-choice">
              <Button kind="primary" busy={busy === "go"} disabled={!!busy} onClick={() => void onNote(note, true)}>{opening ? "Make the rest" : "Make it"}</Button>
              <span className="la-note">{note.trim() ? "Your note goes along with it." : opening ? `Or say what to change below: it redoes the ${current?.part ? "part" : "opening"}.` : "Or say what to change below."}</span>
            </div>
          )}
          {film.session && (
            <>
              <TextArea minRows={2} value={note} onChange={(e) => setNote(e.target.value)}
                placeholder={film.status === "done" ? "Ask for changes: “the second verse drags”, “bigger type in the chorus”…" :
                  film.status === "waiting" ? "Answer it, or say what to change" : "Carry on, or say what to do differently"} />
              <div className="la-choice">
                <Button busy={busy === "note"} disabled={!!busy || !note.trim()} onClick={() => void onNote(note, false).then(() => setNote(""))}>
                  {film.status === "done" ? "Send the note (makes a new version)" : "Send"}
                </Button>
                {(film.status === "failed" || film.status === "stopped") && (
                  <Button kind="ghost" disabled={!!busy} onClick={() => void onNote(`Carry on from where you stopped, all the way to the finished ${name}.`, false)}>
                    Carry on
                  </Button>
                )}
                <Button kind="ghost" disabled={!!busy} onClick={onNew}>Make a new {name}</Button>
              </div>
            </>
          )}
          {!film.session && <div className="la-choice"><Button kind="ghost" disabled={!!busy} onClick={onNew}>Make a new {name}</Button></div>}
        </>
      )}
    </div>
  );
}

function VersionRow({ v, project, mode, onWatch }: { v: KineticVideo; project: Project; mode: Mode; onWatch: () => void }) {
  return (
    <div className="la-render-meta">
      <strong>Version {v.version}{v.part ? `, ${fmt(v.part.start)}–${fmt(v.part.end)}` : v.opening ? ", the opening" : ""}</strong>
      <button type="button" className="kt-linkbtn" onClick={onWatch}>Watch</button>
      <span>{SHAPE[v.shape]} · {fmt(v.seconds)} · {new Date(v.at * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</span>
      <a href={fileUrl(project.id, v.file)} download={`${project.title} (${WORD[mode]}, v${v.version}).mp4`}>Download</a>
    </div>
  );
}

function fmt(t: number) {
  return `${Math.floor(t / 60)}:${String(Math.round(t % 60)).padStart(2, "0")}`;
}

/** "Started 12 min ago", kept current. */
function useSince(at: number, live: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(id);
  }, [live]);
  const m = Math.max(0, Math.round((now / 1000 - at) / 60));
  return m < 1 ? "Started just now" : m < 60 ? `Started ${m} min ago` : `Started ${Math.floor(m / 60)} h ${m % 60} min ago`;
}

type Part = { start: number; end: number; label: string };

/** The parts of a song worth making on their own, about 30 seconds each and ending on a bar line: the app's best
 *  moments (from its loudness and sections) first, then each section from its start. */
function useParts(pid: string): Part[] {
  const [parts, setParts] = useState<Part[]>([]);
  useEffect(() => {
    type M = { duration: number; bars: number[]; sections: { label: string; start: number; end: number }[];
      moments: { start: number; end: number; why: string }[] };
    void api.get<M>(`/api/share/moments/${pid}?seconds=30`).then((m) => {
      const end = (a: number) => Math.min(m.duration, m.bars.find((b) => b >= a + 29.5) ?? a + 30);
      const best = m.moments.map((x, i) => ({ start: x.start, end: end(x.start), label: i === 0 ? "Best 30 seconds" : x.why.split(",")[0].replace(/^./, (c) => c.toUpperCase()) }));
      const sections = m.sections.filter((s) => s.label && s.end - s.start > 8)
        .map((s, i, all) => ({ start: s.start, end: end(s.start), label: all.filter((t, j) => j < i && t.label === s.label).length ? `${s.label} (again)` : s.label }));
      setParts([...best, ...sections].filter((x) => x.end - x.start >= 5));
    }).catch(() => setParts([]));
  }, [pid]);
  return parts;
}
