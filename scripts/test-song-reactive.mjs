import test from "node:test";
import assert from "node:assert/strict";
import {
  analyzeSong,
  sampleSong,
  songFrame,
  SONG_SAMPLE_RATE,
} from "../src/video/visualizers/songAnalysis.ts";
import { songReactiveDirections } from "../src/video/visualizers/directions.ts";
import {
  visualizerAt,
  visualizerSchedule,
} from "../src/video/visualizers/schedule.ts";
import { validateExport } from "./video/visualizer-export-api.mjs";
import { makeDraft } from "../src/video/timeline.ts";
import {
  surfaceTransform,
  validateScene,
} from "../src/video/visualizers/scene.ts";

const sampleScene = () => ({
  version: 1,
  aspect: "16:9",
  dimensions: [1672, 941],
  surfaces: [
    {
      name: "Glass",
      effect: "ribbon",
      color: "#A9C5CE",
      accent: "#DCC7A5",
      strength: 0.6,
      corners: [
        [0.14, 0.25],
        [0.73, 0.28],
        [0.7, 0.7],
        [0.12, 0.68],
      ],
    },
  ],
});
test("perspective fitting maps actual image corners to the exact display edges", () => {
  const scene = validateScene(sampleScene());
  const h = surfaceTransform(scene.surfaces[0].corners);
  scene.surfaces[0].corners.forEach(([x, y], i) => {
    const z = h[2] * x + h[5] * y + h[8],
      u = (h[0] * x + h[3] * y + h[6]) / z,
      v = (h[1] * x + h[4] * y + h[7]) / z;
    const expected = [
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
    ][i];
    assert(
      Math.abs(u - expected[0]) < 1e-10 && Math.abs(v - expected[1]) < 1e-10,
    );
  });
});
test("malformed and ambiguous surface geometry cannot reach the renderer", () => {
  for (const change of [
    {
      corners: [
        [0, 0],
        [1, 1],
        [1, 0],
        [0, 1],
      ],
    },
    {
      corners: [
        [0, 0],
        [0, 0],
        [1, 0],
        [1, 1],
      ],
    },
    {
      corners: [
        [0, 0],
        [NaN, 0],
        [1, 1],
        [0, 1],
      ],
    },
    { strength: 100 },
    { color: "url(https://example.com)" },
    { effect: "arbitrary-code" },
  ]) {
    const scene = sampleScene();
    Object.assign(scene.surfaces[0], change);
    assert.throws(() => validateScene(scene));
  }
});
test("song export binds to a saved artwork ID and ignores caller-supplied asset URLs", () => {
  const draft = {
    ...makeDraft({ title: "Example" }),
    showLyrics: false,
    reactiveMode: "song",
    reactiveArtworkId: "artwork-example-01",
    visualizer: "all",
  };
  const body = {
    takeId: "a".repeat(32),
    requestId: "song-scene-render",
    duration: 5,
    cues: [],
    draft,
    scene: { artworkUrl: "https://example.com/private" },
  };
  const validated = validateExport(body);
  assert.equal(validated.draft.visualizer, "8");
  assert.equal(validated.draft.reactiveArtworkId, "artwork-example-01");
  assert.equal(validated.scene, undefined);
  assert.throws(() =>
    validateExport({
      ...body,
      draft: { ...draft, reactiveArtworkId: "../../escape" },
    }),
  );
  const classic = { ...draft };
  delete classic.reactiveMode;
  delete classic.reactiveArtworkId;
  assert.equal(
    Object.hasOwn(
      validateExport({ ...body, draft: classic }).draft,
      "reactiveMode",
    ),
    false,
  );
});

function tone(hz, start = 0.25, end = 1.5) {
  const pcm = new Float32Array(SONG_SAMPLE_RATE * 2);
  for (let i = 0; i < pcm.length; i++) {
    const t = i / SONG_SAMPLE_RATE;
    if (t >= start && t < end) pcm[i] = 0.4 * Math.sin(t * 2 * Math.PI * hz);
  }
  return pcm;
}
test("silence produces no invented activity or transient events", () => {
  const analysis = analyzeSong(new Float32Array(SONG_SAMPLE_RATE));
  assert.equal(analysis.frames, 120);
  assert.deepEqual(analysis.onsets, []);
  for (let i = 0; i < analysis.frames; i++)
    for (let c = 0; c < 32; c++)
      assert.equal(analysis.data[i * 32 + c], c === 7 ? 65535 : 0);
});
test("a centered transient stays within the analysis window of its actual onset", () => {
  const pcm = tone(80, 1, 1.15),
    analysis = analyzeSong(pcm);
  assert(analysis.onsets.some((t) => Math.abs(t - 1) < 0.03));
  assert.equal(sampleSong(analysis, 0.9)[3], 0);
  assert(sampleSong(analysis, 1.04)[3] > 0.05);
});
test("low and high tones occupy the appropriate independent spectral bands", () => {
  const low = sampleSong(analyzeSong(tone(80)), 1),
    high = sampleSong(analyzeSong(tone(8000)), 1);
  assert(low[8 + 2] > low[8 + 23]);
  assert(high[8 + 21] > high[8 + 2]);
});
test("seeks are deterministic, interpolate consistently and clamp at source edges", () => {
  const a = analyzeSong(tone(440)),
    before = Array.from(sampleSong(a, 0.834));
  sampleSong(a, 1.2);
  assert.deepEqual(Array.from(sampleSong(a, 0.834)), before);
  assert.deepEqual(sampleSong(a, -1), sampleSong(a, 0));
  assert.deepEqual(sampleSong(a, 100), sampleSong(a, a.duration));
  const lo = sampleSong(a, 0.5),
    hi = sampleSong(a, 0.5 + 1 / a.fps),
    mid = sampleSong(a, 0.5 + 0.5 / a.fps);
  for (let i = 0; i < 32; i++)
    assert(Math.abs(mid[i] - (lo[i] + hi[i]) / 2) < 1e-6);
  const frame = songFrame(a, 0.834);
  assert.equal(frame.bass, before[0]);
  assert.equal(frame.tick, before[4]);
  assert.deepEqual(frame.spectrum, before.slice(8));
});
test("analysis rejects invalid PCM and unsupported sample rate", () => {
  assert.throws(() => analyzeSong(new Float32Array()), /Choose audio/);
  assert.throws(() => analyzeSong(new Float32Array([NaN])), /non-finite/);
  assert.throws(() => analyzeSong(new Float32Array(4), 22050), /48 kHz/);
});
test("new style survives export validation without changing existing saved schedules", () => {
  const track = { title: "Example", source: "imported", duration: 5 };
  const draft = { ...makeDraft(track), kind: "visualizer", showLyrics: false };
  assert.equal(draft.visualizer, "8");
  const body = {
    takeId: "a".repeat(32),
    requestId: "song-reactive-test",
    duration: 5,
    cues: [],
    draft,
  };
  assert.equal(validateExport(body).draft.visualizer, "8");
  for (const t of [0, 1, 4.999, 5]) assert.equal(visualizerAt(t, 5, "8"), 8);
  assert.deepEqual(
    visualizerSchedule(9, "all").map((s) => s.preset),
    [0, 1, 2, 3, 4, 5, 6, 7],
  );
  assert.throws(
    () => validateExport({ ...body, draft: { ...draft, visualizer: "9" } }),
    /Invalid visualizer/,
  );
});
test("all sixteen original style directions remain distinct and honestly labeled", () => {
  assert.equal(songReactiveDirections.length, 16);
  assert.equal(new Set(songReactiveDirections.map((s) => s.id)).size, 16);
  assert.equal(
    songReactiveDirections.filter((s) => s.status === "archived-study").length,
    2,
  );
  assert(
    songReactiveDirections.every((s) => s.surface && s.response && s.suits),
  );
});
