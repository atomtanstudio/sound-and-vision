import { useSyncExternalStore } from "react";
import { flushSync } from "react-dom";

export type Theme = "dark" | "light";

const KEY = "sv.theme";
const listeners = new Set<() => void>();

function read(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function write(t: Theme) {
  document.documentElement.dataset.theme = t;
  try {
    localStorage.setItem(KEY, t);
  } catch {
    /* private window: the choice lasts for this page only */
  }
  listeners.forEach((l) => l());
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (l) => (listeners.add(l), () => listeners.delete(l)),
    read,
    () => "dark",
  );
}

/**
 * Switch theme. With View Transitions the new theme spreads out as a circle from
 * `from` (the toggle); otherwise it switches at once.
 */
export function setTheme(t: Theme, from?: { x: number; y: number }) {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!doc.startViewTransition || reduce || !from) {
    write(t);
    return;
  }
  const root = document.documentElement;
  const r = Math.hypot(Math.max(from.x, innerWidth - from.x), Math.max(from.y, innerHeight - from.y));
  root.style.setProperty("--vt-x", `${from.x}px`);
  root.style.setProperty("--vt-y", `${from.y}px`);
  root.style.setProperty("--vt-r", `${r}px`);
  doc.startViewTransition(() => flushSync(() => write(t)));
}
