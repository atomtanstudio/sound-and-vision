import { useEffect, useState } from "react";
import { api, fileUrl } from "../lib/api";
import { go, linkTo, useQuery } from "../lib/router";
import type { Project, Take } from "../lib/types";
import { BringSong } from "../shell/BringSong";
import { KINDS } from "../shell/Home";
import { Button } from "../ui/controls";
import "../shell/home.css";
import "../song/music-index.css";
import "./video.css";

type Listed = Project & { master?: Take | null; takeCount?: number };

/** Video: choose a song (one with its take chosen), then the kind of video. */
export function VideoPage() {
  const [songs, setSongs] = useState<Listed[] | null>(null);
  const [bringing, setBringing] = useState(false);
  const asked = useQuery("kind");
  const kind = KINDS.find((k) => k.key === asked) ?? null;  // picked first: each song then opens on it
  useEffect(() => {
    void api.get<Listed[]>("/api/projects").then(setSongs).catch(() => setSongs([]));
  }, []);
  const ready = (songs ?? []).filter((p) => p.master?.status === "ready");
  const waiting = (songs ?? []).filter((p) => p.master?.status !== "ready" && (p.takeCount ?? 0) > 0);
  return (
    <main className="hm mi">
      <header className="mi-head">
        <div>
          <h1>Video</h1>
          <p>{kind ? <>Choose a song for its {kind.name}.</> : <>Choose a song, then the kind of video.</>} Each starts from the
            song's chosen take and its cover.</p>
        </div>
        <Button onClick={() => setBringing(true)} title="A song you made in Suno or anywhere else">Bring a song</Button>
      </header>
      {bringing && <BringSong onClose={() => setBringing(false)} />}
      <section className="hm-kinds" aria-label="Kinds of video" style={{ marginTop: 28 }}>
        {KINDS.map((k) => (
          <button key={k.key} type="button" className={"hm-kind" + (kind?.key === k.key ? " on" : "")} aria-pressed={kind?.key === k.key}
            style={{ ["--lane" as string]: `var(${k.color})` }} onClick={() => go(kind?.key === k.key ? "/video" : `/video?kind=${k.key}`, true)}>
            <h3><span className="hm-kind-slash" aria-hidden="true">/</span>{k.name}</h3>
            <p>{k.line}</p>
          </button>
        ))}
      </section>
      <section className="vd-sec">
        <h2>Songs ready for a video</h2>
        {songs && ready.length === 0 && <p className="mi-soon">No song has its take chosen yet: open a song and press “Use this one” on a take.</p>}
        <div className="vd-grid">
          {ready.map((p) => (
            <a key={p.id} className="vd-song" {...linkTo(kind && kind.key !== "living" ? `/video/${p.id}?kind=${kind.key}` : `/video/${p.id}`)}>
              {p.cover ? <img src={fileUrl(p.id, p.cover.small)} alt="" /> : <span className="vd-nocover">No cover yet</span>}
              <strong>{p.title}</strong>
              <span>{p.master?.duration ? `${Math.floor(p.master.duration / 60)}:${String(Math.round(p.master.duration % 60)).padStart(2, "0")}` : ""}
                {(p.living?.renders?.length ?? 0) + (p.kinetic?.videos?.length ?? 0) + (p.music?.videos?.length ?? 0) ? " · has videos" : ""}</span>
            </a>
          ))}
        </div>
        {waiting.length > 0 && (
          <p className="vd-waiting">
            Choose a take first: {waiting.slice(0, 6).map((p, i) => (
              <span key={p.id}>{i ? ", " : ""}<a {...linkTo(`/music/${p.id}`)}>{p.title}</a></span>
            ))}{waiting.length > 6 ? "…" : ""}
          </p>
        )}
      </section>
    </main>
  );
}
