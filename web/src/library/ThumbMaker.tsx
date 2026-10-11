import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, fileUrl } from "../lib/api";
import type { Project } from "../lib/types";
import type { Brand } from "../look/BrandPage";
import { LookEditor } from "../look/LookEditor";
import { mergeLook, type Look } from "../look/look";
import { Button, Modal } from "../ui/controls";
import type { Item } from "./LibraryPage";
import { machine } from "../lib/machine";

const SIZE = { wide: [1280, 720], story: [1080, 1920], square: [1080, 1080] } as const;
const PICKS = [0.06, 0.15, 0.25, 0.35, 0.45, 0.55, 0.68, 0.8];

interface Own { file: string; frame: number; layout: Partial<Look>; show: { title?: string; artist?: string }; size: [number, number]; at: number }

/** A thumbnail of your own for a video (for YouTube and the like): pick the frame, then lay the title, the artist and
 *  your logos over it in your look, at the size the platform wants (1280 × 720 for 16:9). */
export function ThumbMaker({ item, onClose, onSaved }: { item: Item; onClose: () => void; onSaved: () => void }) {
  const [brand, setBrand] = useState<Brand | null>(null);
  const [own, setOwn] = useState<Own | null | undefined>(undefined);
  const [at, setAt] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [made, setMade] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const base = `/api/library/frame/${item.pid}/${item.kind}/${item.vid}`;
  const [W, H] = SIZE[item.shape ?? "square"];
  const dur = item.seconds ?? 0;

  useEffect(() => {
    void api.get<Brand>("/api/brand").then(setBrand).catch(() => setError("The brand settings didn't load."));
    void api.get<Project & { thumbs?: Record<string, Own> }>(`/api/projects/${item.pid}`).then((p) => {
      const o = p.thumbs?.[`${item.kind}:${item.vid}`] ?? null;
      setOwn(o);
      setAt(o ? o.frame : Math.round(dur * 0.15 * 10) / 10);
    }).catch(() => { setOwn(null); setAt(Math.round(dur * 0.15 * 10) / 10); });
  }, [item.pid, item.kind, item.vid, dur]);

  const look = useMemo(() => {
    if (!brand) return null;
    const l = mergeLook(brand.look, own?.layout);
    if (!own && item.kind === "living") {  // a living cover's frames already carry its title and logos
      l.title.show = false;
      l.artist.show = false;
      for (const lg of Object.values(l.logos)) lg.show = false;
    }
    return l;
  }, [brand, own, item.kind]);
  const save = async (l: Look, words: { title: string; artist: string }) => {
    setBusy("save");
    setError(null);
    try {
      const p = await api.post<Project & { thumbs?: Record<string, Own> }>(`/api/library/thumb/${item.pid}/${item.kind}/${item.vid}`,
        { at, layout: l, show: words });
      const o = p.thumbs?.[`${item.kind}:${item.vid}`] ?? null;
      setOwn(o);
      setMade(o ? fileUrl(item.pid, o.file) : null);
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Modal title={`Thumbnail · ${item.title} (${item.kindName})`} onClose={onClose} full>
      <div className="tm">
        <div className="tm-frames">
          <video ref={video} src={item.file ? fileUrl(item.pid, item.file) : undefined} controls muted playsInline preload="metadata"
            onLoadedMetadata={(e) => { if (at !== null) e.currentTarget.currentTime = at; }} />
          <div className="tm-pick">
            <Button size="sm" kind="primary" onClick={() => video.current && setAt(Math.round(video.current.currentTime * 100) / 100)}>
              Use this frame
            </Button>
            <span className="la-note">Play or scrub the video and press this, or pick one of these:</span>
          </div>
          <div className="tm-strip" style={{ gridTemplateColumns: `repeat(${item.shape === "story" ? 8 : 4}, 1fr)` }}>
            {PICKS.map((f) => {
              const t = Math.round(dur * f * 10) / 10;
              return (
                <button key={f} type="button" className={"tm-cand" + (at !== null && Math.abs(at - t) < 0.05 ? " on" : "")}
                  onClick={() => { setAt(t); if (video.current) video.current.currentTime = t; }}>
                  <img src={`${base}?at=${t}&w=320`} alt={`At ${t} s`} loading="lazy" style={{ aspectRatio: `${W} / ${H}` }} />
                </button>
              );
            })}
          </div>
        </div>
        {error && <p className="ie-err">{error}</p>}
        {made && (
          <div className="tm-done">
            <img src={`${made}?v=${Date.now()}`} alt="Your thumbnail" />
            <div>
              <strong>Saved as this video's thumbnail.</strong>
              <p className="la-note">{W} × {H}, ready for {item.shape === "wide" ? "YouTube" : item.shape === "story" ? "Shorts, Reels and TikTok" : "posts"}.</p>
              <a className="btn btn-plain btn-sm" href={made} download={`${item.title} (${item.kindName}) thumbnail.jpg`}>Download it</a>
            </div>
          </div>
        )}
        {brand && look && at !== null && own !== undefined ? (
          <LookEditor picture={`${base}?at=${at}&w=1920`} infoUrl={`${base}/info?at=${at}`} W={W} H={H} look={look}
            title={own?.show.title ?? item.title} artist={own?.show.artist ?? item.artist} logos={brand.logos} words
            saving={busy === "save"} saveLabel={own ? "Save the thumbnail again" : "Save the thumbnail"} onSave={save} onCancel={onClose}
            extra={own ? (
              <div className="lk-group">
                <h4>This video's thumbnail</h4>
                <p className="la-note">Yours, made {new Date(own.at * 1000).toLocaleDateString()}. Without it, the Library shows a frame the app picked.</p>
                <Button size="sm" kind="ghost" busy={busy === "forget"} onClick={async () => {
                  setBusy("forget");
                  try {
                    await api.del(`/api/library/thumb/${item.pid}/${item.kind}/${item.vid}`);
                    setOwn(null);
                    setMade(null);
                    onSaved();
                  } finally {
                    setBusy(null);
                  }
                }}>Go back to the app's</Button>
              </div>
            ) : undefined} />
        ) : <p className="mi-soon">Opening…</p>}
      </div>
    </Modal>
  );
}
