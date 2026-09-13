import type { Alignment } from "./production";
import { lyricLines, lyricRenderCues, type VideoDraft } from "./timeline.ts";

type Line = Alignment["cues"][number];
type Edits = VideoDraft["wordEdits"];

function reviseLyricSheet(lyrics: string, before: Line[], after: Line[]) {
  if (!after.length) return "";
  const positions = new Map(after.map((line, i) => [line.id, i]));
  const output: string[] = [];
  let original = 0,
    next = 0;
  for (const raw of lyrics.split(/\r?\n/)) {
    if (!raw.trim() || /^\[[^\]]+\]$/.test(raw.trim())) {
      output.push(raw);
      continue;
    }
    const index = positions.get(before[original++]?.id);
    if (index !== undefined)
      while (next <= index) output.push(after[next++].text);
  }
  while (next < after.length) output.push(after[next++].text);
  return output.join("\n");
}

/** Materialize overrides before changing word indices. Text and timing undo together. */
function lyricRevision(
  alignment: Alignment,
  draft: VideoDraft,
  before: Line[],
  after: Line[],
): Partial<VideoDraft> {
  const cues = after
    .filter((line) => line.words.length)
    .map((line) => {
      const timed = line.words.filter(
        (w) => w.start !== null && w.end !== null,
      );
      return {
        ...line,
        text: line.words.map((w) => w.text).join(" "),
        start: timed.length ? Math.min(...timed.map((w) => w.start!)) : null,
        end: timed.length ? Math.max(...timed.map((w) => w.end!)) : null,
      };
    });
  const lyrics = reviseLyricSheet(draft.lyrics, before, cues);
  if (lyrics.length > 30000 || cues.length > 2000)
    throw new Error(
      "The lyric sheet exceeds the supported length. Shorten it before adding more phrases.",
    );
  return {
    lyrics,
    wordEdits: {},
    cueEdits: {},
    lyricRevision: {
      language: draft.language,
      alignment: {
        lyrics,
        duration: alignment.duration,
        method: "manual-lyrics",
        cues,
        wordCount: cues.reduce((n, line) => n + line.words.length, 0),
        reviewCount: cues.reduce(
          (n, line) => n + line.words.filter((w) => w.review).length,
          0,
        ),
      },
    },
  };
}

export function deleteLyricText(
  alignment: Alignment,
  draft: VideoDraft,
  lineId: string,
  wordIndices?: number[],
) {
  const before = lyricRenderCues(alignment, draft);
  const selected = new Set(wordIndices);
  const after = before.flatMap((line) =>
    line.id !== lineId
      ? [line]
      : wordIndices === undefined
        ? []
        : [{ ...line, words: line.words.filter((_, i) => !selected.has(i)) }],
  );
  return lyricRevision(alignment, draft, before, after);
}

export function lyricInsertionIndex(lines: Line[], playhead: number) {
  const next = lines.findIndex((line) => {
    const bounds = lineBounds(line);
    return bounds && bounds.start > playhead;
  });
  return next < 0 ? lines.length : next;
}

/** Place one existing phrase, keeping its identity and every surrounding timing. */
export function placeLyricPhraseAtPlayhead(
  alignment: Alignment,
  draft: VideoDraft,
  lineId: string,
  playhead: number,
  duration: number,
) {
  const before = lyricRenderCues(alignment, draft);
  const line = before.find((line) => line.id === lineId);
  const at = precision(playhead);
  if (!line?.words.length) throw new Error("Choose a phrase with lyric words.");
  if (!Number.isFinite(at + duration) || at < 0 || at >= duration)
    throw new Error("Move the playhead inside the song to place this phrase.");
  let last = 0;
  const measured = line.words.every((word) => {
    if (
      word.start === null ||
      word.end === null ||
      !Number.isFinite(word.start + word.end) ||
      word.start < last - 0.001 ||
      word.end <= word.start
    )
      return false;
    last = word.end;
    return true;
  });
  const rest = before.filter((item) => item.id !== lineId);
  let placed: Line;
  if (measured) {
    const bounds = lineBounds(line)!;
    if (at + bounds.end - bounds.start > duration + 0.001)
      throw new Error(
        "The full phrase does not fit after the playhead. Move the playhead earlier or shorten the phrase timing.",
      );
    const shift = at - bounds.start;
    placed = {
      ...line,
      words: line.words.map((word) => ({
        ...word,
        start: precision(word.start! + shift),
        end: precision(word.end! + shift),
      })),
    };
  } else {
    // This explicit manual placement is provisional, not audio-derived alignment.
    const nextStart = Math.min(
      duration,
      ...rest
        .map((item) => lineBounds(item)?.start)
        .filter((time): time is number => time !== undefined && time > at),
    );
    const length = Math.min(
      Math.max(1, line.words.length * 0.45),
      8,
      nextStart - at,
    );
    if (length < line.words.length * 0.02)
      throw new Error(
        "There is not enough room before the next phrase. Move the playhead or adjust the neighboring phrase first.",
      );
    placed = {
      ...line,
      words: line.words.map((word, i) => ({
        ...word,
        start: precision(at + (length * i) / line.words.length),
        end: precision(at + (length * (i + 1)) / line.words.length),
        review: "Manual phrase placement · review word timing",
      })),
    };
  }
  const index = lyricInsertionIndex(rest, at);
  return {
    patch: lyricRevision(alignment, draft, before, [
      ...rest.slice(0, index),
      placed,
      ...rest.slice(index),
    ]),
    index,
    estimated: !measured,
    start: at,
  };
}

export function insertLyricPhrases(
  alignment: Alignment,
  draft: VideoDraft,
  text: string,
  index: number,
  copied?: { words: Line["words"]; start: number; duration: number },
) {
  const phrases = lyricLines(text);
  if (!phrases.length) throw new Error("Enter at least one lyric word.");
  if (text.length > 10000)
    throw new Error("Insert up to 10,000 characters at a time.");
  const before = lyricRenderCues(alignment, draft);
  let nextId =
    Math.max(
      -1,
      ...before
        .map((line) => Number(line.id.replace(/^line-/, "")))
        .filter(Number.isFinite),
    ) + 1;
  const added = phrases.map((phrase): Line => ({
    id: `line-${nextId++}`,
    text: phrase.text,
    start: null,
    end: null,
    words: phrase.text.split(/\s+/).map((text) => ({
      text,
      start: null,
      end: null,
      confidence: 0,
      review: "Added lyric · set timing",
    })),
  }));
  if (
    added.some(
      (line) =>
        line.words.length > 200 || line.words.some((w) => w.text.length > 300),
    )
  )
    throw new Error(
      "Split long passages into phrases of at most 200 words, with words under 300 characters.",
    );
  if (copied) {
    const source = copied.words,
      bounds = lineBounds({ words: source });
    if (
      added.length !== 1 ||
      source.length !== added[0].words.length ||
      source.some(
        (word, i) =>
          word.text !== added[0].words[i].text ||
          word.start === null ||
          word.end === null ||
          word.end <= word.start,
      ) ||
      !bounds
    )
      throw new Error(
        "Copied timing requires the same words with complete timestamps. Uncheck Reuse timing to add untimed words.",
      );
    const shift = copied.start - bounds.start;
    if (
      !Number.isFinite(shift) ||
      copied.start < 0 ||
      bounds.end + shift > copied.duration
    )
      throw new Error(
        "The copied phrase would extend beyond the song. Move the playhead earlier or add it without timing.",
      );
    added[0].words = source.map((word) => ({
      ...word,
      start: precision(word.start! + shift),
      end: precision(word.end! + shift),
      review: "Copied timing · review",
    }));
  }
  const at = Math.max(0, Math.min(before.length, index));
  return {
    patch: lyricRevision(alignment, draft, before, [
      ...before.slice(0, at),
      ...added,
      ...before.slice(at),
    ]),
    index: at,
  };
}
export const precision = (seconds: number) => Math.round(seconds * 1000) / 1000;

/** Partial words keep their missing endpoints when the line moves. */
export function lineBounds(line: Pick<Line, "words">) {
  const times = line.words.flatMap((word) =>
    [word.start, word.end].filter(
      (t): t is number => t !== null && Number.isFinite(t),
    ),
  );
  return times.length
    ? { start: Math.min(...times), end: Math.max(...times) }
    : null;
}

export function moveLyricLine(
  line: Line,
  edits: Edits,
  delta: number,
  duration: number,
): Edits {
  const bounds = lineBounds(line);
  if (
    !bounds ||
    !Number.isFinite(delta) ||
    bounds.end - bounds.start > duration
  )
    return edits;
  const shift = Math.max(-bounds.start, Math.min(duration - bounds.end, delta));
  const next = { ...edits };
  line.words.forEach((word, i) => {
    next[`${line.id}:${i}`] = {
      start: word.start === null ? null : precision(word.start + shift),
      end: word.end === null ? null : precision(word.end + shift),
    };
  });
  return next;
}

/** A user's taps replace one line only. The last tap marks the line's end. */
export function tappedLyricLine(
  line: Line,
  edits: Edits,
  taps: number[],
  duration: number,
): Edits | null {
  if (
    taps.length !== line.words.length + 1 ||
    taps.some(
      (t, i) =>
        !Number.isFinite(t) ||
        t < 0 ||
        t > duration ||
        (i > 0 && t - taps[i - 1] < 0.02),
    )
  )
    return null;
  return {
    ...edits,
    ...Object.fromEntries(
      line.words.map((_, i) => [
        `${line.id}:${i}`,
        { start: precision(taps[i]), end: precision(taps[i + 1]) },
      ]),
    ),
  };
}

/** Label the same missing/conflicting words that export rejects. */
export function lyricProblems(lines: Pick<Line, "words">[], duration: number) {
  let last = 0;
  return lines.map((line) =>
    line.words.map((word) => {
      const { start, end } = word;
      if (start === null || end === null) return "Missing timing";
      if (
        !Number.isFinite(start + end) ||
        start < 0 ||
        end <= start ||
        end > duration + 0.05 ||
        start < last - 0.001
      )
        return "Timing conflict";
      last = end;
      return word.review || "";
    }),
  );
}

/** Peak envelope includes both channels so phase cancellation cannot hide audio. */
export function waveformPeaks(channels: Float32Array[], buckets: number) {
  const length = channels[0]?.length || 0;
  const count = Math.min(length, Math.max(1, Math.floor(buckets)));
  const peaks = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    const start = Math.floor((i * length) / count),
      end = Math.floor(((i + 1) * length) / count);
    for (const channel of channels)
      for (let j = start; j < end; j++)
        peaks[i] = Math.max(peaks[i], Math.abs(channel[j] || 0));
  }
  return peaks;
}
