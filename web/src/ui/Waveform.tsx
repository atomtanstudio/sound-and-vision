import { useEffect, useRef, useState } from "react";
import { clock } from "../state/player";
import { useTheme } from "./theme";

export interface Peaks {
  rate: number;
  min: number[];
  max: number[];
  rms?: number[];
}

const cache = new Map<string, Promise<Peaks>>();
export function loadPeaks(url: string): Promise<Peaks> {
  if (!cache.has(url)) cache.set(url, fetch(url).then((r) => r.json()));
  return cache.get(url)!;
}

/**
 * A take's waveform on a canvas: the true min and max of the samples under each pixel (so it
 * never aliases when zoomed out), the played part lit, and click or drag to move the playhead.
 * `active` ties it to the shared player; otherwise a click asks to start playing from there.
 */
export function Waveform({
  url,
  duration,
  active,
  color = "var(--c-song)",
  height = 56,
  onSeek,
}: {
  url: string;
  duration: number;
  active: boolean;
  color?: string;
  height?: number;
  onSeek: (t: number) => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [peaks, setPeaks] = useState<Peaks | null>(null);
  const [width, setWidth] = useState(0);
  const theme = useTheme(); // colours are read from CSS, so redraw when the theme changes

  useEffect(() => {
    let live = true;
    loadPeaks(url).then((p) => live && setPeaks(p));
    return () => {
      live = false;
    };
  }, [url]);

  useEffect(() => {
    const el = ref.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const cv = ref.current;
    if (!cv || !peaks || !width) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = width * dpr;
    cv.height = height * dpr;
    const ctx = cv.getContext("2d")!;
    const css = getComputedStyle(cv);
    const lit = css.getPropertyValue("--wf-lit").trim() || "#4ade80";
    const dim = css.getPropertyValue("--wf-dim").trim() || "#555";
    const n = peaks.min.length;
    const bars = Math.floor(width / 3);
    const lo = new Float32Array(bars);
    const hi = new Float32Array(bars);
    const loud = new Float32Array(bars);
    for (let b = 0; b < bars; b++) {
      const a = Math.floor((b / bars) * n);
      const z = Math.max(a + 1, Math.floor(((b + 1) / bars) * n));
      let mn = 0;
      let mx = 0;
      let sq = 0;
      for (let i = a; i < z; i++) {
        if (peaks.min[i] < mn) mn = peaks.min[i];
        if (peaks.max[i] > mx) mx = peaks.max[i];
        if (peaks.rms) sq += peaks.rms[i] * peaks.rms[i];
      }
      lo[b] = mn / 127;
      hi[b] = mx / 127;
      loud[b] = peaks.rms ? Math.sqrt(sq / (z - a)) / 127 : 0;
    }
    const draw = (t: number) => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      const mid = height / 2;
      const played = active && duration ? (t / duration) * width : -1;
      for (let b = 0; b < bars; b++) {
        const x = b * 3;
        const top = Math.max(1, hi[b] * mid * 0.95);
        const bot = Math.max(1, -lo[b] * mid * 0.95);
        const on = x < played;
        if (peaks.rms) {
          // the peaks as a faint outline, the loudness solid inside it
          ctx.globalAlpha = on ? 0.38 : 0.3;
          ctx.fillStyle = on ? lit : dim;
          ctx.beginPath();
          ctx.roundRect(x, mid - top, 2, top + bot, 1);
          ctx.fill();
          ctx.globalAlpha = 1;
          const r = Math.max(1, loud[b] * mid * 0.95);
          ctx.beginPath();
          ctx.roundRect(x, mid - r, 2, r * 2, 1);
          ctx.fill();
        } else {
          ctx.fillStyle = on ? lit : dim;
          ctx.beginPath();
          ctx.roundRect(x, mid - top, 2, top + bot, 1);
          ctx.fill();
        }
      }
      if (played >= 0) {
        ctx.fillStyle = css.getPropertyValue("--text").trim() || "#fff";
        ctx.fillRect(Math.round(played), 0, 1.5, height);
      }
    };
    draw(active ? clock.now() : 0);
    if (!active) return;
    return clock.onFrame(draw);
  }, [peaks, width, height, active, duration, theme]);

  const seekAt = (e: React.PointerEvent) => {
    const r = e.currentTarget.getBoundingClientRect();
    onSeek(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * duration);
  };

  return (
    <div className="wf" style={{ height, ["--wf-lit" as string]: color }}>
      <canvas
        ref={ref}
        style={{ width: "100%", height }}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          seekAt(e);
        }}
        onPointerMove={(e) => {
          if (e.buttons === 1) seekAt(e);
        }}
      />
      {!peaks && <div className="wf-wait" />}
    </div>
  );
}
