// Dedicated Legion service. Bound to loopback; reached through the app's SSH tunnel.
import { createServer } from "node:http";
import { readFileSync, createReadStream, statSync } from "node:fs";
import { resolve, relative, extname } from "node:path";
import { timingSafeEqual } from "node:crypto";
import { createVisualizerExports } from "./visualizer-export-api.mjs";
const root = process.cwd();
const token = readFileSync(process.env.SOUND_VISION_TOKEN_FILE, "utf8").trim();
if (!token) throw Error("Missing render service authentication");
const assets = resolve(root, "dist-renderer");
const exports = createVisualizerExports({
  projectRoot: root,
  backend: "http://127.0.0.1:5191",
  token,
  outputRoot: resolve(root, "data/renders"),
  renderOrigin: "http://127.0.0.1:5192",
  renderHost: "Legion",
});
const mime = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".woff2": "font/woff2",
  ".frag": "text/plain",
};
const server = createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1:5192");
  if (url.pathname === "/health") {
    res.setHeader("Content-Type", "application/json");
    return res.end(JSON.stringify({ ready: true, renderer: "Legion" }));
  }
  if (url.pathname.startsWith("/local-api/visualizer-renders")) {
    const supplied = Buffer.from(req.headers.authorization || "");
    const expected = Buffer.from(`Bearer ${token}`);
    if (
      supplied.length !== expected.length ||
      !timingSafeEqual(supplied, expected)
    ) {
      res.statusCode = 401;
      return res.end('{"detail":"Unauthorized"}');
    }
    void exports.middleware(req, res, () => {
      res.statusCode = 404;
      res.end();
    });
    return;
  }
  // Only the compiled, credential-free composition is served as static content.
  try {
    const file = resolve(assets, "." + decodeURIComponent(url.pathname));
    if (
      relative(assets, file).startsWith("..") ||
      !["GET", "HEAD"].includes(req.method) ||
      !statSync(file).isFile()
    )
      throw Error();
    res.setHeader(
      "Content-Type",
      mime[extname(file)] || "application/octet-stream",
    );
    if (req.method === "HEAD") return res.end();
    const stream = createReadStream(file);
    stream.on("error", () => res.destroy());
    res.on("close", () => stream.destroy());
    stream.pipe(res);
  } catch {
    res.statusCode = 404;
    res.end();
  }
});
server.listen(5192, "127.0.0.1", () => {
  console.log("Legion visualizer renderer listening on 127.0.0.1:5192");
  void exports.start();
});
for (const signal of ["SIGTERM", "SIGINT"])
  process.once(signal, () => {
    exports.close();
    server.close();
  });
