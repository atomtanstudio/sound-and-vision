import { useEffect, useRef, useState } from "react";
import { clock, usePlayer } from "../state/player";
import { PauseIcon, PlayIcon } from "../song/Takes";
import "./playerbar.css";

const fmt = (s: number) => (isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "–:––");

/** Always at the bottom once something has played: what's playing, where, and play/pause (space bar). */
export function PlayerBar() {
  const p = usePlayer();
  const [t, setT] = useState(0);
  const bar = useRef<HTMLDivElement>(null);

  useEffect(() => clock.onFrame((now) => setT((prev) => (Math.abs(prev - now) > 0.2 ? now : prev))), []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (e.code !== "Space" || el.closest("input, textarea, select, button, [contenteditable]")) return;
      e.preventDefault();
      usePlayer.getState().toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    // the page leaves room at the bottom for the bar (the Make panel's button stays clear of it)
    document.documentElement.toggleAttribute("data-player", !!p.take);
  }, [p.take]);

  if (!p.take) return null;
  const dur = p.duration || p.take.duration || 0;
  return (
    <div className="pb" role="region" aria-label="Player">
      <button type="button" className="pb-play" onClick={p.toggle} aria-label={p.playing ? "Pause" : "Play"}>
        {p.playing ? <PauseIcon /> : <PlayIcon />}
      </button>
      <div className="pb-what">
        <strong>{p.title || "Untitled song"}</strong>
        <span className={p.error ? "pb-err" : undefined} title={p.error ?? undefined}>
          {p.error ? "Couldn't load the audio. Press play to try again." :
            `Take ${p.take.n}${p.source !== "mix" ? ` · ${p.source === "instrumental" ? "no vocals" : p.source} only` : ""}`}
        </span>
      </div>
      <span className="pb-time">{fmt(t)}</span>
      <div
        ref={bar}
        className="pb-bar"
        onPointerDown={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          p.seek(((e.clientX - r.left) / r.width) * dur);
        }}
      >
        <span style={{ width: `${dur ? Math.min(100, (t / dur) * 100) : 0}%` }} />
      </div>
      <span className="pb-time">{fmt(dur)}</span>
    </div>
  );
}
