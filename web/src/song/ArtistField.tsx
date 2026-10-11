import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useHouseArtist } from "../lib/artist";
import type { Project } from "../lib/types";

/** "by …" under a song's title: its own artist, typed in place. Left empty, the song carries your artist name from
 *  Brand (or the one its file came with); the cover's words are set again when it changes. */
export function ArtistField({ project }: { project: Project }) {
  const house = useHouseArtist();
  const fallback = project.cover?.artist || project.source?.artist || house;
  const own = typeof project.artist === "string" ? project.artist : null;
  const [text, setText] = useState(own ?? "");
  const [state, setState] = useState<"idle" | "saving" | "error">("idle");
  useEffect(() => setText(own ?? ""), [own]);
  const save = async () => {
    const next = text.trim();
    if (next === (own ?? "")) return;
    setState("saving");
    try {
      await api.put(`/api/projects/${project.id}/artist`, { artist: next || null });
      setState("idle");
    } catch {
      setState("error");
    }
  };
  return (
    <label className="sp-artist" title="The artist on this song's cover, videos and clips">
      <span>by</span>
      <input value={text} placeholder={fallback ? `${fallback}${!own && !project.cover?.artist && !project.source?.artist ? " (your artist name)" : ""}` : "Add the artist"}
        aria-label="Artist" onChange={(e) => setText(e.target.value)} onBlur={() => void save()}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") { setText(own ?? ""); (e.target as HTMLInputElement).blur(); }
        }} />
      {state === "saving" && <em>Setting the cover's words…</em>}
      {state === "error" && <em className="sp-artist-err">Not saved: try again</em>}
    </label>
  );
}
