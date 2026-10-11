import { useId } from "react";
import { setTheme, useTheme } from "./theme";
import "./theme-toggle.css";

/** Stars on the night side: position in the pill (%), size (px), twinkle period and phase (s). */
const STARS = [
  { x: 14, y: 26, s: 6, d: 2.4, p: 0.0 },
  { x: 30, y: 62, s: 4, d: 1.9, p: 0.7 },
  { x: 42, y: 22, s: 5, d: 2.8, p: 1.3 },
  { x: 22, y: 78, s: 3, d: 2.2, p: 0.4 },
  { x: 52, y: 58, s: 3.5, d: 3.1, p: 1.9 },
  { x: 8, y: 54, s: 3, d: 2.6, p: 1.1 },
  { x: 36, y: 42, s: 2.5, d: 1.7, p: 2.2 },
];

/** Craters on the moon (in the knob's 40 x 40 box). */
const CRATERS = [
  { cx: 14.5, cy: 15.5, r: 2.2 },
  { cx: 16.5, cy: 25, r: 2.6 },
  { cx: 11.6, cy: 21.2, r: 1.3 },
];

/**
 * Light / dark switch. The sun rolls across to become the moon (its rays fold away and
 * a shadow slides over to leave a crescent); stars pop in one by one and twinkle, and
 * now and then one shoots past. By day, two clouds drift. Dark is on (right).
 */
export function ThemeToggle() {
  const theme = useTheme();
  const dark = theme === "dark";
  const mask = useId();

  return (
    <button
      type="button"
      className="tt"
      role="switch"
      aria-checked={dark}
      aria-label="Dark mode"
      title={dark ? "Switch to light" : "Switch to dark"}
      data-dark={dark}
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        setTheme(dark ? "light" : "dark", { x: r.left + r.width / 2, y: r.top + r.height / 2 });
      }}
    >
      <span className="tt-sky" aria-hidden="true">
        <span className="tt-day" />
        <span className="tt-night" />
        {STARS.map((s, i) => (
          <svg
            key={i}
            className="tt-star"
            viewBox="0 0 10 10"
            style={{
              left: `${s.x}%`,
              top: `${s.y}%`,
              width: s.s,
              height: s.s,
              ["--pop" as string]: `${0.18 + i * 0.05}s`,
              ["--tw" as string]: `${s.d}s`,
              ["--ph" as string]: `${s.p}s`,
            }}
          >
            <path d="M5 0 C5.4 3.6 6.4 4.6 10 5 C6.4 5.4 5.4 6.4 5 10 C4.6 6.4 3.6 5.4 0 5 C3.6 4.6 4.6 3.6 5 0Z" />
          </svg>
        ))}
        <span className="tt-shoot" />
        <span className="tt-cloud tt-cloud-a" />
        <span className="tt-cloud tt-cloud-b" />
      </span>

      <span className="tt-knob" aria-hidden="true">
        <svg viewBox="0 0 40 40">
          <defs>
            <mask id={mask} maskUnits="userSpaceOnUse" x="0" y="0" width="40" height="40">
              <rect width="40" height="40" fill="white" />
              <circle className="tt-bite" cx="45" cy="14" r="11" fill="black" />
            </mask>
          </defs>
          <g className="tt-rays">
            {Array.from({ length: 8 }, (_, i) => (
              <line key={i} x1="20" y1="3.2" x2="20" y2="6.6" transform={`rotate(${i * 45} 20 20)`} />
            ))}
          </g>
          <g mask={`url(#${CSS.escape(mask)})`}>
            <circle className="tt-disc" cx="20" cy="20" r="10.5" />
            <g className="tt-craters">
              {CRATERS.map((c, i) => (
                <circle key={i} {...c} />
              ))}
            </g>
          </g>
        </svg>
      </span>
    </button>
  );
}
