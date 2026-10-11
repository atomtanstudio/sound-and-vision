// Read-only view of the song as measured by tools/import_song.py (analysis/): the bar and beat grid, onsets per key,
// envelopes, a log-spaced spectrum, waveforms, sections, and the lyric lines with every word's sung time and cue.
import { clamp } from './math.js';

const ONSET_KEYS = ['kick', 'snare', 'hat', 'hit', 'bass', 'other', 'vocals', 'mix'];

export class Song {
  constructor(meta, envBuf, waveBuf) {
    this.meta = meta;
    this.title = meta.title || '';
    this.artist = meta.artist || '';
    this.duration = meta.duration;
    this.musicEnd = meta.musicEnd ?? meta.duration;
    this.tempo = meta.tempo || 0;
    this.meter = meta.meter || 4;
    this.bars = meta.bars;
    this.beats = meta.beats || [];
    const { hz, n, keys, bands } = meta.env;
    this.envHz = hz; this.envN = n; this.nBands = bands; this.envKeys = keys;
    const all = new Float32Array(envBuf);
    this.envs = {};
    keys.forEach((k, i) => { this.envs[k] = all.subarray(i * n, (i + 1) * n); });
    this.bandData = all.subarray(keys.length * n);
    const w = new Int8Array(waveBuf);
    this.waveHz = meta.wave.hz; this.waveN = meta.wave.n;
    this.waves = {};
    meta.wave.keys.forEach((k, i) => { this.waves[k] = w.subarray(i * this.waveN, (i + 1) * this.waveN); });
    this.onsets = {};
    for (const k of new Set([...ONSET_KEYS, ...Object.keys(meta.onsets || {})])) {
      const list = (meta.onsets && meta.onsets[k]) || [];
      this.onsets[k] = { t: Float64Array.from(list, (o) => o[0]), s: Float32Array.from(list, (o) => o[1]) };
    }
    // Word cues. tools/import_song.py works them out and stores each word as [text, sung start, end, cue, how]:
    // a word that lands on a drum hit (within SNAP) is locked to that transient, 12 ms early so the first new frame is
    // already up when the hit sounds; everything else is cued LEAD ahead of the sung onset, because an entrance needs
    // a moment to read as "landing on" the syllable. Older analysis files without a cue get the same rule here.
    const rule = meta.cueRule || {};
    const LEAD = rule.lead ?? 0.04, SNAP = rule.snap ?? 0.05, EARLY = rule.early ?? 0.012;
    const drums = [['hit', 0.5], ['kick', 0.6], ['snare', 0.6]];
    const cue = (t) => {
      let best = null;
      for (const [key, min] of drums) {
        const o = this.onsets[key];
        for (let i = Math.max(0, this.idx(key, t - SNAP)); i < o.t.length; i++) {
          const d = o.t[i] - t;
          if (d > SNAP) break;
          if (Math.abs(d) <= SNAP && o.s[i] >= min && (best === null || Math.abs(d) < Math.abs(best - t))) best = o.t[i];
        }
      }
      return best !== null ? best - EARLY : t - LEAD;
    };
    this.lines = {};
    this.lineList = [];
    for (const ln of meta.lyrics || []) {
      if (!ln.words || !ln.words.length) continue;
      const words = ln.words.map(([w, t, e, c, how]) => ({ w, t: c ?? cue(t), raw: t, end: e, how: how || (c == null ? 'engine' : '') }));
      words.forEach((w, i) => { w.i = i; if (i + 1 < words.length) w.end = Math.min(w.end, words[i + 1].t); });
      const line = { id: ln.id, sec: ln.sec, section: ln.section, words, start: words[0].t, end: ln.end, text: ln.text };
      words.forEach((w) => { w.line = line; });
      this.lines[ln.id] = line; this.lineList.push(line);
    }
    this.words = this.lineList.flatMap((l) => l.words);
    // sections: id → {id, name, bar0, bar1 (exclusive), t0, t1}. Stored as objects {id, name, start, end, bar0, bar1}
    // by tools/import_song.py; the older [id, name, bar0, bar1] form is still read.
    this.sections = {}; this.sectionList = [];
    for (const s of meta.sections || []) {
      const [id, name, b0, b1, t0, t1] = Array.isArray(s) ? s : [s.id, s.name, s.bar0, s.bar1, s.start, s.end];
      const sec = { id, name, bar0: b0, bar1: b1, t0: t0 ?? this.bar(b0), t1: t1 ?? this.bar(b1) };
      this.sections[id] = sec; this.sectionList.push(sec);
    }
  }

  // ---------- musical grid (bars are 1-indexed; `meter` beats and 4 × meter sixteenths per bar) ----------
  /** Time of bar n (1 = the first downbeat; fractions interpolate, numbers outside the song extrapolate). */
  bar(n) {
    const b = this.bars, last = b.length - 1;
    const x = n - 1;
    if (x <= 0) return b[0] + x * (b[1] - b[0]);
    if (x >= last) return b[last] + (x - last) * (b[last] - b[last - 1]);
    const i = Math.floor(x);
    return b[i] + (x - i) * (b[i + 1] - b[i]);
  }
  /** Time of beat (0 … meter−1, fractional ok) in a bar. */
  bt(bar, beat = 0) { return this.bar(bar + beat / this.meter); }
  /** Time of sixteenth step (0 … 4·meter−1, fractional ok) in a bar. */
  st(bar, step = 0) { return this.bar(bar + step / (4 * this.meter)); }
  /** Time of beat i of the song's beat list (0-indexed, as measured; extrapolated outside it). */
  beat(i) {
    const b = this.beats, n = b.length;
    if (!n) return this.bar(1 + i / this.meter);
    if (i <= 0) return b[0] + i * (n > 1 ? b[1] - b[0] : 0.5);
    if (i >= n - 1) return b[n - 1] + (i - n + 1) * (n > 1 ? b[n - 1] - b[n - 2] : 0.5);
    const k = Math.floor(i);
    return b[k] + (i - k) * (b[k + 1] - b[k]);
  }
  /** Index of the last measured beat at or before t (−1 before the first). */
  beatAt(t) {
    const b = this.beats;
    let lo = -1, hi = b.length;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (b[m] <= t) lo = m; else hi = m; }
    return lo;
  }
  /** Section containing time t (or null). */
  sectionAt(t) { for (const s of this.sectionList) if (t >= s.t0 && t < s.t1) return s; return null; }
  /** Lyric line being sung at t (within [start − lead, end + tail]) or null. */
  lineAt(t, lead = 0, tail = 0) { for (const l of this.lineList) if (t >= l.start - lead && t < l.end + tail) return l; return null; }
  /** Fractional bar position (1-indexed) at time t. */
  barPos(t) {
    const b = this.bars, last = b.length - 1;
    if (t <= b[0]) return 1 + (t - b[0]) / (b[1] - b[0]);
    if (t >= b[last]) return 1 + last + (t - b[last]) / (b[last] - b[last - 1]);
    let lo = 0, hi = last;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (b[m] <= t) lo = m; else hi = m; }
    return 1 + lo + (t - b[lo]) / (b[lo + 1] - b[lo]);
  }
  /** Phase 0..1 inside the current beat, and the beat index since bar 1. */
  beatPhase(t) { const p = (this.barPos(t) - 1) * this.meter; return p - Math.floor(p); }
  beatIndex(t) { return Math.floor((this.barPos(t) - 1) * this.meter); }
  barLen(bar) { return this.bar(bar + 1) - this.bar(bar); }

  // ---------- envelopes ----------
  /** Envelope `key` (see analysis.json env.keys) at t, about 0..1 (1 ≈ the loud end of the song). */
  env(key, t) {
    const a = this.envs[key];
    if (!a) throw new Error(`no envelope "${key}" (have: ${this.envKeys.join(', ')})`);
    const x = clamp(t * this.envHz, 0, this.envN - 1.001);
    const i = Math.floor(x), f = x - i;
    return a[i] + (a[i + 1] - a[i]) * f;
  }
  /** Band i (0 = 40 Hz … nBands−1 = 16 kHz, log-spaced) of the mix's spectrum at t. */
  band(i, t) {
    const n = this.envN;
    const x = clamp(t * this.envHz, 0, n - 1.001);
    const k = Math.floor(x), f = x - k, o = i * n;
    return this.bandData[o + k] + (this.bandData[o + k + 1] - this.bandData[o + k]) * f;
  }
  /** Fill `out` with `count` waveform samples (−1..1) of a key, centred at t, `spanSec` wide. */
  wave(key, t, spanSec, count, out) {
    const w = this.waves[key], hz = this.waveHz;
    if (!w) throw new Error(`no waveform "${key}" (have: ${Object.keys(this.waves).join(', ')})`);
    const t0 = t - spanSec / 2;
    for (let i = 0; i < count; i++) {
      const x = (t0 + (i / (count - 1)) * spanSec) * hz;
      if (x < 0 || x >= this.waveN - 1) { out[i] = 0; continue; }
      const k = Math.floor(x), f = x - k;
      out[i] = (w[k] + (w[k + 1] - w[k]) * f) / 127;
    }
    return out;
  }

  // ---------- onsets ----------
  _o(key) {
    const o = this.onsets[key];
    if (!o) throw new Error(`no onsets "${key}" (have: ${Object.keys(this.onsets).join(', ')})`);
    return o;
  }
  /** Index of the last onset at or before t (−1 if none). */
  idx(key, t) {
    const a = this._o(key).t;
    let lo = -1, hi = a.length;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (a[m] <= t) lo = m; else hi = m; }
    return lo;
  }
  /** Most recent onset ≥ minS strong: {t, s, i} or null. */
  last(key, t, minS = 0) {
    const o = this._o(key);
    for (let i = this.idx(key, t); i >= 0; i--) if (o.s[i] >= minS) return { t: o.t[i], s: o.s[i], i };
    return null;
  }
  next(key, t, minS = 0) {
    const o = this._o(key);
    for (let i = this.idx(key, t) + 1; i < o.t.length; i++) if (o.s[i] >= minS) return { t: o.t[i], s: o.s[i], i };
    return null;
  }
  /** Decaying impulse from recent onsets: Σ s·exp(−Δt/τ), capped at 1. The workhorse for "hits". */
  pulse(key, t, tau = 0.12, minS = 0.3) {
    const o = this._o(key);
    let v = 0;
    for (let i = this.idx(key, t); i >= 0; i--) {
      const dt = t - o.t[i];
      if (dt > tau * 6) break;
      if (o.s[i] >= minS) v += Math.min(1, o.s[i]) * Math.exp(-dt / tau);
    }
    return Math.min(1, v);
  }
  /** Number of onsets (≥ minS) in [t0, t). Handy for stepping through states on hits. */
  count(key, t0, t, minS = 0) {
    const o = this._o(key);
    let n = 0;
    for (let i = this.idx(key, t); i >= 0 && o.t[i] >= t0; i--) if (o.s[i] >= minS) n++;
    return n;
  }
  /** Onset list in a window: [{t,s}] */
  list(key, t0, t1, minS = 0) {
    const o = this._o(key), res = [];
    for (let i = this.idx(key, t0) + 1; i < o.t.length && o.t[i] < t1; i++) if (o.s[i] >= minS) res.push({ t: o.t[i], s: o.s[i] });
    return res;
  }

  // ---------- lyrics ----------
  line(id) {
    const l = this.lines[id];
    if (!l) throw new Error(`no lyric line "${id}" (have: ${Object.keys(this.lines).join(', ')})`);
    return l;
  }
  /** The word whose cue has passed most recently by t (null before the first). */
  wordAt(t) { let hit = null; for (const w of this.words) { if (w.t <= t) hit = w; else break; } return hit; }
  /** Index of the first output frame (frame i shows t = (i + 0.5) / fps) on which something cued at t is up. */
  cueFrame(t, fps = 60) { return Math.ceil(t * fps - 0.5 - 1e-9); }
}

export async function loadSong(base = '/analysis/') {
  const get = async (f, kind) => {
    const r = await fetch(base + f, { cache: 'no-store' });
    if (!r.ok) throw new Error(`analysis/${f} is missing: run python3 tools/import_song.py`);
    return kind === 'json' ? r.json() : r.arrayBuffer();
  };
  const [meta, env, wave] = await Promise.all([get('analysis.json', 'json'), get('env.bin'), get('wave.bin')]);
  return new Song(meta, env, wave);
}
