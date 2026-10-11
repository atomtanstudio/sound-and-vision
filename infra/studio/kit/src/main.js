// Boot: read the song (analysis/, song/meta.json), the fonts and the H3 plates, build the show, then either play live
// against the song or expose a frame-exact render API for the tools: window.FILM and window.seek(t).
//
// The render contract: a frame is a pure function of t. Everything async happens in engine.prepare(t) (plate frames,
// a scene's own loads), which every call below awaits before it draws; engine.render(t) itself never waits.
import { Engine } from './engine/core.js';
import { loadSong } from './engine/audio.js';
import { Plates } from './engine/plates.js';
import * as Type from './engine/type.js';
import { build, FONTS } from './show.js';

const q = new URLSearchParams(location.search);
const renderMode = q.has('render');
const msg = document.getElementById('msg');

try {
  const meta = await fetch('/song/meta.json', { cache: 'no-store' }).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
  const W = +(q.get('w') || meta.width || 1920), H = +(q.get('h') || meta.height || 1080);
  const FPS = +(meta.fps || 60);
  const canvas = document.getElementById('view');
  canvas.width = W; canvas.height = H;
  canvas.style.aspectRatio = `${W} / ${H}`;
  if (renderMode) { document.body.classList.add('render'); canvas.style.width = W + 'px'; canvas.style.height = H + 'px'; }
  if (meta.title) document.title = meta.title + (meta.artist ? ` — ${meta.artist}` : '');

  const [song, plates] = await Promise.all([loadSong(), new Plates().init(), Type.loadFonts('/fonts/', FONTS)]);
  plates.strict = renderMode;
  const engine = new Engine(canvas, { width: W, height: H, song });
  plates.W = engine.DW; plates.H = engine.DH;
  engine.plates = plates;
  const timeline = await build(engine, { only: q.get('only'), meta });
  engine.timeline = timeline;
  await timeline.init(engine);
  msg.remove();

  const opts = (o = {}) => ({ nsub: o.nsub ?? 1, shutter: o.shutter ?? 0.5, fps: o.fps ?? FPS });
  const api = (window.FILM = {
    engine, song, timeline, plates, meta, Type, W, H, fps: FPS,
    /** Load what the frame centred on t needs (plate frames…). */
    prepare(t, o = {}) { return engine.prepare(t, opts(o)); },
    /** Paint exactly the frame centred on song time t. o: { nsub, shutter, fps } */
    async still(t, o = {}) { const p = opts(o); await engine.prepare(t, p); engine.render(t, { ...p, frameIndex: Math.floor(t * p.fps + 1e-6) }); },
    /** Song time shown by output frame i (frames are centred: frame i covers [i/fps, (i+1)/fps)). */
    frameTime(i, fps = FPS) { return (i + 0.5) / fps; },
    /** First output frame on which something cued at song time t is up. */
    cueFrame(t, fps = FPS) { return song.cueFrame(t, fps); },
    /** Every lyric word with its sung time, cue and cue frame, optionally only those cued in [from, to). */
    cues(from = -Infinity, to = Infinity, fps = FPS) {
      return song.words.filter((w) => w.t >= from && w.t < to)
        .map((w) => ({ line: w.line.id, i: w.i, word: w.w, sung: w.raw, cue: +w.t.toFixed(4), how: w.how, frame: song.cueFrame(w.t, fps) }));
    },
    /** Render frames [from, to) and POST raw RGBA to the render server (tools/render.mjs). */
    async range({ from, to, fps = FPS, nsub = 4, shutter = 0.5, job = '0' }) {
      const buf = new Uint8Array(W * H * 4);
      const st = { prepare: 0, render: 0, read: 0, post: 0 };
      for (let i = from; i < to; i++) {
        const t = (i + 0.5) / fps;
        const a0 = performance.now();
        await engine.prepare(t, { nsub, shutter, fps });
        const a = performance.now();
        try { engine.render(t, { nsub, shutter, fps, frameIndex: i }); }
        catch (e) { throw new Error(`frame ${i} (t=${t.toFixed(3)}s): ${e && e.message}`); }
        const b = performance.now();
        engine.readPixels(buf);
        const c = performance.now();
        const res = await fetch(`/frame?job=${job}&i=${i}`, { method: 'POST', body: buf });
        if (!res.ok) throw new Error(`frame ${i}: ${res.status}`);
        st.prepare += a - a0; st.render += b - a; st.read += c - b; st.post += performance.now() - c;
      }
      return st;
    },
    /** Contact sheet of frames at the given song times → JPEG data URL. */
    async sheet(times, { cols = 4, tw = 480, nsub = 1, fps = FPS, labels = true, quality = 0.86 } = {}) {
      const th = Math.round((tw * H) / W), pad = labels ? 22 : 0;
      const rows = Math.ceil(times.length / cols);
      const c = document.createElement('canvas');
      c.width = cols * tw; c.height = rows * (th + pad);
      const x = c.getContext('2d');
      x.fillStyle = '#111'; x.fillRect(0, 0, c.width, c.height);
      for (let i = 0; i < times.length; i++) {
        const t = times[i];
        await engine.prepare(t, { nsub, fps });
        engine.render(t, { nsub, fps, frameIndex: Math.floor(t * fps + 1e-6) });
        const cx = (i % cols) * tw, cy = Math.floor(i / cols) * (th + pad);
        x.imageSmoothingQuality = 'high';
        x.drawImage(canvas, cx, cy, tw, th);
        if (labels) {
          const bp = song.barPos(t), bar = Math.floor(bp), beat = (bp - bar) * song.meter;
          const clip = timeline.at(t);
          x.fillStyle = '#ddd'; x.font = `${tw < 400 ? 11 : 13}px monospace`; x.textBaseline = 'middle';
          x.fillText(`${t.toFixed(2)}s  f${Math.floor(t * fps + 1e-6)}  bar ${bar}.${(beat + 1).toFixed(1)}  ${clip ? clip.id : ''}`, cx + 6, cy + th + pad / 2 + 1);
        }
      }
      return c.toDataURL('image/jpeg', quality);
    },
    frameJPEG(quality = 0.92) { return canvas.toDataURL('image/jpeg', quality); },
    framePNG() { return canvas.toDataURL('image/png'); },
    ready: true,
  });
  /** The render contract's entry point: paint exactly the frame at song time t (resolves once it is painted). */
  window.seek = (t, o = {}) => api.still(t, o);

  if (!renderMode) {
    const audio = document.getElementById('audio');
    const play = document.getElementById('play'), seek = document.getElementById('seek'), time = document.getElementById('time');
    seek.max = String(song.duration);
    const fmt = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(2).padStart(5, '0')}`;
    let last = -1;
    const tick = () => {
      const t = audio.currentTime;
      if (t !== last || !audio.paused) {
        engine.prepare(t).catch((e) => console.error(e));   // live: start loading, draw what is there
        engine.render(t, { nsub: 1, fps: FPS });
        const bp = song.barPos(t);
        const clip = timeline.at(t);
        time.textContent = `${fmt(t)} / ${fmt(song.duration)}  ·  bar ${Math.floor(bp)}.${Math.floor((bp % 1) * song.meter) + 1}  ·  ${clip ? clip.id : '—'}`;
        if (document.activeElement !== seek) seek.value = String(t);
        last = t;
      }
      requestAnimationFrame(tick);
    };
    play.onclick = () => (audio.paused ? audio.play() : audio.pause());
    audio.onplay = () => (play.textContent = '❚❚');
    audio.onpause = () => (play.textContent = '▶');
    seek.oninput = () => { audio.currentTime = +seek.value; };
    addEventListener('keydown', (e) => {
      if (e.code === 'Space') { e.preventDefault(); play.onclick(); }
      const bar = song.barPos(audio.currentTime);
      if (e.code === 'ArrowRight') audio.currentTime = song.bar(Math.floor(bar) + (e.shiftKey ? 4 : 1));
      if (e.code === 'ArrowLeft') audio.currentTime = song.bar(Math.max(1, Math.ceil(bar) - (e.shiftKey ? 4 : 1)));
    });
    if (q.has('t')) audio.currentTime = +q.get('t');
    tick();
  }
} catch (err) {
  console.error(err);
  window.FILM_ERROR = String(err && err.stack ? err.stack : err);
  if (msg) msg.textContent = 'error — see console';
}
