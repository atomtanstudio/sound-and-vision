import { api } from "../lib/api";
import type { FontInfo } from "./look";

/** The app's fonts (server data/fonts), loaded into the browser on first use under their own names ("sv-<id>"), so
 *  the editor draws with exactly the files the server sets the cover with. */
let catalog: Promise<FontInfo[]> | null = null;
const loaded = new Map<string, Promise<void>>();

export function fonts(): Promise<FontInfo[]> {
  catalog ??= api.get<FontInfo[]>("/api/fonts").catch(() => []);
  return catalog;
}

export const family = (id: string) => `sv-${id}`;

export function loadFont(id: string, info?: FontInfo): Promise<void> {
  let p = loaded.get(id);
  if (!p) {
    const face = new FontFace(family(id), `url(/api/fonts/${encodeURIComponent(id)})`,
      info?.weight ? { weight: `${info.weight[0]} ${info.weight[1]}` } : {});
    p = face.load().then((f) => {
      document.fonts.add(f);
    }).catch(() => undefined);
    loaded.set(id, p);
  }
  return p;
}

/** The weight a text is drawn at: its own, or the font's default (a variable font's default instance, as the server). */
export function weightOf(w: number | null, info?: FontInfo): number {
  return w ?? info?.weight?.[2] ?? 400;
}
