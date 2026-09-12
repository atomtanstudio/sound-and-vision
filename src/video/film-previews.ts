type Scene = {
  index: number;
  selected: string;
  takes: { id: string; state: string }[];
};
export type FilmPreviews = Record<
  number,
  { takeId: string; newestReadyId: string }
>;

export function reconcilePreviews(
  scenes: Scene[],
  saved: FilmPreviews,
): FilmPreviews {
  const next: FilmPreviews = {};
  for (const scene of scenes) {
    const newest =
      scene.takes.filter((t) => t.state === "ready").at(-1)?.id ||
      scene.selected;
    const previous = saved[scene.index];
    const changed = !previous || previous.newestReadyId !== newest;
    next[scene.index] = {
      takeId:
        changed || !scene.takes.some((t) => t.id === previous.takeId)
          ? newest
          : previous.takeId,
      newestReadyId: newest,
    };
  }
  return next;
}
