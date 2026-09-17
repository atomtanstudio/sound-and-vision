import type { Alignment } from "./production";
import { FPS, type VideoDraft } from "./timeline";

export function LyricTimingPreview({
  lines,
  cueEdits,
  position,
}: {
  lines: Alignment["cues"];
  cueEdits?: VideoDraft["cueEdits"];
  position: number;
}) {
  const active = lines.filter((line) => {
    const words = line.words.filter(
      (w) => w.start !== null && w.end !== null && w.end > w.start,
    );
    const edit = cueEdits?.[line.id];
    const lineStart = edit
      ? edit.startFrame / FPS
      : Math.min(...words.map((w) => w.start!));
    const lineEnd = edit
      ? edit.endFrame / FPS
      : Math.max(...words.map((w) => w.end!));
    return words.length && position >= lineStart && position < lineEnd;
  });
  return (
    <section className="lyric-live-preview" aria-label="Live lyric preview">
      <div className="lyric-live-preview-label">
        <span>LIVE LYRIC PREVIEW</span>
        <span>
          {active.length > 1
            ? `${active.length} overlapping lines`
            : "Follows the playhead"}
        </span>
      </div>
      <div className="lyric-live-preview-words">
        {active.length ? (
          active.slice(0, 3).map((line) => (
            <p key={line.id}>
              {line.words.map((word, i) => {
                const timed = word.start !== null && word.end !== null;
                const current =
                  timed && position >= word.start! && position < word.end!;
                return (
                  <span
                    key={i}
                    aria-current={current ? "true" : undefined}
                    className={
                      !timed
                        ? "untimed"
                        : current
                          ? "current"
                          : position < word.start!
                            ? "upcoming"
                            : ""
                    }
                  >
                    {word.text}{" "}
                  </span>
                );
              })}
            </p>
          ))
        ) : (
          <p className="lyric-live-empty">No timed lyrics here</p>
        )}
      </div>
      <small>
        {active.some((line) =>
          line.words.some((word) => word.start === null || word.end === null),
        )
          ? "Dotted words still need timing."
          : active.length &&
              !active.some((line) =>
                line.words.some(
                  (word) =>
                    word.start !== null &&
                    word.end !== null &&
                    position >= word.start &&
                    position < word.end,
                ),
              )
            ? "Gap between words"
            : "Play or scrub to check the words against the vocal."}
      </small>
    </section>
  );
}
