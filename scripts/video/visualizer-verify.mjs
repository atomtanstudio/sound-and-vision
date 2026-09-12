// Copyright 2026 Sound/Vision contributors. SPDX-License-Identifier: Apache-2.0
// Compiles the real shader and checks rendering, audio influence, and determinism.
import { spawnSync } from "node:child_process";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const temp = resolve("/private/tmp/soundvision-visualizer-verify");
await mkdir(temp, { recursive: true });
const binary = resolve(temp, "renderer"),
  frames = resolve(temp, "frames.csv");
const build = spawnSync(
  "clang++",
  [
    "-O3",
    "-std=c++17",
    resolve(root, "scripts/video/visualizer-native.cpp"),
    "-framework",
    "OpenGL",
    "-o",
    binary,
  ],
  { encoding: "utf8" },
);
if (build.status !== 0) throw Error(build.stderr);
const rows = [];
for (let id = 0; id < 8; id++) {
  const quiet = [12, 0, 0, 0, 0, 0, id, id, 0].join(",");
  rows.push(
    quiet,
    quiet,
    [12, 0.85, 0.65, 0.55, 0.9, 0.8, id, id, 0].join(","),
  );
}
await writeFile(frames, rows.join("\n") + "\n");
const rendered = spawnSync(
  binary,
  [resolve(root, "public/visualizers/collection.frag"), frames, "320", "180"],
  { maxBuffer: 32 * 1024 * 1024 },
);
if (rendered.status !== 0) throw Error(rendered.stderr.toString());
const size = 320 * 180 * 3;
if (rendered.stdout.length !== 24 * size) throw Error("Frame count mismatch");
const results = [];
for (let id = 0; id < 8; id++) {
  const off = rendered.stdout.subarray(id * 3 * size, (id * 3 + 1) * size),
    repeat = rendered.stdout.subarray((id * 3 + 1) * size, (id * 3 + 2) * size),
    on = rendered.stdout.subarray((id * 3 + 2) * size, (id * 3 + 3) * size);
  let difference = 0,
    minimum = 255,
    maximum = 0;
  for (let i = 0; i < size; i++) {
    difference += Math.abs(off[i] - on[i]);
    minimum = Math.min(minimum, off[i]);
    maximum = Math.max(maximum, off[i]);
  }
  if (!off.equals(repeat)) throw Error(`Preset ${id} is nondeterministic`);
  const meanAudioDifference = difference / size;
  if (meanAudioDifference < 0.5)
    throw Error(
      `Preset ${id} has insufficient audio influence (${meanAudioDifference})`,
    );
  if (maximum - minimum < 20)
    throw Error(`Preset ${id} rendered insufficient image range`);
  results.push({
    preset: id,
    deterministic: true,
    meanAudioPixelDifference: Number(meanAudioDifference.toFixed(3)),
    range: [minimum, maximum],
    sha256: createHash("sha256").update(off).digest("hex"),
  });
}
const report = {
  renderer: rendered.stderr.toString().split("\n")[0],
  resolution: [320, 180],
  allCompiled: true,
  allRendered: true,
  results,
};
await writeFile(
  resolve(root, "public/visualizers/verification.json"),
  JSON.stringify(report, null, 2) + "\n",
);
console.log(JSON.stringify(report, null, 2));
