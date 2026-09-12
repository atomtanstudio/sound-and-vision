import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  visualizerAt,
  visualizerSchedule,
} from "../src/video/visualizers/schedule.ts";
import {
  validateExport,
  trustedLocalRequest,
  byteRange,
  createVisualizerExports,
} from "./video/visualizer-export-api.mjs";

const input = () => ({
  takeId: "a".repeat(32),
  requestId: "test-export-123",
  duration: 191.359,
  cues: [],
  draft: {
    aspect: "16:9",
    visualizer: "all",
    visualizerStrength: 1.3,
    shade: 35,
    showLyrics: false,
    font: "bold",
    textSize: 100,
    placement: "center",
    lyricMotion: "pop",
    intensity: 1,
    textColor: "#ffffff",
    highlightColor: "#ffcbb2",
    lyrics: "",
  },
});
test("all eight styles cover the whole song equally without gaps or lost final frames", () => {
  for (const seconds of [1, 8, 180, 191.359, 265.438667, 3599.999]) {
    const schedule = visualizerSchedule(seconds, "all");
    assert.deepEqual(
      schedule.map((s) => s.preset),
      [0, 1, 2, 3, 4, 5, 6, 7],
    );
    assert.equal(schedule[0].startFrame, 0);
    assert.equal(schedule.at(-1).endFrame, Math.ceil(seconds * 24));
    const lengths = schedule.map((s) => s.endFrame - s.startFrame);
    assert(Math.max(...lengths) - Math.min(...lengths) <= 1);
    schedule.forEach((s, i) => {
      if (i) assert.equal(s.startFrame, schedule[i - 1].endFrame);
      assert.equal(visualizerAt(s.startFrame / 24, seconds, "all"), s.preset);
      assert.equal(
        visualizerAt(Number((s.startFrame / 24).toFixed(6)), seconds, "all"),
        s.preset,
        "media seeks rounded to microseconds select the intended style",
      );
      assert.equal(
        visualizerAt((s.endFrame - 1) / 24, seconds, "all"),
        s.preset,
      );
    });
    assert.equal(visualizerAt(seconds, seconds, "all"), 7);
  }
});
test("single and older style selections remain stable across seeks", () => {
  for (const [selection, id] of [
    ["6", 6],
    ["spectrum", 4],
    ["orbit", 2],
    ["waveform", 0],
  ]) {
    for (const t of [0, 30, 99, 180])
      assert.equal(visualizerAt(t, 180, selection), id);
    assert.equal(visualizerSchedule(180, selection).length, 1);
  }
});
test("render validation keeps supported controls and rejects arbitrary source paths and invalid timing", () => {
  const good = validateExport(input());
  assert.equal(good.draft.visualizer, "all");
  assert.equal(good.draft.visualizerStrength, 1.3);
  for (const takeId of ["../private/file", "http://evil/audio", "a".repeat(33)])
    assert.throws(() => validateExport({ ...input(), takeId }));
  for (const strength of [NaN, Infinity, -1, 5]) {
    const bad = input();
    bad.draft.visualizerStrength = strength;
    assert.throws(() => validateExport(bad));
  }
  const lyrics = input();
  lyrics.draft.showLyrics = true;
  lyrics.draft.lyrics = "One line";
  assert.throws(() => validateExport(lyrics), /Align lyrics/);
  lyrics.cues = [
    {
      id: "line-0",
      text: "One line",
      startFrame: 24,
      endFrame: 72,
      words: [
        { text: "One", start: 1, end: 2 },
        { text: "line", start: 2, end: 3 },
      ],
    },
  ];
  assert.equal(validateExport(lyrics).cues[0].words.length, 2);
  lyrics.cues[0].words[0].start = null;
  assert.throws(() => validateExport(lyrics), /word start/);
});
test("local render mutations reject cross-site and hostile Host requests", () => {
  assert(
    trustedLocalRequest({
      headers: {
        host: "localhost:5190",
        origin: "http://localhost:5190",
        "sec-fetch-site": "same-origin",
      },
    }),
  );
  for (const headers of [
    { host: "evil.com:5190" },
    { host: "localhost:5190", origin: "https://evil.com" },
    { host: "localhost:5190", "sec-fetch-site": "cross-site" },
    { host: "localhost:5190", "sec-fetch-site": "same-site" },
  ])
    assert.equal(trustedLocalRequest({ headers }), false);
});
test("MP4 range handling supports seek, suffix ranges, and rejects malformed or impossible ranges", () => {
  assert.deepEqual(byteRange("bytes=10-19", 100), {
    start: 10,
    end: 19,
    partial: true,
  });
  assert.deepEqual(byteRange("bytes=90-", 100), {
    start: 90,
    end: 99,
    partial: true,
  });
  assert.deepEqual(byteRange("bytes=-10", 100), {
    start: 90,
    end: 99,
    partial: true,
  });
  for (const h of [
    "bytes=100-",
    "bytes=50-20",
    "bytes=-0",
    "bytes=0-5,10-15",
    "bytes=-",
  ])
    assert.equal(byteRange(h, 100), null);
});
test("server recovery retains finished videos and marks interrupted work without resubmitting it", () => {
  const dir = mkdtempSync(join(tmpdir(), "sv-export-recovery-"));
  for (const [id, state] of [
    ["b".repeat(32), "running"],
    ["c".repeat(32), "succeeded"],
  ]) {
    mkdirSync(join(dir, id));
    writeFileSync(
      join(dir, id, "job.json"),
      JSON.stringify({ id, state, input: input(), created: 1 }),
    );
  }
  const service = createVisualizerExports({
    projectRoot: process.cwd(),
    outputRoot: dir,
    backend: null,
    token: null,
  });
  service.close();
  const failed = JSON.parse(
    readFileSync(join(dir, "b".repeat(32), "job.json")),
  );
  assert.equal(failed.state, "failed");
  assert.match(failed.error, /restarted/);
  assert.equal(
    JSON.parse(readFileSync(join(dir, "c".repeat(32), "job.json"))).state,
    "succeeded",
  );
});
