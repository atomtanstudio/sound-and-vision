import { create } from "zustand";
import { api } from "../lib/api";

/** Who does each job right now (Settings → Who does what): the first connected model of each role. The interface names
 *  a model only once one is connected; until then it says "the AI". Loaded when the app starts and again whenever
 *  Settings closes. */
export interface Doer { provider: string; name: string; model: string }
interface Who {
  roles: Record<string, Doer | null>;
  plan: string | null; // the plan videos made in code run on ("Claude"), once it's connected
  filmModels: { id: string; name: string }[]; // the models that can direct videos in code
  loaded: boolean;
  load: () => Promise<void>;
}

export const useWho = create<Who>((set) => ({
  roles: {},
  plan: null,
  filmModels: [],
  loaded: false,
  load: async () => {
    try {
      const w = await api.get<Omit<Who, "loaded" | "load">>("/api/who");
      set({ ...w, loaded: true });
    } catch {
      set({ loaded: true });
    }
  },
}));

/** The roles behind the interface's words: who reads the Home prompt, writes lyrics, researches a sound, plans living
 *  covers and motion, writes cover prompts, and directs videos in code. */
export type Role = "interpret" | "lyrics" | "research" | "direct" | "chores" | "film";

/** The short name of whoever does this job ("Claude", "ChatGPT", "your local model"), or `otherwise` until one is
 *  connected. */
export function doer(roles: Record<string, Doer | null>, role: Role, otherwise = "the AI"): string {
  return roles[role]?.name ?? otherwise;
}

/** The same, for the start of a sentence. */
export function Doer(roles: Record<string, Doer | null>, role: Role, otherwise = "the AI"): string {
  const s = doer(roles, role, otherwise);
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** "…'s" for a name, "its" when no model is connected yet. */
export function doers(roles: Record<string, Doer | null>, role: Role): string {
  const d = roles[role];
  return d ? `${d.name}'s` : "the AI's";
}
