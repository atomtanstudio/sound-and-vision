// Copyright 2026 Sound/Vision contributors. SPDX-License-Identifier: Apache-2.0
// Offline centered-window FFT analysis. All animation features come from PCM.
import { spawnSync } from "node:child_process";
import { writeFile, mkdir } from "node:fs/promises";
import { resolve, dirname } from "node:path";
const args = Object.fromEntries(
  process.argv.slice(2).reduce((pairs, arg, i, all) => {
    if (arg.startsWith("--")) pairs.push([arg.slice(2), all[i + 1]]);
    return pairs;
  }, []),
);
if (!args.audio || !args.output) {
  console.error(
    "Usage: node scripts/video/visualizer-analyze.mjs --audio song.wav --output analysis.json [--fps 24]",
  );
  process.exit(1);
}
const fps = Number(args.fps ?? 24),
  sampleRate = 22050,
  n = 2048;
if (!Number.isFinite(fps) || fps < 1 || fps > 120)
  throw Error("Invalid frame rate");
const decoded = spawnSync(
  "ffmpeg",
  [
    "-v",
    "error",
    "-i",
    resolve(args.audio),
    "-f",
    "f32le",
    "-ac",
    "1",
    "-ar",
    String(sampleRate),
    "pipe:1",
  ],
  { maxBuffer: 1024 * 1024 * 300 },
);
if (decoded.status !== 0)
  throw Error(decoded.stderr.toString() || "Audio decode failed");
const pcm = new Float32Array(
    decoded.stdout.buffer,
    decoded.stdout.byteOffset,
    decoded.stdout.byteLength / 4,
  ),
  duration = pcm.length / sampleRate;
if (!pcm.length) throw Error("No audio samples");
const re = new Float64Array(n),
  im = new Float64Array(n),
  window = new Float64Array(n),
  previous = new Float64Array(n / 2);
for (let i = 0; i < n; i++)
  window[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1));
function fft() {
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      [re[i], re[j]] = [re[j], re[i]];
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ar = Math.cos((-2 * Math.PI) / len),
      ai = Math.sin((-2 * Math.PI) / len);
    for (let i = 0; i < n; i += len) {
      let wr = 1,
        wi = 0;
      for (let j = 0; j < len / 2; j++) {
        const u = i + j,
          v = u + len / 2,
          tr = re[v] * wr - im[v] * wi,
          ti = re[v] * wi + im[v] * wr;
        re[v] = re[u] - tr;
        im[v] = im[u] - ti;
        re[u] += tr;
        im[u] += ti;
        const old = wr;
        wr = wr * ar - wi * ai;
        wi = old * ai + wi * ar;
      }
    }
  }
}
const raw = [];
for (let frame = 0; frame < Math.ceil(duration * fps); frame++) {
  const center = Math.round((frame / fps) * sampleRate);
  let rms = 0;
  for (let i = 0; i < n; i++) {
    const value = pcm[center + i - n / 2] ?? 0;
    re[i] = value * window[i];
    im[i] = 0;
    rms += value * value;
  }
  fft();
  let bass = 0,
    mid = 0,
    treble = 0,
    flux = 0,
    bins = [0, 0, 0];
  for (let k = 1; k < n / 2; k++) {
    const hz = (k * sampleRate) / n,
      mag = Math.hypot(re[k], im[k]) / n,
      power = mag * mag;
    if (hz >= 35 && hz < 190) {
      bass += power;
      bins[0]++;
    } else if (hz >= 190 && hz < 2400) {
      mid += power;
      bins[1]++;
    } else if (hz >= 2400 && hz < 10000) {
      treble += power;
      bins[2]++;
    }
    if (hz >= 35 && hz < 5500) flux += Math.max(0, mag - previous[k]);
    previous[k] = mag;
  }
  raw.push({
    time: frame / fps,
    bass: Math.sqrt(bass / bins[0]),
    mid: Math.sqrt(mid / bins[1]),
    treble: Math.sqrt(treble / bins[2]),
    onset: flux,
    energy: Math.sqrt(rms / n),
  });
}
const names = ["bass", "mid", "treble", "onset", "energy"],
  ranges = {};
for (const name of names) {
  const sorted = raw.map((f) => f[name]).sort((a, b) => a - b);
  ranges[name] = {
    low: sorted[Math.floor(sorted.length * 0.06)],
    high: sorted[Math.floor(sorted.length * 0.97)],
  };
}
let held = { bass: 0, mid: 0, treble: 0, onset: 0, energy: 0 };
const normalized = raw.map((frame) => {
  const out = { time: frame.time };
  for (const name of names) {
    const range = ranges[name],
      floor = name === "onset" ? 0 : range.low * 0.6;
    let value = Math.max(
      0,
      Math.min(1, (frame[name] - floor) / Math.max(1e-8, range.high - floor)),
    );
    if (frame.energy < 0.0001) value = 0;
    const release =
      name === "onset" ? Math.exp(-1 / fps / 0.13) : Math.exp(-1 / fps / 0.11);
    value = Math.max(value, held[name] * release);
    held[name] = value;
    out[name] = Number(value.toFixed(6));
  }
  return out;
});
const onsets = [];
for (let i = 1; i < raw.length - 1; i++) {
  const v = raw[i].onset;
  if (
    v > ranges.onset.high * 0.29 &&
    v > raw[i - 1].onset &&
    v >= raw[i + 1].onset &&
    raw[i].time - (onsets.at(-1) ?? -1) > 0.27
  )
    onsets.push(Number(raw[i].time.toFixed(6)));
}
const result = {
  version: 1,
  source: resolve(args.audio),
  sampleRate,
  fftSize: n,
  fps,
  duration,
  featureMethod:
    "Centered Hann-window FFT, per-song robust band normalization, fast attack and 110 ms release. Onsets are measured spectral-flux peaks, not an inferred BPM grid.",
  frames: normalized,
  onsets,
  beats: onsets,
  statistics: ranges,
};
const output = resolve(args.output);
await mkdir(dirname(output), { recursive: true });
await writeFile(output, JSON.stringify(result) + "\n");
console.log(
  JSON.stringify(
    {
      output,
      duration,
      frames: normalized.length,
      onsets: onsets.length,
      ranges,
    },
    null,
    2,
  ),
);
