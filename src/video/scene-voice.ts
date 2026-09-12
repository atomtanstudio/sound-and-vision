export function sceneVoiceLabel(scene: {
  type: string;
  story?: { beat: string };
  timing: { source?: string; words: unknown[]; leadingRest: number };
}) {
  if (scene.timing.source === "recording") {
    if (!scene.timing.words.length) return "Instrumental · no singing";
    if (scene.type !== "performance") return "Story · vocals off screen";
    return scene.timing.leadingRest > 0.05
      ? `Singing · starts +${scene.timing.leadingRest.toFixed(2)}s`
      : "Singing · timed to vocals";
  }
  if (scene.story?.beat === "performance" && scene.type !== "performance") return "Instrumental performance";
  return scene.type === "performance" ? "Singing" : "Story";
}
