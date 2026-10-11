// Offline renderer: N headless-Chrome workers each render a contiguous frame range and stream raw RGBA to their own
// ffmpeg; the segments are then joined and muxed with the song.
//   node tools/render.mjs                                    the whole song → out/film.mp4
//   node tools/render.mjs --from 65.9 --to 69.9 --out out/review/chorus1.mp4
//   node tools/render.mjs --w 1080 --h 1920 --out out/final-9x16.mp4
// Options: --from/--to (song seconds), --fps (song/meta.json, else 60), --nsub 4 (motion-blur sub-frames), --shutter 0.5,
// --w/--h (song/meta.json, else 1920×1080), --workers 4, --crf 16, --preset slow, --maxrate <Mbit/s>, --noaudio, --keep.
// Frame i shows song time (i + 0.5) / fps. A whole-song render carries song/song.m4a as a stream copy (bit-identical);
// an excerpt carries the same stretch of it re-encoded. Next to the film it writes <out>.json: what was rendered, how
// (tools/qa.py reads it to know which song time the file starts at), and how long it took.
import puppeteer from 'puppeteer';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { join, dirname, relative } from 'node:path';
import { startServer, openFilm, ROOT, CHROME_ARGS, CHROME, filmMeta } from './server.mjs';

const flags = {};
for (let i = 2; i < process.argv.length; i++) if (process.argv[i].startsWith('--')) flags[process.argv[i].slice(2)] = process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[++i] : '1';
const meta = filmMeta();
const fps = +(flags.fps || meta.fps || 60), nsub = +(flags.nsub || 4), shutter = +(flags.shutter || 0.5);
const W = +(flags.w || meta.width || 1920), H = +(flags.h || (flags.w ? Math.round((W * (meta.height || 1080)) / (meta.width || 1920)) : meta.height || 1080));
const analysisFile = join(ROOT, 'analysis/analysis.json');
if (!existsSync(analysisFile)) { console.error('analysis/analysis.json is missing: run python3 tools/import_song.py first'); process.exit(1); }
const DUR = JSON.parse(readFileSync(analysisFile, 'utf8')).duration;
const from = Math.max(0, +(flags.from || 0)), to = Math.min(DUR, +(flags.to || DUR));
const workers = Math.max(1, +(flags.workers || 4));
const crf = flags.crf || '16', preset = flags.preset || 'slow';
// --maxrate N caps the video at N Mbit/s (capped CRF), which bounds the file size: size ≤ N × duration / 8 + audio
const cap = flags.maxrate ? ['-maxrate', `${flags.maxrate}M`, '-bufsize', `${2 * flags.maxrate}M`] : [];
const out = join(ROOT, flags.out || 'out/film.mp4');
const audio = flags.noaudio ? null : join(ROOT, flags.audio || 'song/song.m4a');
if (audio && !existsSync(audio)) { console.error(`${relative(ROOT, audio)} is missing (use --noaudio for picture only)`); process.exit(1); }
const tmp = join(ROOT, 'out/tmp_' + Date.now());
mkdirSync(tmp, { recursive: true }); mkdirSync(dirname(out), { recursive: true });

const f0 = Math.round(from * fps), f1 = Math.round(to * fps), total = f1 - f0;
if (total <= 0) { console.error(`nothing to render between ${from} and ${to} s`); process.exit(1); }
const per = Math.ceil(total / workers);
const jobs = [];
for (let k = 0; k < workers; k++) {
  const a = f0 + k * per, b = Math.min(f1, a + per);
  if (a < b) jobs.push({ id: String(k), a, b, next: a, seg: join(tmp, `seg_${String(k).padStart(3, '0')}.mp4`) });
}
console.log(`rendering frames ${f0}–${f1 - 1} (${from.toFixed(3)}–${to.toFixed(3)} s, ${total} frames) at ${W}×${H}, ${fps} fps, ${nsub} sub-frames, on ${jobs.length} workers`);

for (const j of jobs) {
  const ff = spawn('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', `${W}x${H}`, '-r', String(fps), '-i', 'pipe:0',
    '-vf', 'vflip,format=yuv420p', '-c:v', 'libx264', '-preset', preset, '-crf', crf, ...cap, '-profile:v', 'high', '-x264-params', 'keyint=120:min-keyint=1:bframes=3:aq-mode=3:deblock=-1,-1:psy-rd=1.0,0.15',
    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv', '-movflags', '+faststart', j.seg], { stdio: ['pipe', 'inherit', 'inherit'] });
  j.ff = ff;
  j.done = new Promise((res, rej) => ff.on('close', (c) => (c === 0 ? res() : rej(new Error(`ffmpeg ${j.id} exit ${c}`)))));
}
const sinks = new Map(jobs.map((j) => [j.id, j]));

let rendered = 0, lastShown = 0;
const t0 = Date.now();
const { server, port } = await startServer({
  onFrame: async (job, i, data) => {
    const j = sinks.get(job);
    if (i !== j.next) throw new Error(`job ${job}: frame ${i} out of order (expected ${j.next})`);
    j.next++;
    if (!j.ff.stdin.write(data)) await new Promise((r) => j.ff.stdin.once('drain', r));
    rendered++;
    if (rendered - lastShown >= 120 || rendered === total) {
      lastShown = rendered;
      const el = (Date.now() - t0) / 1000, rate = rendered / el;
      console.log(`${rendered}/${total} frames  ${rate.toFixed(1)} fps  eta ${((total - rendered) / rate).toFixed(0)} s`);
    }
  },
});

const browser = await puppeteer.launch({ headless: true, executablePath: CHROME, args: CHROME_ARGS, defaultViewport: { width: W, height: H, deviceScaleFactor: 1 }, protocolTimeout: 0 });
const fail = async (e) => {
  console.error(`\nrender failed: ${e && e.message ? e.message : e}`);
  for (const j of jobs) { try { j.ff.kill('SIGKILL'); } catch {} }
  await browser.close().catch(() => {});
  server.close();
  process.exit(1);
};
let gpu = '';
try {
  await Promise.all(jobs.map(async (j) => {
    // several pages boot at once, each shaping its own fonts: openFilm waits as long as it takes
    const page = await openFilm(browser, port, { w: W, h: H, onLog: (l) => { if (/pageerror|\[error\]/.test(l)) console.log(`[job ${j.id}] ${l}`); } });
    if (j.id === '0') gpu = await page.evaluate(() => { const gl = FILM.engine.gl, x = gl.getExtension('WEBGL_debug_renderer_info'); return x ? gl.getParameter(x.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER); });
    // Stop CDP network events: otherwise every frame upload is echoed (base64) to the driver.
    await page._client().send('Network.disable');
    j.stats = await page.evaluate((o) => FILM.range(o), { from: j.a, to: j.b, fps, nsub, shutter, job: j.id });
    j.ff.stdin.end();
    await j.done;
    await page.close();
  }));
} catch (e) { await fail(e); }
await browser.close();
server.close();
const renderSec = (Date.now() - t0) / 1000;
console.log(`rendered ${total} frames in ${renderSec.toFixed(1)} s (${(total / renderSec).toFixed(1)} fps) on ${gpu}`);
const st = jobs.reduce((a, j) => ({ prepare: a.prepare + j.stats.prepare, render: a.render + j.stats.render, read: a.read + j.stats.read, post: a.post + j.stats.post }), { prepare: 0, render: 0, read: 0, post: 0 });
const ms = Object.fromEntries(Object.entries(st).map(([k, v]) => [k, +(v / total).toFixed(2)]));
console.log(`per frame per worker (ms): prepare ${ms.prepare}  render ${ms.render}  readPixels ${ms.read}  upload ${ms.post}`);

const list = join(tmp, 'list.txt');
writeFileSync(list, jobs.map((j) => `file '${j.seg.replace(/'/g, "'\\''")}'`).join('\n'));
const args = ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list];
const whole = f0 === 0 && to >= DUR - 1e-3;
if (audio && whole) args.push('-i', audio, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'copy');
else if (audio) args.push('-ss', String(f0 / fps), '-t', String(total / fps), '-i', audio, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-shortest');
else args.push('-c', 'copy');
// make the colour description explicit (BT.709 primaries / transfer / matrix) so no player has to guess
args.push('-bsf:v', 'h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1', '-movflags', '+faststart', out);
await new Promise((res, rej) => spawn('ffmpeg', args, { stdio: 'inherit' }).on('close', (c) => (c === 0 ? res() : rej(new Error('mux failed'))))).catch(fail);
if (!flags.keep && existsSync(out)) rmSync(tmp, { recursive: true, force: true });
writeFileSync(out + '.json', JSON.stringify({
  file: relative(ROOT, out), from: f0 / fps, to: f1 / fps, firstFrame: f0, frames: total, fps, nsub, shutter, width: W, height: H,
  frameTime: '(firstFrame + j + 0.5) / fps for frame j of this file', audio: audio ? relative(ROOT, audio) + (whole ? ' (stream copy)' : ' (excerpt, AAC 256k)') : null,
  crf: +crf, preset, workers: jobs.length, gpu, renderSeconds: +renderSec.toFixed(1), msPerFrame: ms,
}, null, 1));
console.log(relative(ROOT, out));
