import {
  useEffect,
  useRef,
  useState,
  type PointerEvent,
  type MouseEvent,
  type KeyboardEvent,
} from "react";

type Drag = {
  x: number;
  y: number;
  clientX: number;
  clientY: number;
  additive: boolean;
  initial: Set<string>;
  active: boolean;
  pointer: number;
};

export function useLibrarySelection(ids: string[], scope: string) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [enabled, setEnabled] = useState(false);
  const [box, setBox] = useState<{
    left: number;
    top: number;
    width: number;
    height: number;
  } | null>(null);
  const area = useRef<HTMLDivElement>(null);
  const anchor = useRef<string | null>(null);
  const drag = useRef<Drag | null>(null);
  const frame = useRef(0);
  const suppressClick = useRef(false);
  const idsKey = ids.join(",");
  const available = new Set(ids);
  const chosen = new Set([...selected].filter((id) => available.has(id)));
  useEffect(() => {
    cancelAnimationFrame(frame.current);
    drag.current = null;
    setBox(null);
    setSelected(new Set());
    setEnabled(false);
    anchor.current = null;
  }, [scope]);
  useEffect(() => {
    const available = new Set(idsKey.split(","));
    setSelected(
      (previous) => new Set([...previous].filter((id) => available.has(id))),
    );
  }, [idsKey]);
  useEffect(() => () => cancelAnimationFrame(frame.current), []);
  useEffect(() => {
    const key = (event: globalThis.KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (
        document.querySelector("dialog[open]") ||
        target.closest("input,textarea,select,[contenteditable=true]")
      )
        return;
      if (event.key === "Escape" && enabled) {
        event.preventDefault();
        end(true);
        clear();
      }
      if (
        (event.metaKey || event.ctrlKey) &&
        event.key.toLowerCase() === "a" &&
        target.closest(".music-library") &&
        !target.closest(".tracks")
      ) {
        event.preventDefault();
        setEnabled(true);
        setSelected(new Set(idsKey.split(",").filter(Boolean)));
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [enabled, idsKey]);

  function clear() {
    setSelected(new Set());
    setEnabled(false);
    anchor.current = null;
  }
  function toggle(id: string, range = false) {
    setEnabled(true);
    setSelected((previous) => {
      const next = new Set([...previous].filter((id) => available.has(id)));
      const start = anchor.current ? ids.indexOf(anchor.current) : -1;
      if (range && start !== -1) {
        const end = ids.indexOf(id);
        ids
          .slice(Math.min(start, end), Math.max(start, end) + 1)
          .forEach((item) => next.add(item));
      } else if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    if (!range) anchor.current = id;
  }
  function draw() {
    const current = drag.current,
      node = area.current;
    if (!current?.active || !node) return;
    const scroller = node.closest(".main-content")!;
    const bounds = scroller.getBoundingClientRect();
    if (current.clientY > bounds.bottom - 35) scroller.scrollTop += 16;
    else if (current.clientY < bounds.top + 35) scroller.scrollTop -= 16;
    const rect = node.getBoundingClientRect();
    const startX = rect.left + current.x,
      startY = rect.top + current.y;
    const endX = Math.max(bounds.left, Math.min(bounds.right, current.clientX));
    const endY = Math.max(bounds.top, Math.min(bounds.bottom, current.clientY));
    const left = Math.min(startX, endX),
      top = Math.min(startY, endY);
    const right = Math.max(startX, endX),
      bottom = Math.max(startY, endY);
    const next = current.additive
      ? new Set(current.initial)
      : new Set<string>();
    node.querySelectorAll<HTMLElement>("[data-track]").forEach((item) => {
      const r = item.getBoundingClientRect();
      if (r.left < right && r.right > left && r.top < bottom && r.bottom > top)
        next.add(item.dataset.track!);
    });
    setSelected((previous) =>
      previous.size === next.size && [...next].every((id) => previous.has(id))
        ? previous
        : next,
    );
    setBox({
      left: Math.max(left, bounds.left),
      top: Math.max(top, bounds.top),
      width: Math.max(
        0,
        Math.min(right, bounds.right) - Math.max(left, bounds.left),
      ),
      height: Math.max(
        0,
        Math.min(bottom, bounds.bottom) - Math.max(top, bounds.top),
      ),
    });
    frame.current = requestAnimationFrame(draw);
  }
  function end(cancel = false) {
    const current = drag.current;
    cancelAnimationFrame(frame.current);
    if (current?.active) {
      suppressClick.current = true;
      setTimeout(() => {
        suppressClick.current = false;
      }, 0);
      if (cancel) setSelected(current.initial);
      if (area.current?.hasPointerCapture(current.pointer))
        area.current.releasePointerCapture(current.pointer);
    }
    drag.current = null;
    setBox(null);
  }
  const handlers = {
    onPointerDown(event: PointerEvent<HTMLDivElement>) {
      if (
        event.button !== 0 ||
        event.pointerType === "touch" ||
        (event.target as HTMLElement).closest(
          ".track-actions,.track-check,.track-title,input,a",
        )
      )
        return;
      const rect = event.currentTarget.getBoundingClientRect();
      drag.current = {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
        clientX: event.clientX,
        clientY: event.clientY,
        additive: event.metaKey || event.ctrlKey || event.shiftKey,
        initial: new Set(chosen),
        active: false,
        pointer: event.pointerId,
      };
      suppressClick.current = false;
    },
    onPointerMove(event: PointerEvent<HTMLDivElement>) {
      const current = drag.current;
      if (!current || current.pointer !== event.pointerId) return;
      if (event.buttons !== 1) {
        end(true);
        return;
      }
      if (
        !current.active &&
        Math.hypot(
          event.clientX - current.clientX,
          event.clientY - current.clientY,
        ) < 6
      )
        return;
      current.clientX = event.clientX;
      current.clientY = event.clientY;
      if (!current.active) {
        current.active = true;
        setEnabled(true);
        event.currentTarget.setPointerCapture(event.pointerId);
        frame.current = requestAnimationFrame(draw);
      }
      event.preventDefault();
    },
    onPointerUp() {
      end();
    },
    onPointerCancel() {
      end(true);
    },
    onDragStart(event: React.DragEvent) {
      event.preventDefault();
    },
    onClickCapture(event: MouseEvent<HTMLDivElement>) {
      if (suppressClick.current) {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      const target = event.target as HTMLElement;
      const track = target.closest<HTMLElement>("[data-track]");
      if (
        track &&
        !target.closest(".track-check,.track-actions") &&
        (enabled || event.metaKey || event.ctrlKey || event.shiftKey)
      ) {
        event.preventDefault();
        event.stopPropagation();
        toggle(track.dataset.track!, event.shiftKey);
      }
    },
    onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
      if (event.key === "Escape") {
        end(true);
        clear();
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "a") {
        event.preventDefault();
        setEnabled(true);
        setSelected(new Set(ids));
      }
    },
  };
  return {
    selected: chosen,
    enabled,
    setEnabled,
    clear,
    toggle,
    area,
    box,
    handlers,
    selectAll: () => {
      setEnabled(true);
      setSelected(chosen.size === ids.length ? new Set() : new Set(ids));
    },
  };
}
