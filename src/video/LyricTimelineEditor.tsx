import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent,
  type RefObject,
} from "react";
import {
  Pause,
  Play,
  Undo2,
  Redo2,
  Plus,
  Copy,
  Trash2,
  MousePointer2,
  Hand,
} from "lucide-react";
import type { Alignment } from "./production";
import {
  lyricRenderCues,
  lyricTimingReview,
  type VideoDraft,
} from "./timeline";
import {
  lineBounds,
  lyricProblems,
  moveLyricLine,
  precision,
  tappedLyricLine,
  deleteLyricText,
  insertLyricPhrases,
  placeLyricPhraseAtPlayhead,
} from "./lyricEditing";
import { useWaveform } from "./useWaveform";
import { WordTimingEditor } from "./WordTimingEditor";
import { LyricPhraseForm, type PhraseSource } from "./LyricPhraseForm";
import { LyricTimingPreview } from "./LyricTimingPreview";
import { VocalPreview } from "./VocalPreview";

type Props = {
  alignment: Alignment;
  draft: VideoDraft;
  duration: number;
  audioUrl: string;
  audioRef: RefObject<HTMLAudioElement | null>;
  audioActive: boolean;
  vocalPreviewEndpoint?: string;
  position: number;
  playing: boolean;
  play: () => void;
  seek: (seconds: number) => void;
  change: (patch: Partial<VideoDraft>) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
};
const stamp = (t: number) =>
  `${Math.floor(t / 60)}:${(t % 60).toFixed(2).padStart(5, "0")}`;
const clamp = (v: number, min: number, max: number) =>
  Math.max(min, Math.min(max, v));

export function LyricTimelineEditor(props: Props) {
  const [open, setOpen] = useState(false);
  const timing = lyricTimingReview(
    lyricRenderCues(props.alignment, props.draft),
    props.duration,
  );
  return (
    <section className="lyric-timeline" aria-label="Lyric timing editor">
      <div className="lyric-timeline-heading">
        <div>
          <h2>Lyric timing</h2>
          <p>
            {timing.usable} words timed · {timing.missing} missing ·{" "}
            {timing.conflicting} conflicts
          </p>
        </div>
        <button
          className="secondary-button"
          aria-expanded={open}
          aria-controls="lyric-timeline-body"
          onClick={() => setOpen(!open)}
        >
          {open ? "Close timing editor" : "Edit lyric timing"}
        </button>
      </div>
      {open && <TimelineBody {...props} />}
    </section>
  );
}

function TimelineBody({
  alignment,
  draft,
  duration,
  audioUrl,
  audioRef,
  audioActive,
  vocalPreviewEndpoint,
  position,
  playing,
  play,
  seek,
  change,
  undo,
  redo,
  canUndo,
  canRedo,
}: Props) {
  const [monitorUrl, setMonitorUrl] = useState<string | undefined>();
  const { data: waveform, error: waveformError } = useWaveform(
    monitorUrl || audioUrl,
  );
  const [tool, setTool] = useState<"select" | "pan">("select");
  const pan = useRef<{ x: number; start: number; width: number } | null>(null);
  const [selectedIndex, setSelected] = useState(0),
    [selectedWordIndex, setWordIndex] = useState(0);
  const [windowSize, setWindowSize] = useState(20),
    [windowStart, setWindowStart] = useState(0);
  const [follow, setFollow] = useState(true),
    [notice, setNotice] = useState("");
  const [taps, setTaps] = useState<number[] | null>(null);
  const [phraseSource, setPhraseSource] = useState<PhraseSource | null>(null);
  const [previewEdits, setPreviewEdits] = useState<
    VideoDraft["wordEdits"] | null
  >(null);
  const lineTrack = useRef<HTMLDivElement>(null);
  const lineList = useRef<HTMLDivElement>(null);
  const tapButton = useRef<HTMLButtonElement>(null);
  const tapping = taps !== null;
  useEffect(() => {
    if (tapping) tapButton.current?.focus();
  }, [tapping]);
  type Drag = {
    x: number;
    width: number;
    line: Alignment["cues"][number];
    edits: VideoDraft["wordEdits"];
    word?: number;
    edge?: "start" | "end";
  };
  const drag = useRef<Drag | null>(null);
  const lines = useMemo(
    () =>
      lyricRenderCues(alignment, {
        ...draft,
        wordEdits: previewEdits || draft.wordEdits,
      }),
    [alignment, draft, previewEdits],
  );
  const problems = useMemo(
    () => lyricProblems(lines, duration),
    [lines, duration],
  );
  const selected = Math.min(selectedIndex, Math.max(0, lines.length - 1)),
    line = lines[selected],
    wordIndex = Math.min(
      selectedWordIndex,
      Math.max(0, (line?.words.length || 0) - 1),
    ),
    word = line?.words[wordIndex];
  useEffect(() => {
    setSelected((i) => Math.min(i, Math.max(0, lines.length - 1)));
    setWordIndex((i) =>
      Math.min(i, Math.max(0, (line?.words.length || 0) - 1)),
    );
    setTaps(null);
    setPreviewEdits(null);
    drag.current = null;
  }, [draft.lyrics]);
  const span = Math.max(0.1, Math.min(windowSize, duration)),
    maxStart = Math.max(0, duration - span);
  const start = clamp(windowStart, 0, maxStart),
    end = start + span;
  const percent = (t: number) => ((t - start) / span) * 100;
  const cursorVisible = position >= start && position <= end;
  function startPan(e: PointerEvent<HTMLElement>) {
    if (tool !== "pan" || e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    pan.current = { x: e.clientX, start, width: e.currentTarget.clientWidth };
    setFollow(false);
  }
  function movePan(e: PointerEvent<HTMLElement>) {
    if (pan.current)
      setWindowStart(
        clamp(
          pan.current.start -
            ((e.clientX - pan.current.x) / pan.current.width) * span,
          0,
          maxStart,
        ),
      );
  }
  function endPan() {
    pan.current = null;
  }
  const panHandlers = {
    onPointerDownCapture: startPan,
    onPointerMove: movePan,
    onPointerUp: endPan,
    onPointerCancel: endPan,
    onLostPointerCapture: endPan,
  };

  useEffect(() => {
    const list = lineList.current;
    const button = list?.querySelector<HTMLButtonElement>(".selected");
    if (!list || !button) return;
    const parent = list.getBoundingClientRect(),
      child = button.getBoundingClientRect();
    if (child.top < parent.top) list.scrollTop += child.top - parent.top;
    else if (child.bottom > parent.bottom)
      list.scrollTop += child.bottom - parent.bottom;
  }, [selected]);

  useEffect(() => {
    if (
      follow &&
      playing &&
      !drag.current &&
      (position < start || position > end - 0.4)
    )
      setWindowStart(clamp(position - span * 0.15, 0, maxStart));
  }, [position, playing, follow, start, end, span, maxStart]);

  function focusLine(index: number) {
    setSelected(index);
    setWordIndex(0);
    setTaps(null);
    setNotice("");
    const bounds = lineBounds(lines[index]);
    if (bounds) {
      const time = Math.max(0, bounds.start - 0.7);
      seek(time);
      setWindowStart(clamp(time - span * 0.1, 0, maxStart));
    }
  }
  function scrub(e: PointerEvent<HTMLElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    seek(
      precision(
        clamp(
          start + ((e.clientX - rect.left) / rect.width) * span,
          0,
          duration,
        ),
      ),
    );
  }
  function beginDrag(
    e: PointerEvent<HTMLElement>,
    index: number,
    wi?: number,
    edge?: "start" | "end",
  ) {
    if (e.button !== 0 || taps || tool === "pan") return;
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    setSelected(index);
    setWordIndex(wi ?? 0);
    drag.current = {
      x: e.clientX,
      width: lineTrack.current!.clientWidth,
      line: lines[index],
      edits: draft.wordEdits,
      word: wi,
      edge,
    };
  }
  function dragEdits(e: PointerEvent<HTMLElement>) {
    const d = drag.current;
    if (!d) return null;
    const delta = ((e.clientX - d.x) / d.width) * span;
    if (d.word === undefined)
      return moveLyricLine(d.line, d.edits, delta, duration);
    const w = d.line.words[d.word];
    if (w.start === null || w.end === null) return null;
    let a = w.start,
      b = w.end;
    if (d.edge === "start") a = clamp(a + delta, 0, b - 0.02);
    else if (d.edge === "end") b = clamp(b + delta, a + 0.02, duration);
    else {
      const shift = clamp(delta, -a, duration - b);
      a += shift;
      b += shift;
    }
    return {
      ...d.edits,
      [`${d.line.id}:${d.word}`]: { start: precision(a), end: precision(b) },
    };
  }
  function finishDrag(e: PointerEvent<HTMLElement>) {
    const edits = dragEdits(e);
    const moved = drag.current && Math.abs(e.clientX - drag.current.x) >= 1;
    drag.current = null;
    setPreviewEdits(null);
    if (edits && moved) change({ wordEdits: edits });
  }
  function cancelDrag() {
    drag.current = null;
    setPreviewEdits(null);
  }
  const dragging = {
    onPointerMove: (e: PointerEvent<HTMLElement>) => {
      if (drag.current) setPreviewEdits(dragEdits(e));
    },
    onPointerUp: finishDrag,
    onPointerCancel: cancelDrag,
    onLostPointerCapture: cancelDrag,
  };
  function setWordTime(key: "start" | "end", value: number | null) {
    if (!word || !line) return;
    const next = {
      start: word.start,
      end: word.end,
      [key]: value === null ? null : precision(value),
    };
    if (
      (value !== null &&
        (!Number.isFinite(value) || value < 0 || value > duration)) ||
      (next.start !== null && next.end !== null && next.end <= next.start)
    ) {
      setNotice(
        "A word must end after it starts, within the song. Clear an endpoint first if you are moving it far away.",
      );
      return;
    }
    setNotice("");
    change({
      wordEdits: { ...draft.wordEdits, [`${line.id}:${wordIndex}`]: next },
    });
  }
  function tap() {
    if (!taps || !line) return;
    const time = precision(position);
    if (
      time < 0 ||
      time > duration ||
      (taps.length && time - taps[taps.length - 1] < 0.02)
    ) {
      setNotice("Move forward in the song before marking the next word.");
      return;
    }
    const next = [...taps, time];
    if (next.length === line.words.length + 1) {
      const edits = tappedLyricLine(line, draft.wordEdits, next, duration);
      if (edits) change({ wordEdits: edits });
      setTaps(null);
      setNotice(
        "Line timing saved. Listen again and shorten word endings where there are pauses.",
      );
    } else {
      setTaps(next);
      setWordIndex(Math.min(next.length, line.words.length - 1));
      setNotice("");
    }
  }
  function removeText(indices?: number[]) {
    if (!line) return;
    change(deleteLyricText(alignment, draft, line.id, indices));
    setWordIndex(0);
    setPhraseSource(null);
    setNotice(
      indices
        ? "Word removed. Other word timings are preserved. Use Undo to restore it."
        : "Phrase removed. Other phrases keep their timing. Use Undo to restore it.",
    );
  }
  function placePhrase(lineId: string) {
    try {
      // Do not call focusLine: selecting a row would seek away from this playhead.
      const at =
        audioActive && audioRef.current
          ? audioRef.current.currentTime
          : position;
      const result = placeLyricPhraseAtPlayhead(
        alignment,
        draft,
        lineId,
        at,
        duration,
      );
      change(result.patch);
      setSelected(result.index);
      setWordIndex(0);
      setPhraseSource(null);
      setWindowStart(clamp(result.start - span * 0.1, 0, maxStart));
      setNotice(
        result.estimated
          ? "Full phrase placed at the playhead. Its words have provisional, evenly spaced timing. Listen and fine-tune the word times or use tap timing."
          : "Full phrase placed at the playhead with its word spacing preserved. Use Undo to restore its previous position.",
      );
    } catch (error) {
      setNotice((error as Error).message);
    }
  }

  const wavePath = useMemo(() => {
    if (!waveform) return "";
    const segments: string[] = [];
    for (let x = 0; x < 900; x += 2) {
      const a = Math.floor(
        ((start + (x / 900) * span) / waveform.duration) *
          waveform.peaks.length,
      );
      const b = Math.ceil(
        ((start + ((x + 2) / 900) * span) / waveform.duration) *
          waveform.peaks.length,
      );
      let peak = 0;
      for (let i = Math.max(0, a); i < Math.min(b, waveform.peaks.length); i++)
        peak = Math.max(peak, waveform.peaks[i]);
      const h = peak * 38;
      segments.push(`M${x},${44 - h}V${44 + h}`);
    }
    return segments.join(" ");
  }, [waveform, start, span]);

  const rowEnds: number[] = [];
  const blocks = lines
    .map((l, i) => ({ line: l, i, bounds: lineBounds(l) }))
    .filter((b) => b.bounds && b.bounds.end >= start && b.bounds.start <= end)
    .sort((a, b) => a.bounds!.start - b.bounds!.start)
    .map((b) => {
      let row = rowEnds.findIndex((t) => t <= b.bounds!.start);
      if (row < 0) row = rowEnds.length;
      rowEnds[row] = b.bounds!.end;
      return { ...b, row };
    });
  const issueLines = problems.flatMap((p, i) => (p.some(Boolean) ? [i] : []));
  const blockStyle = (a: number, b: number) => ({
    left: `${percent(a)}%`,
    width: `${Math.max(0.25, ((b - a) / span) * 100)}%`,
  });

  return (
    <div id="lyric-timeline-body" className="lyric-timeline-body">
      <p className="video-field-note">
        {tool === "pan"
          ? "Hand tool: drag the waveform or lyric tracks left or right to move through the song. "
          : "Arrow tool: click the waveform to scrub. Drag a lyric block to move the whole line. "}
        Select a word to move it or drag its edges. Arrow keys nudge a focused
        block by 0.05s; Shift moves it by 0.5s.
      </p>
      <div className="lyric-timeline-toolbar">
        <div className="lyric-tool-picker" aria-label="Timeline tools">
          <button
            className="quiet-button"
            aria-label="Select and move lyrics"
            title="Select and move lyrics"
            aria-pressed={tool === "select"}
            onClick={() => setTool("select")}
          >
            <MousePointer2 size={18} />
          </button>
          <button
            className="quiet-button"
            aria-label="Pan timeline"
            title="Hand tool · pan timeline"
            aria-pressed={tool === "pan"}
            onClick={() => setTool("pan")}
          >
            <Hand size={18} />
          </button>
        </div>
        <button
          className="secondary-button"
          onClick={play}
          aria-label={
            playing ? "Pause timing playback" : "Play timing playback"
          }
        >
          {playing ? <Pause size={16} /> : <Play size={16} />}{" "}
          {playing ? "Pause" : "Play"}
        </button>
        <output className="lyric-clock" aria-label="Timing playhead">
          {stamp(position)}
        </output>
        <label>
          Zoom
          <select
            aria-label="Timeline zoom"
            value={windowSize}
            onChange={(e) => {
              setWindowSize(Number(e.target.value));
              setWindowStart(Math.max(0, position - 2));
            }}
          >
            <option value={2}>2 seconds</option>
            <option value={5}>5 seconds</option>
            <option value={10}>10 seconds</option>
            <option value={20}>20 seconds</option>
            <option value={40}>40 seconds</option>
            <option value={duration}>Whole song</option>
          </select>
        </label>
        <label className="lyric-follow">
          <input
            type="checkbox"
            checked={follow}
            onChange={(e) => setFollow(e.target.checked)}
          />
          Follow playback
        </label>
        <button
          className="quiet-button"
          onClick={() => {
            setPhraseSource(null);
            undo();
          }}
          disabled={!canUndo || !!taps}
          aria-label="Undo timing change"
        >
          <Undo2 size={16} />
        </button>
        <button
          className="quiet-button"
          onClick={() => {
            setPhraseSource(null);
            redo();
          }}
          disabled={!canRedo || !!taps}
          aria-label="Redo timing change"
        >
          <Redo2 size={16} />
        </button>
        <button
          className="secondary-button"
          disabled={!!taps}
          onClick={() => setPhraseSource({ text: "" })}
        >
          <Plus size={16} />
          Add phrase
        </button>
      </div>
      <VocalPreview
        endpoint={vocalPreviewEndpoint}
        masterRef={audioRef}
        active={audioActive}
        onWaveform={setMonitorUrl}
      />
      <div className="lyric-timeline-grid">
        <div className="lyric-line-browser">
          <div className="lyric-line-browser-heading">
            <strong>Lyric lines</strong>
            <button
              className="quiet-button"
              disabled={!issueLines.length || !!taps}
              onClick={() =>
                focusLine(issueLines.find((i) => i > selected) ?? issueLines[0])
              }
            >
              Next to review
            </button>
          </div>
          {!lines.length && (
            <p className="video-field-note">
              No lyric words remain. Add a phrase, or use Undo to restore
              deleted lyrics.
            </p>
          )}
          <div
            ref={lineList}
            className="lyric-line-list"
            aria-label="Choose lyric line"
          >
            {lines.map((l, i) => {
              const bounds = lineBounds(l),
                issue = problems[i].find(Boolean);
              return (
                <div
                  key={l.id}
                  role="group"
                  aria-label={`Phrase ${i + 1}: ${l.text}`}
                  className={`lyric-line-row ${selected === i ? "selected" : ""}`}
                >
                  <button
                    className="lyric-line-select"
                    disabled={!!taps}
                    aria-pressed={selected === i}
                    onClick={() => focusLine(i)}
                  >
                    <span>
                      {i + 1}. {l.text}
                    </span>
                    <small className={issue ? "lyric-needs-review" : ""}>
                      {!bounds
                        ? "Not placed"
                        : `${stamp(bounds.start)}${issue ? ` · ${issue}` : ""}`}
                    </small>
                  </button>
                  <button
                    className="quiet-button lyric-insert-at-playhead"
                    disabled={!!taps}
                    onClick={() => placePhrase(l.id)}
                  >
                    Insert at playhead
                  </button>
                </div>
              );
            })}
          </div>
        </div>
        <div
          className={`lyric-timeline-main ${tool === "pan" ? "lyric-pan-mode" : ""}`}
        >
          <LyricTimingPreview lines={lines} position={position} />
          <div className="lyric-ruler">
            {Array.from({ length: 6 }, (_, i) => (
              <span key={i}>{stamp(start + (span * i) / 5)}</span>
            ))}
          </div>
          <div
            className="lyric-waveform"
            role="slider"
            tabIndex={0}
            aria-label="Audio waveform playhead"
            aria-valuemin={0}
            aria-valuemax={duration}
            aria-valuenow={precision(position)}
            aria-valuetext={stamp(position)}
            onPointerDown={(e) => {
              if (tool === "pan") {
                startPan(e);
                return;
              }
              if (e.button === 0) {
                e.currentTarget.setPointerCapture(e.pointerId);
                scrub(e);
              }
            }}
            onPointerMove={(e) => {
              if (tool === "pan") {
                movePan(e);
                return;
              }
              if (e.currentTarget.hasPointerCapture(e.pointerId)) scrub(e);
            }}
            onPointerUp={endPan}
            onPointerCancel={endPan}
            onLostPointerCapture={endPan}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
                e.preventDefault();
                seek(
                  clamp(
                    position +
                      (e.key === "ArrowRight" ? 1 : -1) *
                        (e.shiftKey ? 1 : 0.1),
                    0,
                    duration,
                  ),
                );
              }
              if (e.key === " ") {
                e.preventDefault();
                e.stopPropagation();
                play();
              }
            }}
          >
            <svg
              viewBox="0 0 900 88"
              preserveAspectRatio="none"
              aria-label="Song audio waveform"
            >
              <path d={wavePath} />
            </svg>
            {!waveform && (
              <span className="lyric-waveform-message">
                {waveformError || "Reading audio waveform…"}
              </span>
            )}
            {cursorVisible && (
              <div
                className="lyric-playhead"
                style={{ left: `${percent(position)}%` }}
              />
            )}
          </div>
          <div
            className="lyric-line-track"
            ref={lineTrack}
            aria-label="Lyric line blocks"
            {...panHandlers}
            style={{ height: Math.max(2, rowEnds.length) * 36 + 8 }}
          >
            {blocks.map(({ line: l, i, bounds, row }) => (
              <button
                key={l.id}
                aria-label={`Move line ${i + 1}: ${l.text}`}
                aria-pressed={selected === i}
                disabled={!!taps}
                className={`lyric-block ${selected === i ? "selected" : ""} ${problems[i].some(Boolean) ? "needs-review" : ""}`}
                style={{
                  ...blockStyle(bounds!.start, bounds!.end),
                  top: row * 36 + 4,
                }}
                title={`${l.text} · ${stamp(bounds!.start)}–${stamp(bounds!.end)}`}
                onPointerDown={(e) => beginDrag(e, i)}
                {...dragging}
                onKeyDown={(e) => {
                  if (e.key === "Escape") cancelDrag();
                  if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
                    e.preventDefault();
                    setSelected(i);
                    change({
                      wordEdits: moveLyricLine(
                        l,
                        draft.wordEdits,
                        (e.key === "ArrowRight" ? 1 : -1) *
                          (e.shiftKey ? 0.5 : 0.05),
                        duration,
                      ),
                    });
                  }
                  if (e.key === "Enter") focusLine(i);
                }}
              >
                <span>
                  {i + 1}. {l.text}
                </span>
              </button>
            ))}
            {cursorVisible && (
              <div
                className="lyric-playhead"
                style={{ left: `${percent(position)}%` }}
              />
            )}
          </div>
          <div className="lyric-pan">
            <span>
              {stamp(start)}–{stamp(end)}
            </span>
            <input
              type="range"
              aria-label="Timeline window start"
              min={0}
              max={maxStart}
              step={0.1}
              value={start}
              disabled={maxStart === 0}
              onChange={(e) => {
                setWindowStart(Number(e.target.value));
                setFollow(false);
              }}
            />
            <button
              className="quiet-button"
              onClick={() =>
                setWindowStart(clamp(position - span / 2, 0, maxStart))
              }
            >
              Find playhead
            </button>
          </div>
          {phraseSource && (
            <LyricPhraseForm
              source={phraseSource}
              lines={lines}
              selected={selected}
              playhead={position}
              onClose={() => setPhraseSource(null)}
              onInsert={(text, index, copiedWords) => {
                const result = insertLyricPhrases(
                  alignment,
                  draft,
                  text,
                  index,
                  copiedWords
                    ? { words: copiedWords, start: position, duration }
                    : undefined,
                );
                change(result.patch);
                setSelected(result.index);
                setWordIndex(0);
                setPhraseSource(null);
                setNotice(
                  copiedWords
                    ? "Copy inserted at the playhead. Review its timing against the vocal."
                    : "Phrase inserted. Use tap timing or the word controls to place its words.",
                );
              }}
            />
          )}
          {line && (
            <div className="lyric-line-detail">
              <div className="lyric-line-detail-heading">
                <h3>
                  {selected + 1}. {line.text}
                </h3>
                <div className="lyric-text-actions">
                  <button
                    className="quiet-button"
                    disabled={!!taps}
                    onClick={() =>
                      setPhraseSource({ text: line.text, words: line.words })
                    }
                  >
                    <Copy size={14} />
                    Duplicate phrase
                  </button>
                  <button
                    className="quiet-button lyric-delete"
                    disabled={!!taps}
                    onClick={() => removeText()}
                  >
                    <Trash2 size={14} />
                    Delete phrase
                  </button>
                  <button
                    className="quiet-button"
                    disabled={
                      !!taps ||
                      !line.words.some(
                        (_, i) => draft.wordEdits[`${line.id}:${i}`],
                      )
                    }
                    onClick={() => {
                      const edits = { ...draft.wordEdits };
                      line.words.forEach(
                        (_, i) => delete edits[`${line.id}:${i}`],
                      );
                      change({ wordEdits: edits });
                    }}
                  >
                    Reset line
                  </button>
                </div>
              </div>
              <div
                className="lyric-word-track"
                aria-label="Selected line word blocks"
                {...panHandlers}
              >
                {line.words.map(
                  (w, i) =>
                    w.start !== null &&
                    w.end !== null &&
                    w.end >= start &&
                    w.start <= end && (
                      <div
                        key={i}
                        className={`lyric-word-block ${i === wordIndex ? "selected" : ""}`}
                        style={blockStyle(w.start, w.end)}
                      >
                        <button
                          aria-label={`Move word ${i + 1}: ${w.text}`}
                          disabled={!!taps}
                          onPointerDown={(e) => beginDrag(e, selected, i)}
                          {...dragging}
                          onClick={() => setWordIndex(i)}
                          onKeyDown={(e) => {
                            if (e.key === "Escape") cancelDrag();
                            if (
                              e.key === "ArrowLeft" ||
                              e.key === "ArrowRight"
                            ) {
                              e.preventDefault();
                              const edits = moveLyricLine(
                                { ...line, words: [w] },
                                {},
                                (e.key === "ArrowRight" ? 1 : -1) *
                                  (e.shiftKey ? 0.5 : 0.05),
                                duration,
                              );
                              change({
                                wordEdits: {
                                  ...draft.wordEdits,
                                  [`${line.id}:${i}`]: edits[`${line.id}:0`],
                                },
                              });
                            }
                          }}
                        >
                          {w.text}
                        </button>
                        {(["start", "end"] as const).map((edge) => (
                          <button
                            key={edge}
                            className={`lyric-word-edge ${edge}`}
                            tabIndex={-1}
                            aria-label={`Drag ${w.text} ${edge}`}
                            disabled={!!taps}
                            onPointerDown={(e) =>
                              beginDrag(e, selected, i, edge)
                            }
                            {...dragging}
                          />
                        ))}
                      </div>
                    ),
                )}
                {cursorVisible && (
                  <div
                    className="lyric-playhead"
                    style={{ left: `${percent(position)}%` }}
                  />
                )}
              </div>
              <div className="lyric-word-picker">
                {line.words.map((w, i) => (
                  <button
                    key={i}
                    aria-pressed={wordIndex === i}
                    disabled={!!taps}
                    className={`${i === wordIndex ? "selected" : ""} ${problems[selected][i] ? "needs-review" : ""}`}
                    onClick={() => setWordIndex(i)}
                  >
                    {w.text}
                    {problems[selected][i] && (
                      <span aria-label="Needs review"> •</span>
                    )}
                  </button>
                ))}
              </div>
              {word && (
                <div className="lyric-word-controls">
                  <fieldset className="lyric-word-adjust" disabled={!!taps}>
                    <legend>
                      “{word.text}”{" "}
                      <small>
                        {problems[selected][wordIndex] ||
                          (draft.wordEdits[`${line.id}:${wordIndex}`]
                            ? "Manually timed"
                            : "Audio aligned")}
                      </small>
                    </legend>
                    {(["start", "end"] as const).map((edge) => (
                      <div key={edge}>
                        <label>
                          {edge === "start" ? "Start" : "End"} (seconds)
                          <input
                            type="number"
                            aria-label={`Selected word ${edge}`}
                            min={0}
                            max={duration}
                            step={0.02}
                            value={word[edge] ?? ""}
                            placeholder="Not timed"
                            onChange={(e) =>
                              setWordTime(
                                edge,
                                e.target.value === ""
                                  ? null
                                  : Number(e.target.value),
                              )
                            }
                          />
                        </label>
                        <button
                          className="quiet-button"
                          onClick={() => setWordTime(edge, position)}
                        >
                          Set {edge} at playhead
                        </button>
                      </div>
                    ))}
                  </fieldset>
                  <div className="lyric-text-actions">
                    <button
                      className="quiet-button"
                      disabled={!!taps}
                      onClick={() =>
                        setPhraseSource({ text: word.text, words: [word] })
                      }
                    >
                      <Copy size={14} />
                      Duplicate word
                    </button>
                    <button
                      className="quiet-button lyric-delete"
                      disabled={!!taps}
                      onClick={() => removeText([wordIndex])}
                    >
                      <Trash2 size={14} />
                      Delete word
                    </button>
                  </div>
                </div>
              )}
              <div className="lyric-tap-controls">
                {taps ? (
                  <>
                    <button
                      ref={tapButton}
                      className="primary-button"
                      onClick={tap}
                    >
                      {taps.length === line.words.length
                        ? "Mark line end"
                        : `Mark “${line.words[taps.length].text}”`}
                    </button>
                    <button
                      className="quiet-button"
                      onClick={() => {
                        setTaps(null);
                        setNotice("");
                      }}
                    >
                      Cancel tapping
                    </button>
                    <span>
                      {taps.length}/{line.words.length} words marked. Keep this
                      button focused and press Space as you listen.
                    </span>
                  </>
                ) : (
                  <>
                    <button
                      className="secondary-button"
                      onClick={() => {
                        setTaps([]);
                        setPhraseSource(null);
                        setNotice("");
                      }}
                    >
                      Time this line by tapping
                    </button>
                    <span>
                      Mark each word as you hear it, then mark the line’s end.
                    </span>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      <p className="lyric-edit-notice" role="status">
        {notice ||
          (taps
            ? "Taps stay temporary until you mark the line end. Other lines keep their timing."
            : "Edits save in this browser and apply to new previews and exports. Delete unwanted words or phrases here; add or duplicate phrases without realigning the song.")}
      </p>
      <WordTimingEditor
        alignment={alignment}
        draft={draft}
        duration={duration}
        change={change}
        seek={seek}
      />
    </div>
  );
}
