import { build } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { mkdir, copyFile } from "node:fs/promises";
const outDir = resolve(process.argv[2] || "dist-renderer");
await build({
  configFile: false,
  plugins: [react()],
  publicDir: false,
  build: {
    outDir,
    emptyOutDir: true,
    rollupOptions: { input: resolve("visualizer-render.html") },
  },
});
await mkdir(resolve(outDir, "visualizers"), { recursive: true });
await copyFile(
  "public/visualizers/collection.frag",
  resolve(outDir, "visualizers/collection.frag"),
);
