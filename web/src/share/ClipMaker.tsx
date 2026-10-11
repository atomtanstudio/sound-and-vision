import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, fileUrl } from "../lib/api";
import type { Item } from "../library/LibraryPage";
import { useQuery } from "../lib/router";
import type { Listed } from "../shell/RecentList";
import { Button, Segmented, Slider } from "../ui/controls";
import { machine } from "../lib/machine";

interface Preset { name: string; size: [number, number]; most: number; best: number }
interface Moment { start: number; end: number; why: string }
interface Moments {
  duration: number;
  seconds: number;
  moments: Moment[];
  bars: number[];
  sections: { label: string; start: number; end: number }[];
  lines: { start: number; end: number }[];
  level: number[];
  levelRate: number;
}
export interface Clip {
  id: string; pid: string; title: string; preset: string; presetName: string; file: string; poster: string;
  size: [number, number]; start: number; end: number; seconds: number; bytes: number; at: number; captions: boolean;
}

const t = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const ORDER = ["tiktok", "reels", "shorts", "portrait", "square", "wide"];

/** Make a clip for social: a song (or one of its videos), the place it's going, the best moment, the frame, what's
 *  laid on it, and the sound levelled for the platforms. The picture on the right is the clip exactly as it'll be. */
export function ClipMaker() {
  const [presets, setPresets] = useState<Record<string, Preset>>({});
  const [songs, setSongs] = useState<Listed[]>([]);
  const [loaded, setLoaded] = useState(false);
  const wanted = useQuery("song");  // ?song=<id>&video=<key>: opened from a song or a video
  const wantedVideo = useQuery("video");
  const [items, setItems] = useState<Item[]>([]);
  const [pid, setPid] = useState("");
  const [source, setSource] = useState("cover");
  const [preset, setPreset] = useState("tiktok");
  const [length, setLength] = useState(30);
  const [moments, setMoments] = useState<Moments | null>(null);
  const [start, setStart] = useState(0);
  const [frame, setFrame] = useState<"blur" | "fill" | "bars">("blur");
  const [focus, setFocus] = useState(0.5);
  const [words, setWords] = useState(true);
  const [logos, setLogos] = useState(true);
  const [captions, setCaptions] = useState(false);
  const [level, setLevel] = useState(true);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [clips, setClips] = useState<Clip[]>([]);
  const [job, setJob] = useState<{ id: string; message?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const [listening, setListening] = useState(false);

  const loadClips = useCallback(() => api.get<Clip[]>("/api/share/clips").then(setClips).catch(() => undefined), []);
  useEffect(() => {
    void api.get<{ presets: Record<string, Preset> }>("/api/share/presets").then((r) => setPresets(r.presets));
    void api.get<Listed[]>("/api/projects").then((ps) => {
      const ready = ps.filter((p) => p.master?.status === "ready").sort((a, b) => b.updatedAt - a.updatedAt);
      setSongs(ready);
      setLoaded(true);
      setPid((x) => x || (ready.some((p) => p.id === wanted) ? wanted! : ready[0]?.id) || "");
    }).catch(() => setLoaded(true));
    void api.get<{ items: Item[] }>("/api/library").then((l) => setItems(l.items));
    void loadClips();
  }, [loadClips]);

  const song = songs.find((s) => s.id === pid);
  const videos = useMemo(() => items.filter((i) => i.pid === pid && i.type === "video" && i.kind !== "clip"), [items, pid]);
  const src = videos.find((v) => v.key === source);
  const P = presets[preset];
  // where in the song the chosen video runs (a video of a part of the song starts there)
  const from = src?.part?.start ?? 0;
  const until = src ? from + (src.seconds ?? 0) : moments?.duration ?? 600;
  const most = Math.min(P?.most ?? 60, Math.floor(until - from));
  // a new song: its newest video, or its cover; a living cover already carries its title and logos
  useEffect(() => {
    if (!pid) return;
    const v = videos.find((x) => x.key === wantedVideo) ?? videos[0];
    setSource(v ? v.key : "cover");
  }, [pid, videos, wantedVideo]);
  useEffect(() => {
    if (src?.kind === "living") setWords(false);
  }, [src?.kind]);
  useEffect(() => {
    if (!pid) return;
    let live = true;
    const id = window.setTimeout(() => {
      api.get<Moments>(`/api/share/moments/${pid}?seconds=${length}${src?.seconds ? `&upto=${until}&since=${from}` : ""}`).then((m) => {
        if (!live) return;
        setMoments(m);
        const fits = m.moments.filter((x) => !src?.seconds || (x.start >= from - 0.5 && x.end <= until + 0.5));
        setStart(fits[0]?.start ?? from);
      }).catch((e) => live && setError(e instanceof ApiError ? e.message : String(e)));
    }, 250);
    return () => { live = false; window.clearTimeout(id); };
  }, [pid, length, src?.seconds, from, until]);
  useEffect(() => { if (P && length > most) setLength(Math.max(5, Math.min(P.best, most))); }, [P, most, length]);

  const end = Math.min(start + length, src ? until : moments?.duration ?? start + length);
  const body = useMemo(() => ({
    preset, start, end, frame, focus, words, logos, captions, level,
    source: src ? { type: "video", kind: src.kind, vid: src.vid } : { type: "cover" },
  }), [preset, start, end, frame, focus, words, logos, captions, level, src]);

  // the exact picture, a moment after each change
  useEffect(() => {
    if (!pid || !moments) return;
    let live = true;
    const id = window.setTimeout(async () => {
      setPreviewing(true);
      try {
        const r = await fetch(`/api/share/preview/${pid}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        if (!r.ok) throw new ApiError((await r.json().catch(() => ({}))).detail || "The preview didn't come.", r.status);
        const url = URL.createObjectURL(await r.blob());
        if (live) setPreview((old) => { if (old) URL.revokeObjectURL(old); return url; });
        if (live) setError(null);
      } catch (e) {
        if (live) setError(e instanceof ApiError ? e.message : "The preview didn't come.");
      } finally {
        if (live) setPreviewing(false);
      }
    }, 450);
    return () => { live = false; window.clearTimeout(id); };
  }, [pid, body, moments]);

  // a job: follow it until it's done, then the clip shows in the list
  useEffect(() => {
    if (!job) return;
    const id = window.setInterval(async () => {
      const js = await api.get<{ id: string; message?: string }[]>("/api/jobs").catch(() => null);
      if (!js) return;
      const mine = js.find((j) => j.id === job.id);
      if (mine) return setJob(mine);
      // gone from the live list: done, or failed (then say why)
      const end = await api.get<{ status: string; message?: string; error?: string }>(`/api/jobs/${job.id}`).catch(() => null);
      setJob(null);
      if (end && (end.status === "failed" || end.status === "cancelled")) {
        setError(end.status === "cancelled" ? "The clip was stopped." : `The clip didn't work: ${end.message || end.error || "something went wrong"}`);
      }
      void loadClips();
    }, 2000);
    return () => window.clearInterval(id);
  }, [job, loadClips]);

  const listen = () => {
    const a = audio.current;
    const take = song?.master as unknown as { files?: { audio: string }; projectId: string } | null;
    if (!a || !take?.files) return;
    if (listening) {
      a.pause();
      setListening(false);
      return;
    }
    a.src = fileUrl(pid, take.files.audio);
    a.currentTime = start;
    void a.play();
    setListening(true);
  };
  useEffect(() => {
    const a = audio.current;
    if (!a) return;
    const tick = () => { if (a.currentTime >= end) { a.pause(); setListening(false); } };
    a.addEventListener("timeupdate", tick);
    return () => a.removeEventListener("timeupdate", tick);
  }, [end]);

  const make = async () => {
    setError(null);
    try {
      const j = await api.post<{ id: string; message?: string }>(`/api/share/clips/${pid}`, body);
      setJob(j);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    }
  };

  if (!loaded) return <p className="mi-soon">Opening your songs…</p>;
  if (!songs.length) return <p className="mi-soon">Choose a take for a song first: clips are made from a song's chosen take.</p>;
  return (
    <div className="sh">
      <div className="sh-form">
        <section className="sh-step">
          <h3><span>1</span> What</h3>
          <select className="in" value={pid} onChange={(e) => setPid(e.target.value)} aria-label="Song">
            {songs.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select>
          <div className="sh-sources" role="radiogroup" aria-label="Picture">
            {videos.map((v) => (
              <button key={v.key} type="button" role="radio" aria-checked={source === v.key} className={"sh-src" + (source === v.key ? " on" : "")}
                onClick={() => setSource(v.key)} title={`${v.kindName}${v.opening ? " (opening)" : ""} · ${t(v.seconds ?? 0)}`}>
                <img src={v.thumb} alt="" style={{ aspectRatio: `${v.aspect}` }} />
                <span>{v.kindName}{v.opening ? " · opening" : ""}</span>
              </button>
            ))}
            {song?.cover && (
              <button type="button" role="radio" aria-checked={source === "cover"} className={"sh-src" + (source === "cover" ? " on" : "")}
                onClick={() => setSource("cover")}>
                <img src={fileUrl(song.id, song.cover.small)} alt="" style={{ aspectRatio: "1" }} />
                <span>The cover, moving in</span>
              </button>
            )}
          </div>
        </section>

        <section className="sh-step">
          <h3><span>2</span> Where it's going</h3>
          <div className="sh-presets">
            {ORDER.filter((k) => presets[k]).map((k) => {
              const [w, h] = presets[k].size;
              return (
                <button key={k} type="button" className={"sh-preset" + (preset === k ? " on" : "")} aria-pressed={preset === k}
                  onClick={() => { setPreset(k); setLength(Math.min(presets[k].best, Math.floor(src?.seconds ?? 600))); }}>
                  <i style={{ aspectRatio: `${w} / ${h}` }} />
                  <span>{presets[k].name}</span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="sh-step">
          <h3><span>3</span> The moment</h3>
          <Slider label="Length" value={length} min={5} max={Math.max(6, most)} step={1} onChange={setLength} format={(v) => `${v} s`} />
          {moments && (
            <>
              <div className="sh-moments">
                {moments.moments.filter((m) => !src?.seconds || m.end <= src.seconds + 0.5).map((m) => (
                  <button key={m.start} type="button" className={"sh-moment" + (Math.abs(m.start - start) < 0.05 ? " on" : "")} onClick={() => setStart(m.start)}>
                    <strong>{t(m.start)}–{t(m.end)}</strong>
                    <span>{m.why}</span>
                  </button>
                ))}
              </div>
              <Timeline m={moments} start={start} length={end - start} from={from} limit={src ? until : moments.duration} onStart={setStart} />
              <div className="sh-row">
                <Button size="sm" onClick={listen}>{listening ? "❚❚ Stop" : "▶ Listen to it"}</Button>
                <span className="la-note">{t(start)} to {t(end)} · drag the window, or pick a suggestion. It starts on a bar.</span>
              </div>
            </>
          )}
          <audio ref={audio} preload="none" />
        </section>

        <section className="sh-step">
          <h3><span>4</span> The frame and what's on it</h3>
          <Segmented size="sm" label="Frame" value={frame} onChange={setFrame} options={[
            { value: "blur", label: "Fit, blurred behind", hint: "The whole picture, over a soft blurred copy of itself" },
            { value: "fill", label: "Fill", hint: "Cropped to fill the frame" },
            { value: "bars", label: "Fit, black bars" }]} />
          {frame === "fill" && <Slider label="Keep in view" value={focus} min={0} max={1} step={0.01} onChange={setFocus}
            format={(v) => (v < 0.34 ? "the left" : v > 0.66 ? "the right" : "the middle")} />}
          <div className="sh-checks">
            <label><input type="checkbox" checked={words} onChange={(e) => setWords(e.target.checked)} /> The title and artist</label>
            <label><input type="checkbox" checked={logos} onChange={(e) => setLogos(e.target.checked)} /> Your logos</label>
            <label title={moments?.lines.length ? "" : "This song has no sung words"}>
              <input type="checkbox" checked={captions} disabled={!moments?.lines.length} onChange={(e) => setCaptions(e.target.checked)} /> Captions (the sung words)
            </label>
            <label><input type="checkbox" checked={level} onChange={(e) => setLevel(e.target.checked)} /> Sound levelled for social (−14 LUFS)</label>
          </div>
          {src?.kind === "living" && words && <p className="la-note">A living cover already shows its title: you may not want it twice.</p>}
        </section>

        <div className="sh-go">
          <Button kind="primary" size="lg" busy={!!job} disabled={!!job || !P} onClick={() => void make()}>
            {job ? (job.message || "Making it") : `Make the ${P?.name ?? ""} clip`}
          </Button>
          {error && <p className="ie-err">{error}</p>}
        </div>
      </div>

      <aside className="sh-preview">
        <div className={"sh-frame" + (previewing ? " busy" : "")} style={{ aspectRatio: P ? `${P.size[0]} / ${P.size[1]}` : "9 / 16" }}>
          {preview ? <img src={preview} alt="The clip, a moment in" /> : <span>The clip shows here</span>}
        </div>
        <p className="la-note">{P ? `${P.size[0]} × ${P.size[1]}` : ""} · exactly as it will be made, at the middle of the moment.</p>
      </aside>

      <section className="sh-clips">
        <h2>Your clips</h2>
        {!clips.length ? <p className="mi-soon">The clips you make gather here, ready to download and post.</p> : (
          <div className="sh-cliplist">
            {clips.map((c) => (
              <div key={c.id} className="sh-clip">
                <a href={fileUrl(c.pid, c.file)} target="_blank" rel="noreferrer" className="sh-clip-pic" style={{ aspectRatio: `${c.size[0]} / ${c.size[1]}` }}>
                  <img src={fileUrl(c.pid, c.poster)} alt="" loading="lazy" />
                  <span className="lib-len">{Math.round(c.seconds)} s</span>
                </a>
                <strong>{c.title}</strong>
                <span>{c.presetName} · {t(c.start)}–{t(c.end)}</span>
                <div className="sh-row">
                  <a className="btn btn-plain btn-sm" href={fileUrl(c.pid, c.file)} download={`${c.title} (${c.presetName}).mp4`}>Download</a>
                  <Button size="sm" kind="ghost" onClick={async () => {
                    if (!confirm("Delete this clip?")) return;
                    await api.del(`/api/share/clips/${c.pid}/${c.id}`);
                    void loadClips();
                  }}>Delete</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

/** The song as a strip: how loud it is, its sections, where the voice is, and the clip's window (drag it). */
function Timeline({ m, start, length, from = 0, limit, onStart }: { m: Moments; start: number; length: number; from?: number; limit: number; onStart: (s: number) => void }) {
  const ref = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x0: number; s0: number } | null>(null);
  const D = m.duration;
  const snap = (s: number) => {
    const max = Math.max(from, Math.min(D, limit) - length);
    const clamped = Math.min(max, Math.max(from, s));
    const bar = m.bars.reduce((best, b) => (Math.abs(b - clamped) < Math.abs(best - clamped) && b <= max && b >= from ? b : best), from);
    return Math.abs(bar - clamped) < 3 ? bar : clamped;
  };
  const toTime = (clientX: number) => {
    const r = ref.current!.getBoundingClientRect();
    return ((clientX - r.left) / r.width) * D;
  };
  const W = 1000;
  const x = (s: number) => (s / D) * W;
  return (
    <svg ref={ref} className="sh-time" viewBox={`0 0 ${W} 70`} preserveAspectRatio="none" role="slider"
      aria-label="Where the clip starts" aria-valuemin={0} aria-valuemax={D} aria-valuenow={start} tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") onStart(snap(start - (e.shiftKey ? 10 : 1)));
        if (e.key === "ArrowRight") onStart(snap(start + (e.shiftKey ? 10 : 1)));
      }}
      onPointerDown={(e) => {
        const at = toTime(e.clientX);
        if (at < start || at > start + length) onStart(snap(at - length / 2));
        drag.current = { x0: e.clientX, s0: at < start || at > start + length ? snap(at - length / 2) : start };
        (e.target as Element).setPointerCapture?.(e.pointerId);
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d) return;
        const r = ref.current!.getBoundingClientRect();
        onStart(Math.min(Math.max(from, Math.min(D, limit) - length), Math.max(from, d.s0 + ((e.clientX - d.x0) / r.width) * D)));
      }}
      onPointerUp={() => { if (drag.current) onStart(snap(start)); drag.current = null; }}>
      {m.sections.map((s, i) => (
        <g key={i}>
          <rect x={x(s.start)} y={0} width={Math.max(0, x(s.end) - x(s.start))} height={70} className={i % 2 ? "sec b" : "sec"} />
          {s.label && <text x={x(s.start) + 4} y={11} className="lab">{s.label}</text>}
        </g>
      ))}
      {m.level.map((v, i) => {
        const at = i / m.levelRate;
        const w = W / m.level.length;
        return <rect key={i} x={x(at)} y={62 - v * 44} width={Math.max(0.6, w * 0.8)} height={v * 44} className="lvl" />;
      })}
      {m.lines.map((l, i) => <rect key={i} x={x(l.start)} y={65} width={Math.max(1, x(l.end) - x(l.start))} height={3} className="voice" />)}
      {limit < D && <rect x={x(limit)} y={0} width={W - x(limit)} height={70} className="past" />}
      <rect x={x(start)} y={1} width={x(length)} height={68} className="win" rx={4} />
    </svg>
  );
}
