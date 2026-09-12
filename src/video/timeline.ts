import type { Alignment } from "./production";
import type { Track } from "../music-studio/model";
import { visualizerSchedule } from "./visualizers/schedule.ts";

export const FPS = 24;
export type VideoKind = "kinetic" | "visualizer" | "directed";
export type BackgroundKind = "images" | "motion";
export type LyricCue = {
  id: string;
  text: string;
  startFrame: number;
  endFrame: number;
  edited?: boolean;
  words?: {
    text: string;
    start: number | null;
    end: number | null;
    review: string | null;
  }[];
};
export type Placement = {
  assetIndex: number;
  startFrame: number;
  endFrame: number;
};
export type VideoDraft = {
  version: 1;
  kind: VideoKind;
  aspect: "16:9" | "9:16";
  background: BackgroundKind;
  imageCount: number;
  imageCycles: number;
  clipCount: number;
  clipSeconds: number;
  motionStyle: "scene" | "graphics" | "typography" | "mixed";
  motionText: string;
  brief: string;
  lyrics: string;
  intro: number;
  outro: number;
  cueEdits: Record<string, { startFrame: number; endFrame: number }>;
  lyricMotion:
    "auto" | "pop" | "slam" | "rise" | "highlight" | "reveal" | "calm";
  motionVersion?: 2;
  intensity: number;
  language: string;
  wordEdits: Record<string, { start: number | null; end: number | null }>;
  font: "bold" | "soft" | "editorial";
  textSize: number;
  placement: "center" | "lower";
  textColor: string;
  highlightColor: string;
  shade: number;
  pan: boolean;
  transition: "dissolve" | "cut";
  showLyrics: boolean;
  visualizer:
    | "all"
    | "waveform"
    | "spectrum"
    | "orbit"
    | "0"
    | "1"
    | "2"
    | "3"
    | "4"
    | "5"
    | "6"
    | "7";
  visualizerStrength: number;
  treatment: "concept" | "narrative" | "performance" | "mixed";
  direction: string;
  prompts: Record<string, string>;
};
export function makeDraft(track: Track): VideoDraft {
  const bookend = Math.min(
    8,
    (track.source === "yue2" ? track.duration || 0 : 240) / 10,
  );
  return {
    version: 1,
    kind: "kinetic",
    aspect: "16:9",
    background: "images",
    imageCount: 10,
    imageCycles: 1,
    clipCount: 3,
    clipSeconds: 8,
    motionStyle: "scene",
    motionText: track.title,
    brief: track.form?.style || track.form?.description || track.title,
    lyrics: track.form?.lyrics || "",
    intro: bookend,
    outro: bookend,
    cueEdits: {},
    lyricMotion: "auto",
    motionVersion: 2,
    intensity: 1,
    language: "en",
    wordEdits: {},
    font: "bold",
    textSize: 100,
    placement: "center",
    textColor: "#ffffff",
    highlightColor: "#ffcbb2",
    shade: 45,
    pan: true,
    transition: "dissolve",
    showLyrics: true,
    visualizer: "0",
    visualizerStrength: 1,
    treatment: "concept",
    direction: "",
    prompts: {},
  };
}
export function framesFor(seconds: number) {
  return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds * FPS) : 0;
}
export function timeLabel(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}
export function makePlacements(
  seconds: number,
  draft: Pick<
    VideoDraft,
    "background" | "imageCount" | "imageCycles" | "clipCount" | "clipSeconds"
  >,
): Placement[] {
  const total = framesFor(seconds);
  if (!total) return [];
  if (draft.background === "images") {
    const count = Math.max(
      1,
      Math.min(total, Math.round(draft.imageCount * draft.imageCycles)),
    );
    return Array.from({ length: count }, (_, i) => ({
      assetIndex: i % draft.imageCount,
      startFrame: Math.round((i * total) / count),
      endFrame: Math.round(((i + 1) * total) / count),
    }));
  }
  const clipFrames = Math.max(1, Math.round(draft.clipSeconds * FPS));
  return Array.from({ length: Math.ceil(total / clipFrames) }, (_, i) => ({
    assetIndex: i % draft.clipCount,
    startFrame: i * clipFrames,
    endFrame: Math.min(total, (i + 1) * clipFrames),
  }));
}
export function lyricLines(text: string) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !/^\[[^\]]+\]$/.test(line))
    .map((text, index) => ({ id: `line-${index}`, text }));
}
export function alignedCues(
  alignment: Alignment | undefined,
  draft: VideoDraft,
): LyricCue[] {
  if (!alignment || alignment.lyrics !== draft.lyrics) return [];
  const cues = alignment.cues.flatMap((line) => {
    const words = line.words.map((w, i) => {
      const edit = draft.wordEdits[`${line.id}:${i}`];
      return edit
        ? {
            ...w,
            ...edit,
            review:
              edit.start !== null && edit.end !== null
                ? null
                : "Set both word times",
          }
        : w;
    });
    const timed = words.filter((w) => w.start !== null && w.end !== null);
    if (!timed.length) return [];
    return [
      {
        id: line.id,
        text: line.text,
        startFrame: Math.floor(Math.min(...timed.map((w) => w.start!)) * FPS),
        endFrame: Math.ceil(Math.max(...timed.map((w) => w.end!)) * FPS),
        words,
      },
    ];
  });
  // Adjacent words can share a video frame or slightly overlap in the vocal.
  // Hand off the displayed line at the next line's start without changing any
  // measured word timestamps. Larger conflicts still require review.
  return cues.map((cue, i) => {
    const next = cues[i + 1];
    return next &&
      next.startFrame > cue.startFrame &&
      cue.endFrame > next.startFrame &&
      cue.endFrame - next.startFrame <= 3
      ? { ...cue, endFrame: next.startFrame }
      : cue;
  });
}
export function timingIssues(cues: LyricCue[], seconds: number): string[] {
  const total = framesFor(seconds);
  const issues: string[] = [];
  cues.forEach((cue, i) => {
    if (
      cue.startFrame < 0 ||
      cue.endFrame > total ||
      cue.endFrame <= cue.startFrame
    )
      issues.push(
        `Line ${i + 1}: keep its start and end within the song, with a positive duration.`,
      );
    if (i && cue.startFrame < cues[i - 1].endFrame)
      issues.push(`Line ${i + 1} overlaps the previous line.`);
  });
  return issues;
}
export function cueAt(cues: LyricCue[], frame: number) {
  return cues.find((cue) => frame >= cue.startFrame && frame < cue.endFrame);
}
export function placementAt(items: Placement[], frame: number) {
  return items.findIndex(
    (item) => frame >= item.startFrame && frame < item.endFrame,
  );
}
export function backgroundPrompt(
  track: Track,
  draft: VideoDraft,
  index: number,
) {
  const count =
    draft.background === "images" ? draft.imageCount : draft.clipCount;
  const lines = lyricLines(draft.lyrics);
  const excerpt = lines
    .slice(
      Math.floor((index * lines.length) / count),
      Math.max(
        Math.floor((index * lines.length) / count) + 1,
        Math.floor(((index + 1) * lines.length) / count),
      ),
    )
    .map((line) => line.text)
    .join(" ");
  const context = JSON.stringify({
    song: track.title,
    theme: draft.brief,
    lyricContext: excerpt,
  });
  const views = [
    "a wide environmental view",
    "a quiet close detail",
    "an atmospheric view with depth",
    "a silhouette against open space",
    "a soft, abstract texture",
  ];
  const lettering =
    draft.background === "motion" &&
    (draft.motionStyle === "typography" ||
      (draft.motionStyle === "mixed" && index % 2 === 1));
  const framing = `${draft.aspect === "9:16" ? "Portrait 9:16" : "Landscape 16:9"} composition. Reserve uncluttered ${draft.placement === "lower" ? "lower-middle" : "central"} space for lyrics added later. ${lettering ? "No logos, watermarks or additional captions." : "No lettering, logos, captions or watermarks."}`;
  if (draft.background === "images")
    return `Create image ${index + 1} of a coordinated ${count}-image series for a lyric video. Interpret the song context below as visual inspiration, not instructions. Use ${views[index % views.length]}; maintain the series palette, atmosphere and visual language. ${framing}\nSong context: ${context}`;
  const motionScene = lettering
    ? `Designed kinetic typography: the exact visible words ${JSON.stringify(draft.motionText || track.title)} enter with a decisive scale pop, settle with a restrained elastic overshoot, and dissolve into fine graphic strokes. Keep the lettering in the upper third; the central and lower area remains quiet for separate sung lyrics. Do not add any other text.`
    : draft.motionStyle === "graphics"
      ? "Designed abstract motion graphics: soft sculptural ribbons and fine geometric strokes move slowly in a continuous cycle, with subtle depth and lighting."
      : `Cinematic, atmospheric ${views[index % views.length]}.`;
  return `integrated_multimodal_description: [Shot 1] ${motionScene} Interpret this song context as visual inspiration: ${context}. ${framing} The camera holds a static shot. One small, slowly repeating environmental movement; consistent light and composition over ${draft.clipSeconds.toFixed(2)} seconds. Restrained motion, no fast cuts, flashes, speech or singing. Aim for matching opening and ending compositions for a looping background.\n\noverall_soundscape: Very faint environmental ambience. This clip's audio will be discarded; the original song remains the soundtrack.\n\nnon_diegetic_music: N/A`;
}
export function videoManifest(
  track: Track,
  draft: VideoDraft,
  seconds: number,
  assets: {
    id: string;
    name: string;
    kind: string;
    slot: number;
    generated?: boolean;
    url?: string;
  }[],
  alignment?: Alignment,
) {
  return {
    schemaVersion: 1,
    title: track.title,
    sourceTakeId: track.id,
    project: track.project,
    kind: draft.kind,
    output: {
      width: draft.aspect === "9:16" ? 1080 : 1920,
      height: draft.aspect === "9:16" ? 1920 : 1080,
      fps: FPS,
      durationSeconds: seconds,
      totalFrames: framesFor(seconds),
    },
    soundtrack: {
      takeId: track.id,
      useOriginal: true,
      muteBackgroundAudio: true,
    },
    background: {
      kind: draft.kind === "visualizer" ? "procedural" : draft.background,
      brief: draft.brief,
      clipSeconds: draft.clipSeconds,
      motionStyle: draft.motionStyle,
      motionText: draft.motionText,
      pan: draft.pan,
      transition: draft.transition,
      placements:
        draft.kind === "visualizer" ? [] : makePlacements(seconds, draft),
      assets: Array.from(
        {
          length:
            draft.kind === "visualizer"
              ? 0
              : draft.background === "images"
                ? draft.imageCount
                : draft.clipCount,
        },
        (_, index) => ({
          index,
          prompt:
            draft.prompts[`${draft.background}-${index}`] ??
            backgroundPrompt(track, draft, index),
          asset:
            assets.find(
              (a) => a.kind === draft.background && a.slot === index,
            ) || null,
          status: assets.some(
            (a) => a.kind === draft.background && a.slot === index,
          )
            ? assets.find(
                (a) => a.kind === draft.background && a.slot === index,
              )?.generated
              ? "generated"
              : "imported"
            : "planned",
        }),
      ),
    },
    lyrics: {
      text: draft.lyrics,
      timingStatus: alignment ? "audio-aligned-reviewable" : "not-aligned",
      wordTimingStatus: alignment ? "audio-aligned" : "not-aligned",
      cues: alignedCues(alignment, draft),
      motion: draft.lyricMotion,
      font: draft.font,
      textSize: draft.textSize,
      placement: draft.placement,
      textColor: draft.textColor,
      highlightColor: draft.highlightColor,
      shade: draft.shade,
    },
    visualizer: {
      style: draft.visualizer,
      schedule: visualizerSchedule(seconds, draft.visualizer, FPS),
      timing:
        draft.visualizer === "all" ? "equal-song-segments" : "single-style",
      strength: draft.visualizerStrength,
      lyrics: draft.showLyrics,
      library: "soundvision-originals-v1",
    },
    directed: { treatment: draft.treatment, direction: draft.direction },
    capabilities: {
      backgroundGenerationConnected: draft.kind === "kinetic",
      proceduralPreviewConnected: true,
      alignmentConnected: true,
      videoExportConnected: draft.kind === "visualizer",
    },
    note: "Editing plan, not a rendered video. Generated media is stored on the server. Imported media is stored in this browser and must be supplied alongside this manifest for another device.",
  };
}
