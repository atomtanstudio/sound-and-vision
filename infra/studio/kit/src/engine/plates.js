// H3 plates: word-free background clips made with H3 on the machine's ComfyUI by tools/h3plate.py, used as seekable pictures.
//
// A plate is plates/<name>/plate.json ({ start, fps, frames, width, height, … }) plus its frames
// plates/<name>/f_00000.jpg, f_00001.jpg … at the plate's fps (24): frame f shows song time start + f / fps.
// plates/index.json lists the plates ({ "plates": ["chorus1", …] }); h3plate.py keeps it up to date.
//
// Rendering stays a pure function of t: the engine's prepare(t) step loads, before every frame, each plate frame its
// sub-frames need (every plate that covers the moment, plus whatever a scene asks for in its own prepare hook), and the
// scene then draws plates.frame(name, t) synchronously. In render mode (strict) asking for a frame that wasn't
// prepared is an error rather than a silently different picture; in the live preview it shows the nearest loaded one.

export class Plates {
  constructor(base = '/plates/') {
    this.base = base;
    this.list = [];
    this.byName = {};
    this.cache = new Map();     // "name|frame" → ImageBitmap, oldest first
    this.loading = new Map();   // "name|frame" → Promise
    this.strict = false;
    this.max = 48;              // decoded frames kept (≈2.4 MB each at 1024×576)
    this.W = 1920; this.H = 1080; // design frame (main.js sets the engine's)
  }

  async init() {
    let names = [];
    try {
      const r = await fetch(this.base + 'index.json', { cache: 'no-store' });
      if (r.ok) names = (await r.json()).plates || [];
    } catch { /* no plates in this film */ }
    for (const name of names) {
      const r = await fetch(`${this.base}${name}/plate.json`, { cache: 'no-store' });
      if (!r.ok) throw new Error(`plates/index.json lists "${name}" but plates/${name}/plate.json is missing`);
      const p = await r.json();
      p.name = name;
      p.fps = p.fps || 24;
      p.end = p.start + p.frames / p.fps;
      this.list.push(p);
      this.byName[name] = p;
    }
    return this;
  }

  has(name) { return !!this.byName[name]; }
  info(name) {
    const p = this.byName[name];
    if (!p) throw new Error(`no plate "${name}" (plates/index.json lists: ${this.list.map((x) => x.name).join(', ') || 'none'})`);
    return p;
  }
  /** Frame of the plate shown at song time t (clamped to the clip: before it, its first frame; after it, its last). */
  index(name, t) {
    const p = this.info(name);
    return Math.min(p.frames - 1, Math.max(0, Math.floor((t - p.start) * p.fps + 1e-6)));
  }
  /** Names of the plates whose clip covers song time t. */
  covering(t) { return this.list.filter((p) => t >= p.start && t < p.end).map((p) => p.name); }
  url(name, i) { return `${this.base}${name}/f_${String(i).padStart(5, '0')}.jpg`; }

  /** Load the frame of `name` for song time t (resolves when it can be drawn). */
  load(name, t) { return this._load(name, this.index(name, t)); }

  async _load(name, i) {
    const key = `${name}|${i}`;
    if (this.cache.has(key)) { const b = this.cache.get(key); this.cache.delete(key); this.cache.set(key, b); return b; }
    if (this.loading.has(key)) return this.loading.get(key);
    const job = (async () => {
      const r = await fetch(this.url(name, i));
      if (!r.ok) throw new Error(`plate ${name}: ${this.url(name, i)} is missing (${r.status})`);
      const bmp = await createImageBitmap(await r.blob());
      this.cache.set(key, bmp);
      return bmp;
    })();
    this.loading.set(key, job);
    try { return await job; } finally { this.loading.delete(key); }
  }

  /**
   * Load every frame these sub-frame times need: each plate covering each time, plus `extra` [[name, t], …].
   * The engine calls it (through engine.prepare) before each rendered frame.
   */
  async prepare(times, extra = []) {
    const want = [];
    for (const t of times) for (const name of this.covering(t)) want.push([name, this.index(name, t)]);
    for (const [name, t] of extra) want.push([name, this.index(name, t)]);
    if (!want.length) return;
    await Promise.all(want.map(([name, i]) => this._load(name, i)));
    const keep = new Set(want.map(([n, i]) => `${n}|${i}`));
    for (const key of this.cache.keys()) {
      if (this.cache.size <= this.max) break;
      if (keep.has(key)) continue;
      this.cache.get(key).close();
      this.cache.delete(key);
    }
  }

  /** The decoded frame of `name` for song time t (an ImageBitmap for ctx.drawImage), or null in the live preview. */
  frame(name, t) {
    const i = this.index(name, t), key = `${name}|${i}`;
    const b = this.cache.get(key);
    if (b) return b;
    if (this.strict) throw new Error(`plate ${name} frame ${i} (t=${t.toFixed(3)}) was not prepared: a scene that draws a plate at another time must load it in its prepare(times, E) hook (E.plates.load(name, t))`);
    this.load(name, t).catch(() => {});
    let near = null, best = Infinity;
    for (const [k, v] of this.cache) {
      const [n, j] = k.split('|');
      if (n === name && Math.abs(+j - i) < best) { best = Math.abs(+j - i); near = v; }
    }
    return near;
  }

  /**
   * Draw a plate's frame for song time t into a 2D layer. Fits the box like CSS object-fit ('cover' by default).
   * o: { x, y, w, h (default the whole design frame), fit: 'cover' | 'contain' | 'fill', alpha }
   */
  draw(ctx, name, t, o = {}) {
    const img = this.frame(name, t);
    if (!img) return false;
    const { x = 0, y = 0, w = this.W, h = this.H, fit = 'cover', alpha = 1 } = o;
    let dw = w, dh = h;
    if (fit !== 'fill') {
      const s = (fit === 'contain' ? Math.min : Math.max)(w / img.width, h / img.height);
      dw = img.width * s; dh = img.height * s;
    }
    ctx.save();
    ctx.globalAlpha *= alpha;
    ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(img, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
    ctx.restore();
    return true;
  }
}
