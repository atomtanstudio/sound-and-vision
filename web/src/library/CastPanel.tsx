import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, fileUrl } from "../lib/api";
import { Button, TextArea } from "../ui/controls";
import "./cast.css";

export type Who = "invented" | "me" | "permission";
export interface CastMember {
  id: string;
  name: string;
  about: string;
  who: Who;
  whoSays: string;
  pictures: { name: string; url: string }[];
}
export interface VideoCast {
  projectId: string;
  filmId: string;
  title: string;
  at: number;
  cast: { key: string; name: string; about: string; who: Who; pictures: number; path: string }[];
}

const WHO: { value: Who; label: string }[] = [
  { value: "invented", label: "An invented character" },
  { value: "me", label: "Me" },
  { value: "permission", label: "Someone who agreed to it" },
];
const MOST = 4;
const day = (t: number) => new Date(t * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

async function send<T>(path: string, form: FormData): Promise<T> {
  const r = await fetch(path, { method: "POST", body: form, credentials: "same-origin" });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(body.detail || body.error || "That didn't save.", r.status);
  return body as T;
}

/** Library → Cast: your own characters, saved once and used in any lip-synced music video (Performance or Hybrid), so
 *  the same faces carry through a whole series; and the characters of your earlier videos, to keep and name. */
export function CastPanel({ onCount }: { onCount?: (n: number) => void }) {
  const [members, setMembers] = useState<CastMember[] | null>(null);
  const [videos, setVideos] = useState<VideoCast[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    const [c, v] = await Promise.all([api.get<{ members: CastMember[] }>("/api/cast"), api.get<VideoCast[]>("/api/cast/videos")]);
    setMembers(c.members);
    setVideos(v);
    onCount?.(c.members.length);
  }, [onCount]);
  useEffect(() => { void load().catch((e) => setError(e.message)); }, [load]);
  const act = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  return (
    <section className="lib-main cast">
      <header className="lib-head">
        <div>
          <h2>Cast</h2>
          <p>Your characters, saved once and used in any lip-synced music video (Performance or Hybrid), so the same faces carry
            through a video and a whole series. Choose them when you start the video.</p>
        </div>
      </header>
      {error && <p className="ie-err">{error}</p>}
      {!members ? <p className="mi-soon">Opening your Cast…</p> : (
        <div className="cast-grid">
          {members.map((m) => (
            <MemberCard key={m.id} m={m} busy={busy} act={act} />
          ))}
          <AddCharacter busy={busy === "add"} onAdd={(form) => act("add", () => send("/api/cast", form))} />
        </div>
      )}
      {videos && videos.length > 0 && (
        <div className="cast-videos">
          <h3>From your earlier videos</h3>
          <p className="la-note">The characters made for your music videos. Save one to your Cast to name it and use it again; a
            new video can also use a whole video's cast as it is (“Same as an earlier video” when you start it).</p>
          {videos.map((v) => (
            <div key={v.filmId} className="cast-video">
              <h4>{v.title} <span>· {day(v.at)}</span></h4>
              <div className="cast-row">
                {v.cast.map((c) => (
                  <SaveFromVideo key={c.key} v={v} c={c} busy={busy === `${v.filmId}/${c.key}`}
                    onSave={(name, who) => act(`${v.filmId}/${c.key}`, () => api.post("/api/cast/from-video",
                      { projectId: v.projectId, filmId: v.filmId, key: c.key, name, who, confirmed: true }))} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function MemberCard({ m, busy, act }: { m: CastMember; busy: string | null; act: (key: string, fn: () => Promise<unknown>) => Promise<void> }) {
  const [name, setName] = useState(m.name);
  const [about, setAbout] = useState(m.about);
  const file = useRef<HTMLInputElement>(null);
  const main = m.pictures[0];
  const mine = busy?.startsWith(m.id);
  return (
    <div className="cast-card">
      <div className="cast-main">{main && <img src={main.url} alt={m.name} />}</div>
      <div className="cast-thumbs">
        {m.pictures.map((p, i) => (
          <div key={p.name} className={"cast-thumb" + (i === 0 ? " on" : "")}>
            <img src={p.url} alt="" />
            {i > 0 && (
              <span className="cast-thumb-acts">
                <button type="button" disabled={!!busy} onClick={() => void act(`${m.id}-main`, () => api.post(`/api/cast/${m.id}/main/${p.name}`))}>Main</button>
                <button type="button" disabled={!!busy} aria-label="Remove this picture"
                  onClick={() => void act(`${m.id}-less`, () => api.del(`/api/cast/${m.id}/pictures/${p.name}`))}>Remove</button>
              </span>
            )}
          </div>
        ))}
        {m.pictures.length < MOST && (
          <button type="button" className="cast-thumb cast-more" disabled={!!busy} onClick={() => file.current?.click()}>+ Picture</button>
        )}
      </div>
      <input className="in" value={name} aria-label="Name" onChange={(e) => setName(e.target.value)}
        onBlur={() => name.trim() && name !== m.name && void act(`${m.id}-name`, () => api.patch(`/api/cast/${m.id}`, { name }))} />
      <TextArea minRows={2} value={about} placeholder="A few words about them (what they wear, how they move)…" aria-label="About them"
        onChange={(e) => setAbout(e.target.value)}
        onBlur={() => about !== m.about && void act(`${m.id}-about`, () => api.patch(`/api/cast/${m.id}`, { about }))} />
      <div className="cast-foot">
        <span className="la-note">{m.whoSays[0].toUpperCase() + m.whoSays.slice(1)}</span>
        <Button size="sm" kind="ghost" busy={mine && busy === `${m.id}-del`} disabled={!!busy}
          onClick={() => confirm(`Delete ${m.name} from your Cast? Videos already made with them keep their pictures.`)
            && void act(`${m.id}-del`, () => api.del(`/api/cast/${m.id}`))}>Delete</Button>
      </div>
      <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" multiple hidden
        onChange={(e) => {
          const files = [...(e.target.files ?? [])].slice(0, MOST - m.pictures.length);
          e.target.value = "";
          if (!files.length) return;
          const form = new FormData();
          files.forEach((f) => form.append("files", f));
          void act(`${m.id}-more`, () => send(`/api/cast/${m.id}/pictures`, form));
        }} />
    </div>
  );
}

/** Who's in the pictures, and the box that says so: nothing is saved without it. */
function WhoAndConsent({ who, setWho, confirmed, setConfirmed, id }: {
  who: Who | ""; setWho: (w: Who) => void; confirmed: boolean; setConfirmed: (b: boolean) => void; id: string;
}) {
  return (
    <>
      <fieldset className="cast-who">
        <legend>Who is this?</legend>
        {WHO.map((w) => (
          <label key={w.value}>
            <input type="radio" name={`who-${id}`} value={w.value} checked={who === w.value} onChange={() => setWho(w.value)} />
            {w.label}
          </label>
        ))}
      </fieldset>
      <label className="cast-consent">
        <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
        <span>I confirm these pictures show an invented character, me, or someone who has agreed to appear in AI-made videos,
          and not anyone famous or anyone who hasn't agreed.</span>
      </label>
    </>
  );
}

function AddCharacter({ busy, onAdd }: { busy: boolean; onAdd: (form: FormData) => Promise<void> }) {
  const file = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [about, setAbout] = useState("");
  const [who, setWho] = useState<Who | "">("");
  const [confirmed, setConfirmed] = useState(false);
  useEffect(() => {
    const urls = files.map((f) => URL.createObjectURL(f));
    setPreviews(urls);
    return () => urls.forEach((u) => URL.revokeObjectURL(u));
  }, [files]);
  const ready = files.length > 0 && name.trim() && who && confirmed;
  const save = async () => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    form.append("name", name.trim());
    form.append("about", about.trim());
    form.append("who", who);
    form.append("confirmed", String(confirmed));
    await onAdd(form);
    setFiles([]);
    setName("");
    setAbout("");
    setWho("");
    setConfirmed(false);
  };
  return (
    <div className="cast-card cast-add">
      <button type="button" className="cast-main cast-pick" onClick={() => file.current?.click()}>
        {previews[0] ? <img src={previews[0]} alt="" /> : <span>+ Add a character<br /><em>1 to {MOST} pictures: a clear face first, then
          more of them (full length, other angles)</em></span>}
      </button>
      {previews.length > 1 && (
        <div className="cast-thumbs">{previews.slice(1).map((u) => <div key={u} className="cast-thumb"><img src={u} alt="" /></div>)}</div>
      )}
      <input className="in" value={name} placeholder="Their name" aria-label="Their name" onChange={(e) => setName(e.target.value)} />
      <TextArea minRows={2} value={about} placeholder="A few words about them (optional)" aria-label="About them" onChange={(e) => setAbout(e.target.value)} />
      <WhoAndConsent who={who} setWho={setWho} confirmed={confirmed} setConfirmed={setConfirmed} id="new" />
      <Button size="sm" kind="primary" busy={busy} disabled={!ready || busy} onClick={() => void save()}>Save to your Cast</Button>
      <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" multiple hidden
        onChange={(e) => { setFiles([...(e.target.files ?? [])].slice(0, MOST)); e.target.value = ""; }} />
    </div>
  );
}

function SaveFromVideo({ v, c, busy, onSave }: {
  v: VideoCast; c: VideoCast["cast"][number]; busy: boolean; onSave: (name: string, who: Who) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(c.name);
  const [who, setWho] = useState<Who | "">(c.who);
  const [confirmed, setConfirmed] = useState(false);
  return (
    <div className="cast-from">
      <img src={fileUrl(v.projectId, c.path)} alt={c.name} />
      <strong>{c.name}</strong>
      {c.pictures > 1 && <span className="la-note">{c.pictures} pictures</span>}
      {!open ? <Button size="sm" kind="ghost" onClick={() => setOpen(true)}>Save to Cast</Button> : (
        <div className="cast-from-form">
          <input className="in" value={name} aria-label="Their name" onChange={(e) => setName(e.target.value)} />
          <WhoAndConsent who={who} setWho={setWho} confirmed={confirmed} setConfirmed={setConfirmed} id={`${v.filmId}-${c.key}`} />
          <div className="cast-foot">
            <Button size="sm" kind="primary" busy={busy} disabled={!name.trim() || !who || !confirmed || busy}
              onClick={() => void onSave(name.trim(), who as Who).then(() => setOpen(false))}>Save</Button>
            <Button size="sm" kind="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          </div>
        </div>
      )}
    </div>
  );
}
