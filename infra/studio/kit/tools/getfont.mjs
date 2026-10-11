// Fetch a font family from the Google Fonts repository (open licences: OFL, Apache, UFL) into fonts-extra/, for a face the
// image's fonts/ doesn't have. Only github.com/google/fonts is contacted.
//   node tools/getfont.mjs "Russo One" ["Space Grotesk" …]      → fonts-extra/RussoOne-Regular.ttf, …
//   node tools/getfont.mjs --list                                → what's in fonts/ and fonts-extra/
import { mkdir, readdir, writeFile } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'fonts-extra');
const API = 'https://api.github.com/repos/google/fonts/contents/';
const RAW = 'https://raw.githubusercontent.com/google/fonts/main/';

async function list() {
  for (const dir of ['fonts', 'fonts-extra']) {
    const files = await readdir(join(ROOT, dir)).catch(() => []);
    console.log(`${dir}/ (${files.length}):\n  ${files.sort().join('\n  ')}`);
  }
}

async function family(name) {
  const slug = name.toLowerCase().replace(/[^a-z0-9]/g, '');
  for (const licence of ['ofl', 'apache', 'ufl']) {
    const r = await fetch(API + `${licence}/${slug}`, { headers: { 'User-Agent': 'sv-film-kit', Accept: 'application/vnd.github+json' } });
    if (r.status === 404) continue;
    if (!r.ok) throw new Error(`GitHub answered ${r.status} for ${name}`);
    const files = (await r.json()).filter((f) => /\.(ttf|otf)$/i.test(f.name));
    if (!files.length) continue;
    await mkdir(OUT, { recursive: true });
    for (const f of files) {
      const b = await fetch(RAW + `${licence}/${slug}/${encodeURIComponent(f.name)}`);
      if (!b.ok) throw new Error(`couldn't download ${f.name} (${b.status})`);
      await writeFile(join(OUT, f.name), Buffer.from(await b.arrayBuffer()));
      console.log(`fonts-extra/${f.name}`);
    }
    return;
  }
  throw new Error(`no family called "${name}" in the Google Fonts repository (try its exact name, e.g. "Space Grotesk")`);
}

const args = process.argv.slice(2);
if (!args.length) { console.log('usage: node tools/getfont.mjs "Family Name" … | --list'); process.exit(2); }
if (args[0] === '--list') await list();
else for (const name of args) {
  try { await family(name); } catch (e) { console.error(String(e.message || e)); process.exitCode = 1; }
}
