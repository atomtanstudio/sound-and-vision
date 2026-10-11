// Local server: static files for the page + a POST sink that receives raw frames from the renderer page.
//   node tools/server.mjs [port]        serve the film for a browser (http://127.0.0.1:8765/)
// Also exports the Chrome flags every tool launches with: SV_CHROME_ARGS when set (studio.sh sets it: the machine's GPU, or
// SwiftShader with SV_STUDIO_GPU=0), otherwise the GPU through EGL on Linux when an NVIDIA device is present,
// SwiftShader on Linux without one, and Metal on macOS.
import http from 'node:http';
import { createReadStream, statSync, existsSync, readFileSync } from 'node:fs';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = fileURLToPath(new URL('..', import.meta.url));
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json', '.wasm': 'application/wasm', '.ttf': 'font/ttf', '.otf': 'font/otf', '.woff2': 'font/woff2',
  '.bin': 'application/octet-stream', '.m4a': 'audio/mp4', '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.flac': 'audio/flac',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml',
  '.css': 'text/css', '.mp4': 'video/mp4', '.txt': 'text/plain; charset=utf-8', '.md': 'text/markdown; charset=utf-8',
};

/** The film's own settings (song/meta.json), or {} before the app has written it. */
export function filmMeta() {
  try { return JSON.parse(readFileSync(join(ROOT, 'song/meta.json'), 'utf8')); } catch { return {}; }
}

/**
 * @param {(job: string, index: number, data: Buffer) => Promise<void>|void} onFrame
 */
export function startServer({ port = 0, onFrame = null } = {}) {
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      if (req.method === 'POST' && url.pathname === '/frame') {
        const chunks = [];
        for await (const c of req) chunks.push(c);
        if (onFrame) await onFrame(url.searchParams.get('job') || '0', +url.searchParams.get('i'), Buffer.concat(chunks));
        res.writeHead(200).end('ok');
        return;
      }
      let p = decodeURIComponent(url.pathname);
      if (p === '/') p = '/index.html';
      const file = normalize(join(ROOT, p));
      if (!file.startsWith(ROOT) || !existsSync(file) || !statSync(file).isFile()) { res.writeHead(404).end('not found'); return; }
      const size = statSync(file).size;
      const type = MIME[extname(file).toLowerCase()] || 'application/octet-stream';
      const range = req.headers.range && /bytes=(\d*)-(\d*)/.exec(req.headers.range);
      const headers = { 'Content-Type': type, 'Cache-Control': 'no-store', 'Accept-Ranges': 'bytes' };
      if (range) {
        const start = range[1] ? +range[1] : 0, end = range[2] ? +range[2] : size - 1;
        res.writeHead(206, { ...headers, 'Content-Range': `bytes ${start}-${end}/${size}`, 'Content-Length': end - start + 1 });
        createReadStream(file, { start, end }).pipe(res);
      } else {
        res.writeHead(200, { ...headers, 'Content-Length': size });
        createReadStream(file).pipe(res);
      }
    } catch (e) {
      res.writeHead(500).end(String(e));
    }
  });
  return new Promise((resolve) => server.listen(port, '127.0.0.1', () => resolve({ server, port: server.address().port })));
}

const GPU_LINUX = ['--no-sandbox', '--ozone-platform=headless', '--use-angle=gl-egl', '--use-gl=angle', '--ignore-gpu-blocklist', '--enable-gpu'];
const CPU_LINUX = ['--no-sandbox', '--ozone-platform=headless', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'];
const own = process.env.SV_CHROME_ARGS ? process.env.SV_CHROME_ARGS.split(/\s+/).filter(Boolean)
  : process.platform === 'darwin' ? ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist']
  : existsSync('/dev/nvidiactl') ? GPU_LINUX : CPU_LINUX;
export const CHROME_ARGS = [...own, '--enable-webgl', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows', '--autoplay-policy=no-user-gesture-required'];
/** Chromium to drive: PUPPETEER_EXECUTABLE_PATH (set in the studio image), else puppeteer's own. */
export const CHROME = process.env.PUPPETEER_EXECUTABLE_PATH || undefined;

/** Boot the film page in render mode on a puppeteer browser; resolves to the page once window.FILM is ready. */
export async function openFilm(browser, port, { w, h, only = null, onLog = null, timeout = 300000 } = {}) {
  const page = await browser.newPage();
  page.on('console', (m) => { const t = m.text(); if (onLog && !/GPU stall|Download the React/.test(t)) onLog(`[${m.type()}] ${t}`); });
  page.on('pageerror', (e) => onLog && onLog(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/index.html?render=1&w=${w}&h=${h}${only ? '&only=' + encodeURIComponent(only) : ''}`, { waitUntil: 'domcontentloaded', timeout: 0 });
  // poll on a timer, not on animation frames: a page that isn't in front gets no animation frames while the other
  // workers render, and a long render then times out waiting for a page that booted long ago
  await page.waitForFunction('window.FILM?.ready || window.FILM_ERROR', { timeout, polling: 200 });
  const err = await page.evaluate('window.FILM_ERROR || null');
  if (err) throw new Error('the film failed to load:\n' + err);
  return page;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const { port } = await startServer({ port: +(process.argv[2] || 8765) });
  console.log(`serving ${ROOT} on http://127.0.0.1:${port}`);
}
