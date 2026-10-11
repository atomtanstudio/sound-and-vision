import { useSyncExternalStore } from "react";

/** A tiny router: the address is the state (its path, and its query for things like ?kind=); links call go(). */
const listeners = new Set<() => void>();
const tell = () => listeners.forEach((l) => l());
const subscribe = (l: () => void) => (listeners.add(l), () => void listeners.delete(l));
window.addEventListener("popstate", tell);

/** Go to a path, with its query if it has one. `replace` swaps the current entry instead (a tab or a filter changing
 *  on the same page) and keeps the scroll where it is. */
export function go(path: string, replace = false) {
  if (path === location.pathname + location.search) return;
  history[replace ? "replaceState" : "pushState"](null, "", path);
  tell();
  if (!replace) window.scrollTo({ top: 0 });
}

export function usePath(): string {
  return useSyncExternalStore(subscribe, () => location.pathname);
}

/** One value from the address's query (`?kind=music` → useQuery("kind")), kept in step with every navigation. */
export function useQuery(name: string): string | null {
  return useSyncExternalStore(subscribe, () => new URLSearchParams(location.search).get(name));
}

/** For <a> elements: navigate in-app on a plain click, let modified clicks open tabs. `then` runs after an in-app
 *  click (closing a menu, say). */
export function linkTo(path: string, then?: () => void) {
  return {
    href: path,
    onClick: (e: React.MouseEvent) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      go(path);
      then?.();
    },
  };
}
