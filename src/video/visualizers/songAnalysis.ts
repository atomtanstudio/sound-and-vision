/** Shared browser/Node analysis, derived from the verified Tremor showcase.
 * No DOM, provider, Python, or song-specific assets. SPDX-License-Identifier: Apache-2.0
 */
import type { VisualizerAudioFrame } from "./library.ts";
export const SONG_SAMPLE_RATE = 48000;
export const SONG_ANALYSIS_FPS = 120;
export const SONG_FEATURE_COLUMNS = 32;
export type SongAnalysis = {
  version: 1;
  fps: number;
  duration: number;
  frames: number;
  data: Uint16Array;
  onsets: number[];
};
const N = 2048,
  BANDS = 24,
  FPS = SONG_ANALYSIS_FPS,
  COLS = SONG_FEATURE_COLUMNS;
const clamp = (x: number) => Math.max(0, Math.min(1, x));
function percentile(values: ArrayLike<number>, q: number) {
  const sorted = Array.from(values).sort((a, b) => a - b);
  const at = (sorted.length - 1) * q,
    lo = Math.floor(at);
  return (
    sorted[lo] * (1 - (at - lo)) +
    sorted[Math.min(lo + 1, sorted.length - 1)] * (at - lo)
  );
}
function normalized(a: Float32Array, q = 0.98) {
  const scale = Math.max(1e-8, percentile(a, q));
  return a.map((x) => clamp(x / scale));
}
function smooth(a: Float32Array, attack: number, release: number) {
  const result = new Float32Array(a.length);
  let prior = 0;
  for (let i = 0; i < a.length; i++) {
    prior += (a[i] > prior ? attack : release) * (a[i] - prior);
    result[i] = prior;
  }
  return result;
}
function peaks(a: Float32Array, gap: number) {
  const result: number[] = [];
  for (let i = 1; i < a.length - 1; i++) {
    if (a[i] <= a[i - 1] || a[i] < a[i + 1]) continue;
    const local = a.subarray(Math.max(0, i - 60), Math.min(a.length, i + 60));
    const median = percentile(local, 0.5);
    const threshold = Math.max(
      0.11,
      median +
        1.6 *
          percentile(
            local.map((x) => Math.abs(x - median)),
            0.5,
          ),
    );
    if (a[i] < threshold) continue;
    const previous = result.at(-1);
    if (previous !== undefined && i - previous < Math.floor(FPS * gap)) {
      if (a[i] > a[previous]) result[result.length - 1] = i;
    } else result.push(i);
  }
  return result;
}
function fft(re: Float64Array, im: Float64Array) {
  for (let i = 1, j = 0; i < N; i++) {
    let bit = N >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      const a = re[i];
      re[i] = re[j];
      re[j] = a;
    }
  }
  for (let len = 2; len <= N; len <<= 1) {
    const ar = Math.cos((-2 * Math.PI) / len),
      ai = Math.sin((-2 * Math.PI) / len);
    for (let i = 0; i < N; i += len) {
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
export function analyzeSong(
  pcm: Float32Array,
  sampleRate = SONG_SAMPLE_RATE,
  progress?: (fraction: number) => void,
): SongAnalysis {
  if (sampleRate !== SONG_SAMPLE_RATE)
    throw Error("Song analysis requires 48 kHz PCM.");
  if (!pcm.length || pcm.length > sampleRate * 3600)
    throw Error("Choose audio between one sample and one hour long.");
  for (const value of pcm)
    if (!Number.isFinite(value))
      throw Error("Audio contains non-finite samples.");
  const duration = pcm.length / sampleRate,
    count = Math.ceil(duration * FPS);
  const re = new Float64Array(N),
    im = new Float64Array(N),
    window = Float64Array.from(
      { length: N },
      (_, i) => 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (N - 1)),
    );
  const bins = Array.from({ length: BANDS }, (_, b) => {
    const low = 40 * (15000 / 40) ** (b / BANDS),
      high = 40 * (15000 / 40) ** ((b + 1) / BANDS);
    const result: number[] = [];
    for (let k = 0; k <= N / 2; k++)
      if ((k * sampleRate) / N >= low && (k * sampleRate) / N < high)
        result.push(k);
    return result.length
      ? result
      : [Math.round((((low + high) / 2) * N) / sampleRate)];
  });
  const raw = Array.from({ length: BANDS }, () => new Float32Array(count)),
    rms = new Float32Array(count);
  for (let frame = 0; frame < count; frame++) {
    const center = Math.min(pcm.length - 1, frame * (sampleRate / FPS));
    let power = 0;
    for (let i = 0; i < N; i++) {
      const v = pcm[center + i - N / 2] ?? 0;
      re[i] = v * window[i];
      im[i] = 0;
      power += v * v;
    }
    rms[frame] = Math.sqrt(power / N);
    fft(re, im);
    for (let b = 0; b < BANDS; b++) {
      let total = 0;
      for (const k of bins[b]) total += re[k] * re[k] + im[k] * im[k];
      raw[b][frame] = Math.sqrt(total / bins[b].length);
    }
    if (frame % 256 === 0) progress?.((frame / count) * 0.8);
  }
  const gate = rms.map((x) => clamp((20 * Math.log10(x + 1e-9) + 64) / 25));
  const spectral = raw.map((a) => {
    const ref = percentile(a, 0.98);
    return smooth(
      a.map((x, i) => clamp(x / (ref + 1e-8)) ** 0.67 * gate[i]),
      0.5,
      0.12,
    );
  });
  const group = (start: number, end: number) => {
    const values = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      let sum = 0;
      for (let b = start; b < end; b++) sum += raw[b][i] ** 2;
      values[i] = Math.sqrt(sum / (end - start));
    }
    return normalized(values).map((x, i) => x ** 0.7 * gate[i]);
  };
  const bass = group(0, 6),
    mid = group(6, 17),
    air = group(17, 24),
    energy = normalized(rms, 0.99).map((x, i) => x ** 0.65 * gate[i]);
  const flux = (a: Float32Array) =>
    normalized(
      a.map((x, i) => Math.max(0, x - (a[i - 1] || 0))),
      0.995,
    ).map((x, i) => x * gate[i]);
  const lowFlux = flux(bass),
    highFlux = flux(air),
    lows = peaks(lowFlux, 0.17),
    highs = peaks(highFlux, 0.095);
  const impulse = (ids: number[], f: Float32Array, decay: number) => {
    const out = new Float32Array(count);
    for (const start of ids)
      for (let i = start; i < Math.min(count, start + FPS * 1.5); i++)
        out[i] = Math.max(
          out[i],
          f[start] * Math.exp(-(i - start) / FPS / decay),
        );
    return out;
  };
  const age = new Float32Array(count).fill(1);
  lows.forEach((start, n) => {
    for (let i = start; i < (lows[n + 1] ?? count); i++)
      age[i] = Math.min(3, (i - start) / FPS) / 3;
  });
  const columns = [
    smooth(bass, 0.75, 0.13),
    smooth(mid, 0.38, 0.09),
    smooth(air, 0.58, 0.14),
    impulse(lows, lowFlux, 0.135),
    impulse(highs, highFlux, 0.065),
    smooth(energy, 0.48, 0.08),
    smooth(energy, 0.035, 0.015),
    age,
    ...spectral,
  ];
  const data = new Uint16Array(count * COLS);
  for (let i = 0; i < count; i++)
    for (let c = 0; c < COLS; c++)
      data[i * COLS + c] = Math.round(clamp(columns[c][i]) * 65535);
  progress?.(1);
  return {
    version: 1,
    fps: FPS,
    duration,
    frames: count,
    data,
    onsets: lows.map((i) => i / FPS),
  };
}
export function sampleSong(
  analysis: SongAnalysis,
  time: number,
  target = new Float32Array(COLS),
) {
  const f = Math.max(
    0,
    Math.min(
      analysis.frames - 1,
      (Number.isFinite(time) ? time : 0) * analysis.fps,
    ),
  );
  const lo = Math.floor(f),
    hi = Math.min(lo + 1, analysis.frames - 1),
    mix = f - lo;
  for (let c = 0; c < COLS; c++)
    target[c] =
      (analysis.data[lo * COLS + c] * (1 - mix) +
        analysis.data[hi * COLS + c] * mix) /
      65535;
  return target;
}
export function songFrame(
  analysis: SongAnalysis,
  time: number,
): VisualizerAudioFrame {
  const a = sampleSong(analysis, time);
  return {
    time,
    bass: a[0],
    mid: a[1],
    treble: a[2],
    onset: a[3],
    tick: a[4],
    energy: a[5],
    breath: a[6],
    age: a[7] * 3,
    spectrum: Array.from(a.subarray(8)),
  };
}
