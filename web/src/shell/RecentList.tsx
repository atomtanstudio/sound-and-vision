import { fileUrl } from "../lib/api";
import { linkTo } from "../lib/router";
import type { Project } from "../lib/types";

export type Listed = Project & {
  takeCount: number;
  master: { duration?: number; n: number; status?: string } | null;
};

export function ago(t: number) {
  const s = Date.now() / 1000 - t;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(t * 1000).toLocaleDateString();
}

const len = (d?: number) => (d ? `${Math.floor(d / 60)}:${String(Math.round(d % 60)).padStart(2, "0")}` : "");

/** Songs as cover tiles: the art when there is some, otherwise a tile in the song's colours. */
export function RecentList({ items, limit }: { items: Listed[]; limit?: number }) {
  if (!items.length) return <div className="hm-empty">Nothing here yet. Your songs and videos will gather here.</div>;
  return (
    <ul className="hm-list">
      {items.slice(0, limit ?? items.length).map((p) => (
        <li key={p.id}>
          <a className="hm-item" {...linkTo(`/music/${p.id}`)}>
            {p.cover ? (
              <img className="hm-item-art hm-item-img" src={fileUrl(p.id, p.cover.small || p.cover.file)} alt="" loading="lazy" />
            ) : (
              <span className="hm-item-art" aria-hidden="true">{(p.title || "U").slice(0, 1)}</span>
            )}
            <span className="hm-item-text">
              <strong>{p.title || "Untitled song"}</strong>
              <span>
                {p.master ? `Take ${p.master.n}${p.master.duration ? ` · ${len(p.master.duration)}` : ""}` :
                  p.takeCount ? `${p.takeCount} take${p.takeCount > 1 ? "s" : ""}` : p.title === "New song" ? "Being written…" : "No takes yet"} · {ago(p.updatedAt)}
              </span>
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}
