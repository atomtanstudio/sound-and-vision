/** The look of what's laid over a picture (the title, the artist and the brand's logos): the same description and the
 *  same layout rules as the server's (server/sv/look.py), so what the editor draws is what the cover or thumbnail
 *  gets. Positions are an anchor ("tl" … "br") and a distance in from that edge, in percent of the shorter side. */

export type Anchor = "tl" | "tc" | "tr" | "ml" | "mc" | "mr" | "bl" | "bc" | "br";
export type Case = "upper" | "asis" | "lower";

export interface TextEl {
  show: boolean;
  place: "auto" | "manual";
  font: string;
  weight: number | null;
  size: number;
  tracking: number;
  case: Case;
  color: string; // "auto" or "#rrggbb"
  shadow: boolean;
  anchor: Anchor;
  dx: number;
  dy: number;
  width?: number; // the title: the widest it may run, in percent of the picture's width
  rules?: boolean; // the artist: a short rule either side when centred
}
export interface LogoEl {
  show: boolean;
  anchor: Anchor;
  dx: number;
  dy: number;
  size: number;
}
export interface Look {
  title: TextEl;
  artist: TextEl;
  logos: Record<string, LogoEl>;
  scrim: "auto" | "none" | number;
}
export interface BrandLogo {
  id: string;
  name: string;
  file: string;
  w: number;
  h: number;
}
export interface FontInfo {
  id: string;
  family: string;
  style: string;
  weight: [number, number, number] | null;
}

export const ANCHORS: Record<Anchor, [number, number]> = {
  tl: [0, 0], tc: [0.5, 0], tr: [1, 0], ml: [0, 0.5], mc: [0.5, 0.5], mr: [1, 0.5], bl: [0, 1], bc: [0.5, 1], br: [1, 1],
};
export const LEAD = 1.32;
export const BASE = 0.86;

export const DEFAULT: Look = {
  title: { show: true, place: "auto", font: "Inter-Medium", weight: null, size: 6.2, tracking: 0.3, case: "upper", color: "auto",
    shadow: true, width: 82, anchor: "bc", dx: 0, dy: 10.5 },
  artist: { show: true, place: "auto", font: "Inter-Medium", weight: null, size: 2.108, tracking: 0.5, case: "upper", color: "auto",
    shadow: true, rules: true, anchor: "bc", dx: 0, dy: 6 },
  logos: {
    label: { show: true, anchor: "bl", dx: 2.5, dy: 2.5, size: 6 },
    app: { show: true, anchor: "br", dx: 1.25, dy: 1.25, size: 17.5 },
  },
  scrim: "auto",
};

export function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x)) as T;
}

/** The top-left corner of a w × h box anchored in a W × H picture, dx/dy (percent of the short side s) in from the
 *  anchored edges; a middle anchor measures from the centre line, positive to the right or down. */
export function place(anchor: Anchor, dx: number, dy: number, w: number, h: number, W: number, H: number, s: number,
  whole = false): [number, number] {
  const [ax, ay] = ANCHORS[anchor];
  let mx = (dx * s) / 100;
  let my = (dy * s) / 100;
  if (whole) {
    mx = Math.trunc(mx);
    my = Math.trunc(my);
  }
  const px = ax * W + (ax === 0 ? mx : ax === 1 ? -mx : mx);
  const py = ay * H + (ay === 0 ? my : ay === 1 ? -my : my);
  return [px - ax * w, py - ay * h];
}

/** The reverse: the distances in (dx, dy) that put the box's top-left corner at x, y. */
export function inset(anchor: Anchor, x: number, y: number, w: number, h: number, W: number, H: number, s: number): [number, number] {
  const [ax, ay] = ANCHORS[anchor];
  const px = x + ax * w;
  const py = y + ay * h;
  const mx = ax === 0 ? px : ax === 1 ? W - px : px - W / 2;
  const my = ay === 0 ? py : ay === 1 ? H - py : py - H / 2;
  return [(mx / s) * 100, (my / s) * 100];
}

export function cased(text: string, c: Case) {
  const t = (text || "").split(/\s+/).filter(Boolean).join(" ");
  return c === "upper" ? t.toUpperCase() : c === "lower" ? t.toLowerCase() : t;
}

export type Measure = (font: string, weight: number | null, px: number, text: string) => number;

/** A browser measure with the same per-letter sums as the server's (letters drawn one at a time). `weight` gives the
 *  weight a text is drawn at (its own, or its font's default). */
export function canvasMeasure(family: (id: string) => string, weight: (font: string, w: number | null) => number): Measure {
  const ctx = document.createElement("canvas").getContext("2d")!;
  return (font, w, px, text) => {
    ctx.font = `${weight(font, w)} ${px}px "${family(font)}"`;
    let sum = 0;
    for (const c of text) sum += ctx.measureText(c).width;
    return sum;
  };
}

export const trackedWidth = (m: Measure, font: string, weight: number | null, px: number, text: string, tr: number) =>
  m(font, weight, px, text) + tr * Math.max(0, [...text].length - 1);

function split(m: Measure, font: string, weight: number | null, px: number, text: string, tr: number, most: number): string[] {
  const one = text.split(/\s+/).filter(Boolean).join(" ");
  if (!one || trackedWidth(m, font, weight, px, one, tr) <= most) return one ? [one] : [];
  const words = one.split(" ");
  if (words.length < 2) return [one];
  let best = [one];
  let gap = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(" ");
    const b = words.slice(i).join(" ");
    const g = Math.abs(trackedWidth(m, font, weight, px, a, tr) - trackedWidth(m, font, weight, px, b, tr));
    if (g < gap) {
      best = [a, b];
      gap = g;
    }
  }
  return best;
}

export interface Block {
  lines: string[];
  px: number;
  tracking: number;
  w: number;
  h: number;
  widths: number[];
  box: [number, number, number, number];
  align: number;
  xs: number[];
  baselines: number[];
}
export interface Laid {
  title?: Block;
  artist?: Block;
  place: "upper" | "lower" | "manual";
  logos: Record<string, [number, number, number, number]>;
}

/** A small grayscale of the picture (96 × 96, 0..1) and its two title colours, as the server finds them. */
export interface PictureInfo {
  lum: Float32Array;
  n: number;
  palette: [number, number, number][];
}

export function zone(info: PictureInfo, top: number, height: number): [number, number] {
  const n = info.n;
  const y0 = Math.max(0, Math.floor((top - 0.02) * n));
  const y1 = Math.min(n, Math.floor((top + height + 0.03) * n) + 1);
  const v: number[] = [];
  for (let y = y0; y < y1; y++) for (let x = Math.floor(0.12 * n); x < Math.floor(0.88 * n); x++) v.push(info.lum[y * n + x]);
  if (!v.length) return [0.5, 0.2];
  v.sort((a, b) => a - b);
  const q = (v.length - 1) * 0.85;
  const p85 = v[Math.floor(q)] + (v[Math.ceil(q)] - v[Math.floor(q)]) * (q - Math.floor(q));
  const mean = v.reduce((a, b) => a + b, 0) / v.length;
  const sd = Math.sqrt(v.reduce((a, b) => a + (b - mean) ** 2, 0) / v.length);
  return [p85, sd];
}

export function layout(look: Look, W: number, H: number, title: string, artist: string, m: Measure, info: PictureInfo | null,
  logos: BrandLogo[]): Laid {
  const s = Math.min(W, H);
  const T = look.title;
  const A = look.artist;
  const out: Laid = { place: "manual", logos: {} };
  let t: Omit<Block, "box" | "align" | "xs" | "baselines"> | null = null;
  if (T.show && title.trim()) {
    let px = Math.max(1, Math.round((s * T.size) / 100));
    const raw = (s * T.size) / 100;
    let tr = T.tracking * raw;
    const most = (W * (T.width ?? 82)) / 100;
    const lines = split(m, T.font, T.weight, px, cased(title, T.case), tr, most);
    let widest = Math.max(1, ...lines.map((x) => trackedWidth(m, T.font, T.weight, px, x, tr)));
    let em = raw;
    if (widest > most) {
      em = raw * (most / widest);
      px = Math.max(1, Math.round(em));
      tr = T.tracking * em;
      widest = Math.max(1, ...lines.map((x) => trackedWidth(m, T.font, T.weight, px, x, tr)));
    }
    t = { lines, px, tracking: tr, w: widest, h: lines.length * em * LEAD, widths: lines.map((x) => trackedWidth(m, T.font, T.weight, px, x, tr)) };
    (t as { em?: number }).em = em;
  }
  let a: Omit<Block, "box" | "align" | "xs" | "baselines"> | null = null;
  if (A.show && artist.trim()) {
    const raw = (s * A.size) / 100;
    const px = Math.max(1, Math.round(raw));
    const tr = A.tracking * raw;
    const text = cased(artist, A.case);
    const w = trackedWidth(m, A.font, A.weight, px, text, tr);
    a = { lines: [text], px, tracking: tr, w, h: raw * 1.2, widths: [w] };
    (a as { em?: number }).em = raw;
  }
  const em = (b: object) => (b as { em: number }).em;
  const follow = !!a && !!t && A.place === "auto";
  const gap = follow && t ? em(t) * 0.62 : 0;
  if (t) {
    let anchor = T.anchor;
    let dx = T.dx;
    let dy = T.dy;
    const groupH = t.h + (follow && a ? gap + a.h : 0);
    const groupW = Math.max(t.w, follow && a ? a.w : 0);
    if (T.place === "auto") {
      anchor = "bc";
      dx = 0;
      dy = DEFAULT.title.dy;
      out.place = "lower";
      if (info) {
        const hh = groupH / H;
        const lo = zone(info, 1 - 0.105 - hh, hh);
        const up = zone(info, 0.105, hh);
        if (up[0] + 1.2 * up[1] + 0.06 < lo[0] + 1.2 * lo[1]) {
          anchor = "tc";
          out.place = "upper";
        }
      }
    }
    const [x0, y0] = place(anchor, dx, dy, groupW, groupH, W, H, s);
    const align = ANCHORS[anchor][0];
    out.title = { ...t, box: [x0, y0, groupW, t.h], align, xs: t.widths.map((w) => x0 + (groupW - w) * align),
      baselines: t.lines.map((_, i) => y0 + i * em(t!) * LEAD + em(t!) * BASE) };
    if (follow && a) {
      const ay = y0 + t.h + gap;
      out.artist = { ...a, box: [x0, ay, groupW, a.h], align, xs: [x0 + (groupW - a.w) * align], baselines: [ay + em(a) * 0.95] };
    }
  }
  if (a && !out.artist) {
    const [x0, y0] = place(A.anchor, A.dx, A.dy, a.w, a.h, W, H, s);
    out.artist = { ...a, box: [x0, y0, a.w, a.h], align: ANCHORS[A.anchor][0], xs: [x0], baselines: [y0 + em(a) * 0.95] };
  }
  for (const lg of logos) {
    const el = look.logos[lg.id];
    if (!el || !el.show) continue;
    const w = Math.max(2, Math.trunc((s * el.size) / 100));
    const h = Math.max(2, Math.trunc((w * lg.h) / lg.w));
    const [x, y] = place(el.anchor, el.dx, el.dy, w, h, W, H, s, true);
    out.logos[lg.id] = [Math.trunc(x), Math.trunc(y), w, h];
  }
  return out;
}

function hsv(h: number, s: number, v: number): [number, number, number] {
  const i = Math.floor(h * 6) % 6;
  const f = h * 6 - Math.floor(h * 6);
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);
  const [r, g, b] = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][i];
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

/** The picture's small grayscale and its two title colours (look.palette on the server). */
export function pictureInfo(img: CanvasImageSource): PictureInfo {
  const n = 96;
  const c = document.createElement("canvas");
  c.width = n;
  c.height = n;
  const ctx = c.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(img, 0, 0, n, n);
  const d = ctx.getImageData(0, 0, n, n).data;
  const lum = new Float32Array(n * n);
  const bins = 18;
  const hist = new Array(bins).fill(0);
  let colourful = 0;
  for (let i = 0; i < n * n; i++) {
    const r = d[i * 4] / 255;
    const g = d[i * 4 + 1] / 255;
    const b = d[i * 4 + 2] / 255;
    lum[i] = 0.299 * r + 0.587 * g + 0.114 * b;
    const mx = Math.max(r, g, b);
    const mn = Math.min(r, g, b);
    const dd = Math.max(mx - mn, 1e-6);
    let h = mx === r ? (((g - b) / dd) % 6 + 6) % 6 : mx === g ? (b - r) / dd + 2 : (r - g) / dd + 4;
    h /= 6;
    const sat = mx > 0 ? (mx - mn) / Math.max(mx, 1e-6) : 0;
    hist[Math.floor(h * bins) % bins] += sat ** 1.2 * mx ** 1.5;
    colourful += sat * mx;
  }
  let palette: [number, number, number][];
  if (hist.reduce((a, b) => a + b, 0) < 1 || colourful / (n * n) < 0.06) palette = [[242, 238, 230]];
  else {
    const picks: number[] = [];
    for (const k of [...hist.keys()].sort((a, b) => hist[b] - hist[a])) {
      if (picks.every((p) => Math.min(Math.abs(k - p), bins - Math.abs(k - p)) >= 3)) picks.push(k);
      if (picks.length === 2) break;
    }
    palette = picks.map((k) => hsv((k + 0.5) / bins, 0.45, 1)).sort((x, y) => x[0] - x[2] - (y[0] - y[2]));
  }
  return { lum, n, palette };
}

/** A look's distances as whole pixels at a given output size, for "px from the edge" fields. */
export const toPx = (pct: number, W: number, H: number) => Math.round((pct * Math.min(W, H)) / 100);
export const toPct = (px: number, W: number, H: number) => (px / Math.min(W, H)) * 100;

/** `over` laid over `base` (a song's or a thumbnail's own look over the house look), part by part. */
export function mergeLook(base: Look, over?: Partial<Look> | null): Look {
  const out = clone(base);
  if (!over) return out;
  if (over.title) out.title = { ...out.title, ...over.title };
  if (over.artist) out.artist = { ...out.artist, ...over.artist };
  if (over.logos) for (const [id, lg] of Object.entries(over.logos)) out.logos[id] = { ...(out.logos[id] ?? {}), ...lg };
  if (over.scrim !== undefined) out.scrim = over.scrim;
  return out;
}
