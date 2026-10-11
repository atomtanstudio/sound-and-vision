/** Something that can make pictures, as the server lists it (Settings → Pictures; the covers' "Made with"). */
export interface PictureChoice {
  id: string; // "openai", "grok", "local" (Krea 2) or "local:<model>", an MCP server ("mcp:<id>"), or the owner's own
  name: string;
  note: string;
  cost: number | null; // USD a picture, when it's known
  paid: boolean; // may charge the person's account: asked first, every time
  connected?: boolean;
}

/** The choices to offer: only what's connected (signed in, answering, installed), and the one chosen now even if it
 *  isn't, so it never vanishes without a word. */
export const usable = (cs: PictureChoice[], keep?: string) => cs.filter((c) => c.connected !== false || c.id === keep);

/** The short name for a picker. */
export const choiceLabel = (c: PictureChoice) => c.name + (c.connected === false ? " (not connected)" : "");

/** Before a picture from a paid service: the person says yes, every time (they asked for that). `using`: the model
 *  and settings chosen there in Settings ("GPT Image 2.5, 2K, high"), so they know what they're paying for. */
export function okToSpend(c: PictureChoice | undefined, what = "this picture", using = ""): boolean {
  return !c?.paid || window.confirm(`${c.name}${using ? ` (${using})` : ""} may charge your account for ${what}. Go ahead?`);
}

/** What /api/covers/settings says is chosen on MCP servers, by role ("" for a server's own default). */
export type Using = Partial<Record<"covers" | "scenes" | "motion", string>>;

/** Settings, opened from anywhere ("Change in Settings"); and the word when it closes, so whatever shows a choice
 *  made there can read it again. */
export const openSettings = () => window.dispatchEvent(new Event("sv-open-settings"));
export const settingsChanged = () => window.dispatchEvent(new Event("sv-settings-changed"));
export function onSettingsChanged(fn: () => void): () => void {
  window.addEventListener("sv-settings-changed", fn);
  return () => window.removeEventListener("sv-settings-changed", fn);
}
