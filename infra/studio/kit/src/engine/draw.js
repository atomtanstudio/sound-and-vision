// 2D drawing vocabulary shared by the scenes: rings, rules, arrows, labels, text on arcs, poster stacks.
import * as Type from './type.js';
import { TAU, clamp, lerp, sat, noise1 } from './math.js';

/** Default inks for the helpers below; pass your film's own colours instead. */
export const P = { ink: '#15131a', bone: '#f4ecd8' };

// 16:9 design space + safe margin. For 9:16 or 1:1 use f.W / f.H (the design space is always 1080 on its short side).
export const W = 1920, H = 1080, CX = 960, CY = 540, M = 90;

/** Fill the whole layer, whatever the aspect and the current transform. */
export function fill(ctx, color) { ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = color; ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height); ctx.restore(); }

/** Ring with outer radius r and stroke thickness w (drawn inside the radius). */
export function ring(ctx, x, y, r, w, color, a0 = 0, a1 = TAU) {
  if (r <= 0 || w <= 0) return;
  const ww = Math.min(w, r);
  ctx.save();
  ctx.strokeStyle = color; ctx.lineWidth = ww;
  ctx.beginPath(); ctx.arc(x, y, r - ww / 2, a0, a1); ctx.stroke();
  ctx.restore();
}
export function disc(ctx, x, y, r, color) {
  if (r <= 0) return;
  ctx.save(); ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fill(); ctx.restore();
}
/** Straight rule, optionally trimmed: draws from p0..p1 (0..1) of its length. */
export function rule(ctx, x0, y0, x1, y1, w, color, p0 = 0, p1 = 1, cap = 'butt') {
  if (p1 <= p0) return;
  ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = w; ctx.lineCap = cap;
  ctx.beginPath(); ctx.moveTo(lerp(x0, x1, p0), lerp(y0, y1, p0)); ctx.lineTo(lerp(x0, x1, p1), lerp(y0, y1, p1)); ctx.stroke(); ctx.restore();
}
export function rect(ctx, x, y, w, h, color) { ctx.save(); ctx.fillStyle = color; ctx.fillRect(x, y, w, h); ctx.restore(); }

export function capsulePath(ctx, x, y, w, h) {
  const r = Math.min(w, h) / 2;
  ctx.beginPath();
  ctx.roundRect(x - w / 2, y - h / 2, w, h, r);
}
/** Two-tone capsule (pill) centred at x,y; length w, thickness h, rotation rot. */
export function pill(ctx, x, y, w, h, rot, colA, colB, split = 0.5) {
  ctx.save();
  ctx.translate(x, y); ctx.rotate(rot);
  capsulePath(ctx, 0, 0, w, h); ctx.clip();
  ctx.fillStyle = colA; ctx.fillRect(-w / 2, -h / 2, w * split, h);
  ctx.fillStyle = colB; ctx.fillRect(-w / 2 + w * split, -h / 2, w * (1 - split), h);
  ctx.restore();
}

export function arrow(ctx, x0, y0, x1, y1, { w = 4, head = 22, color = P.ink, p = 1 } = {}) {
  if (p <= 0) return;
  const ex = lerp(x0, x1, p), ey = lerp(y0, y1, p);
  const a = Math.atan2(y1 - y0, x1 - x0);
  ctx.save(); ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = w; ctx.lineCap = 'butt'; ctx.lineJoin = 'miter';
  ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(ex - Math.cos(a) * head * 0.6, ey - Math.sin(a) * head * 0.6); ctx.stroke();
  ctx.translate(ex, ey); ctx.rotate(a);
  ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(-head, -head * 0.5); ctx.lineTo(-head, head * 0.5); ctx.closePath(); ctx.fill();
  ctx.restore();
}

/** Small technical label (Space Mono caps). */
export function label(ctx, str, x, y, { size = 22, color = P.bone, align = 'left', font = 'mono', tracking = 0.1, alpha = 1, baseline = 'alphabetic' } = {}) {
  if (alpha <= 0) return null;
  ctx.save(); ctx.globalAlpha *= alpha;
  const L = Type.text(ctx, str, x, y, { font, size, fill: color, align, tracking, baseline });
  ctx.restore();
  return L;
}
/** Typewriter label: types `str` to progress p but stays anchored where the finished line will sit. */
export function typedLabel(ctx, str, p, x, y, opts = {}) {
  const n = Math.round(sat(p) * str.length);
  if (n <= 0) return;
  const { size = 22, font = 'mono', tracking = 0.1, align = 'left' } = opts;
  const full = Type.line(str, { font, size, tracking });
  const x0 = align === 'right' ? x - full.width : align === 'center' ? x - full.width / 2 : x;
  label(ctx, str.slice(0, n), x0, y, { ...opts, align: 'left' });
}
/** Typewriter reveal: first n chars of str (n fractional → cursor). */
export const typed = (str, p) => str.slice(0, Math.round(sat(p) * str.length));

/** Partial polyline: pts = [x0,y0,x1,y1,...]; draws arclength fraction a..b. */
export function polyTrim(ctx, pts, a, b) {
  let total = 0;
  const n = pts.length / 2;
  const seg = new Float32Array(n);
  for (let i = 1; i < n; i++) { seg[i] = Math.hypot(pts[i * 2] - pts[i * 2 - 2], pts[i * 2 + 1] - pts[i * 2 - 1]); total += seg[i]; }
  const s0 = a * total, s1 = b * total;
  if (s1 <= s0) return;
  let acc = 0, started = false;
  ctx.beginPath();
  for (let i = 1; i < n; i++) {
    const e0 = acc, e1 = acc + seg[i];
    if (e1 >= s0 && e0 <= s1 && seg[i] > 0) {
      const t0 = Math.max(0, (s0 - e0) / seg[i]), t1 = Math.min(1, (s1 - e0) / seg[i]);
      const ax = pts[i * 2 - 2], ay = pts[i * 2 - 1], bx = pts[i * 2], by = pts[i * 2 + 1];
      if (!started) { ctx.moveTo(ax + (bx - ax) * t0, ay + (by - ay) * t0); started = true; }
      ctx.lineTo(ax + (bx - ax) * t1, ay + (by - ay) * t1);
    }
    acc = e1;
    if (acc > s1) break;
  }
  ctx.stroke();
}

/** Run fn with a 2D "camera": zoom/rotate about (px,py) (default centre) then pan. */
export function cam(ctx, { x = 0, y = 0, zoom = 1, rot = 0, px = CX, py = CY }, fn) {
  ctx.save();
  ctx.translate(px, py); ctx.rotate(rot); ctx.scale(zoom, zoom); ctx.translate(-px - x, -py - y);
  fn();
  ctx.restore();
}

/** Deterministic handheld shake offset in px. */
export const shake = (t, amp = 10, freq = 14, seed = 0) => [noise1(t * freq, seed) * amp, noise1(t * freq, seed + 9) * amp];

/** Text set on a circle. angle = centre angle (radians, 0 = right, clockwise). inward=false → tops point out. */
export function arcText(ctx, L, cx, cy, r, angle, { fill = P.bone, inside = false, spin = 0, alpha = null } = {}) {
  ctx.save(); ctx.fillStyle = fill;
  const total = L.width / r;
  for (const g of L.glyphs) {
    if (g.ch === ' ') continue;
    const mid = (g.x + g.w / 2) / r;
    const a = angle + spin + (inside ? -1 : 1) * (mid - total / 2);
    ctx.save();
    if (alpha) ctx.globalAlpha *= alpha(g);
    ctx.translate(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
    ctx.rotate(a + (inside ? -Math.PI / 2 : Math.PI / 2));
    ctx.translate(-g.w / 2, 0);
    Type.glyph(ctx, L, g);
    ctx.restore();
  }
  ctx.restore();
}

/** Lines of text each scaled to the same width (poster stack). Returns [{L, y}] + total height. */
export function stack(lines, width, { font = 'anton', vars = null, gap = 0.12, tracking = 0 } = {}) {
  const out = []; let y = 0;
  for (const str of lines) {
    const size = Type.fitSize(str, width, { font, vars, tracking });
    const L = Type.line(str, { font, size, vars, tracking });
    y += L.cap;
    out.push({ L, y, size });
    y += L.cap * gap;
  }
  return { rows: out, height: y - (out.length ? out[out.length - 1].L.cap * gap : 0) };
}
