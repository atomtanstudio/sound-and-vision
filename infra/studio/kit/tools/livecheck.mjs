// Sanity check for the live player page (index.html without ?render, what a person previews in a browser): it loads,
// seeks, plays a moment against the song and draws without errors. Writes a screenshot to out/review/live.jpg.
//   node tools/livecheck.mjs [song seconds]
import puppeteer from 'puppeteer';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { startServer, ROOT, CHROME_ARGS, CHROME } from './server.mjs';
const at = +(process.argv[2] || 30);
const { server, port } = await startServer();
const browser = await puppeteer.launch({ headless: true, executablePath: CHROME, args: CHROME_ARGS, defaultViewport: { width: 1440, height: 900 } });
const page = await browser.newPage();
const errs = [];
page.on('pageerror', (e) => errs.push(e.message));
page.on('console', (m) => { if (m.type() === 'error' && !/404/.test(m.text())) errs.push(m.text()); });
await page.goto(`http://127.0.0.1:${port}/index.html?t=${at}`, { waitUntil: 'load' });
await page.waitForFunction('window.FILM?.ready || window.FILM_ERROR', { timeout: 120000 });
const res = await page.evaluate(async () => {
  const a = document.getElementById('audio');
  await a.play().catch((e) => (window.__playErr = String(e)));
  await new Promise((r) => setTimeout(r, 1500));
  a.pause();
  return { err: window.FILM_ERROR || null, playErr: window.__playErr || null, time: a.currentTime, label: document.getElementById('time').textContent, dur: a.duration };
});
mkdirSync(join(ROOT, 'out/review'), { recursive: true });
await page.screenshot({ path: join(ROOT, 'out/review/live.jpg'), type: 'jpeg', quality: 80 });
console.log(JSON.stringify(res), errs.length ? 'errors: ' + JSON.stringify(errs) : 'no errors', '→ out/review/live.jpg');
await browser.close(); server.close();
process.exit(res.err || errs.length ? 1 : 0);
