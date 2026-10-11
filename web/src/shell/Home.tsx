import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { go } from "../lib/router";
import type { Project } from "../lib/types";
import { NEW_SONG } from "../state/song";
import { BringSong } from "./BringSong";
import { PromptBox } from "./PromptBox";
import { RecentList, type Listed } from "./RecentList";
import "./home.css";
import { Machine } from "../lib/machine";

/** A row of level bars that rise and fall like a song taking shape. */
function SongBars() {
  return (
    <div className="hm-bars" aria-hidden="true">
      {Array.from({ length: 48 }, (_, i) => (
        <span
          key={i}
          style={{
            ["--h" as string]: (0.25 + 0.75 * Math.abs(Math.sin(i * 0.55) * Math.cos(i * 0.21))).toFixed(3),
            ["--d" as string]: `${(i * 0.045).toFixed(3)}s`,
          }}
        />
      ))}
    </div>
  );
}

/** Words lighting up as a playhead passes over a vocal line: what "we time every word" looks like. */
const WORDS = ["drop", "in", "any", "song", "we", "find", "every", "word"];
function WordSweep() {
  return (
    <div className="hm-sweep" aria-hidden="true">
      <div className="hm-words">
        {WORDS.map((w, i) => (
          <span key={i} style={{ ["--at" as string]: `${(i / WORDS.length) * 100}%`, ["--k" as string]: i }}>
            {w}
          </span>
        ))}
      </div>
      <div className="hm-vocal">
        {Array.from({ length: 64 }, (_, i) => (
          <span key={i} style={{ ["--h" as string]: (0.15 + 0.85 * Math.abs(Math.sin(i * 0.9) * Math.sin(i * 0.13 + 1))).toFixed(3) }} />
        ))}
      </div>
      <span className="hm-playhead" />
    </div>
  );
}

export const KINDS = [
  { key: "living", name: "Living Album Cover", line: "Your cover, gently alive, in up to four loops.", color: "--c-picture" },
  { key: "kinetic", name: "Motion Graphics", line: "A music video designed and written in code by your director model, with your lyrics or without.", color: "--c-graphics" },
  { key: "music", name: "Music Video", line: "Performance, Hybrid (a story with singing) or Surreal: directed by your director model, filmed with MiniMax H3.", color: "--c-video" },
];


export function Home() {
  const [recent, setRecent] = useState<Listed[] | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bringing, setBringing] = useState(false);
  useEffect(() => {
    api.get<Listed[]>("/api/projects").then(setRecent).catch((e) => setError(String(e.message ?? e)));
  }, []);

  async function newSong(e: React.MouseEvent) {
    e.preventDefault();
    if (starting) return;
    setStarting(true);
    try {
      const p = await api.post<Project>("/api/projects", { title: "Untitled song", doc: NEW_SONG });
      go(`/music/${p.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStarting(false);
    }
  }

  return (
    <main className="hm">
      <section className="hm-hero">
        <h1>What are we making?</h1>
        <PromptBox />
      </section>

      <section className="hm-doors" aria-label="Start">
        <a className={"hm-door" + (starting ? " hm-starting" : "")} href="/new/song" onClick={newSong} style={{ ["--lane" as string]: "var(--c-song)" }}>
          <SongBars />
          <div className="hm-door-text">
            <h2>Make a song, in detail</h2>
            <p>Every choice in your hands: the words, the sound, influences, and each model's own settings.</p>
          </div>
          <span className="hm-go" aria-hidden="true">
            →
          </span>
        </a>
        <a className="hm-door" href="/video" onClick={(e) => { e.preventDefault(); setBringing(true); }} style={{ ["--lane" as string]: "var(--c-sound)" }}>
          <WordSweep />
          <div className="hm-door-text">
            <h2>Make a video for a song I have</h2>
            <p>Drop in any song. We find the words, the beat and the stems, then make the video.</p>
          </div>
          <span className="hm-go" aria-hidden="true">
            →
          </span>
        </a>
      </section>
      {bringing && <BringSong onClose={() => setBringing(false)} />}

      <section className="hm-recent" aria-label="Recent">
        <h2>Recent</h2>
        {error && <div className="hm-empty">{Machine()} isn't answering: {error}</div>}
        {recent && <RecentList items={recent} />}
      </section>
    </main>
  );
}
