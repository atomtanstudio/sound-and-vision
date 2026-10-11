// Type engine. Fonts are shaped with HarfBuzz (wasm) and drawn as vector outlines, which buys us:
// continuous variable-font axes, exact metrics, per-glyph animation, trim paths, warps and 3D extrusion —
// none of which the browser's own text API can do on a canvas.
import * as hb from 'harfbuzzjs';

const FONT_FILES = {
  anton: 'Anton.ttf', bebas: 'BebasNeue.ttf',
  anybody: 'Anybody.ttf', anybodyI: 'Anybody-Italic.ttf',
  archivo: 'Archivo.ttf', archivoI: 'Archivo-Italic.ttf',
  shoulders: 'BigShouldersDisplay.ttf', league: 'LeagueGothic.ttf', sixcaps: 'SixCaps.ttf',
  unbounded: 'Unbounded.ttf', syne: 'Syne.ttf', flex: 'RobotoFlex.ttf', dela: 'DelaGothicOne.ttf',
  climate: 'ClimateCrisis.ttf', tilt: 'TiltWarp.ttf', bricolage: 'Bricolage.ttf', oswald: 'Oswald.ttf',
  barlow: 'BarlowCondensed-Black.ttf', barlowI: 'BarlowCondensed-BlackItalic.ttf',
  playfair: 'PlayfairDisplay.ttf', playfairI: 'PlayfairDisplay-Italic.ttf',
  fraunces: 'Fraunces.ttf', frauncesI: 'Fraunces-Italic.ttf',
  instrument: 'InstrumentSerif.ttf', instrumentI: 'InstrumentSerif-Italic.ttf',
  bodoni: 'BodoniModa.ttf', bodoniI: 'BodoniModa-Italic.ttf',
  cormorant: 'Cormorant.ttf', cormorantI: 'Cormorant-Italic.ttf',
  dmserif: 'DMSerifDisplay.ttf', dmserifI: 'DMSerifDisplay-Italic.ttf',
  abril: 'AbrilFatface.ttf', cinzel: 'Cinzel.ttf',
  mono: 'SpaceMono.ttf', monoB: 'SpaceMono-Bold.ttf', jet: 'JetBrainsMono.ttf',
  fraktur: 'UnifrakturMaguntia.ttf', pirata: 'PirataOne.ttf', grenze: 'GrenzeGotisch.ttf',
  rye: 'Rye.ttf', monoton: 'Monoton.ttf', elite: 'SpecialElite.ttf', barcode: 'LibreBarcode39Text.ttf',
  marker: 'PermanentMarker.ttf', rocksalt: 'RockSalt.ttf', handjet: 'Handjet.ttf', alfa: 'AlfaSlabOne.ttf',
  ultra: 'Ultra.ttf', shrikhand: 'Shrikhand.ttf', bungee: 'Bungee.ttf', doto: 'Doto.ttf', caveat: 'Caveat.ttf',
  silk: 'Silkscreen.ttf', silkB: 'Silkscreen-Bold.ttf', vt: 'VT323.ttf', press: 'PressStart2P.ttf', pixelify: 'PixelifySans.ttf',
  tiny5: 'Tiny5.ttf', jersey10: 'Jersey10.ttf', jersey15: 'Jersey15.ttf', dotgothic: 'DotGothic16.ttf',
  overpass: 'OverpassMono.ttf', plexB: 'IBMPlexMono-Bold.ttf', plexM: 'IBMPlexMono-Medium.ttf', sharetech: 'ShareTechMono.ttf',
  martian: 'MartianMono.ttf', courierB: 'CourierPrime-Bold.ttf',
  limelight: 'Limelight.ttf', poiret: 'PoiretOne.ttf', righteous: 'Righteous.ttf', pacifico: 'Pacifico.ttf', yellowtail: 'Yellowtail.ttf',
  bangers: 'Bangers.ttf', lucky: 'LuckiestGuy.ttf', fredoka: 'Fredoka.ttf', cinzelD: 'CinzelDecorative-Bold.ttf', cinzelDB: 'CinzelDecorative-Black.ttf',
  codystar: 'Codystar.ttf', stencil: 'StardosStencil-Bold.ttf', oldstd: 'OldStandard-Bold.ttf', franklin: 'LibreFranklin.ttf',
  neonder: 'Neonderthaw.ttf', tiltneon: 'TiltNeon.ttf', rubikmono: 'RubikMonoOne.ttf', staat: 'Staatliches.ttf', graduate: 'Graduate.ttf', lobster: 'Lobster.ttf',
};

const fonts = new Map();
const shapeCache = new Map();
const pathCache = new Map();
const flatCache = new Map();
const PATH_CACHE_MAX = 40000;

const q = (tag, v) => (tag === 'wght' || tag === 'YEAR' ? Math.round(v) : Math.round(v * 4) / 4);
function varKey(f, vars) {
  if (!vars || !f.axisTags.length) return '';
  let k = '';
  for (const tag of f.axisTags) {
    if (vars[tag] === undefined) continue;
    const a = f.axes[tag];
    k += `${tag}${q(tag, Math.min(a.max, Math.max(a.min, vars[tag])))};`;
  }
  return k;
}
function applyVars(f, key, vars) {
  if (f.curVar === key) return;
  const list = [];
  if (key) {
    for (const tag of f.axisTags) {
      if (vars[tag] === undefined) continue;
      const a = f.axes[tag];
      list.push(new hb.Variation(tag, q(tag, Math.min(a.max, Math.max(a.min, vars[tag])))));
    }
  }
  f.font.setVariations(list);
  f.curVar = key;
}

export async function loadFonts(baseUrl = '/fonts/', only = null) {
  const names = Object.keys(FONT_FILES).filter((n) => !only || only.includes(n));
  await Promise.all(names.map(async (name) => {
    if (fonts.has(name)) return;
    const buf = await (await fetch(baseUrl + encodeURIComponent(FONT_FILES[name]))).arrayBuffer();
    const face = new hb.Face(new hb.Blob(buf), 0);
    const font = new hb.Font(face);
    const upem = face.upem;
    font.setScale(upem, upem);
    const axes = {};
    for (const a of Object.values(face.getAxisInfos())) axes[a.tag] = { min: a.min, max: a.max, def: a.default };
    const f = { name, face, font, upem, axes, axisTags: Object.keys(axes), curVar: '' };
    const ext = font.hExtents();
    f.ascent = ext.ascender / upem; f.descent = -ext.descender / upem;
    const top = (ch, fallback) => {
      const g = font.nominalGlyph(ch.codePointAt(0));
      const e = g !== undefined ? font.glyphExtents(g) : null;
      return e && e.yBearing > 0 ? e.yBearing / upem : fallback;
    };
    f.cap = top('H', 0.7); f.xh = top('x', 0.5);
    fonts.set(name, f);
  }));
}
export const fontNames = () => [...fonts.keys()];
export const fontInfo = (name) => fonts.get(name);

function getFont(name) {
  const f = fonts.get(name);
  if (!f) throw new Error(`font not loaded: ${name}`);
  return f;
}

/** Shape a string → glyph run in font units (cached). */
function shape(text, fontName, vars, features) {
  const f = getFont(fontName);
  const vk = varKey(f, vars);
  const key = `${fontName}|${vk}|${features || ''}|${text}`;
  let run = shapeCache.get(key);
  if (run) return run;
  applyVars(f, vk, vars);
  const buf = new hb.Buffer();
  buf.addText(text);
  buf.guessSegmentProperties();
  const feats = features ? features.split(',').map((s) => hb.Feature.fromString(s.trim())).filter(Boolean) : undefined;
  hb.shape(f.font, buf, feats);
  const infos = buf.getGlyphInfos(), pos = buf.getGlyphPositions();
  const glyphs = [];
  let x = 0;
  for (let i = 0; i < infos.length; i++) {
    const gid = infos[i].codepoint;
    if (gid === 0 && text[infos[i].cluster] !== ' ') console.warn(`missing glyph ${JSON.stringify(text[infos[i].cluster])} in ${fontName}`);
    const ext = f.font.glyphExtents(gid) || { xBearing: 0, yBearing: 0, width: 0, height: 0 };
    glyphs.push({ gid, cl: infos[i].cluster, x: x + pos[i].xOffset, y: pos[i].yOffset, adv: pos[i].xAdvance,
      bx: ext.xBearing, by: ext.yBearing, bw: ext.width, bh: ext.height });
    x += pos[i].xAdvance;
  }
  run = { glyphs, width: x, vk };
  if (shapeCache.size > 20000) shapeCache.clear();
  shapeCache.set(key, run);
  return run;
}

function glyphPath(f, vk, vars, gid) {
  const key = `${f.name}|${vk}|${gid}`;
  let p = pathCache.get(key);
  if (p) return p;
  applyVars(f, vk, vars);
  p = new Path2D(f.font.glyphToPath(gid));
  if (pathCache.size > PATH_CACHE_MAX) pathCache.clear();
  pathCache.set(key, p);
  return p;
}

/** Flattened contours in font units: [{pts: Float32Array[x0,y0,...], len}] (closed). */
function glyphFlat(f, vk, vars, gid, steps = 8) {
  const key = `${f.name}|${vk}|${gid}|${steps}`;
  let c = flatCache.get(key);
  if (c) return c;
  applyVars(f, vk, vars);
  const cmds = f.font.glyphToJson(gid);
  const contours = [];
  let cur = null, px = 0, py = 0;
  const push = (x, y) => { cur.push(x, y); px = x; py = y; };
  for (const { type, values: v } of cmds) {
    if (type === 'M') { cur = []; contours.push(cur); push(v[0], v[1]); }
    else if (type === 'L') push(v[0], v[1]);
    else if (type === 'Q') {
      const x0 = px, y0 = py;
      for (let i = 1; i <= steps; i++) { const t = i / steps, u = 1 - t; push(u * u * x0 + 2 * u * t * v[0] + t * t * v[2], u * u * y0 + 2 * u * t * v[1] + t * t * v[3]); }
    } else if (type === 'C') {
      const x0 = px, y0 = py;
      for (let i = 1; i <= steps; i++) {
        const t = i / steps, u = 1 - t;
        push(u * u * u * x0 + 3 * u * u * t * v[0] + 3 * u * t * t * v[2] + t * t * t * v[4],
          u * u * u * y0 + 3 * u * u * t * v[1] + 3 * u * t * t * v[3] + t * t * t * v[5]);
      }
    }
  }
  c = contours.filter((p) => p.length >= 6).map((p) => {
    // close the loop explicitly if needed
    if (p[0] !== p[p.length - 2] || p[1] !== p[p.length - 1]) p.push(p[0], p[1]);
    const pts = Float32Array.from(p);
    let len = 0;
    for (let i = 2; i < pts.length; i += 2) len += Math.hypot(pts[i] - pts[i - 2], pts[i + 1] - pts[i - 1]);
    return { pts, len };
  });
  if (flatCache.size > 20000) flatCache.clear();
  flatCache.set(key, c);
  return c;
}

/**
 * Lay out one line of text.
 * opts: { font, size, vars, tracking (em), features }
 * Returns glyph boxes in px relative to the line origin (left end of the baseline, y down).
 */
export function line(text, opts) {
  const { font: fontName = 'anton', size = 100, vars = null, tracking = 0, features = '' } = opts;
  const f = getFont(fontName);
  const run = shape(text, fontName, vars, features);
  const s = size / f.upem;
  const tr = tracking * size;
  const glyphs = [];
  let word = 0, n = 0;
  const chars = [...text];
  // cluster → char (clusters are UTF-16 offsets)
  for (let i = 0; i < run.glyphs.length; i++) {
    const g = run.glyphs[i];
    const ch = text[g.cl] || '';
    if (ch === ' ') { word++; }
    glyphs.push({
      i, ch, word: ch === ' ' ? -1 : word, gid: g.gid,
      x: g.x * s + tr * i, y: -g.y * s, w: g.adv * s + tr,
      // ink box (px, y down, relative to glyph origin)
      ix: g.bx * s, iy: -g.by * s, iw: g.bw * s, ih: -g.bh * s,
      n: ch === ' ' ? -1 : n,
    });
    if (ch !== ' ') n++;
  }
  const width = run.width * s + tr * Math.max(0, run.glyphs.length - 1);
  return {
    text, font: fontName, f, vars, vk: run.vk, size, s, glyphs, width, count: n, words: word + 1,
    ascent: f.ascent * size, descent: f.descent * size, cap: f.cap * size, xh: f.xh * size, chars,
  };
}

/** Size that makes `text` exactly `width` px wide. */
export function fitSize(text, width, opts) {
  const L = line(text, { ...opts, size: 100 });
  return (100 * width) / L.width;
}

const alignX = (L, align) => (align === 'center' ? -L.width / 2 : align === 'right' ? -L.width : 0);
const baseY = (L, baseline) => (baseline === 'cap' ? L.cap : baseline === 'middle' ? L.cap / 2 : baseline === 'xmiddle' ? L.xh / 2 : baseline === 'bottom' ? -L.descent : baseline === 'top' ? L.ascent : 0);

/** Offset to apply so the line sits at (x,y) with the given alignment. */
export function origin(L, x, y, align = 'left', baseline = 'alphabetic') {
  return [x + alignX(L, align), y + baseY(L, baseline)];
}

export const pathOf = (L, g) => glyphPath(L.f, L.vk, L.vars, g.gid);
export const flatOf = (L, g, steps) => glyphFlat(L.f, L.vk, L.vars, g.gid, steps);

/** Fill/stroke a single glyph with its origin at the current transform's (0,0). */
export function glyph(ctx, L, g, { fill = true, stroke = false, lineWidth = 1 } = {}) {
  const p = pathOf(L, g);
  ctx.save();
  ctx.scale(L.s, -L.s);
  if (fill) ctx.fill(p);
  if (stroke) { ctx.lineWidth = lineWidth / L.s; ctx.stroke(p); }
  ctx.restore();
}

/**
 * Draw a laid-out line. style: { fill, stroke, lineWidth, align, baseline, each }
 * `each(g, i)` may return a per-glyph transform/alpha override: {dx, dy, rot, sx, sy, alpha, fill, skip}
 */
export function draw(ctx, L, x, y, style = {}) {
  const { fill = '#fff', stroke = null, lineWidth = 2, align = 'left', baseline = 'alphabetic', each = null, lineJoin = 'round' } = style;
  const [ox, oy] = origin(L, x, y, align, baseline);
  ctx.save();
  if (fill) ctx.fillStyle = fill;
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineJoin = lineJoin; }
  for (const g of L.glyphs) {
    if (g.ch === ' ') continue;
    let o = null;
    if (each) { o = each(g, g.n); if (o && o.skip) continue; }
    ctx.save();
    if (o) {
      // transform about the glyph's ink centre
      const cx = ox + g.x + g.ix + g.iw / 2, cy = oy + g.y + (o.pivotBase ? 0 : g.iy + g.ih / 2);
      ctx.translate(cx + (o.dx || 0), cy + (o.dy || 0));
      if (o.rot) ctx.rotate(o.rot);
      if (o.sx !== undefined || o.sy !== undefined || o.s !== undefined) ctx.scale(o.sx ?? o.s ?? 1, o.sy ?? o.s ?? 1);
      if (o.skew) ctx.transform(1, 0, o.skew, 1, 0, 0);
      ctx.translate(-(cx - ox - g.x), -(cy - oy - g.y));
      if (o.alpha !== undefined) ctx.globalAlpha *= o.alpha;
      if (o.fill) ctx.fillStyle = o.fill;
      if (o.stroke) ctx.strokeStyle = o.stroke;
    } else ctx.translate(ox + g.x, oy + g.y);
    const p = pathOf(L, g);
    ctx.scale(L.s, -L.s);
    if (fill || (o && o.fill)) ctx.fill(p);
    if (stroke || (o && o.stroke)) { ctx.lineWidth = (o && o.lineWidth ? o.lineWidth : lineWidth) / L.s; ctx.stroke(p); }
    ctx.restore();
  }
  ctx.restore();
}

/** Convenience: shape + draw in one call. Returns the layout. */
export function text(ctx, str, x, y, opts = {}) {
  const L = line(str, opts);
  draw(ctx, L, x, y, opts);
  return L;
}

/** One Path2D for the whole line (for clipping / masks), positioned at (x,y). */
export function linePath(L, x = 0, y = 0, align = 'left', baseline = 'alphabetic') {
  const [ox, oy] = origin(L, x, y, align, baseline);
  const out = new Path2D();
  for (const g of L.glyphs) {
    if (g.ch === ' ') continue;
    out.addPath(pathOf(L, g), new DOMMatrix([L.s, 0, 0, -L.s, ox + g.x, oy + g.y]));
  }
  return out;
}

/**
 * Flattened outlines of a line in px (y down): [{g, contours: [{pts: Float32Array, len}]}].
 * Used for trim-path write-ons, warps, particles and 3D extrusion.
 */
export function outlines(L, x = 0, y = 0, align = 'left', baseline = 'alphabetic', steps = 8) {
  const [ox, oy] = origin(L, x, y, align, baseline);
  const res = [];
  for (const g of L.glyphs) {
    if (g.ch === ' ') continue;
    const contours = flatOf(L, g, steps).map((c) => {
      const pts = new Float32Array(c.pts.length);
      for (let i = 0; i < pts.length; i += 2) { pts[i] = ox + g.x + c.pts[i] * L.s; pts[i + 1] = oy + g.y - c.pts[i + 1] * L.s; }
      return { pts, len: c.len * L.s };
    });
    res.push({ g, contours });
  }
  return res;
}

/** Stroke a fraction [a,b] (0..1) of every contour — After Effects "trim paths" for type. */
export function trim(ctx, outs, a, b, { stroke = '#fff', lineWidth = 3, stagger = 0, lineCap = 'round' } = {}) {
  ctx.save();
  ctx.strokeStyle = stroke; ctx.lineWidth = lineWidth; ctx.lineCap = lineCap; ctx.lineJoin = 'round';
  const n = outs.length;
  outs.forEach((o, gi) => {
    const off = n > 1 ? (gi / (n - 1)) * stagger : 0;
    const ga = Math.min(1, Math.max(0, (a - off) / (1 - stagger || 1)));
    const gb = Math.min(1, Math.max(0, (b - off) / (1 - stagger || 1)));
    if (gb <= ga) return;
    for (const c of o.contours) {
      const s0 = ga * c.len, s1 = gb * c.len;
      ctx.beginPath();
      let acc = 0, started = false;
      const p = c.pts;
      for (let i = 2; i < p.length; i += 2) {
        const d = Math.hypot(p[i] - p[i - 2], p[i + 1] - p[i - 1]);
        const e0 = acc, e1 = acc + d;
        if (e1 >= s0 && e0 <= s1 && d > 0) {
          const t0 = Math.max(0, (s0 - e0) / d), t1 = Math.min(1, (s1 - e0) / d);
          const x0 = p[i - 2] + (p[i] - p[i - 2]) * t0, y0 = p[i - 1] + (p[i + 1] - p[i - 1]) * t0;
          const x1 = p[i - 2] + (p[i] - p[i - 2]) * t1, y1 = p[i - 1] + (p[i + 1] - p[i - 1]) * t1;
          if (!started) { ctx.moveTo(x0, y0); started = true; }
          ctx.lineTo(x1, y1);
        }
        acc = e1;
        if (acc > s1) break;
      }
      ctx.stroke();
    }
  });
  ctx.restore();
}

/** Fill outlines after passing every point through warp(x,y) → [x,y]. */
export function fillWarped(ctx, outs, warp, fill = '#fff') {
  ctx.save();
  ctx.fillStyle = fill;
  for (const o of outs) {
    ctx.beginPath();
    for (const c of o.contours) {
      const p = c.pts;
      for (let i = 0; i < p.length; i += 2) {
        const [x, y] = warp(p[i], p[i + 1], o.g);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
    }
    ctx.fill();
  }
  ctx.restore();
}

/** Evenly spaced sample points along every outline: [{x,y,nx,ny,g}] */
export function samplePoints(outs, spacing = 6) {
  const res = [];
  for (const o of outs) {
    for (const c of o.contours) {
      const p = c.pts;
      let next = 0, acc = 0;
      for (let i = 2; i < p.length; i += 2) {
        const dx = p[i] - p[i - 2], dy = p[i + 1] - p[i - 1];
        const d = Math.hypot(dx, dy);
        if (d === 0) continue;
        while (next <= acc + d) {
          const t = (next - acc) / d;
          res.push({ x: p[i - 2] + dx * t, y: p[i - 1] + dy * t, nx: dy / d, ny: -dx / d, g: o.g });
          next += spacing;
        }
        acc += d;
      }
    }
  }
  return res;
}

export { hb };
