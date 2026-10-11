// The demo show: what a freshly seeded film renders before its own show is written. On a dark field each lyric line
// is set word by word, every word landing on its cue frame (analysis/analysis.json); a thin rule answers the drums;
// any H3 plate (plates/) that covers the moment is drawn behind the words. It exists so a new film renders something
// correct out of the box. Replace it: build() returns the Timeline of the real film's scenes.
import { Timeline } from './engine/timeline.js';
import * as Type from './engine/type.js';
import { sp, sat } from './engine/math.js';

/** Faces this show uses (keys of FONT_FILES in engine/type.js); only these are loaded. */
export const FONTS = ['archivo'];

const FACE = { font: 'archivo', vars: { wght: 780, wdth: 100 } };
const FIELD = '#0d0d11', INK = '#ebe5d9', LIT = '#f0b84a';
const LAND = { k: 420, d: 41 };          // critically damped: a word drops into place with no overshoot
const HOLD = 1.0;                        // a line stays this long after its last word ends, unless the next one starts

/** Words of a line set left-aligned on the safe area, wrapped into at most three rows. Cached per line and frame size. */
export function layout(line, W, H, caps) {
  const mx = W * 0.06, width = W - 2 * mx;
  const words = line.words.map((w) => (caps ? w.w.toUpperCase() : w.w));
  let size = Math.min(W, H) * 0.13, rows;
  for (;;) {
    const space = size * 0.28;
    rows = [[]];
    let x = 0;
    words.forEach((str, i) => {
      const wd = Type.line(str, { ...FACE, size }).width;
      if (x > 0 && x + wd > width) { rows.push([]); x = 0; }
      rows[rows.length - 1].push({ i, str, x, wd });
      x += wd + space;
    });
    if (rows.length <= 3 || size < Math.min(W, H) * 0.045) break;
    size *= 0.92;
  }
  const lead = size * 1.12, cap = Type.fontInfo(FACE.font).cap * size;
  const top = H * 0.5 - ((rows.length - 1) * lead + cap) / 2 + cap;     // block centred on the frame's middle
  const placed = [];
  rows.forEach((row, r) => row.forEach((p) => placed.push({ ...p, x: mx + p.x, y: top + r * lead })));
  const right = Math.max(...placed.map((p) => p.x + p.wd));
  return { size, words: placed, x0: mx, x1: right, bottom: top + (rows.length - 1) * lead };
}

export async function build(E, opts = {}) {
  const S = E.song, tl = new Timeline();
  const caps = !!(opts.meta && opts.meta.look && opts.meta.look.caps);
  const lines = S.lineList;
  const exits = lines.map((l, i) => Math.min(i + 1 < lines.length ? lines[i + 1].start : Infinity, l.end + HOLD));
  const cache = new Map();

  const lyrics = {
    id: 'lyrics',
    render(f) {
      const t = f.t, W = f.W, H = f.H;
      f.clear(FIELD);
      // a plate behind the words, held down so the type reads
      const under = E.plates ? E.plates.covering(t) : [];
      if (under.length) {
        f.canvas((ctx) => { E.plates.draw(ctx, under[0], t); });
        f.canvas((ctx) => { ctx.fillStyle = 'rgba(8,8,12,0.55)'; ctx.fillRect(0, 0, W, H); });
      }
      let li = -1;
      for (let i = 0; i < lines.length; i++) if (t >= lines[i].start && t < exits[i]) li = i;
      const hit = S.pulse('hit', t, 0.11, 0.3);
      f.canvas((ctx) => {
        let x0 = W * 0.06, x1 = W * 0.3, y = H * 0.5 + 10;
        if (li >= 0) {
          const line = lines[li], key = `${line.id}|${W}x${H}`;
          if (!cache.has(key)) cache.set(key, layout(line, W, H, caps));
          const L = cache.get(key);
          let cur = -1;
          for (const w of line.words) if (t >= w.t) cur = w.i;
          const after = t >= line.words[line.words.length - 1].end;
          for (const p of L.words) {
            const w = line.words[p.i];
            if (t < w.t) continue;                                  // not sung yet: not on screen
            const k = sp(t - w.t, LAND);
            ctx.save();
            ctx.translate(0, (1 - k) * L.size * 0.1);
            Type.text(ctx, p.str, p.x, p.y, { ...FACE, size: L.size, fill: p.i === cur && !after ? LIT : INK });
            ctx.restore();
          }
          x0 = L.x0; x1 = L.x1; y = L.bottom + L.size * 0.32;
        }
        // the rule under the block answers the drums: it stretches on every hit and settles back
        ctx.fillStyle = LIT;
        ctx.globalAlpha = 0.35 + 0.65 * hit;
        ctx.fillRect(x0, y, (x1 - x0) * (0.18 + 0.82 * sat(hit)), Math.max(3, H * 0.005));
      });
      f.post({ bloom: 0.12, bloomThreshold: 0.8, ca: 0.0015, grain: 0.03, vignette: 0.3, vigSoft: 0.4 });
    },
  };
  tl.add(lyrics, -1, Math.max(S.duration, S.musicEnd) + 1);
  return tl;
}
