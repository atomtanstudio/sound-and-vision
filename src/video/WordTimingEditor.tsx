import type { Alignment } from "./production";
import type { VideoDraft } from "./timeline";
export function WordTimingEditor({
  alignment,
  draft,
  duration,
  change,
  seek,
}: {
  alignment: Alignment;
  draft: VideoDraft;
  duration: number;
  change: (patch: Partial<VideoDraft>) => void;
  seek: (seconds: number) => void;
}) {
  function edit(
    id: string,
    key: "start" | "end",
    value: string,
    start: number | null,
    end: number | null,
  ) {
    if (value === "" || !Number.isFinite(Number(value))) return;
    const next = {
      start,
      end,
      [key]: Number(value),
    };
    if (
      (next.start !== null && next.start < 0) ||
      (next.end !== null && next.end > duration) ||
      (next.start !== null && next.end !== null && next.end <= next.start)
    )
      return;
    change({ wordEdits: { ...draft.wordEdits, [id]: next } });
  }
  return (
    <details className="video-cue-editor">
      <summary>
        Word timing{" "}
        <small>Listen, review flagged words, adjust if needed</small>
      </summary>
      <p className="video-field-note">
        Times come from the vocal. Automatic alignment can still miss sung
        words. Unmatched words have no timestamp until you set one.
      </p>
      {!!alignment.unmatchedVocalWords && (
        <p className="video-field-note">
          The vocal also contains {alignment.unmatchedVocalWords} recognized
          words that could not be matched to this lyric sheet. Review the text
          before relying on the final sequence.
        </p>
      )}
      {alignment.cues.map((line, lineIndex) => (
        <details className="video-word-line" key={line.id}>
          <summary>
            <span>
              {lineIndex + 1}. {line.text}
            </span>
            <small>
              {line.words.filter(
                (w, i) =>
                  w.review &&
                  !(
                    draft.wordEdits[`${line.id}:${i}`]?.start != null &&
                    draft.wordEdits[`${line.id}:${i}`]?.end != null
                  ),
              ).length || ""}
              {line.words.some(
                (w, i) =>
                  w.review &&
                  !(
                    draft.wordEdits[`${line.id}:${i}`]?.start != null &&
                    draft.wordEdits[`${line.id}:${i}`]?.end != null
                  ),
              )
                ? " to review"
                : ""}
            </small>
          </summary>
          <div className="video-word-table">
            {line.words.map((original, index) => {
              const id = `${line.id}:${index}`,
                override = draft.wordEdits[id],
                w = override
                  ? {
                      ...original,
                      ...override,
                      review:
                        override.start !== null && override.end !== null
                          ? null
                          : "Set both word times",
                    }
                  : original;
              return (
                <div className={w.review ? "needs-review" : ""} key={id}>
                  <button
                    className="quiet-button"
                    disabled={w.start === null}
                    onClick={() => seek(Math.max(0, w.start! - 0.3))}
                  >
                    {w.text}
                  </button>
                  <label>
                    <span className="sr-only">
                      Line {lineIndex + 1} word {index + 1} start
                    </span>
                    <input
                      type="number"
                      min={0}
                      max={duration}
                      step={0.02}
                      value={w.start ?? ""}
                      placeholder="Start"
                      onChange={(e) =>
                        edit(id, "start", e.target.value, w.start, w.end)
                      }
                    />
                  </label>
                  <label>
                    <span className="sr-only">
                      Line {lineIndex + 1} word {index + 1} end
                    </span>
                    <input
                      type="number"
                      min={0}
                      max={duration}
                      step={0.02}
                      value={w.end ?? ""}
                      placeholder="End"
                      onChange={(e) =>
                        edit(id, "end", e.target.value, w.start, w.end)
                      }
                    />
                  </label>
                  <small>
                    {override ? "Edited" : w.review || "Audio aligned"}
                  </small>
                  {override && (
                    <button
                      className="quiet-button"
                      onClick={() => {
                        const edits = { ...draft.wordEdits };
                        delete edits[id];
                        change({ wordEdits: edits });
                      }}
                    >
                      Reset
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </details>
      ))}
    </details>
  );
}
