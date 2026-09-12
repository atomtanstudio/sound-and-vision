import { wordMotion } from "../kinetics";
import { cueAt, FPS, type LyricCue, type VideoDraft } from "../timeline";
import { visualizerFrame } from "./schedule";

/** The same lyric layout is mounted in the editor and the export composition. */
export function LyricOverlay({
  draft,
  cues,
  time,
  title,
  aligned,
  reduceMotion = false,
}: {
  draft: VideoDraft;
  cues: LyricCue[];
  time: number;
  title: string;
  aligned: boolean;
  reduceMotion?: boolean;
}) {
  const frame = visualizerFrame(time, FPS),
    cue = cueAt(cues, frame);
  const progress = cue
    ? Math.max(
        0,
        Math.min(
          1,
          (frame - cue.startFrame) / Math.max(1, cue.endFrame - cue.startFrame),
        ),
      )
    : 0;
  const effect =
    draft.lyricMotion === "auto"
      ? ["pop", "slam", "rise"][Number(cue?.id.split("-")[1] || 0) % 3]
      : draft.lyricMotion;
  const current =
    cue?.words?.findIndex(
      (w) =>
        w.start !== null && w.end !== null && time >= w.start && time < w.end,
    ) ?? -1;
  return (
    <div
      className="kinetic-words"
      style={{
        fontSize: `${((draft.aspect === "9:16" ? 10 : 7) * draft.textSize) / 100}cqw`,
        opacity:
          !reduceMotion && draft.lyricMotion === "reveal" && cue
            ? Math.min(1, progress * 9)
            : 1,
        transform:
          !reduceMotion && draft.lyricMotion === "reveal" && cue
            ? `translateY(${(1 - Math.min(1, progress * 9)) * 12}px)`
            : undefined,
      }}
    >
      {cue ? (
        cue.text.split(/\s+/).map((word, i) => (
          <span
            key={`${cue.id}-${i}`}
            style={wordMotion(
              effect,
              cue.words?.[i]?.start == null ? -1 : time - cue.words[i].start!,
              i,
              draft.intensity,
              reduceMotion,
            )}
            className={i === current ? "current-word" : ""}
            data-word-start={cue.words?.[i]?.start ?? undefined}
          >
            {word}{" "}
          </span>
        ))
      ) : (
        <span className="video-title-frame">
          {!aligned || frame < (cues[0]?.startFrame || 0) ? title : ""}
        </span>
      )}
    </div>
  );
}
