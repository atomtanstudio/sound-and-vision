/* The preview stage composition: background media + frame-exact lyric
 * overlay driven by the same timing math and word motions as the MP4 export. */
import { cueAt, FPS, type LyricCue, type Placement, type VideoDraft } from "../../../video/timeline";
import { placementAt } from "../../../video/timeline";
import { wordMotion } from "../../../video/kinetics";
import { visualizerFrame } from "../../../video/visualizers/schedule";
import { cn } from "../../ui";

export function StageBackground({
  draft,
  cues: _cues,
  time,
  placements,
  urls,
}: {
  draft: VideoDraft;
  cues: LyricCue[];
  time: number;
  placements: Placement[];
  urls: (string | undefined)[];
}) {
  const frame = visualizerFrame(time, FPS);
  const index = placementAt(placements, frame);
  const url = index >= 0 ? urls[placements[index]!.assetIndex] : undefined;
  return (
    <div className={cn("stage-bg", draft.transition === "dissolve" && "dissolve")} aria-hidden="true">
      {urls.map((asset, i) =>
        asset ? (
          <img
            key={`${i}-${asset}`}
            src={asset}
            alt=""
            className={cn("stage-slide", i === index && "on")}
            style={draft.pan ? undefined : { transform: "none" }}
          />
        ) : null,
      )}
      {!url ? <div className="stage-empty" /> : null}
      <div className="stage-shade" style={{ opacity: draft.shade / 100 }} />
    </div>
  );
}

export function LyricStage({
  draft,
  cues,
  time,
  title,
  aligned,
}: {
  draft: VideoDraft;
  cues: LyricCue[];
  time: number;
  title: string;
  aligned: boolean;
}) {
  if (!draft.showLyrics) return null;
  const frame = visualizerFrame(time, FPS);
  const cue = cueAt(cues, frame);
  const progress = cue
    ? Math.max(
        0,
        Math.min(1, (frame - cue.startFrame) / Math.max(1, cue.endFrame - cue.startFrame)),
      )
    : 0;
  const effect =
    draft.lyricMotion === "auto"
      ? ["pop", "slam", "rise"][Number(cue?.id.split("-")[1] || 0) % 3]
      : draft.lyricMotion;
  const current =
    cue?.words?.findIndex((w) => w.start !== null && w.end !== null && time >= w.start && time < w.end) ?? -1;
  return (
    <div
      className={cn("stage-lyrics", `placement-${draft.placement}`, `font-${draft.font}`)}
      style={{
        fontSize: `${((draft.aspect === "9:16" ? 10 : 7) * draft.textSize) / 100}cqw`,
        color: draft.textColor,
        opacity: draft.lyricMotion === "reveal" && cue ? Math.min(1, progress * 9) : 1,
      }}
    >
      {cue ? (
        cue.text.split(/\s+/).map((word, i) => (
          <span
            key={`${cue.id}-${i}`}
            className={cn(i === current && "current-word")}
            style={{
              ...wordMotion(effect, cue.words?.[i]?.start == null ? -1 : time - cue.words[i].start!, i, draft.intensity),
              ...(i === current ? { color: draft.highlightColor } : {}),
            }}
          >
            {word}{" "}
          </span>
        ))
      ) : (
        <span className="stage-title-frame">
          {!aligned || frame < (cues[0]?.startFrame || 0) ? title : ""}
        </span>
      )}
    </div>
  );
}
