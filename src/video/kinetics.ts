// Frame-clock equivalents of Max Music's overshoot/impact word entrances.
export function wordMotion(
  effect: string,
  elapsed: number,
  index: number,
  intensity = 1,
  reduced = false,
) {
  if (reduced || effect === "calm" || effect === "highlight")
    return { opacity: 1, transform: "none" };
  if (elapsed < 0) return { opacity: 0.14, transform: "none" };
  const u = Math.min(1, elapsed / 0.24),
    back = 1 + 2.70158 * (u - 1) ** 3 + 1.70158 * (u - 1) ** 2;
  if (effect === "slam")
    return {
      opacity: 1,
      transform: `scale(${1 + 0.3 * intensity * (1 - u) ** 4}) rotate(${(index % 2 ? 1 : -1) * 2 * intensity * (1 - u) ** 4}deg)`,
    };
  if (effect === "rise")
    return {
      opacity: 1 - (1 - u) ** 4,
      transform: `translateY(${28 * intensity * (1 - u) ** 4}px) rotate(${(index % 2 ? 1 : -1) * 4 * intensity * (1 - u) ** 4}deg)`,
    };
  return {
    opacity: 1 - (1 - u) ** 5,
    transform: `scale(${1 - 0.3 * intensity * (1 - back)}) translateY(${8 * intensity * (1 - u) ** 4}px)`,
  };
}
