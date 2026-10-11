import { useEffect, useRef, useState } from "react";
import { artistOf, setHouseArtist, useHouseArtist } from "../lib/artist";
import { api, ApiError, fileUrl } from "../lib/api";
import type { Project } from "../lib/types";
import { Button, Segmented } from "../ui/controls";
import { LookEditor } from "./LookEditor";
import type { BrandLogo, FontInfo, Look } from "./look";
import "../shell/home.css";
import "../song/music-index.css";
import "./look.css";
import { machine } from "../lib/machine";

export interface Brand {
  logos: BrandLogo[];
  look: Look;
  fonts: FontInfo[];
}

const SHAPES = { cover: { W: 3000, H: 3000, label: "Cover" }, wide: { W: 1280, H: 720, label: "16:9 thumbnail" },
  story: { W: 1080, H: 1920, label: "9:16 story" } } as const;

/** Brand (in Share): your logos, and your house look: where the title, the artist and the logos sit on every cover,
 *  living cover, thumbnail and clip, and how the words are set. Any song can have a look of its own on top (its cover's
 *  "Edit the look"). */
export function BrandBody() {
  const [brand, setBrand] = useState<Brand | null>(null);
  const [songs, setSongs] = useState<Project[]>([]);
  const [sample, setSample] = useState<string>("");
  const [shape, setShape] = useState<keyof typeof SHAPES>("cover");
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rev, setRev] = useState(0);
  const house = useHouseArtist();
  const [name, setName] = useState<string | null>(null);  // your artist name, while it's being typed
  const typed = name ?? house;
  useEffect(() => {
    void api.get<Brand>("/api/brand").then(setBrand).catch((e) => setError(String(e.message ?? e)));
    void api.get<Project[]>("/api/projects").then((ps) => {
      const covered = ps.filter((p) => p.cover).sort((a, b) => b.updatedAt - a.updatedAt);
      setSongs(covered);
      setSample((s) => s || covered[0]?.id || "");
    }).catch(() => undefined);
  }, []);
  const song = songs.find((p) => p.id === sample);
  const act = async (what: string, fn: () => Promise<unknown>, done?: string) => {
    setBusy(what);
    setError(null);
    setNote(null);
    try {
      await fn();
      if (done) setNote(done);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    } finally {
      setBusy(null);
    }
  };
  const S = SHAPES[shape];
  return (
    <div className="bp">
      {error && <p className="ie-err">{error}</p>}
      {note && <p className="bp-note">{note}</p>}

      <section className="bp-sec">
        <h2>Logos</h2>
        <div className="bp-logos">
          {brand?.logos.map((l) => (
            <LogoCard key={l.id + l.file} logo={l} busy={busy}
              onRename={(name) => act("name", async () => setBrand({ ...brand, ...(await api.patch<Brand>(`/api/brand/logos/${l.id}`, { name })) }))}
              onReplace={(file) => act("replace", async () => setBrand(await upload(file, l.name, l.id)))}
              onRemove={() => act("remove", async () => {
                if (!confirm(`Remove “${l.name}”? It comes off the house look (covers already made keep it until they're set again).`)) return;
                setBrand(await api.del<Brand>(`/api/brand/logos/${l.id}`));
              })} />
          ))}
          <AddLogo busy={busy === "add"} onAdd={(file, name) => act("add", async () => { setBrand(await upload(file, name)); setRev((r) => r + 1); })} />
        </div>
        <p className="mi-soon">PNG with a transparent background works best (JPEG and WebP too). The empty margin around a
          logo is trimmed, so it sits exactly where you put it.</p>
      </section>

      <section className="bp-sec">
        <div className="bp-head">
          <h2>House look</h2>
          <div className="bp-tools">
            {songs.length > 0 && (
              <select className="in" value={sample} onChange={(e) => setSample(e.target.value)} aria-label="Shown on">
                {songs.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
              </select>
            )}
            <Segmented size="sm" label="Shape" value={shape} onChange={setShape}
              options={Object.entries(SHAPES).map(([k, v]) => ({ value: k as keyof typeof SHAPES, label: v.label }))} />
          </div>
        </div>
        {brand && song ? (
          <LookEditor key={`${sample}-${shape}-${rev}`} picture={`/api/projects/${song.id}/cover/picture`}
            infoUrl={shape === "cover" ? `/api/projects/${song.id}/cover/picture/info` : undefined} W={S.W} H={S.H}
            look={brand.look} title={song.title} artist={artistOf(song, typed) || "Artist name"} logos={brand.logos}
            artistName={{
              label: "Your artist name", value: typed, placeholder: "The name on your songs", saving: busy === "name",
              note: "On every song without an artist of its own (a song's own goes under its title, on its page). Then set the covers you've already made again, below.",
              onChange: setName,
              onCommit: () => { if (name !== null && name.trim() !== house) void act("name", () => setHouseArtist(name), "Saved your artist name."); },
            }}
            saving={busy === "look"} saveLabel="Save the house look"
            onSave={(look) => act("look", async () => setBrand(await api.put<Brand>("/api/brand/look", { look })),
              "Saved. New covers and thumbnails use it; set the existing covers again below to bring them in line.")}
            extra={(
              <div className="lk-group">
                <h4>Covers you've already made</h4>
                <p className="la-note">Their pictures stay; only the title, the artist and the logos are set again (songs
                  with a look of their own keep it).</p>
                <Button busy={busy === "apply"} disabled={!!busy}
                  onClick={() => act("apply", async () => {
                    const r = await api.post<{ updated: number }>("/api/brand/apply");
                    setNote(`Set ${r.updated} cover${r.updated === 1 ? "" : "s"} again with the house look.`);
                  })}>Set every cover again</Button>
              </div>
            )} />
        ) : brand && !songs.length ? (
          <p className="mi-soon">Make a cover for a song first: the look is shown on it here.</p>
        ) : <p className="mi-soon">Opening…</p>}
        {song?.cover && (
          <p className="la-note bp-now">Shown on {song.title}'s picture. Its cover now: <a href={fileUrl(song.id, song.cover.file)} target="_blank" rel="noreferrer">open</a>.</p>
        )}
      </section>
    </div>
  );
}

async function upload(file: File, name: string, replace?: string): Promise<Brand> {
  const form = new FormData();
  form.append("file", file);
  form.append("name", name);
  if (replace) form.append("replace", replace);
  const r = await fetch("/api/brand/logos", { method: "POST", body: form, credentials: "same-origin" });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(body.detail || body.error || "The logo didn't upload.", r.status);
  return body as Brand;
}

function LogoCard({ logo, busy, onRename, onReplace, onRemove }: {
  logo: BrandLogo; busy: string | null; onRename: (n: string) => void; onReplace: (f: File) => void; onRemove: () => void;
}) {
  const [name, setName] = useState(logo.name);
  const file = useRef<HTMLInputElement>(null);
  return (
    <div className="bp-logo">
      <div className="bp-logo-pic"><img src={logo.file} alt={logo.name} /></div>
      <input className="in" value={name} aria-label="Name" onChange={(e) => setName(e.target.value)}
        onBlur={() => name.trim() && name !== logo.name && onRename(name)} />
      <span className="la-note">{logo.w} × {logo.h}</span>
      <div className="bp-logo-acts">
        <Button size="sm" kind="ghost" disabled={!!busy} onClick={() => file.current?.click()}>Replace</Button>
        <Button size="sm" kind="ghost" disabled={!!busy} onClick={onRemove}>Remove</Button>
      </div>
      <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" hidden
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onReplace(f); e.target.value = ""; }} />
    </div>
  );
}

function AddLogo({ busy, onAdd }: { busy: boolean; onAdd: (f: File, name: string) => void }) {
  const file = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  return (
    <div className="bp-logo bp-add">
      <div className="bp-logo-pic bp-add-pic" onClick={() => file.current?.click()} role="button" tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && file.current?.click()}>+ Add a logo</div>
      <input className="in" value={name} placeholder="Its name (your label, your handle…)" onChange={(e) => setName(e.target.value)} />
      <Button size="sm" kind="primary" busy={busy} onClick={() => file.current?.click()}>Choose a picture</Button>
      <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" hidden
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onAdd(f, name.trim() || f.name.replace(/\.\w+$/, "")); e.target.value = ""; setName(""); }} />
    </div>
  );
}
