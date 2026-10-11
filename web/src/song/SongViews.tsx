import { fileUrl } from "../lib/api";
import { go, linkTo } from "../lib/router";
import type { Take } from "../lib/types";
import { ago, type Listed } from "../shell/RecentList";
import { usePlayer } from "../state/player";

const len = (d?: number) => (d ? `${Math.floor(d / 60)}:${String(Math.round(d % 60)).padStart(2, "0")}` : "");
const artistOf = (p: Listed) => p.cover?.artist || p.source?.artist || "";
const status = (p: Listed) => p.master ? `Take ${p.master.n}` : p.takeCount ? `${p.takeCount} take${p.takeCount > 1 ? "s" : ""}` :
  p.title === "New song" ? "Being written…" : "No takes yet";

function Play({ p }: { p: Listed }) {
  const take = p.master as unknown as Take | null;
  const playing = usePlayer((s) => s.playing && s.take?.id === take?.id);
  if (!take || p.master?.status !== "ready") return null;
  return (
    <button type="button" className={"sv-play" + (playing ? " on" : "")} aria-label={playing ? `Pause ${p.title}` : `Play ${p.title}`}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        const pl = usePlayer.getState();
        if (playing) pl.toggle();
        else pl.play(take, p.title);
      }}>
      {playing ? "❚❚" : "▶"}
    </button>
  );
}

/** Songs as album art: the cover big, the title and the artist under it, play on hover. */
export function SongGrid({ items }: { items: Listed[] }) {
  return (
    <ul className="sv-grid">
      {items.map((p) => (
        <li key={p.id}>
          <a className="sv-card" {...linkTo(`/music/${p.id}`)}>
            <span className="sv-art">
              {p.cover ? <img src={fileUrl(p.id, p.cover.small || p.cover.file)} alt="" loading="lazy" /> :
                <span className="sv-noart" aria-hidden="true">{(p.title || "U").slice(0, 1)}</span>}
              <Play p={p} />
            </span>
            <strong>{p.title || "Untitled song"}</strong>
            <span className="sv-sub">{[artistOf(p), p.master?.duration ? len(p.master.duration) : status(p)].filter(Boolean).join(" · ")}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

/** Songs as a list: small art, title and artist, its genres, takes, length and when it last changed. */
export function SongList({ items }: { items: Listed[] }) {
  return (
    <div className="sv-list" role="table" aria-label="Your songs">
      <div className="sv-row sv-row-head" role="row">
        <span role="columnheader" />
        <span role="columnheader">Title</span>
        <span role="columnheader">Style</span>
        <span role="columnheader">Takes</span>
        <span role="columnheader">Length</span>
        <span role="columnheader">Changed</span>
      </div>
      {items.map((p) => (
        <div key={p.id} className="sv-row" role="row" tabIndex={0} onClick={() => go(`/music/${p.id}`)}
          onKeyDown={(e) => e.key === "Enter" && go(`/music/${p.id}`)}>
          <span className="sv-thumb" role="cell">
            {p.cover ? <img src={fileUrl(p.id, p.cover.small || p.cover.file)} alt="" loading="lazy" /> :
              <span className="sv-noart" aria-hidden="true">{(p.title || "U").slice(0, 1)}</span>}
            <Play p={p} />
          </span>
          <span className="sv-name" role="cell"><strong>{p.title || "Untitled song"}</strong>{artistOf(p) && <span>{artistOf(p)}</span>}</span>
          <span className="sv-style" role="cell">{[...(p.genres ?? []), ...(p.moods ?? [])].slice(0, 3).join(", ")}</span>
          <span role="cell">{status(p)}</span>
          <span role="cell" className="sv-num">{len(p.master?.duration)}</span>
          <span role="cell" className="sv-when">{ago(p.updatedAt)}</span>
        </div>
      ))}
    </div>
  );
}
