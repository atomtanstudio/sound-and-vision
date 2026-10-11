// Where does render time go? Times one full-quality frame (prepare + render + readPixels) at a list of song times.
//   node tools/profile.mjs 12 66.05 120 --nsub 4 [--w 1920]
import puppeteer from 'puppeteer';
import { startServer, openFilm, CHROME_ARGS, CHROME, filmMeta } from './server.mjs';
const argv = process.argv.slice(2), flags = {}, pos = [];
for (let i = 0; i < argv.length; i++) { if (argv[i].startsWith('--')) flags[argv[i].slice(2)] = argv[++i]; else pos.push(+argv[i]); }
const meta = filmMeta();
const W = +(flags.w || meta.width || 1920), H = Math.round((W * (meta.height || 1080)) / (meta.width || 1920)), nsub = +(flags.nsub || 4), fps = +(meta.fps || 60);
const { server, port } = await startServer();
const browser = await puppeteer.launch({ headless: true, executablePath: CHROME, args: CHROME_ARGS, defaultViewport: { width: W, height: H, deviceScaleFactor: 1 }, protocolTimeout: 0 });
const page = await openFilm(browser, port, { w: W, h: H });
const res = await page.evaluate(async (times, nsub, W, H, fps) => {
  const buf = new Uint8Array(W * H * 4), out = [];
  const gl = FILM.engine.gl, x = gl.getExtension('WEBGL_debug_renderer_info');
  const gpu = x ? gl.getParameter(x.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
  for (const t of times) {
    await FILM.prepare(t, { nsub }); FILM.engine.render(t, { nsub, fps }); FILM.engine.readPixels(buf);   // warm caches
    const a = performance.now();
    for (let k = 0; k < 3; k++) { const tk = t + k / fps; await FILM.prepare(tk, { nsub }); FILM.engine.render(tk, { nsub, fps }); FILM.engine.readPixels(buf); }
    const clip = FILM.timeline.at(t);
    out.push([t, clip ? clip.id : '-', Math.round((performance.now() - a) / 3)]);
  }
  return { gpu, out };
}, pos, nsub, W, H, fps);
console.log(`${W}×${H}, ${nsub} sub-frames, on ${res.gpu}`);
for (const [t, id, ms] of res.out) console.log(`${String(t).padStart(8)} s  ${String(id).padEnd(14)} ${String(ms).padStart(5)} ms/frame`);
await browser.close(); server.close();
