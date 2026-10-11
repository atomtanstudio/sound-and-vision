// Animation math: easing, timing helpers, deterministic noise. Everything is a pure function of its inputs
// so any frame can be rendered in isolation.

export const TAU = Math.PI * 2;
export const clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x);
export const lerp = (a, b, t) => a + (b - a) * t;
export const invLerp = (a, b, x) => (x - a) / (b - a);
export const sat = (x) => clamp(x, 0, 1);
export const remap = (x, a, b, c = 0, d = 1) => c + (d - c) * sat((x - a) / (b - a));
export const smoothstep = (a, b, x) => { const t = sat((x - a) / (b - a)); return t * t * (3 - 2 * t); };
export const mix = lerp;
export const fract = (x) => x - Math.floor(x);
export const mod = (x, n) => ((x % n) + n) % n;
export const sign = Math.sign;
export const deg = (d) => (d * Math.PI) / 180;

// ---------- easing ----------
const pow = Math.pow;
const c1 = 1.70158, c3 = c1 + 1, c2 = c1 * 1.525;
export const ease = {
  linear: (t) => t,
  inQuad: (t) => t * t,
  outQuad: (t) => 1 - (1 - t) * (1 - t),
  inOutQuad: (t) => (t < 0.5 ? 2 * t * t : 1 - pow(-2 * t + 2, 2) / 2),
  inCubic: (t) => t * t * t,
  outCubic: (t) => 1 - pow(1 - t, 3),
  inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - pow(-2 * t + 2, 3) / 2),
  inQuart: (t) => t * t * t * t,
  outQuart: (t) => 1 - pow(1 - t, 4),
  inOutQuart: (t) => (t < 0.5 ? 8 * t * t * t * t : 1 - pow(-2 * t + 2, 4) / 2),
  inQuint: (t) => t * t * t * t * t,
  outQuint: (t) => 1 - pow(1 - t, 5),
  inOutQuint: (t) => (t < 0.5 ? 16 * t * t * t * t * t : 1 - pow(-2 * t + 2, 5) / 2),
  inExpo: (t) => (t <= 0 ? 0 : pow(2, 10 * t - 10)),
  outExpo: (t) => (t >= 1 ? 1 : 1 - pow(2, -10 * t)),
  inOutExpo: (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t < 0.5 ? pow(2, 20 * t - 10) / 2 : (2 - pow(2, -20 * t + 10)) / 2),
  inCirc: (t) => 1 - Math.sqrt(1 - t * t),
  outCirc: (t) => Math.sqrt(1 - pow(t - 1, 2)),
  inOutCirc: (t) => (t < 0.5 ? (1 - Math.sqrt(1 - pow(2 * t, 2))) / 2 : (Math.sqrt(1 - pow(-2 * t + 2, 2)) + 1) / 2),
  inBack: (t) => c3 * t * t * t - c1 * t * t,
  outBack: (t) => 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2),
  inOutBack: (t) => (t < 0.5 ? (pow(2 * t, 2) * ((c2 + 1) * 2 * t - c2)) / 2 : (pow(2 * t - 2, 2) * ((c2 + 1) * (t * 2 - 2) + c2) + 2) / 2),
  outElastic: (t) => (t <= 0 ? 0 : t >= 1 ? 1 : pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * (TAU / 3)) + 1),
  outBounce: (t) => {
    const n1 = 7.5625, d1 = 2.75;
    if (t < 1 / d1) return n1 * t * t;
    if (t < 2 / d1) return n1 * (t -= 1.5 / d1) * t + 0.75;
    if (t < 2.5 / d1) return n1 * (t -= 2.25 / d1) * t + 0.9375;
    return n1 * (t -= 2.625 / d1) * t + 0.984375;
  },
  // back with adjustable overshoot
  outBackK: (k) => (t) => 1 + (k + 1) * pow(t - 1, 3) + k * pow(t - 1, 2),
};

// CSS-style cubic-bezier easing (x1,y1,x2,y2) → f(t)
export function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const fx = (t) => ((ax * t + bx) * t + cx) * t;
  const fy = (t) => ((ay * t + by) * t + cy) * t;
  const dfx = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 6; i++) {
      const d = dfx(t);
      if (Math.abs(d) < 1e-6) break;
      t -= (fx(t) - x) / d;
    }
    t = clamp(t, 0, 1);
    return fy(t);
  };
}
// House curves — the "feel" of the piece.
export const E = {
  snap: bezier(0.16, 1, 0.3, 1),        // fast attack, long settle (expo-out-ish)
  swift: bezier(0.55, 0, 0.1, 1),       // strong in-out, weighted to the front
  heavy: bezier(0.87, 0, 0.13, 1),      // dramatic in-out
  soft: bezier(0.33, 1, 0.68, 1),       // cubic out
  drop: bezier(0.7, 0, 0.84, 0),        // accelerate out of frame
  whip: bezier(0.9, 0, 0.1, 1),
  over: bezier(0.34, 1.56, 0.64, 1),    // overshoot
  anticipate: bezier(0.36, 0, 0.66, -0.56),
};

/** Normalised progress of a tween that starts at t0 and lasts dur, shaped by easing e. */
export const tw = (t, t0, dur, e = E.snap) => e(sat((t - t0) / dur));
/** 0→1 over [a,b], eased. */
export const span = (t, a, b, e = ease.linear) => e(sat((t - a) / (b - a)));
/** In at t0 (dIn), hold, out ending at t1 (dOut). Returns 0..1. */
export const inOut = (t, t0, t1, dIn = 0.3, dOut = 0.3, eIn = E.snap, eOut = ease.inCubic) =>
  Math.min(eIn(sat((t - t0) / dIn)), 1 - eOut(sat((t - (t1 - dOut)) / dOut)));
/** Exponential decay impulse since t0 (0 before). */
export const decay = (t, t0, tau = 0.15) => (t < t0 ? 0 : Math.exp(-(t - t0) / tau));
/** Under-damped spring step response 0→1. */
export const spring = (t, freq = 3, damp = 0.5) => {
  if (t <= 0) return 0;
  const w = TAU * freq, wd = w * Math.sqrt(Math.max(1e-6, 1 - damp * damp));
  return 1 - Math.exp(-damp * w * t) * (Math.cos(wd * t) + ((damp * w) / wd) * Math.sin(wd * t));
};
/** Damped oscillation impulse (rings then settles at 0). */
export const ring = (t, freq = 6, tau = 0.2) => (t < 0 ? 0 : Math.exp(-t / tau) * Math.sin(TAU * freq * t));
/** 0 → 1 starting at t0 over d seconds (snappy); 0 before t0, so it can gate drawing. */
export const inn = (t, t0, d = 0.22, e = E.snap) => (t < t0 ? 0 : e(sat((t - t0) / d)));
/** 1 at t0, decaying after: for anything that flinches on a hit. 0 before t0. */
export const punch = (t, t0, tau = 0.12) => (t < t0 ? 0 : Math.exp(-(t - t0) / tau));
/** Scale for something slapped down at t0: arrives `amt` larger and settles to 1 in d seconds; 0 before t0. */
export const slap = (t, t0, amt = 0.35, d = 0.16) => (t < t0 ? 0 : 1 + amt * (1 - E.snap(sat((t - t0) / d))));
/** How many of `times` have passed by t. */
export const passed = (times, t) => { let n = 0; for (const x of times) if (t >= x) n++; return n; };
/** Index of the last word of a lyric line (song.lines[id]) whose cue has passed by t; −1 before the first. */
export const sung = (line, t) => { let i = -1; for (const w of line.words) if (t >= w.t) i++; return i; };
/** Stepped time for stop-motion / "on twos" feel. */
export const stepTime = (t, fps = 12) => Math.floor(t * fps) / fps;

// ---------- deterministic randomness ----------
export function rng(seed = 1) {
  let a = seed >>> 0 || 1;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export const hash = (n) => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453123; return s - Math.floor(s); };
export const hash2 = (x, y) => { const s = Math.sin(x * 127.1 + y * 311.7 + 74.7) * 43758.5453123; return s - Math.floor(s); };
export const pick = (arr, r) => arr[Math.floor(r * arr.length) % arr.length];

// value noise (smooth), 1D/2D/3D + fbm
const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);
export function noise1(x, seed = 0) {
  const i = Math.floor(x), f = x - i;
  return lerp(hash(i + seed * 57.3), hash(i + 1 + seed * 57.3), fade(f)) * 2 - 1;
}
export function noise2(x, y, seed = 0) {
  const ix = Math.floor(x), iy = Math.floor(y), fx = x - ix, fy = y - iy;
  const s = seed * 13.7;
  const a = hash2(ix + s, iy), b = hash2(ix + 1 + s, iy), c = hash2(ix + s, iy + 1), d = hash2(ix + 1 + s, iy + 1);
  const u = fade(fx), v = fade(fy);
  return lerp(lerp(a, b, u), lerp(c, d, u), v) * 2 - 1;
}
export function fbm1(x, oct = 4, seed = 0) {
  let a = 0.5, f = 1, s = 0, n = 0;
  for (let i = 0; i < oct; i++) { s += a * noise1(x * f, seed + i * 17); n += a; a *= 0.5; f *= 2; }
  return s / n;
}
export function fbm2(x, y, oct = 4, seed = 0) {
  let a = 0.5, f = 1, s = 0, n = 0;
  for (let i = 0; i < oct; i++) { s += a * noise2(x * f, y * f, seed + i * 17); n += a; a *= 0.5; f *= 2; }
  return s / n;
}
/** Smooth organic wiggle (AE's wiggle): freq in Hz, returns -1..1. */
export const wiggle = (t, freq = 2, seed = 0, oct = 2) => fbm1(t * freq, oct, seed);

// ---------- colour ----------
export function hexToRgb(hex) {
  if (Array.isArray(hex)) return hex;
  if (hex[0] !== '#') {
    // rgb()/rgba() strings, so colour helpers can be nested
    const m = hex.match(/[\d.]+/g);
    return [m[0] / 255, m[1] / 255, m[2] / 255];
  }
  let h = hex.slice(1);
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  const n = parseInt(h, 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}
const hx = (v) => Math.round(sat(v) * 255).toString(16).padStart(2, '0');
export const rgbToCss = ([r, g, b], a = 1) => (a >= 1 ? `#${hx(r)}${hx(g)}${hx(b)}` : `rgba(${Math.round(sat(r) * 255)},${Math.round(sat(g) * 255)},${Math.round(sat(b) * 255)},${a})`);
/** Mix two colours (hex / rgb() / [r,g,b]) in sRGB; returns a css string (hex when opaque, so it can be nested). */
export function mixHex(a, b, t, alpha = 1) {
  const A = hexToRgb(a), B = hexToRgb(b);
  return rgbToCss([lerp(A[0], B[0], t), lerp(A[1], B[1], t), lerp(A[2], B[2], t)], alpha);
}
export const withAlpha = (hex, a) => rgbToCss(hexToRgb(hex), a);

// ---------- tiny vector helpers ----------
export const dist = (x0, y0, x1, y1) => Math.hypot(x1 - x0, y1 - y0);
export const polar = (r, a) => [Math.cos(a) * r, Math.sin(a) * r];
export const rot2 = (x, y, a) => { const c = Math.cos(a), s = Math.sin(a); return [x * c - y * s, x * s + y * c]; };

// ---------- springs (playbook §7.2): closed-form step response of a damped spring, mass 1 ----------
export const SPRING = {
  snappy: { k: 320, d: 30 },   // leading edges, plugs, taps
  default: { k: 170, d: 26 },  // camera, hands, containers
  heavy: { k: 90, d: 20 },     // big type, whole films
  playful: { k: 220, d: 14 },  // visible overshoot: cables, loose ends
};
/** 0 at t ≤ 0, settles at 1. Pure function of t, so any frame can be rendered alone. */
export function sp(t, { k, d } = SPRING.default) {
  if (t <= 0) return 0;
  const w0 = Math.sqrt(k), zeta = d / (2 * w0);
  if (zeta < 1) {
    const wd = w0 * Math.sqrt(1 - zeta * zeta);
    return 1 - Math.exp(-zeta * w0 * t) * (Math.cos(wd * t) + ((zeta * w0) / wd) * Math.sin(wd * t));
  }
  if (zeta === 1) return 1 - Math.exp(-w0 * t) * (1 + w0 * t);
  const s = w0 * Math.sqrt(zeta * zeta - 1), r1 = -zeta * w0 + s, r2 = -zeta * w0 - s;
  return 1 - (r2 * Math.exp(r1 * t) - r1 * Math.exp(r2 * t)) / (r2 - r1);
}
/** A value that changes target over time. keys = [[time, value], ...]; each retarget adds its own spring. */
export function track(t, keys, preset = SPRING.default) {
  let v = keys[0][1];
  for (let i = 1; i < keys.length && t > keys[i][0]; i++) v += (keys[i][1] - keys[i - 1][1]) * sp(t - keys[i][0], preset);
  return v;
}
/** track() for arrays of numbers (poses, points): keys = [[time, [..]], ...]. */
export function trackV(t, keys, preset = SPRING.default) {
  const out = keys[0][1].slice();
  for (let i = 1; i < keys.length && t > keys[i][0]; i++) {
    const s = sp(t - keys[i][0], preset), a = keys[i - 1][1], b = keys[i][1];
    for (let j = 0; j < out.length; j++) out[j] += (b[j] - a[j]) * s;
  }
  return out;
}
