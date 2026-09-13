import test from "node:test";
import assert from "node:assert/strict";
import {
  lineBounds,
  moveLyricLine,
  tappedLyricLine,
  waveformPeaks,
  lyricProblems,
  deleteLyricText,
  insertLyricPhrases,
  lyricInsertionIndex,
  placeLyricPhraseAtPlayhead,
} from "../src/video/lyricEditing.ts";
import {
  makeDraft,
  lyricRenderCues,
  lyricTimingReview,
  alignedCues,
  currentLyricAlignment,
} from "../src/video/timeline.ts";
const line = {
  id: "line-0",
  text: "Stay right here",
  words: [
    { text: "Stay", start: 1, end: 1.4, review: null },
    { text: "right", start: 2, end: 2.5, review: null },
    { text: "here", start: null, end: null, review: "Missing" },
  ],
};
test("moving a line preserves sung pauses, missing words, and other line corrections", () => {
  const other = { "line-3:0": { start: 8, end: 9 } };
  const moved = moveLyricLine(line, other, 3, 10);
  assert.deepEqual(moved, {
    ...other,
    "line-0:0": { start: 4, end: 4.4 },
    "line-0:1": { start: 5, end: 5.5 },
    "line-0:2": { start: null, end: null },
  });
  assert.deepEqual(other, { "line-3:0": { start: 8, end: 9 } });
  assert.equal(line.words[0].start, 1);
  assert.deepEqual(lineBounds(line), { start: 1, end: 2.5 });
});
test("whole-line clamping stops at the song edges without compressing word spacing", () => {
  const left = moveLyricLine(line, {}, -100, 10),
    right = moveLyricLine(line, {}, 100, 10);
  assert.deepEqual(left["line-0:0"], { start: 0, end: 0.4 });
  assert.deepEqual(left["line-0:1"], { start: 1, end: 1.5 });
  assert.deepEqual(right["line-0:0"], { start: 8.5, end: 8.9 });
  assert.deepEqual(right["line-0:1"], { start: 9.5, end: 10 });
  assert.deepEqual(
    moveLyricLine({ ...line, words: [line.words[2]] }, {}, 3, 10),
    {},
  );
});
test("a partially timed word stays incomplete after a line move", () => {
  const partial = { ...line, words: [{ text: "Stay", start: null, end: 2 }] };
  assert.deepEqual(moveLyricLine(partial, {}, 1, 10), {
    "line-0:0": { start: null, end: 3 },
  });
});
test("tap timing requires every word start and a final end, with forward in-bounds taps", () => {
  assert.equal(tappedLyricLine(line, {}, [1, 2, 3], 10), null);
  assert.equal(tappedLyricLine(line, {}, [1, 2, 2, 4], 10), null);
  assert.equal(tappedLyricLine(line, {}, [1, 3, 2, 4], 10), null);
  assert.equal(tappedLyricLine(line, {}, [1, 2, 3, 11], 10), null);
  assert.equal(tappedLyricLine(line, {}, [1, NaN, 3, 4], 10), null);
  assert.deepEqual(tappedLyricLine(line, {}, [4, 4.5, 5, 5.8], 10), {
    "line-0:0": { start: 4, end: 4.5 },
    "line-0:1": { start: 4.5, end: 5 },
    "line-0:2": { start: 5, end: 5.8 },
  });
});
test("manual repairs reach preview and complete render payload, with no word omission", () => {
  const track = { id: "test", title: "Test", form: { lyrics: line.text } };
  const draft = {
    ...makeDraft(track),
    lyrics: line.text,
    wordEdits: tappedLyricLine(line, {}, [4, 4.5, 5, 5.8], 10),
  };
  const alignment = { lyrics: line.text, duration: 10, cues: [line] };
  const result = lyricRenderCues(alignment, draft);
  assert.deepEqual(
    result[0].words.map((w) => w.text),
    ["Stay", "right", "here"],
  );
  assert.equal(result[0].words[2].start, 5);
  assert.equal(lyricTimingReview(result, 10).omitted, 0);
  assert.equal(alignedCues(alignment, draft)[0].startFrame, 96);
  assert.equal(
    lyricRenderCues(alignment, { ...draft, lyrics: "Changed lyric sheet" })
      .length,
    0,
  );
});
test("review markers identify out-of-order words and gaps using export ordering", () => {
  const lines = [
    line,
    {
      words: [
        { start: 2.2, end: 3, review: null },
        { start: 3, end: 4, review: "Low confidence" },
      ],
    },
  ];
  assert.deepEqual(lyricProblems(lines, 10), [
    ["", "", "Missing timing"],
    ["Timing conflict", "Low confidence"],
  ]);
  assert.deepEqual(lyricTimingReview(lines, 10), {
    missing: 1,
    conflicting: 1,
    usable: 3,
    omitted: 2,
  });
});
test("waveform peaks include both stereo channels, silence, and the last sample", () => {
  assert.deepEqual(
    [
      ...waveformPeaks(
        [
          new Float32Array([0, -1, 0.25, 0.5]),
          new Float32Array([0, 1, 0, 0.75]),
        ],
        2,
      ),
    ],
    [1, 0.75],
  );
  assert.deepEqual(
    [...waveformPeaks([new Float32Array(5)], 20)],
    [0, 0, 0, 0, 0],
  );
  assert.deepEqual([...waveformPeaks([], 10)], []);
});

function editableSong() {
  const lyrics = "[Verse]\nStay right here\n\n[Outro]\nMegalomaniac";
  const alignment = {
    lyrics,
    duration: 30,
    cues: [
      line,
      {
        id: "line-1",
        text: "Megalomaniac",
        words: [
          {
            text: "Megalomaniac",
            start: 10,
            end: 11.2,
            confidence: 0.9,
            review: null,
          },
        ],
      },
    ],
  };
  const draft = {
    ...makeDraft({ id: "edit", title: "Song", form: { lyrics } }),
    wordEdits: { "line-0:1": { start: 2.2, end: 2.8 } },
  };
  return { alignment, draft };
}
test("deleting text preserves corrections through word index shifts, stale polling, and JSON reload", () => {
  const { alignment, draft } = editableSong();
  const next = {
    ...draft,
    ...deleteLyricText(alignment, draft, "line-0", [0]),
  };
  assert.equal(next.lyrics, "[Verse]\nright here\n\n[Outro]\nMegalomaniac");
  assert.deepEqual(next.wordEdits, {});
  const result = lyricRenderCues(alignment, JSON.parse(JSON.stringify(next)));
  assert.equal(result[0].words[0].text, "right");
  assert.equal(result[0].words[0].start, 2.2);
  assert.equal(result[0].words[0].end, 2.8);
  assert.equal(result[0].words[1].start, null);
  assert.equal(result[1].words[0].start, 10);
  assert.equal(currentLyricAlignment(next)?.wordCount, 3);
  assert.equal(lyricRenderCues(undefined, next).length, 2);
  assert.equal(alignment.cues[0].words.length, 3);
  assert.equal(draft.wordEdits["line-0:1"].start, 2.2);
  assert.equal(currentLyricAlignment({ ...next, language: "de" }), undefined);
  assert.equal(
    currentLyricAlignment({ ...next, lyrics: "different text" }),
    undefined,
  );
});
test("whole-phrase removal and deleting the last word leave a usable empty draft", () => {
  const { alignment, draft } = editableSong();
  const next = { ...draft, ...deleteLyricText(alignment, draft, "line-0") };
  assert.equal(lyricRenderCues(undefined, next)[0].id, "line-1");
  const empty = {
    ...next,
    ...deleteLyricText(currentLyricAlignment(next), next, "line-1", [0]),
  };
  assert.equal(empty.lyrics, "");
  assert.deepEqual(lyricRenderCues(undefined, empty), []);
  const added = {
    ...empty,
    ...insertLyricPhrases(
      currentLyricAlignment(empty),
      empty,
      "Megalomaniac",
      0,
    ).patch,
  };
  assert.equal(
    lyricRenderCues(undefined, added)[0].words[0].text,
    "Megalomaniac",
  );
  assert.equal(lyricRenderCues(undefined, added)[0].words[0].start, null);
});
test("pasted phrases retain all original timing and leave only new words untimed", () => {
  const { alignment, draft } = editableSong();
  const result = insertLyricPhrases(
    alignment,
    draft,
    "A missing phrase\nMegalomaniac",
    1,
  );
  const next = { ...draft, ...result.patch },
    cues = lyricRenderCues(undefined, next);
  assert.equal(cues.length, 4);
  assert.deepEqual(
    cues.map((c) => c.id),
    ["line-0", "line-2", "line-3", "line-1"],
  );
  assert.equal(cues[0].words[1].start, 2.2);
  assert.equal(cues[3].words[0].start, 10);
  assert(
    cues[1].words.every((w) => w.start === null && w.end === null && w.review),
  );
  assert.equal(lyricTimingReview(cues, 30).missing, 5);
  assert.equal(
    next.lyrics
      .replace(/\[[^\]]+\]/g, "")
      .split(/\s+/)
      .filter(Boolean)
      .join(" "),
    cues.flatMap((c) => c.words.map((w) => w.text)).join(" "),
  );
});
test("repeated words get separate IDs and copied durations at the new playhead", () => {
  const { alignment, draft } = editableSong(),
    words = alignment.cues[1].words;
  const at = lyricInsertionIndex(alignment.cues, 15);
  assert.equal(at, 2);
  const first = {
    ...draft,
    ...insertLyricPhrases(alignment, draft, "Megalomaniac", at, {
      words,
      start: 15,
      duration: 30,
    }).patch,
  };
  const next = {
    ...first,
    ...insertLyricPhrases(
      currentLyricAlignment(first),
      first,
      "Megalomaniac",
      3,
      { words, start: 20, duration: 30 },
    ).patch,
  };
  const cues = lyricRenderCues(undefined, next);
  assert.deepEqual(
    cues.slice(1).map((c) => [c.id, c.words[0].start, c.words[0].end]),
    [
      ["line-1", 10, 11.2],
      ["line-2", 15, 16.2],
      ["line-3", 20, 21.2],
    ],
  );
  assert.equal(cues[2].words[0].review, "Copied timing · review");
  assert.throws(
    () =>
      insertLyricPhrases(alignment, draft, "Megalomaniac", 2, {
        words,
        start: 29.5,
        duration: 30,
      }),
    /beyond the song/,
  );
  assert.throws(
    () =>
      insertLyricPhrases(alignment, draft, "Changed", 2, {
        words,
        start: 15,
        duration: 30,
      }),
    /same words/,
  );
});

test("placing an untimed phrase gives every word a reviewed block at the exact playhead without duplication", () => {
  const { alignment, draft } = editableSong();
  const result = placeLyricPhraseAtPlayhead(
    alignment,
    draft,
    "line-0",
    3.125,
    30,
  );
  const next = { ...draft, ...result.patch },
    cues = lyricRenderCues(undefined, next);
  assert.equal(result.estimated, true);
  assert.equal(cues.length, 2);
  assert.equal(cues[0].id, "line-0");
  assert.equal(cues[0].text, "Stay right here");
  assert.deepEqual(
    cues[0].words.map((w) => [w.text, w.start, w.end]),
    [
      ["Stay", 3.125, 3.575],
      ["right", 3.575, 4.025],
      ["here", 4.025, 4.475],
    ],
  );
  assert(
    cues[0].words.every((w) => w.review.includes("Manual phrase placement")),
  );
  assert.equal(cues[1].words[0].start, 10);
  assert.equal(lyricTimingReview(cues, 30).omitted, 0);
  assert.equal(alignment.cues[0].words[2].start, null);
  assert.equal(draft.wordEdits["line-0:1"].start, 2.2);
  assert.deepEqual(
    lyricRenderCues(undefined, JSON.parse(JSON.stringify(next))),
    cues,
  );
});
test("placing a fully timed phrase preserves corrected word spacing and moves its lyric-sheet position", () => {
  const { alignment, draft } = editableSong();
  draft.wordEdits["line-0:2"] = { start: 3, end: 4 };
  const result = placeLyricPhraseAtPlayhead(alignment, draft, "line-0", 15, 30);
  assert.equal(result.estimated, false);
  const next = { ...draft, ...result.patch },
    cues = lyricRenderCues(undefined, next);
  assert.equal(result.index, 1);
  assert.deepEqual(
    cues.map((line) => line.id),
    ["line-1", "line-0"],
  );
  assert.deepEqual(
    cues[1].words.map((w) => [w.start, w.end]),
    [
      [15, 15.4],
      [16.2, 16.8],
      [17, 18],
    ],
  );
  assert.equal(cues[0].words[0].start, 10);
  assert.deepEqual(
    next.lyrics.split(/\s+/).filter((s) => !/^\[/.test(s)),
    ["Megalomaniac", "Stay", "right", "here"],
  );
  assert.equal(lyricTimingReview(cues, 30).omitted, 0);
  const again = placeLyricPhraseAtPlayhead(
    currentLyricAlignment(next),
    next,
    "line-0",
    20,
    30,
  );
  assert.equal(
    lyricRenderCues(undefined, { ...next, ...again.patch }).flatMap(
      (c) => c.words,
    ).length,
    4,
  );
});
test("phrase placement respects song edges and keeps provisional timing before the next phrase", () => {
  const { alignment, draft } = editableSong();
  const result = placeLyricPhraseAtPlayhead(alignment, draft, "line-0", 9, 30);
  const cues = lyricRenderCues(undefined, { ...draft, ...result.patch });
  assert.equal(cues[0].words[0].start, 9);
  assert.equal(cues[0].words[2].end, 10);
  assert.throws(
    () => placeLyricPhraseAtPlayhead(alignment, draft, "line-0", 9.99, 30),
    /not enough room/,
  );
  assert.throws(
    () => placeLyricPhraseAtPlayhead(alignment, draft, "line-1", 29, 30),
    /does not fit/,
  );
  assert.throws(
    () => placeLyricPhraseAtPlayhead(alignment, draft, "line-0", 30, 30),
    /inside the song/,
  );
  assert.throws(
    () => placeLyricPhraseAtPlayhead(alignment, draft, "line-0", NaN, 30),
    /inside the song/,
  );
});
