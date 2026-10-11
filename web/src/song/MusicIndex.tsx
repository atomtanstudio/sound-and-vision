import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { go } from "../lib/router";
import type { Project } from "../lib/types";
import type { Listed } from "../shell/RecentList";
import { NEW_SONG } from "../state/song";
import { Button, Segmented } from "../ui/controls";
import { SongGrid, SongList } from "./SongViews";
import "../shell/home.css";
import "./music-index.css";
import { machine } from "../lib/machine";

type View = "grid" | "list";
const saved = (): View => {
  try {
    return localStorage.getItem("sv.music.view") === "list" ? "list" : "grid";
  } catch {
    return "grid";
  }
};

/** Music: start a song with every control, or open one you've made (as album art, or as a list). */
export function MusicIndex() {
  const [songs, setSongs] = useState<Listed[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>(saved);
  const [q, setQ] = useState("");
  useEffect(() => {
    api.get<Listed[]>("/api/projects").then(setSongs).catch(() => setSongs([]));
  }, []);
  useEffect(() => {
    try { localStorage.setItem("sv.music.view", view); } catch { /* fine */ }
  }, [view]);
  const shown = useMemo(() => {
    const words = q.trim().toLowerCase();
    return (songs ?? []).filter((p) => !words || `${p.title} ${p.cover?.artist ?? ""} ${(p.genres ?? []).join(" ")} ${(p.moods ?? []).join(" ")}`
      .toLowerCase().includes(words));
  }, [songs, q]);
  async function start() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const p = await api.post<Project>("/api/projects", { title: "Untitled song", doc: NEW_SONG });
      go(`/music/${p.id}`);
    } catch {
      setBusy(false);
      setError(`The new song didn't start: ${machine()} didn't answer. Try again.`);
    }
  }
  return (
    <main className="hm mi mi-wide">
      <header className="mi-head">
        <div>
          <h1>Music</h1>
          <p>Write a song with every control: the words, the sound, influences, the model and its exact settings.</p>
        </div>
        <Button kind="primary" size="lg" busy={busy} disabled={busy} onClick={start}>Start a new song</Button>
      </header>
      {error && <p className="ie-err">{error}</p>}
      <section className="hm-recent">
        <div className="mi-bar">
          <h2>Your songs{songs ? <span className="mi-count">{songs.length}</span> : null}</h2>
          <div className="mi-tools">
            <input className="in mi-search" type="search" placeholder="Search titles, artists, styles…" value={q} onChange={(e) => setQ(e.target.value)} />
            <Segmented size="sm" label="View" value={view} onChange={setView}
              options={[{ value: "grid", label: "▦ Covers" }, { value: "list", label: "☰ List" }]} />
          </div>
        </div>
        {songs && !songs.length && <div className="hm-empty">No songs yet. Start one above, or bring one in from the Video page.</div>}
        {songs && songs.length > 0 && !shown.length && <div className="hm-empty">No song matches “{q}”.</div>}
        {shown.length > 0 && (view === "grid" ? <SongGrid items={shown} /> : <SongList items={shown} />)}
      </section>
    </main>
  );
}
