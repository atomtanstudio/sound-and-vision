/** What the interface calls the machine Sound / Vision runs on: SV_MACHINE on the server, else its own hostname.
 *  Set once from /api/health before the app first draws. */
let name = "the server";

export const machine = () => name;
/** For the start of a sentence: "The server is making…" */
export const Machine = () => name.charAt(0).toUpperCase() + name.slice(1);
export function setMachine(n?: string) {
  if (n?.trim()) name = n.trim();
}
