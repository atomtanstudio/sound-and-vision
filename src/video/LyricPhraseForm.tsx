import { useEffect, useState } from "react";
import type { Alignment, AlignedWord } from "./production";
import { lyricLines } from "./timeline";
import { lyricInsertionIndex } from "./lyricEditing";

export type PhraseSource = { text: string; words?: AlignedWord[] };

export function LyricPhraseForm({
  source,
  lines,
  selected,
  playhead,
  onInsert,
  onClose,
}: {
  source: PhraseSource;
  lines: Alignment["cues"];
  selected: number;
  playhead: number;
  onInsert: (text: string, index: number, copiedWords?: AlignedWord[]) => void;
  onClose: () => void;
}) {
  const [text, setText] = useState(source.text),
    [reuse, setReuse] = useState(!!source.words);
  const [placement, setPlacement] = useState("playhead"),
    [error, setError] = useState("");
  useEffect(() => {
    setText(source.text);
    setReuse(!!source.words);
    setPlacement("playhead");
    setError("");
  }, [source]);
  const phrases = lyricLines(text);
  const canReuse =
    !!source.words?.length &&
    phrases.length === 1 &&
    source.words.map((w) => w.text).join(" ") ===
      phrases[0].text.split(/\s+/).join(" ") &&
    source.words.every(
      (w) =>
        w.start !== null &&
        w.end !== null &&
        Number.isFinite(w.start + w.end) &&
        w.end > w.start,
    );
  const index =
    placement === "playhead"
      ? lyricInsertionIndex(lines, playhead)
      : placement === "end"
        ? lines.length
        : selected + (placement === "after" ? 1 : 0);
  return (
    <form
      className="lyric-phrase-form"
      aria-label="Insert lyric phrase"
      onSubmit={(e) => {
        e.preventDefault();
        try {
          onInsert(text, index, reuse && canReuse ? source.words : undefined);
        } catch (e) {
          setError((e as Error).message);
        }
      }}
    >
      <div className="lyric-line-detail-heading">
        <h3>{source.words ? "Duplicate lyrics" : "Add a phrase"}</h3>
        <button type="button" className="quiet-button" onClick={onClose}>
          Cancel insertion
        </button>
      </div>
      <label>
        Phrase text
        <textarea
          aria-label="Phrase text"
          rows={3}
          maxLength={10000}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setError("");
          }}
          placeholder="Type or paste lyrics. Put each phrase on its own line."
        />
      </label>
      <label>
        Insert position
        <select
          aria-label="Phrase insert position"
          value={placement}
          onChange={(e) => setPlacement(e.target.value)}
        >
          <option value="playhead">
            Near playhead · {playhead.toFixed(2)}s
          </option>
          {!!lines.length && (
            <option value="before">Before line {selected + 1}</option>
          )}
          {!!lines.length && (
            <option value="after">After line {selected + 1}</option>
          )}
          <option value="end">End of lyrics</option>
        </select>
      </label>
      {source.words && (
        <label className="lyric-reuse-timing">
          <input
            type="checkbox"
            checked={reuse && canReuse}
            disabled={!canReuse}
            onChange={(e) => setReuse(e.target.checked)}
          />
          Reuse copied timing at playhead
        </label>
      )}
      <p className="video-field-note">
        {reuse && canReuse
          ? "The copy starts at the playhead and keeps its word lengths and pauses. Review it against the new vocal."
          : "New words start untimed. Place them with tap timing or the word start/end controls. Existing timings stay in place."}
      </p>
      <p className="video-field-note">
        {index === lines.length
          ? "Adds to the end of your lyrics."
          : `Inserts before line ${index + 1}: ${lines[index]?.text}`}{" "}
        Each new line becomes a separate phrase.
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <button
        type="submit"
        className="primary-button"
        disabled={!phrases.length}
      >
        Insert {phrases.length > 1 ? `${phrases.length} phrases` : "phrase"}
      </button>
    </form>
  );
}
