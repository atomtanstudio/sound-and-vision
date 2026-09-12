// Copyright 2026 Sound/Vision contributors. SPDX-License-Identifier: Apache-2.0
import { spawn, spawnSync } from "node:child_process";
import { readFile, writeFile, mkdir, stat, rename } from "node:fs/promises";
import { writeFileSync, renameSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { visualizerSchedule } from "../../src/video/visualizers/schedule.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const args = Object.fromEntries(
  process.argv.slice(2).reduce((pairs, arg, i, all) => {
    if (arg.startsWith("--")) pairs.push([arg.slice(2), all[i + 1]]);
    return pairs;
  }, []),
);
if (!args.analysis || !args.output) {
  console.error(
    "Usage: node scripts/video/visualizer-render.mjs --analysis frames.json --output background.mp4 [--audio song.mp3] [--width 1920 --height 1080 --sequence 0,5,1,2,3,7,4,6 --interval 20 --duration 193]",
  );
  process.exit(1);
}
if (process.platform !== "darwin")
  throw Error(
    "Native renderer currently requires macOS CGL. The WebGL preview is portable.",
  );
const analysis = JSON.parse(await readFile(resolve(args.analysis), "utf8"));
const fps = Number(analysis.fps ?? 24),
  width = Number(args.width ?? 1920),
  height = Number(args.height ?? 1080);
const threads = Number(args.threads ?? 4);
if (!Number.isInteger(threads) || threads < 1 || threads > 32)
  throw Error("Encoder threads must be between 1 and 32");
const duration = Math.min(
  Number(args.duration ?? analysis.duration),
  Number(analysis.duration),
);
const count = Math.ceil(duration * fps);
if (!Array.isArray(analysis.frames) || analysis.frames.length < count)
  throw Error(`Expected at least ${count} audio frames`);
if (
  !Number.isFinite(duration) ||
  duration <= 0 ||
  !Number.isFinite(fps) ||
  fps <= 0 ||
  fps > 120
)
  throw Error("Invalid duration or frame rate");
const exactSchedule = args.visualizer
  ? visualizerSchedule(duration, args.visualizer, fps)
  : null;
const sequence = exactSchedule
  ? exactSchedule.map((s) => s.preset)
  : (args.sequence ?? "0,5,1,2,3,7,4,6").split(",").map(Number);
const strength = Number(args.strength ?? 1),
  shade = Number(args.shade ?? 0);
if (
  !Number.isFinite(strength) ||
  strength < 0.25 ||
  strength > 2 ||
  !Number.isFinite(shade) ||
  shade < 0 ||
  shade > 100
)
  throw Error("Invalid strength or shade");
if (
  !sequence.length ||
  sequence.some((v) => !Number.isInteger(v) || v < 0 || v > 7)
)
  throw Error("Invalid preset sequence");
const interval = Number(args.interval ?? 20),
  fade = exactSchedule ? 0 : Math.max(0, Number(args.fade ?? 1.3));
if (
  !Number.isFinite(interval) ||
  interval < 5 ||
  !Number.isFinite(fade) ||
  fade > interval / 2
)
  throw Error("Invalid scene interval or crossfade duration");
if (
  ![width, height].every(
    (value) =>
      Number.isInteger(value) &&
      value >= 16 &&
      value <= 7680 &&
      value % 2 === 0,
  )
)
  throw Error(
    "H.264 output dimensions must be even integers between 16 and 7680",
  );
const beats = (analysis.beats ?? [])
  .filter((t) => typeof t === "number" && t > 0 && t < duration)
  .sort((a, b) => a - b);
const changes = [0];
if (exactSchedule)
  changes.splice(0, 1, ...exactSchedule.map((s) => s.startFrame / fps));
for (
  let desired = interval;
  !exactSchedule && desired < duration - 5;
  desired += interval
) {
  const nearby = beats.filter((t) => Math.abs(t - desired) < 2.5);
  const at = nearby.length
    ? nearby.reduce((a, b) =>
        Math.abs(a - desired) < Math.abs(b - desired) ? a : b,
      )
    : desired;
  if (at > changes.at(-1) + 4) changes.push(at);
}
const output = resolve(args.output);
const staging = output + ".rendering.mp4";
await mkdir(dirname(output), { recursive: true });
const framePath = output + ".frames.csv",
  cuePath = output + ".scenes.json";
let scene = 0;
const rows = analysis.frames
  .slice(0, count)
  .map((frame, index) => {
    const time = index / fps;
    while (scene + 1 < changes.length && time >= changes[scene + 1]) scene++;
    const preset = sequence[scene % sequence.length],
      next = sequence[(scene + 1) % sequence.length];
    const boundary = changes[scene + 1] ?? Infinity;
    const blend = fade
      ? Math.max(0, Math.min(1, (time - (boundary - fade)) / fade))
      : 0;
    const features = ["bass", "mid", "treble", "onset", "energy"].map((key) => {
      const value = Number(frame[key] ?? 0);
      if (!Number.isFinite(value))
        throw Error(`Invalid ${key} at frame ${index}`);
      return Math.max(0, Math.min(1, value));
    });
    return [time, ...features, preset, next, blend].join(",");
  })
  .join("\n");
await writeFile(framePath, rows + "\n");
const source = resolve(root, "scripts/video/visualizer-native.cpp"),
  shader = resolve(root, "public/visualizers/collection.frag");
const shaderBytes = await readFile(shader);
const shaderDigest = createHash("sha256").update(shaderBytes).digest("hex");
const shaderSnapshot = output + ".shader.frag";
await writeFile(shaderSnapshot, shaderBytes);
const cache = resolve("/private/tmp/soundvision-visualizer");
await mkdir(cache, { recursive: true });
const digest = createHash("sha256")
  .update(await readFile(source))
  .digest("hex")
  .slice(0, 16);
const binary = resolve(cache, "visualizer-" + digest);
try {
  await stat(binary);
} catch {
  const compile = spawnSync(
    "clang++",
    ["-O3", "-std=c++17", source, "-framework", "OpenGL", "-o", binary],
    { stdio: "inherit" },
  );
  if (compile.status !== 0) throw Error("Could not build native renderer");
}
const ffmpegArgs = [
  "-hide_banner",
  "-loglevel",
  "warning",
  "-nostats",
  "-y",
  "-f",
  "rawvideo",
  "-pixel_format",
  "rgb24",
  "-video_size",
  `${width}x${height}`,
  "-framerate",
  String(fps),
  "-i",
  "pipe:0",
];
if (args.audio) ffmpegArgs.push("-i", resolve(args.audio));
ffmpegArgs.push(
  "-vf",
  "vflip",
  "-c:v",
  "libx264",
  "-preset",
  "fast",
  "-crf",
  "18",
  "-pix_fmt",
  "yuv420p",
  "-threads",
  String(threads),
);
if (args.audio)
  ffmpegArgs.push(
    "-map",
    "0:v:0",
    "-map",
    "1:a:0",
    "-af",
    `atrim=duration=${duration}`,
    "-c:a",
    "aac",
    "-b:a",
    "256k",
  );
// Frame count, rather than -t, prevents fractional source duration rounding
// from dropping the final visual frame and leaving the audio tail uncovered.
ffmpegArgs.push("-frames:v", String(count), "-movflags", "+faststart", staging);
const renderer = spawn(
  binary,
  [
    shaderSnapshot,
    framePath,
    String(width),
    String(height),
    String(strength),
    String(shade / 100),
  ],
  { stdio: ["ignore", "pipe", "pipe"] },
);
renderer.stderr.pipe(process.stderr);
if (args.progress) {
  let pending = "";
  renderer.stderr.on("data", (data) => {
    pending += data.toString();
    const lines = pending.split("\n");
    pending = lines.pop();
    for (const line of lines) {
      const match = /Rendered (\d+) frames/.exec(line);
      if (match) {
        const path = resolve(args.progress);
        // Synchronous atomic writes avoid overlapping progress-file updates.
        writeFileSync(
          path + ".tmp",
          JSON.stringify({
            phase: "Rendering video",
            frames: Number(match[1]),
            totalFrames: count,
          }),
        );
        renameSync(path + ".tmp", path);
      }
    }
  });
}
const encoder = spawn("ffmpeg", ffmpegArgs, {
  stdio: ["pipe", "ignore", "inherit"],
});
for (const signal of ["SIGTERM", "SIGINT"])
  process.once(signal, () => {
    renderer.kill("SIGTERM");
    encoder.kill("SIGTERM");
    process.exit(130);
  });
renderer.stdout.pipe(encoder.stdin);
encoder.stdin.on("error", (err) => {
  if (err.code !== "EPIPE") console.error(err);
  renderer.kill("SIGTERM");
});
function completed(child) {
  return new Promise((res, rej) => {
    child.once("error", rej);
    child.once("close", (code, signal) =>
      code === 0 ? res() : rej(Error(`Process failed: ${code ?? signal}`)),
    );
  });
}
try {
  await Promise.all([completed(renderer), completed(encoder)]);
} catch (error) {
  renderer.kill();
  encoder.kill();
  throw error;
}
const probed = spawnSync(
  "ffprobe",
  [
    "-v",
    "error",
    "-select_streams",
    "v:0",
    "-show_entries",
    "stream=nb_frames,duration",
    "-of",
    "json",
    staging,
  ],
  { encoding: "utf8" },
);
if (probed.status !== 0) throw Error("Could not verify encoded frame count");
const encoded = JSON.parse(probed.stdout).streams[0];
if (Number(encoded.nb_frames) !== count)
  throw Error(`Encoded ${encoded.nb_frames} frames; expected ${count}`);
await rename(staging, output);
const report = {
  fps,
  duration,
  width,
  height,
  frameCount: count,
  encodedDuration: Number(encoded.duration),
  shaderSha256: shaderDigest,
  shaderSource: shaderSnapshot,
  analysis: resolve(args.analysis),
  output,
  fadeSeconds: fade,
  beatAligned: !exactSchedule && beats.length > 0,
  equalTime: args.visualizer === "all",
  strength,
  shade,
  scenes: changes.map((start, i) => ({
    start,
    end: changes[i + 1] ?? duration,
    preset: sequence[i % sequence.length],
  })),
};
await writeFile(cuePath, JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify(report, null, 2));
