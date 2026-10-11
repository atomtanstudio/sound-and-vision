// Clip timeline: which scene owns which stretch of the song. A scene is { id, init?(E), prepare?(times, E), render(f, clip) }.
export class Timeline {
  constructor() { this.clips = []; this.overlays = []; }

  /** Add a scene for [t0, t1) seconds. Later clips win where ranges overlap. */
  add(scene, t0, t1, data = {}) {
    this.clips.push({ scene, t0, t1, id: scene.id || `clip${this.clips.length}`, ...data });
    return this;
  }
  /** Overlay scenes render on top of whatever clip is active (HUD, global dressing). */
  overlay(scene) { this.overlays.push(scene); return this; }

  at(t) {
    let hit = null;
    for (const c of this.clips) if (t >= c.t0 && t < c.t1) hit = c;
    return hit;
  }

  async init(E) {
    const seen = new Set();
    for (const c of [...this.clips.map((c) => c.scene), ...this.overlays]) {
      if (seen.has(c)) continue;
      seen.add(c);
      if (c.init) await c.init(E);
    }
  }

  /** Let the scenes active at any of these sub-frame times load what they need (scene.prepare(times, engine)). */
  async prepare(times, E) {
    const seen = new Set(), jobs = [];
    for (const t of times) {
      const c = this.at(t);
      for (const s of [c && c.scene, ...this.overlays]) {
        if (!s || !s.prepare || seen.has(s)) continue;
        seen.add(s);
        jobs.push(s.prepare(times, E));
      }
    }
    await Promise.all(jobs);
  }

  render(f) {
    const c = this.at(f.t);
    f.clip = c;
    if (c) {
      f.lt = f.t - c.t0; f.dur = c.t1 - c.t0; f.p = f.lt / f.dur;
      c.scene.render(f, c);
    }
    for (const o of this.overlays) o.render(f, c);
  }
}
