// Original, deterministic instrumental fixtures. No model or external recording.
import { writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
const sr = 24000,
  seconds = 240,
  notes = [57, 60, 64, 67, 53, 57, 60, 65, 48, 52, 55, 60, 55, 59, 62, 67];
const waveforms = [];
for (let take = 0; take < 2; take++) {
  const data = Buffer.alloc(sr * seconds * 2 * 2 + 44);
  data.write("RIFF");
  data.writeUInt32LE(data.length - 8, 4);
  data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16);
  data.writeUInt16LE(1, 20);
  data.writeUInt16LE(2, 22);
  data.writeUInt32LE(sr, 24);
  data.writeUInt32LE(sr * 4, 28);
  data.writeUInt16LE(4, 32);
  data.writeUInt16LE(16, 34);
  data.write("data", 36);
  data.writeUInt32LE(data.length - 44, 40);
  const peaks = Array(360).fill(0);
  for (let i = 0; i < sr * seconds; i++) {
    const t = i / sr,
      chord = Math.floor(t / 8) % 4,
      beat = t % (take ? 0.8 : 1),
      n =
        notes[chord * 4 + (Math.floor(t / (take ? 0.8 : 1)) % 4)] +
        (take ? 12 : 0),
      f = 440 * 2 ** ((n - 69) / 12),
      env = Math.exp(-beat * 4) * (1 - Math.exp(-beat * 80));
    let v = 0;
    for (let j = 0; j < 4; j++) {
      const hz = 440 * 2 ** ((notes[chord * 4 + j] - 69) / 12);
      v += Math.sin(t * hz * 2 * Math.PI + 0.2 * Math.sin(t * 0.5)) * 0.025;
    }
    v +=
      env *
      (Math.sin(t * f * 2 * Math.PI) * 0.12 +
        Math.sin(t * f * 4 * Math.PI) * 0.025);
    const pulse = t % 1;
    v +=
      Math.sin(pulse * 2 * Math.PI * (55 + 40 * Math.exp(-pulse * 20))) *
      Math.exp(-pulse * 15) *
      0.065;
    v *= Math.min(1, t / 3, (seconds - t) / 6);
    peaks[Math.floor((t / seconds) * 360)] = Math.max(
      peaks[Math.floor((t / seconds) * 360)],
      Math.abs(v),
    );
    data.writeInt16LE(Math.round(v * 32767), 44 + i * 4);
    data.writeInt16LE(
      Math.round((v * 0.96 + Math.sin(t * 0.9) * v * 0.04) * 32767),
      46 + i * 4,
    );
  }
  const path = `public/media/desert-afterglow-${take + 1}`;
  writeFileSync(path + ".wav", data);
  execFileSync("ffmpeg", [
    "-v",
    "error",
    "-y",
    "-i",
    path + ".wav",
    "-codec:a",
    "libmp3lame",
    "-b:a",
    "128k",
    path + ".mp3",
  ]);
  waveforms.push(peaks.map((v) => Math.round(v * 1000) / 1000));
}
writeFileSync("src/waveforms.json", JSON.stringify(waveforms));
console.log(
  "Created two original 240-second stereo fixtures and measured peak envelopes.",
);
