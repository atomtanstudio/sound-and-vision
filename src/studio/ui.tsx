/* Music Studio UI primitives: gradient glass controls shared by every page. */
import {
  useEffect,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { X } from "lucide-react";

export const cn = (...parts: (string | false | null | undefined)[]) =>
  parts.filter(Boolean).join(" ");

/* --------------------------------------------------------------- buttons */
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "quiet" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
};
export function Btn({
  variant = "ghost",
  size = "md",
  loading,
  className,
  children,
  disabled,
  ...rest
}: BtnProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cn("btn", `btn-${variant}`, `btn-${size}`, className)}
    >
      {loading ? <Spinner /> : null}
      {children}
    </button>
  );
}
export function IconBtn({
  label,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      {...rest}
      aria-label={label}
      title={label}
      className={cn("icon-btn", className)}
    />
  );
}

/* ---------------------------------------------------------------- labels */
export function Kicker({ children }: { children: ReactNode }) {
  return <span className="kicker">{children}</span>;
}
export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("field", className)}>
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}
export const TextInput = ({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) => (
  <input {...rest} className={cn("input", className)} />
);
export const TextArea = ({
  className,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea {...rest} className={cn("input textarea", className)} />
);
export const Select = ({
  className,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select {...rest} className={cn("input select", className)}>
    {children}
  </select>
);

/* ---------------------------------------------------------------- inputs */
export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      className={cn("toggle", checked && "on")}
      onClick={() => onChange(!checked)}
    >
      <span className="toggle-knob" />
      <span className="toggle-label">{label}</span>
    </button>
  );
}
export function Slider({
  label,
  value,
  display,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  display?: string;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="slider">
      <div className="slider-head">
        <span className="slider-label">{label}</span>
        <span className="slider-value">{display ?? value}</span>
      </div>
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step ?? 1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  size = "md",
}: {
  options: { value: T; label: ReactNode; title?: string }[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  size?: "sm" | "md";
}) {
  return (
    <div className={cn("segmented", size === "sm" && "segmented-sm")} role="tablist" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          key={option.value}
          role="tab"
          aria-selected={value === option.value}
          title={option.title}
          className={cn("segmented-item", value === option.value && "on")}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
export function CheckRow({
  checked,
  onChange,
  children,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className={cn("check-row", disabled && "disabled")}>
      <input type="checkbox" disabled={disabled} checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{children}</span>
    </label>
  );
}

/* --------------------------------------------------------------- display */
export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}
export function Equalizer({ playing }: { playing: boolean }) {
  return (
    <span className={cn("equalizer", playing && "playing")} aria-hidden="true">
      <i />
      <i />
      <i />
      <i />
    </span>
  );
}
export function StatusDot({
  tone = "idle",
  pulse,
}: {
  tone?: "live" | "ok" | "warn" | "err" | "idle";
  pulse?: boolean;
}) {
  return <span className={cn("status-dot", `dot-${tone}`, pulse && "pulse")} aria-hidden="true" />;
}
export function ProgressRing({ value, size = 22 }: { value: number; size?: number }) {
  const r = (size - 4) / 2;
  const c = 2 * Math.PI * r;
  return (
    <svg className="progress-ring" width={size} height={size} aria-hidden="true">
      <circle cx={size / 2} cy={size / 2} r={r} strokeWidth="3" className="ring-track" fill="none" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        strokeWidth="3"
        className="ring-value"
        fill="none"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - Math.max(0, Math.min(1, value)))}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  );
}
export function Empty({
  icon,
  title,
  body,
  action,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      {icon ? <div className="empty-icon">{icon}</div> : null}
      <strong>{title}</strong>
      {body ? <p>{body}</p> : null}
      {action}
    </div>
  );
}
export function ErrorNote({ children }: { children: ReactNode }) {
  return children ? <p className="error-note">{children}</p> : null;
}

/* ----------------------------------------------------------------- modal */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className={cn("modal", wide && "modal-wide")}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="modal-card">
        <header className="modal-head">
          <div>
            <h2>{title}</h2>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <IconBtn label="Close" onClick={onClose}>
            <X size={17} />
          </IconBtn>
        </header>
        <div className="modal-body">{children}</div>
        {footer ? <footer className="modal-foot">{footer}</footer> : null}
      </div>
    </dialog>
  );
}
