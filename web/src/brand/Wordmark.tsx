import { useId } from "react";
import "./wordmark.css";

/** The six bars of the slash, top to bottom (also the six lanes of the work). */
const BARS = ["--wm-1", "--wm-2", "--wm-3", "--wm-4", "--wm-5", "--wm-6"];

/**
 * "Sound / Vision": Archivo 800, tracking -0.01em, with the slash drawn as six coloured
 * bars (2.75 tall on a 3.4 pitch) clipped to the parallelogram M6.4 0H12L5.6 20H0z in a
 * 12 x 20 box, 4 px from the words at 17 px. Exactly the brand's original geometry
 * (soundandvision.old TopBar.tsx / scripts/make_wordmark.py), scaled by `size`.
 */
export function Wordmark({ size = 17, animate = false }: { size?: number; animate?: boolean }) {
  const clip = useId();
  return (
    <span
      className={"wordmark" + (animate ? " wordmark-animate" : "")}
      style={{ fontSize: size }}
      role="img"
      aria-label="Sound / Vision"
    >
      <span aria-hidden="true">Sound</span>
      <svg viewBox="0 0 12 20" aria-hidden="true">
        <clipPath id={clip}>
          <path d="M6.4 0H12L5.6 20H0z" />
        </clipPath>
        <g clipPath={`url(#${CSS.escape(clip)})`}>
          {BARS.map((c, i) => (
            <rect
              key={c}
              x="0"
              y={i * 3.4}
              width="12"
              height="2.75"
              fill={`var(${c})`}
              style={{ ["--i" as string]: i }}
            />
          ))}
        </g>
      </svg>
      <span aria-hidden="true">Vision</span>
    </span>
  );
}
