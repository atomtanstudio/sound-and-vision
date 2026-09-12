import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const study = path.join(root, "public/shader-studies/blue-hour");
const [html, shader, javascript, font, license] = await Promise.all([
  readFile(path.join(study, "index.html"), "utf8"),
  readFile(path.join(study, "blue-hour.frag"), "utf8"),
  readFile(path.join(study, "study.js"), "utf8"),
  readFile(path.join(study, "manrope.woff2")),
  readFile(path.join(study, "Manrope-OFL.txt"), "utf8"),
]);
const safeScript = (text) => text.replace(/<\/script/gi, "<\\/script");
const fontPattern = /url\(["']\.\/manrope\.woff2["']\)/;
const scriptTag = '<script type="module" src="./study.js"></script>';
if (!fontPattern.test(html) || !html.includes(scriptTag)) {
  throw new Error("Study markup changed: font or script embed point is missing.");
}
const standalone = html
  .replace(
    fontPattern,
    `url('data:font/woff2;base64,${font.toString("base64")}')`,
  )
  .replace('href="/video"', 'href="http://127.0.0.1:5190/video"')
  .replace(
    /\s*·\s*<a href="\.\/blue-hour\.html"[^>]*>\s*Download standalone preview<\/a\s*>/,
    "",
  )
  .replace(
    scriptTag,
    `<script id="shader-source" type="text/plain">${safeScript(shader)}</script>\n` +
      `<script type="module">${safeScript(javascript)}</script>\n` +
      `<script id="font-license" type="text/plain">${safeScript(license)}</script>`,
  );
if (standalone.includes('src="./study.js"') || /url\(["']\.\//.test(standalone)) {
  throw new Error("Standalone preview still references a local dependency.");
}
await writeFile(path.join(study, "blue-hour.html"), standalone);
console.log(
  `Built standalone shader study (${Buffer.byteLength(standalone)} bytes).`,
);
