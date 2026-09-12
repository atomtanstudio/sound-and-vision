/** Shared, frame-exact visualizer schedule for preview and MP4 export. */
export function presetNumber(selection: string): number {
  return selection === "orbit"
    ? 2
    : selection === "spectrum"
      ? 4
      : /^[0-7]$/.test(selection)
        ? Number(selection)
        : 0;
}
export function visualizerSchedule(
  seconds: number,
  selection: string,
  fps = 24,
) {
  if (
    !Number.isFinite(seconds) ||
    seconds <= 0 ||
    !Number.isFinite(fps) ||
    fps <= 0
  )
    return [];
  const frames = Math.ceil(seconds * fps);
  const ids =
    selection === "all" ? [0, 1, 2, 3, 4, 5, 6, 7] : [presetNumber(selection)];
  return ids.map((preset, i) => ({
    preset,
    startFrame: Math.round((i * frames) / ids.length),
    endFrame: Math.round(((i + 1) * frames) / ids.length),
  }));
}
/** Media playback times can round an exact frame boundary to microseconds. */
export function visualizerFrame(seconds: number, fps = 24) {
  return Math.max(
    0,
    Math.floor((Number.isFinite(seconds) ? seconds : 0) * fps + 1e-4),
  );
}
export function visualizerAt(
  seconds: number,
  duration: number,
  selection: string,
  fps = 24,
) {
  const schedule = visualizerSchedule(duration, selection, fps);
  const frame = visualizerFrame(seconds, fps);
  return (
    schedule.find((s) => frame >= s.startFrame && frame < s.endFrame)?.preset ??
    schedule.at(-1)?.preset ??
    presetNumber(selection)
  );
}
