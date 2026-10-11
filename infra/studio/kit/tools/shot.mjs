// Review pictures, rendered by the same code path as the film (so a still is exactly the frame the render will hold).
//   node tools/shot.mjs still 66.05 70.2                 full-size stills (PNG with --png) → out/review/
//   node tools/shot.mjs sheet 60:75:0.5                  contact sheet, from:to:step (or a comma list of times)
//   node tools/shot.mjs beats 60 90                      one frame per beat in [60, 90) s, just after each beat lands
//   node tools/shot.mjs bars 30 38 --per 4               N frames per bar, bars 30 up to 38
//   node tools/shot.mjs sections                         one frame a beat into each section
//   node tools/shot.mjs strip 66.0 --n 12                consecutive frames from 66.0 s (pops, overlaps, fast moves)
//   node tools/shot.mjs phone 60:90:1                    the 360 px phone sheet: every tile 360 px wide (does it read?)
// Every sheet mode also takes --phone (write the 360 px version too), --cols, --tw (tile width), --nsub, --name, --out.
// Times are moved to the centre of the frame that shows them (frame i shows (i + 0.5) / fps), unless --raw.
import puppeteer from 'puppeteer';
import { writeFileSync, mkdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { startServer, openFilm, ROOT, CHROME_ARGS, CHROME, filmMeta } from './server.mjs';

const argv = process.argv.slice(2);
const mode = argv.shift();
const MODES = ['still', 'sheet', 'beats', 'bars', 'sections', 'strip', 'phone'];
if (!MODES.includes(mode)) { console.log(`usage: node tools/shot.mjs <${MODES.join('|')}> …  (see the top of tools/shot.mjs)`); process.exit(2); }
const flags = {}; const pos = [];
for (let i = 0; i < argv.length; i++) {
  if (argv[i].startsWith('--')) { flags[argv[i].slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : '1'; } else pos.push(argv[i]);
}
const meta = filmMeta();
const fps = +(meta.fps || 60);
const outDir = join(ROOT, flags.out || 'out/review');
mkdirSync(outDir, { recursive: true });
const aspect = (meta.height || 1080) / (meta.width || 1920);
const W = +(flags.w || (mode === 'still' ? (meta.width || 1920) : 960)), H = +(flags.h || Math.round(W * aspect));
const nsub = +(flags.nsub || (mode === 'still' ? 4 : 1));
const centre = (t) => (flags.raw ? t : (Math.floor(t * fps + 1e-6) + 0.5) / fps);
const firstFrameFrom = (t) => (Math.ceil(t * fps - 0.5 - 1e-9) + 0.5) / fps;   // first frame whose centre is ≥ t

const { server, port } = await startServer();
const browser = await puppeteer.launch({ headless: true, executablePath: CHROME, args: CHROME_ARGS, defaultViewport: { width: W, height: H, deviceScaleFactor: 1 }, protocolTimeout: 0 });
const logs = [];
let page;
try {
  page = await openFilm(browser, port, { w: W, h: H, only: flags.only, onLog: (l) => logs.push(l), timeout: 120000 });
} catch (e) { console.log(e.message); console.log(logs.join('\n')); await browser.close(); server.close(); process.exit(1); }

const save = (name, dataUrl) => { const f = join(outDir, name); writeFileSync(f, Buffer.from(dataUrl.split(',')[1], 'base64')); console.log(relative(ROOT, f)); };
const stamp = (t) => t.toFixed(2).padStart(6, '0');
const t0 = Date.now();
try {
  if (mode === 'still') {
    for (const p of pos) {
      const t = centre(+p);
      const url = await page.evaluate(async (t, nsub, png) => { await FILM.still(t, { nsub }); return png ? FILM.framePNG() : FILM.frameJPEG(0.92); }, t, nsub, !!flags.png);
      save(`${flags.name || 'still'}_${stamp(t)}.${flags.png ? 'png' : 'jpg'}`, url);
    }
  } else {
    let times = [];
    if (mode === 'beats') {
      const [a, b] = [+(pos[0] ?? 0), +(pos[1] ?? Infinity)];
      times = (await page.evaluate(() => FILM.song.beats)).filter((x) => x >= a && x < b).map(firstFrameFrom);
    } else if (mode === 'bars') {
      const [b0, b1] = pos.map(Number); const per = +(flags.per || 4);
      times = (await page.evaluate((b0, b1, per) => { const out = []; for (let b = b0; b < b1 - 1e-9; b += 1 / per) out.push(FILM.song.bar(b)); return out; }, b0, b1, per)).map(firstFrameFrom);
    } else if (mode === 'sections') {
      times = (await page.evaluate(() => FILM.song.sectionList.map((s) => Math.min(s.t1 - 0.05, s.t0 + 60 / Math.max(1, FILM.song.tempo || 120))))).map(centre);
    } else if (mode === 'strip') {
      const n = +(flags.n || 12), a = centre(+pos[0]);
      for (let i = 0; i < n; i++) times.push(a + i / fps);
      flags.cols = flags.cols || String(Math.min(n, 6));
    } else {
      for (const p of pos) {
        if (p.includes(':')) { const [a, b, s] = p.split(':').map(Number); for (let t = a; t < b - 1e-9; t += s) times.push(centre(+t.toFixed(4))); }
        else times.push(...p.split(',').map((x) => centre(+x)));
      }
    }
    if (!times.length) throw new Error('no times to render');
    const phoneOnly = mode === 'phone';
    const sheets = [];
    if (!phoneOnly) sheets.push({ cols: +(flags.cols || 4), tw: +(flags.tw || 480), suffix: '' });
    if (phoneOnly || flags.phone) sheets.push({ cols: +(flags.pcols || 5), tw: 360, suffix: '_phone' });
    for (const s of sheets) {
      const perSheet = +(flags.max || s.cols * 6);
      for (let i = 0, n = 0; i < times.length; i += perSheet, n++) {
        const chunk = times.slice(i, i + perSheet);
        const url = await page.evaluate((chunk, cols, tw, nsub) => FILM.sheet(chunk, { cols, tw, nsub }), chunk, s.cols, s.tw, nsub);
        save(`${flags.name || mode}_${stamp(chunk[0])}${times.length > perSheet ? '_' + n : ''}${s.suffix}.jpg`, url);
      }
    }
  }
} catch (e) {
  console.log('failed: ' + e.message);
  if (logs.length) console.log(logs.slice(0, 30).join('\n'));
  await browser.close(); server.close(); process.exit(1);
}
console.log(`done in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
if (logs.length) console.log(logs.slice(0, 30).join('\n'));
await browser.close();
server.close();
