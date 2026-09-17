export type AudioFadeCurve = "linear" | "smooth";

export type AudioFade = {
  start: number;
  end: number;
  curve: AudioFadeCurve;
};

const round = (value: number) => Math.round(value * 1000) / 1000;

/** A null end means the complete source recording. Shorter values are the
 * explicit output endpoint selected in the video timeline. */
export function normalizeAudioEnd(
  value: unknown,
  duration: number,
): number | null {
  if (value == null || !Number.isFinite(duration) || duration <= 0) return null;
  const end = Number(value);
  if (
    !Number.isFinite(end) ||
    end < Math.min(1, duration) ||
    end >= duration - 0.05
  )
    return null;
  return round(end);
}

/** Validate and clamp a draft fade to the actual soundtrack duration. */
export function normalizeAudioFade(
  value: unknown,
  duration: number,
): AudioFade | null {
  if (value == null) return null;
  if (!value || typeof value !== "object" || !Number.isFinite(duration))
    return null;
  const source = value as Partial<AudioFade>;
  const start = Number(source.start),
    end = Number(source.end);
  if (
    !Number.isFinite(start) ||
    !Number.isFinite(end) ||
    duration <= 0 ||
    start < 0 ||
    end > duration + 0.05 ||
    end - start < 0.25
  )
    return null;
  const safeStart = Math.max(0, Math.min(duration - 0.25, start));
  const safeEnd = Math.max(safeStart + 0.25, Math.min(duration, end));
  return {
    start: round(safeStart),
    end: round(safeEnd),
    curve: source.curve === "linear" ? "linear" : "smooth",
  };
}

/** Keep an existing envelope attached to a newly selected soundtrack end.
 * If trimming removes the old fade entirely, preserve its length immediately
 * before the new endpoint so the cut still reaches digital silence. */
export function retimeAudioFade(
  value: AudioFade | null | undefined,
  duration: number,
  targetEnd?: number,
): AudioFade | null {
  if (!value || !Number.isFinite(duration) || duration <= 0) return null;
  const source = value as Partial<AudioFade>;
  const oldStart = Number(source.start),
    oldEnd = Number(source.end);
  if (
    !Number.isFinite(oldStart) ||
    !Number.isFinite(oldEnd) ||
    oldEnd <= oldStart
  )
    return null;
  const span = Math.max(0.25, oldEnd - oldStart);
  const end = Math.min(
    duration,
    Math.max(0.25, Number.isFinite(targetEnd) ? targetEnd! : oldEnd),
  );
  const start = Math.max(0, end - Math.min(span, Math.max(0.25, duration)));
  return normalizeAudioFade(
    { start, end, curve: source.curve === "linear" ? "linear" : "smooth" },
    duration,
  );
}

export function audioFadeGain(
  fade: AudioFade | null | undefined,
  time: number,
) {
  if (!fade || !Number.isFinite(time) || time <= fade.start) return 1;
  if (time >= fade.end) return 0;
  const progress = (time - fade.start) / (fade.end - fade.start);
  return fade.curve === "linear"
    ? Math.max(0, 1 - progress)
    : Math.max(0, Math.cos(progress * Math.PI * 0.5));
}

/** FFmpeg's native fade curves keep export behavior identical to preview. */
export function ffmpegAudioFadeFilter(
  fade: AudioFade | null | undefined,
  duration: number,
) {
  const end = Number.isFinite(duration) ? duration : 0;
  if (!fade) return `atrim=duration=${end},asetpts=PTS-STARTPTS`;
  const curve = fade.curve === "linear" ? "tri" : "hsin";
  return `afade=t=out:st=${fade.start}:d=${Math.max(0.25, fade.end - fade.start)}:curve=${curve},atrim=duration=${end},asetpts=PTS-STARTPTS`;
}
