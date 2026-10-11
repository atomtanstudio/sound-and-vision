import { machine } from "./machine";

/** Something that can make pictures, as the server lists it (Settings → Pictures; the covers' "Made with"). */
export interface PictureChoice {
  id: string; // "openai", "local", an MCP server ("mcp:<id>"), or the owner's own where it's on
  name: string;
  note: string;
  cost: number | null; // USD a picture, when it's known
  paid: boolean; // may charge the person's account: asked first, every time
  connected?: boolean;
}

/** The short name for a picker. */
export const choiceLabel = (c: PictureChoice) => (c.id === "local" ? `On ${machine()}` : c.name);

/** Before a picture from a paid service: the person says yes, every time (they asked for that). */
export function okToSpend(c: PictureChoice | undefined, what = "this picture"): boolean {
  return !c?.paid || window.confirm(`${c.name} may charge your account for ${what}. Go ahead?`);
}
