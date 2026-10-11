import { useEffect, useState } from "react";
import { useLine } from "../state/events";
import "./linenotice.css";
import { machine } from "../lib/machine";

/** A quiet notice while the line to the server is down, and a moment's "back" when it returns. */
export function LineNotice() {
  const { state, drops } = useLine();
  const [show, setShow] = useState<"lost" | "back" | null>(null);

  useEffect(() => {
    if (state === "lost") {
      const t = window.setTimeout(() => setShow("lost"), 1500); // a blip shorter than that isn't worth a word
      return () => window.clearTimeout(t);
    }
    if (state === "live" && drops > 0) {
      setShow((s) => (s === "lost" ? "back" : null));
      const t = window.setTimeout(() => setShow(null), 2500);
      return () => window.clearTimeout(t);
    }
  }, [state, drops]);

  if (!show) return null;
  return (
    <div className={`ln ln-${show}`} role="status">
      {show === "lost" ? (
        <>
          <span className="ln-spin" aria-hidden="true" />
          Lost touch with {machine()}. Reconnecting… (anything already making keeps going there)
        </>
      ) : (
        <>Back in touch with {machine()}. Everything's up to date.</>
      )}
    </div>
  );
}
