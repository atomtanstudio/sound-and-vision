import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { family, loadFont, weightOf } from "./fonts";
import {
  ANCHORS, canvasMeasure, clone, inset, layout, pictureInfo, zone,
  type Anchor, type BrandLogo, type FontInfo, type Laid, type Look, type PictureInfo,
} from "./look";

export type Part = "title" | "artist" | `logo:${string}`;

/** The picture with the title, the artist and the logos drawn on it exactly as the server sets them (look.py), at the
 *  output's size; drag anything to move it (it snaps to the grid unless Shift is held), arrows nudge it a pixel. */
export function LookCanvas({ picture, infoUrl, W, H, look, title, artist, logos, fontList, selected, onSelect, onChange, grid, snap, onPicture }: {
  picture: string;
  infoUrl?: string; // the server's reading of the picture (its title colours and grayscale), so auto matches exactly
  W: number;
  H: number;
  look: Look;
  title: string;
  artist: string;
  logos: BrandLogo[];
  fontList: FontInfo[];
  selected: Part | null;
  onSelect: (p: Part | null) => void;
  onChange: (look: Look) => void;
  grid: number; // the grid step, in percent of the short side (0: no grid)
  snap: boolean;
  onPicture?: (info: PictureInfo) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [info, setInfo] = useState<PictureInfo | null>(null);
  const [logoImgs, setLogoImgs] = useState<Record<string, HTMLImageElement>>({});
  const [fontsReady, setFontsReady] = useState(0);
  const drag = useRef<{ part: Part; x0: number; y0: number; box: [number, number, number, number]; start: Look } | null>(null);
  const s = Math.min(W, H);
  const scale = Math.min(1, 1400 / Math.max(W, H));
  const byId = useMemo(() => Object.fromEntries(fontList.map((f) => [f.id, f])), [fontList]);

  useEffect(() => {
    const i = new Image();
    i.crossOrigin = "anonymous";
    i.onload = async () => {
      setImg(i);
      let pi = pictureInfo(i);
      if (infoUrl) {
        try {
          const r = await api.get<{ palette: [number, number, number][]; n: number; lum: number[] }>(infoUrl);
          pi = { palette: r.palette, n: r.n, lum: Float32Array.from(r.lum, (v) => v / 255) };
        } catch {
          /* the browser's own reading, close enough */
        }
      }
      setInfo(pi);
      onPicture?.(pi);
    };
    i.src = picture;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [picture, infoUrl]);
  useEffect(() => {
    let live = true;
    Promise.all(logos.map((l) => new Promise<[string, HTMLImageElement]>((ok) => {
      const i = new Image();
      i.onload = () => ok([l.id, i]);
      i.onerror = () => ok([l.id, i]);
      i.src = l.file;
    }))).then((pairs) => live && setLogoImgs(Object.fromEntries(pairs)));
    return () => { live = false; };
  }, [logos]);
  useEffect(() => {
    let live = true;
    const ids = [look.title.font, look.artist.font];
    Promise.all(ids.map((id) => loadFont(id, byId[id]))).then(() => live && setFontsReady((n) => n + 1));
    return () => { live = false; };
  }, [look.title.font, look.artist.font, byId]);

  const measure = useMemo(() => canvasMeasure(family, (id, w) => weightOf(w, byId[id])),
    // a new measure once the fonts are in, so widths are the loaded faces'
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [byId, fontsReady]);
  const laid: Laid = useMemo(() => layout(look, W, H, title, artist, measure, info, logos),
    [look, W, H, title, artist, measure, info, logos]);

  useEffect(() => {
    const c = canvas.current;
    if (!c || !img) return;
    c.width = Math.round(W * scale);
    c.height = Math.round(H * scale);
    const ctx = c.getContext("2d")!;
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    draw(ctx, img, W, H, look, laid, info, logoImgs, logos, byId);
    // the editor's own marks: the grid, and what's selected
    if (grid > 0) {
      ctx.save();
      ctx.strokeStyle = "rgba(255,255,255,0.10)";
      ctx.lineWidth = 1 / scale;
      const step = (grid * s) / 100;
      for (let x = W / 2 % step; x < W; x += step) line(ctx, x, 0, x, H);
      for (let y = H / 2 % step; y < H; y += step) line(ctx, 0, y, W, y);
      ctx.strokeStyle = "rgba(255,255,255,0.22)";
      line(ctx, W / 2, 0, W / 2, H);
      line(ctx, 0, H / 2, W, H / 2);
      ctx.restore();
    }
    const boxes = partBoxes(laid);
    for (const [part, b] of Object.entries(boxes)) {
      const on = part === selected;
      ctx.save();
      ctx.setLineDash(on ? [] : [6 / scale, 6 / scale]);
      ctx.strokeStyle = on ? "rgba(77,141,255,0.95)" : "rgba(255,255,255,0.28)";
      ctx.lineWidth = (on ? 2 : 1) / scale;
      const pad = 6 / scale;
      ctx.strokeRect(b[0] - pad, b[1] - pad, b[2] + 2 * pad, b[3] + 2 * pad);
      ctx.restore();
    }
  }, [img, W, H, scale, look, laid, info, logoImgs, logos, byId, grid, s, selected]);

  const toLocal = (e: React.PointerEvent) => {
    const r = canvas.current!.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * W, ((e.clientY - r.top) / r.height) * H] as const;
  };
  const hit = (x: number, y: number): Part | null => {
    const boxes = Object.entries(partBoxes(laid)).reverse();
    const pad = s * 0.01;
    for (const [part, b] of boxes) {
      if (x >= b[0] - pad && x <= b[0] + b[2] + pad && y >= b[1] - pad && y <= b[1] + b[3] + pad) return part as Part;
    }
    return null;
  };

  /** Move a part so its box's top-left corner is at x, y (snapped), keeping its anchor. */
  const moved = (start: Look, part: Part, x: number, y: number, box: [number, number, number, number], free: boolean): Look => {
    const next = clone(start);
    const [, , w, h] = box;
    const fit = (anchor: Anchor) => {
      let [dx, dy] = inset(anchor, x, y, w, h, W, H, s);
      if (snap && !free && grid > 0) {
        dx = Math.round(dx / grid) * grid;
        dy = Math.round(dy / grid) * grid;
      }
      if (snap && !free && ANCHORS[anchor][0] === 0.5 && Math.abs(dx) < grid * 0.75) dx = 0;
      if (snap && !free && ANCHORS[anchor][1] === 0.5 && Math.abs(dy) < grid * 0.75) dy = 0;
      return [Math.round(dx * 100) / 100, Math.round(dy * 100) / 100] as const;
    };
    if (part === "title") {
      const t = next.title;
      if (t.place === "auto") {
        t.place = "manual";
        t.anchor = laid.place === "upper" ? "tc" : "bc";
      }
      // the title's box is the whole group (with a following artist under it)
      const [dx, dy] = fitGroup(t.anchor, x, y, box[2], box[3]);
      t.dx = dx;
      t.dy = dy;
    } else if (part === "artist") {
      const a = next.artist;
      if (a.place === "auto") {
        a.place = "manual";
        // it keeps the title's anchor, so it lines up with the title the way it did
        a.anchor = next.title.place === "manual" ? next.title.anchor : laid.place === "upper" ? "tc" : "bc";
      }
      const [dx, dy] = fit(a.anchor);
      a.dx = dx;
      a.dy = dy;
    } else {
      const id = part.slice(5);
      const lg = next.logos[id];
      if (lg) {
        const [dx, dy] = fit(lg.anchor);
        lg.dx = dx;
        lg.dy = dy;
      }
    }
    return next;

    function fitGroup(anchor: Anchor, gx: number, gy: number, gw: number, gh: number) {
      let [dx, dy] = inset(anchor, gx, gy, gw, gh, W, H, s);
      if (snap && !free && grid > 0) {
        dx = Math.round(dx / grid) * grid;
        dy = Math.round(dy / grid) * grid;
      }
      if (snap && !free && ANCHORS[anchor][0] === 0.5 && Math.abs(dx) < grid * 0.75) dx = 0;
      return [Math.round(dx * 100) / 100, Math.round(dy * 100) / 100] as const;
    }
  };

  return (
    <canvas
      ref={canvas}
      className="lk-canvas"
      style={{ aspectRatio: `${W} / ${H}`, width: `min(100%, calc(var(--lk-h, 72vh) * ${W / H}))` }}
      tabIndex={0}
      aria-label="The picture with its title, artist and logos. Drag to move them; arrow keys nudge the selected one."
      onPointerDown={(e) => {
        const [x, y] = toLocal(e);
        const part = hit(x, y);
        onSelect(part);
        if (!part) return;
        const b = partBoxes(laid)[part];
        drag.current = { part, x0: x, y0: y, box: b, start: look };
        (e.target as HTMLCanvasElement).setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d) {
          const [x, y] = toLocal(e);
          (e.target as HTMLCanvasElement).style.cursor = hit(x, y) ? "move" : "default";
          return;
        }
        const [x, y] = toLocal(e);
        onChange(moved(d.start, d.part, d.box[0] + x - d.x0, d.box[1] + y - d.y0, d.box, e.shiftKey));
      }}
      onPointerUp={() => { drag.current = null; }}
      onPointerCancel={() => { drag.current = null; }}
      onKeyDown={(e) => {
        if (!selected || !e.key.startsWith("Arrow")) return;
        e.preventDefault();
        const b = partBoxes(laid)[selected];
        if (!b) return;
        const step = e.shiftKey ? 10 : 1;
        const dx = e.key === "ArrowLeft" ? -step : e.key === "ArrowRight" ? step : 0;
        const dy = e.key === "ArrowUp" ? -step : e.key === "ArrowDown" ? step : 0;
        onChange(moved(look, selected, b[0] + dx, b[1] + dy, b, true));
      }}
    />
  );
}

/** Each part's box, in output pixels: the title's is its whole group (with a following artist under it). */
export function partBoxes(laid: Laid): Record<string, [number, number, number, number]> {
  const out: Record<string, [number, number, number, number]> = {};
  if (laid.title) {
    const t = laid.title.box;
    const a = laid.artist;
    const follows = a && a.box[0] === t[0] && a.box[2] === t[2] && Math.abs(a.box[1] - (t[1] + t[3])) < laid.title.px;
    out.title = follows ? [t[0], t[1], t[2], a.box[1] + a.box[3] - t[1]] : t;
    if (a && !follows) out.artist = a.box;
  } else if (laid.artist) out.artist = laid.artist.box;
  for (const [id, b] of Object.entries(laid.logos)) out[`logo:${id}`] = b;
  return out;
}

function line(ctx: CanvasRenderingContext2D, x0: number, y0: number, x1: number, y1: number) {
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();
}

const smooth = (u: number) => u * u * (3 - 2 * u);

/** The picture and everything on it, as look.render() sets it on the server. */
export function draw(ctx: CanvasRenderingContext2D, img: CanvasImageSource & { width: number; height: number }, W: number, H: number,
  look: Look, laid: Laid, info: PictureInfo | null, logoImgs: Record<string, HTMLImageElement>, logos: BrandLogo[],
  byId: Record<string, FontInfo>) {
  const s = Math.min(W, H);
  const k = Math.max(W / img.width, H / img.height);
  ctx.clearRect(0, 0, W, H);
  ctx.drawImage(img, (W - img.width * k) / 2, (H - img.height * k) / 2, img.width * k, img.height * k);
  const t = laid.title;
  const a = laid.artist;
  const pal = info?.palette ?? [[242, 238, 230]];

  // the scrim
  if ((t || a) && info) {
    const tops = [t, a].filter(Boolean).map((b) => b!.box[1]);
    const bottoms = [t, a].filter(Boolean).map((b) => b!.box[1] + b!.box[3]);
    const top = Math.min(...tops);
    const bottom = Math.max(...bottoms);
    const [bright] = zone(info, Math.max(0, top / H), Math.max(0.01, (bottom - top) / H));
    const strength = look.scrim === "auto" ? Math.min(0.75, Math.max(0.15, (bright - 0.1) * 2)) : look.scrim === "none" ? 0 : Number(look.scrim);
    if (strength > 0) {
      ctx.save();
      if ((top + bottom) / 2 >= H / 2) {
        const y0 = Math.max(0, top - 0.14 * s);
        const g = ctx.createLinearGradient(0, y0, 0, H);
        for (let i = 0; i <= 16; i++) g.addColorStop(i / 16, `rgba(0,0,0,${smooth(i / 16) * strength})`);
        ctx.fillStyle = g;
        ctx.fillRect(0, y0, W, H - y0);
      } else {
        const y1 = laid.place === "upper" ? 0.3 * s : Math.min(H, Math.max(0.3 * s, bottom + 0.14 * s));
        const g = ctx.createLinearGradient(0, 0, 0, y1);
        for (let i = 0; i <= 16; i++) g.addColorStop(i / 16, `rgba(0,0,0,${(1 - smooth(i / 16)) * strength})`);
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, W, y1);
      }
      ctx.restore();
    }
  }

  const fontOf = (spec: Look["title"], px: number) => `${weightOf(spec.weight, byId[spec.font])} ${px}px "${family(spec.font)}"`;
  const words = (b: NonNullable<Laid["title"]>, spec: Look["title"], alpha: number, rulesAlpha: number) => {
    ctx.font = fontOf(spec, b.px);
    ctx.textBaseline = "alphabetic";
    b.lines.forEach((ln, i) => {
      let x = b.xs[i];
      ctx.globalAlpha = alpha;
      for (const c of ln) {
        ctx.fillText(c, x, b.baselines[i]);
        x += ctx.measureText(c).width + b.tracking;
      }
    });
    if (rulesAlpha && spec.rules && Math.abs(b.align - 0.5) < 0.01) {
      const em = b.h / 1.2;
      const bx = b.xs[0];
      const gap = em * 1.1;
      const rl = 0.07 * s;
      const cy = b.baselines[0] - em * 0.36;
      ctx.globalAlpha = rulesAlpha;
      for (const dy of [-2.2, 2.2]) {
        const yy = cy + (dy * s) / 1080;
        const lw = Math.max(1, Math.round(s / 1080));
        ctx.fillRect(bx - gap - rl, yy - lw / 2, rl, lw);
        ctx.fillRect(bx + b.w + gap, yy - lw / 2, rl, lw);
      }
    }
    ctx.globalAlpha = 1;
  };
  // shadows first, then the letters
  for (const [b, spec, alpha, ra] of [[t, look.title, 1, 0], [a, look.artist, 235 / 255, 160 / 255]] as const) {
    if (!b || !spec.shadow) continue;
    ctx.save();
    ctx.filter = `blur(${s * 0.006}px)`;
    ctx.translate(0, Math.round(s * 0.0025));
    ctx.fillStyle = "#000";
    words(b, spec, alpha * 0.6, ra * 0.6);
    ctx.restore();
  }
  if (t) {
    ctx.save();
    if (look.title.color === "auto") {
      const left = t.box[0] + (t.box[2] - t.w) * t.align;
      const g = ctx.createLinearGradient(left, 0, left + t.w, 0);
      g.addColorStop(0, rgb(pal[0]));
      g.addColorStop(1, rgb(pal[pal.length - 1]));
      ctx.fillStyle = g;
    } else ctx.fillStyle = look.title.color;
    words(t, look.title, 1, 0);
    ctx.restore();
  }
  if (a) {
    ctx.save();
    const c = pal[pal.length - 1];
    ctx.fillStyle = look.artist.color === "auto" ? rgb(c.map((v) => Math.trunc(v + (255 - v) * 0.6)) as [number, number, number]) : look.artist.color;
    words(a, look.artist, 235 / 255, 160 / 255);
    ctx.restore();
  }
  for (const lg of logos) {
    const box = laid.logos[lg.id];
    const im = logoImgs[lg.id];
    if (!box || !im || !im.width) continue;
    const [x, y, w, h] = box;
    const blur = Math.max(2, Math.floor(s / 200));
    const off = Math.max(1, Math.floor(s / 300));
    ctx.save();
    ctx.filter = `brightness(0) blur(${blur}px)`;
    ctx.globalAlpha = 0.55;
    ctx.drawImage(im, x + off, y + off, w, h);
    ctx.restore();
    ctx.drawImage(im, x, y, w, h);
  }
}

const rgb = (c: [number, number, number]) => `rgb(${c[0]},${c[1]},${c[2]})`;
