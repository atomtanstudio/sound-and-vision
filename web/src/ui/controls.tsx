import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import "./controls.css";

export function Button({
  kind = "plain",
  size = "md",
  busy,
  children,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  kind?: "primary" | "plain" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  busy?: boolean;
}) {
  return (
    <button type="button" className={`btn btn-${kind} btn-${size}`} aria-busy={busy || undefined} {...rest}>
      {busy && <span className="btn-spin" aria-hidden="true" />}
      {children}
    </button>
  );
}

/** One choice out of a few, shown as a row of pills. */
export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
  size = "md",
}: {
  value: T;
  options: { value: T; label: ReactNode; hint?: string; disabled?: boolean }[];
  onChange: (v: T) => void;
  label: string;
  size?: "sm" | "md";
}) {
  return (
    <div className={`seg seg-${size}`} role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          disabled={o.disabled}
          title={o.hint}
          aria-label={typeof o.label === "string" || typeof o.label === "number" ? String(o.label) : undefined}
          className="seg-opt"
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Chip({
  on,
  children,
  onClick,
  onRemove,
  tone,
}: {
  on?: boolean;
  children: ReactNode;
  onClick?: () => void;
  onRemove?: () => void;
  tone?: string;
}) {
  return (
    <span className={"chip" + (on ? " chip-on" : "")} style={tone ? ({ ["--tone" as string]: tone } as React.CSSProperties) : undefined}>
      <button type="button" className="chip-main" aria-pressed={on} onClick={onClick}>
        {children}
      </button>
      {onRemove && (
        <button type="button" className="chip-x" aria-label="Remove" onClick={onRemove}>
          ×
        </button>
      )}
    </span>
  );
}

/** A slider whose thumb starts where the value is: clicking the track moves it to the click, never to an arbitrary default. */
export function Slider({
  value,
  min,
  max,
  step,
  onChange,
  label,
  left,
  right,
  format,
  defaultValue,
}: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  label: string;
  left?: string;
  right?: string;
  format?: (v: number) => string;
  defaultValue?: number;
}) {
  const id = useId();
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="sld">
      <div className="sld-head">
        <label htmlFor={id}>{label}</label>
        <span className="sld-val">
          {format ? format(value) : value}
          {defaultValue !== undefined && Math.abs(value - defaultValue) > step / 2 && (
            <button type="button" className="sld-reset" onClick={() => onChange(defaultValue)} title="Back to the default">
              reset
            </button>
          )}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        style={{ ["--pct" as string]: `${pct}%` }}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      {(left || right) && (
        <div className="sld-ends">
          <span>{left}</span>
          <span>{right}</span>
        </div>
      )}
    </div>
  );
}

/** A section that opens; remembers being open for this browser. */
export function Disclosure({ id, title, hint, children }: { id: string; title: string; hint?: string; children: ReactNode }) {
  const key = `sv.open.${id}`;
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(key) === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(key, open ? "1" : "0");
    } catch {
      /* not saved; fine */
    }
  }, [key, open]);
  return (
    <section className={"dis" + (open ? " dis-open" : "")}>
      <button type="button" className="dis-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="dis-caret" aria-hidden="true">
          ›
        </span>
        <span className="dis-title">{title}</span>
        {hint && <span className="dis-hint">{hint}</span>}
      </button>
      {open && <div className="dis-body">{children}</div>}
    </section>
  );
}

export function Modal({ title, onClose, children, wide, full }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean; full?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    d?.showModal();
    return () => d?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={"mod" + (wide ? " mod-wide" : "") + (full ? " mod-full" : "")}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="mod-head">
        <h2>{title}</h2>
        <button type="button" className="mod-x" aria-label="Close" onClick={onClose}>
          ×
        </button>
      </div>
      <div className="mod-body">{children}</div>
    </dialog>
  );
}

/** A text area that grows with its words (CSS field-sizing; older browsers measure after each change). */
const NATIVE_FIT = typeof CSS !== "undefined" && CSS.supports?.("field-sizing", "content");
export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { minRows?: number }) {
  const { minRows = 2, ...rest } = props;
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const t = ref.current;
    if (!t || NATIVE_FIT) return;
    t.style.height = "auto";
    t.style.height = `${t.scrollHeight + 2}px`;
  }, [props.value]);
  return <textarea ref={ref} rows={minRows} className="ta" style={{ minHeight: `${minRows * 1.55 + 1.3}em` }} {...rest} />;
}
