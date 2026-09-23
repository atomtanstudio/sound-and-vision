/** Immutable, song-owned artwork; effect choices are made by the song director. */
export type SceneSurface = {
  name: string;
  effect: "spectrum" | "ribbon" | "halo" | "contours";
  reason: string;
  color: string;
  accent: string;
  strength: number;
  confidence: number;
  corners: [number, number][];
};
export type SongScene = {
  version: 1;
  renderer?: "reference-player-v1";
  directorRevision?: string;
  takeId?: string;
  artworkJobId?: string;
  artworkUrl: string;
  artworkSha256: string;
  dimensions: [number, number];
  aspect: "16:9" | "9:16";
  title: string;
  concept: string;
  mood: string;
  reasoning: string;
  evidence: string[];
  observations: string;
  quality: number;
  surfaces: SceneSurface[];
};

export const sceneEffects = ["spectrum", "ribbon", "halo", "contours"] as const;

export function validateScene(value: unknown): SongScene {
  const s = value as SongScene;
  if (
    !s ||
    s.version !== 1 ||
    (s.renderer !== undefined && s.renderer !== "reference-player-v1") ||
    !["16:9", "9:16"].includes(s.aspect) ||
    !Array.isArray(s.dimensions) ||
    s.dimensions.length !== 2 ||
    s.dimensions.some((n) => !Number.isInteger(n) || n < 16 || n > 8192) ||
    !Array.isArray(s.surfaces) ||
    s.surfaces.length < 1 ||
    s.surfaces.length > 3
  )
    throw Error("Invalid song artwork composition");
  for (const r of s.surfaces) {
    if (
      !sceneEffects.includes(r.effect) ||
      (s.renderer === "reference-player-v1" && !["spectrum", "ribbon"].includes(r.effect)) ||
      !/^#[0-9a-f]{6}$/i.test(r.color) ||
      !/^#[0-9a-f]{6}$/i.test(r.accent) ||
      !Number.isFinite(r.strength) ||
      r.strength < 0.3 ||
      r.strength > 1.2 ||
      !Array.isArray(r.corners) ||
      r.corners.length !== 4 ||
      r.corners.some(
        (p) =>
          !Array.isArray(p) ||
          p.length !== 2 ||
          p.some((n) => !Number.isFinite(n) || n < 0 || n > 1),
      )
    )
      throw Error("Invalid artwork surface");
    const p = r.corners;
    let area = 0;
    for (let i = 0; i < 4; i++) {
      const a = p[i],
        b = p[(i + 1) % 4],
        c = p[(i + 2) % 4];
      if ((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) <= 0)
        throw Error("Artwork corners must be clockwise and convex");
      area += a[0] * b[1] - b[0] * a[1];
    }
    if (area / 2 < 0.006 || area / 2 > 0.65)
      throw Error("Artwork surface has unusable area");
  }
  return s;
}

/** Project whole-image coordinates into a surface's unit square (column-major). */
export function surfaceTransform(corners: [number, number][]): number[] {
  const target = [
    [0, 0],
    [1, 0],
    [1, 1],
    [0, 1],
  ];
  const rows: number[][] = [];
  corners.forEach(([x, y], i) => {
    const [u, v] = target[i];
    rows.push(
      [x, y, 1, 0, 0, 0, -u * x, -u * y, u],
      [0, 0, 0, x, y, 1, -v * x, -v * y, v],
    );
  });
  for (let c = 0; c < 8; c++) {
    let pivot = c;
    for (let r = c + 1; r < 8; r++)
      if (Math.abs(rows[r][c]) > Math.abs(rows[pivot][c])) pivot = r;
    if (Math.abs(rows[pivot][c]) < 1e-10)
      throw Error("Artwork surface is degenerate");
    [rows[c], rows[pivot]] = [rows[pivot], rows[c]];
    const scale = rows[c][c];
    rows[c] = rows[c].map((v) => v / scale);
    for (let r = 0; r < 8; r++)
      if (r !== c) {
        const factor = rows[r][c];
        rows[r] = rows[r].map((v, k) => v - factor * rows[c][k]);
      }
  }
  const a = rows.map((r) => r[8]);
  return [a[0], a[3], a[6], a[1], a[4], a[7], a[2], a[5], 1];
}

export function sceneUniforms(scene: SongScene) {
  validateScene(scene);
  const hex = (color: string) =>
    [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16) / 255);
  return scene.surfaces.map((s) => ({
    transform: surfaceTransform(s.corners),
    style: [sceneEffects.indexOf(s.effect), s.strength, 0, 0],
    color: hex(s.color),
    accent: hex(s.accent),
  }));
}
