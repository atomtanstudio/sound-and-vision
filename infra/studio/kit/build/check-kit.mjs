// Build time only: after the kit is copied into the image, check that every face src/engine/type.js can load is in
// fonts/, the npm packages the page and tools import are there, and every script parses.
import { readFileSync, existsSync, readdirSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
const KIT = new URL('..', import.meta.url).pathname;
const problems = [];
const type = readFileSync(join(KIT, 'src/engine/type.js'), 'utf8');
const files = [...new Set([...type.matchAll(/'([A-Za-z0-9-]+\.ttf)'/g)].map((m) => m[1]))];
for (const f of files) if (!existsSync(join(KIT, 'fonts', f))) problems.push(`font missing: fonts/${f}`);
for (const p of ['three/build/three.module.js', 'harfbuzzjs/dist/index.mjs', 'puppeteer/package.json', 'opentype.js/package.json'])
  if (!existsSync(join(KIT, 'node_modules', p))) problems.push(`package missing: node_modules/${p}`);
const scripts = [...readdirSync(join(KIT, 'src/engine')).map((f) => 'src/engine/' + f), 'src/main.js', 'src/show.js',
  ...readdirSync(join(KIT, 'tools')).filter((f) => f.endsWith('.mjs')).map((f) => 'tools/' + f)];
for (const s of scripts) {
  try { execFileSync('node', ['--check', join(KIT, s)], { stdio: 'pipe' }); } catch (e) { problems.push(`${s}: ${String(e.stderr || e.message).split('\n').slice(0, 4).join(' ')}`); }
}
const pyc = mkdtempSync(join(tmpdir(), 'kit-check-'));
for (const s of readdirSync(join(KIT, 'tools')).filter((f) => f.endsWith('.py'))) {
  try { execFileSync('python3', ['-m', 'py_compile', join(KIT, 'tools', s)], { stdio: 'pipe', env: { ...process.env, PYTHONPYCACHEPREFIX: pyc } }); }
  catch (e) { problems.push(`tools/${s}: ${String(e.stderr || e.message).slice(0, 300)}`); }
}
rmSync(pyc, { recursive: true, force: true });
if (problems.length) { console.error('film kit check failed:\n  ' + problems.join('\n  ')); process.exit(1); }
console.log(`film kit ok: ${files.length} fonts, ${scripts.length} scripts`);
