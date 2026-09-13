import test from "node:test";
import assert from "node:assert/strict";
import {
  makeDraft,
  makePlacements,
  framesFor,
  FPS,
  lyricLines,
  alignedCues,
  cueAt,
  timingIssues,
  backgroundPrompt,
  videoManifest,
} from "../src/video/timeline.ts";
const track = {
  id: "test-take",
  title: "Night Drive",
  project: "Album",
  favorite: false,
  created: 1,
  source: "yue2",
  duration: 180,
  form: {
    lyrics:
      "[Verse]\nFollow the light\n[Chorus]\nBring me home\n[Chorus]\nBring me home",
    description: "Rain on a nighttime city street",
  },
};
function checkCoverage(seconds, placements) {
  assert.equal(placements[0].startFrame, 0);
  assert.equal(placements.at(-1).endFrame, framesFor(seconds));
  for (let i = 0; i < placements.length; i++) {
    assert(placements[i].endFrame > placements[i].startFrame);
    if (i) assert.equal(placements[i].startFrame, placements[i - 1].endFrame);
  }
  assert(framesFor(seconds) / FPS - seconds < 1 / FPS + 0.00001);
}
test("180-second song and ten images gives exactly 18 seconds each", () => {
  const p = makePlacements(180, makeDraft(track));
  assert.equal(p.length, 10);
  assert(p.every((s) => (s.endFrame - s.startFrame) / FPS === 18));
  assert.deepEqual(
    p.map((s) => s.assetIndex),
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  );
  checkCoverage(180, p);
});
test("uneven durations distribute rounding without gaps, cumulative drift or lost ending", () => {
  for (const seconds of [59.7987, 207.719, 288.439, 302.399]) {
    const p = makePlacements(seconds, {
      ...makeDraft(track),
      imageCount: 13,
      imageCycles: 3,
    });
    checkCoverage(seconds, p);
    assert.equal(p.length, 39);
    const durations = p.map((p) => p.endFrame - p.startFrame);
    assert(Math.max(...durations) - Math.min(...durations) <= 1);
    assert.equal(p[13].assetIndex, 0);
  }
});
test("short H3 clips repeat at normal speed and the final placement is trimmed", () => {
  const draft = {
    ...makeDraft(track),
    background: "motion",
    clipCount: 3,
    clipSeconds: 8,
  };
  const p = makePlacements(180, draft);
  assert.equal(p.length, 23);
  assert(p.slice(0, -1).every((p) => (p.endFrame - p.startFrame) / FPS === 8));
  assert.equal((p.at(-1).endFrame - p.at(-1).startFrame) / FPS, 4);
  assert.deepEqual(
    p.slice(0, 6).map((p) => p.assetIndex),
    [0, 1, 2, 0, 1, 2],
  );
  checkCoverage(180, p);
});
test("zero duration produces no fictional timeline", () => {
  assert.deepEqual(makePlacements(0, makeDraft(track)), []);
});
test("visualizer plans preserve shader controls without requesting unused image or H3 assets", () => {
  const draft = {
    ...makeDraft(track),
    kind: "visualizer",
    background: "motion",
    visualizer: "6",
    visualizerStrength: 1.4,
  };
  const manifest = videoManifest(track, draft, 180, []);
  assert.equal(manifest.background.kind, "procedural");
  assert.deepEqual(manifest.background.assets, []);
  assert.deepEqual(manifest.background.placements, []);
  assert.equal(manifest.visualizer.style, "6");
  assert.equal(manifest.visualizer.strength, 1.4);
  assert.equal(manifest.soundtrack.useOriginal, true);
  assert.equal(manifest.capabilities.backgroundGenerationConnected, false);
  assert.equal(manifest.capabilities.videoExportConnected, true);
});
test("repeated chorus lines preserve separate occurrences", () => {
  const lines = lyricLines(track.form.lyrics);
  assert.equal(lines.length, 3);
  assert.equal(lines[1].text, lines[2].text);
  assert.notEqual(lines[1].id, lines[2].id);
});
test("background prompts carry song context, aspect, quiet text area and H3 native fields", () => {
  const d = { ...makeDraft(track), aspect: "9:16" };
  const image = backgroundPrompt(track, d, 0);
  assert(image.includes("Portrait 9:16"));
  assert(image.includes("Follow the light"));
  assert(image.includes("No lettering"));
  const motion = backgroundPrompt(track, { ...d, background: "motion" }, 0);
  assert(motion.startsWith("integrated_multimodal_description: [Shot 1]"));
  assert(motion.includes("overall_soundscape:"));
  assert(motion.includes("non_diegetic_music: N/A"));
  assert(motion.includes("static shot"));
});
test("portable editing plan states timing and rendering limitations and preserves original soundtrack", () => {
  const m = videoManifest(
    track,
    { ...makeDraft(track), kind: "kinetic", aspect: "9:16" },
    180,
    [],
  );
  assert.deepEqual(m.output, {
    width: 1080,
    height: 1920,
    fps: 24,
    durationSeconds: 180,
    totalFrames: 4320,
  });
  assert(m.soundtrack.useOriginal);
  assert(m.soundtrack.muteBackgroundAudio);
  assert.equal(m.capabilities.videoExportConnected, false);
  assert.equal(m.capabilities.backgroundGenerationConnected, true);
  assert.equal(m.lyrics.wordTimingStatus, "not-aligned");
  assert(m.background.assets.every((a) => a.status === "planned"));
  assert(!JSON.stringify(m).includes("blob:"));
});

test("no guessed lyric cues before alignment or after lyrics change", () => {
  const draft = makeDraft(track);
  assert.deepEqual(alignedCues(undefined, draft), []);
  assert.deepEqual(
    alignedCues({ lyrics: "different words", cues: [] }, draft),
    [],
  );
});
test("word timestamps preserve real gaps and missing words without interpolation", () => {
  const draft = makeDraft(track),
    alignment = {
      lyrics: draft.lyrics,
      cues: [
        {
          id: "line-0",
          text: "Follow the light",
          words: [
            { text: "Follow", start: 22.2, end: 22.6, review: null },
            { text: "the", start: 24.1, end: 24.25, review: null },
            { text: "light", start: null, end: null, review: "Unmatched" },
          ],
        },
      ],
    };
  const cues = alignedCues(alignment, draft);
  assert.equal(cues[0].startFrame, Math.floor(22.2 * 24));
  assert.equal(cues[0].words[1].start, 24.1);
  assert.equal(cues[0].words[2].start, null);
  const edited = alignedCues(alignment, {
    ...draft,
    wordEdits: { "line-0:2": { start: 25.3, end: 26 } },
  });
  assert.equal(edited[0].words[2].start, 25.3);
  assert.equal(edited[0].words[2].review, null);
});
const { wordMotion } = await import("../src/video/kinetics.ts");
test("kinetic pops are deterministic, pronounced, settle and respect reduced motion", () => {
  assert.deepEqual(wordMotion("pop", 0.1, 0), wordMotion("pop", 0.1, 0));
  assert.match(wordMotion("slam", 0, 0).transform, /scale\(1.3\)/);
  assert.equal(wordMotion("slam", 1, 0).transform, "scale(1) rotate(0deg)");
  assert.equal(wordMotion("pop", -0.1, 0).opacity, 0.14);
  assert.equal(wordMotion("pop", 0.1, 0, 1, true).transform, "none");
});

test("adjacent lyric lines hand off cleanly despite frame rounding or short vocal overlaps", () => {
  const draft = makeDraft(track);
  for (const [end, start] of [
    [59.009, 59.033],
    [217.27, 217.273],
    [47.809, 47.752],
  ]) {
    const words = [
      [
        {
          text: "First",
          start: end - 1,
          end,
          review: "Low alignment confidence",
        },
      ],
      [{ text: "Second", start, end: start + 1, review: null }],
    ];
    const a = {
      lyrics: draft.lyrics,
      cues: words.map((words, i) => ({
        id: `line-${i}`,
        text: words[0].text,
        words,
      })),
    };
    const cues = alignedCues(a, draft);
    assert.equal(cues[0].endFrame, cues[1].startFrame);
    assert.deepEqual(
      cues.map((c) => c.words),
      words,
      "measured timestamps and confidence flags remain intact",
    );
    assert.deepEqual(timingIssues(cues, 300), []);
    assert.equal(cueAt(cues, cues[1].startFrame).id, "line-1");
  }
  const cues = alignedCues(
    {
      lyrics: draft.lyrics,
      cues: [
        {
          id: "line-0",
          text: "First",
          words: [{ text: "First", start: 1, end: 5 }],
        },
        {
          id: "line-1",
          text: "Second",
          words: [{ text: "Second", start: 3, end: 6 }],
        },
      ],
    },
    draft,
  );
  assert.match(timingIssues(cues, 10)[0], /overlaps/);
});

test("library refresh repairs duplicate imported-song cache entries", async () => {
  const { uniqueTracks } = await import("../src/music-studio/model.ts");
  const imported = {
    id: "imported",
    source: "imported",
    title: "Current title",
  };
  const cached = { id: "imported", title: "Old cached title" };
  const local = { id: "sample", title: "Local sample" };
  let result = uniqueTracks([imported, cached, cached, local]);
  assert.deepEqual(result, [imported, local]);
  for (let i = 0; i < 5; i++)
    result = uniqueTracks([imported, ...result.filter((t) => !t.source)]);
  assert.deepEqual(result, [imported, local]);
});

test("music-video export retains every lyric line even when preview has no timestamps", async () => {
  const { lyricRenderCues, lyricTimingReview } =
    await import("../src/video/timeline.ts");
  const draft = {
    ...makeDraft(track),
    lyrics: "First\nMissing line\nLast",
    wordEdits: {},
  };
  const alignment = {
    lyrics: draft.lyrics,
    cues: [
      {
        id: "line-0",
        text: "First",
        words: [{ text: "First", start: 1, end: 2 }],
      },
      {
        id: "line-1",
        text: "Missing line",
        words: [
          { text: "Missing", start: null, end: null },
          { text: "line", start: null, end: null },
        ],
      },
      {
        id: "line-2",
        text: "Last",
        words: [{ text: "Last", start: 3, end: 4 }],
      },
    ],
  };
  assert.equal(alignedCues(alignment, draft).length, 2);
  const output = lyricRenderCues(alignment, draft);
  assert.equal(output.length, 3);
  assert.deepEqual(
    output.flatMap((c) => c.words.map((w) => w.text)),
    ["First", "Missing", "line", "Last"],
  );
  assert.deepEqual(lyricTimingReview(output, 10), {
    missing: 2,
    conflicting: 0,
    usable: 2,
    omitted: 2,
  });
  const corrected = lyricRenderCues(alignment, {
    ...draft,
    wordEdits: {
      "line-1:0": { start: 2.1, end: 2.4 },
      "line-1:1": { start: 2.4, end: 2.8 },
    },
  });
  assert.equal(lyricTimingReview(corrected, 10).omitted, 0);
  assert.equal(
    lyricRenderCues(alignment, { ...draft, lyrics: "Other lyrics" }).length,
    0,
  );
  assert.equal(alignment.cues[1].words[0].start, null);
});

test("timing review counts conflicts without moving or guessing timestamps", async () => {
  const { lyricTimingReview } = await import("../src/video/timeline.ts");
  const cues = [
    {
      words: [
        { text: "A", start: 1, end: 2 },
        { text: "B", start: 1.5, end: 2.5 },
        { text: "C", start: 3, end: 4 },
        { text: "D", start: null, end: null },
      ],
    },
  ];
  assert.deepEqual(lyricTimingReview(cues, 10), {
    missing: 1,
    conflicting: 1,
    usable: 2,
    omitted: 2,
  });
});
