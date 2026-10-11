import { useEffect, useState } from "react";
import { api } from "./api";
import type { Project } from "./types";

/** The song's artist, as the server decides it: its own when set (blank included), else what its cover or its file
 *  said, else your artist name from Brand. */
export function artistOf(p: Pick<Project, "artist" | "cover" | "source">, house = ""): string {
  if (typeof p.artist === "string") return p.artist;
  return p.cover?.artist || p.source?.artist || house;
}

let house: string | null = null;
const listeners = new Set<(v: string) => void>();

/** Your artist name (Brand), shared by every page that shows one; setHouseArtist saves it. */
export function useHouseArtist(): string {
  const [v, setV] = useState(house ?? "");
  useEffect(() => {
    listeners.add(setV);
    if (house === null) void api.get<{ artist: string }>("/api/covers/settings").then((s) => { house = s.artist ?? ""; listeners.forEach((l) => l(house!)); }).catch(() => undefined);
    return () => void listeners.delete(setV);
  }, []);
  return v;
}

export async function setHouseArtist(artist: string): Promise<void> {
  await api.put("/api/covers/settings", { artist });
  house = artist.trim();
  listeners.forEach((l) => l(house!));
}
