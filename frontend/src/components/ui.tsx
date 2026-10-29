import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";
import { Loader2 } from "lucide-react";
import { STATUS_LABEL, statusTone } from "../lib/format";

/* ------------------------------------------------------------------ button */
type Variant = "primary" | "secondary" | "ghost" | "danger" | "subtle";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-amber-400 text-ink-950 hover:bg-amber-300 shadow-lg shadow-amber-500/10 font-semibold",
  secondary:
    "border border-white/10 bg-white/[0.05] text-slate-100 hover:bg-white/[0.09]",
  ghost: "text-slate-300 hover:bg-white/[0.06] hover:text-white",
  danger:
    "border border-red-500/30 bg-red-500/10 text-red-200 hover:bg-red-500/20",
  subtle: "bg-ink-800 text-slate-200 hover:bg-ink-700 border border-white/5",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs rounded-lg gap-1.5",
  md: "h-10 px-4 text-sm rounded-xl gap-2",
  lg: "h-12 px-6 text-sm rounded-xl gap-2.5",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={`inline-flex items-center justify-center whitespace-nowrap transition-all duration-150
        disabled:cursor-not-allowed disabled:opacity-45 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    >
      {loading && <Loader2 size={15} className="animate-spin" />}
      {children}
    </button>
  );
}

/* -------------------------------------------------------------------- card */
export function Card({
  children,
  className = "",
  raised = false,
}: {
  children: ReactNode;
  className?: string;
  raised?: boolean;
}) {
  return <div className={`${raised ? "panel-raised" : "panel"} ${className}`}>{children}</div>;
}

export function SectionHeading({
  title,
  description,
  action,
  eyebrow,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && (
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.2em] text-amber-400/80">
            {eyebrow}
          </p>
        )}
        <h2 className="text-xl font-semibold tracking-tight text-white">{title}</h2>
        {description && <p className="mt-1 max-w-2xl text-sm text-slate-400">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/* ------------------------------------------------------------------- badge */
export function Badge({
  children,
  tone = "slate",
  dot = false,
  className = "",
}: {
  children: ReactNode;
  tone?: "green" | "amber" | "red" | "slate" | "blue";
  dot?: boolean;
  className?: string;
}) {
  const tones: Record<string, string> = {
    green: "border-emerald-400/20 bg-emerald-400/10 text-emerald-300",
    amber: "border-amber-400/25 bg-amber-400/10 text-amber-300",
    red: "border-red-400/25 bg-red-400/10 text-red-300",
    blue: "border-sky-400/25 bg-sky-400/10 text-sky-300",
    slate: "border-white/10 bg-white/[0.04] text-slate-300",
  };
  const dots: Record<string, string> = {
    green: "bg-emerald-400",
    amber: "bg-amber-400",
    red: "bg-red-400",
    blue: "bg-sky-400",
    slate: "bg-slate-400",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${tones[tone]} ${className}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${dots[tone]}`} />}
      {children}
    </span>
  );
}

export function StatusBadge({ status, label }: { status?: string | null; label?: string }) {
  return (
    <Badge tone={statusTone(status)} dot>
      {label ?? STATUS_LABEL[status || ""] ?? status ?? "—"}
    </Badge>
  );
}

/* ----------------------------------------------------------------- progress */
export function Progress({
  value,
  indeterminate = false,
  className = "",
  tone = "amber",
}: {
  value: number;
  indeterminate?: boolean;
  className?: string;
  tone?: "amber" | "green" | "blue";
}) {
  const colors = { amber: "bg-amber-400", green: "bg-emerald-400", blue: "bg-sky-400" };
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06] ${className}`}>
      <div
        className={`h-full rounded-full transition-[width] duration-500 ${
          indeterminate ? "w-1/3 animate-shimmer stripe bg-amber-400/80" : colors[tone]
        }`}
        style={indeterminate ? undefined : { width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------- fields */
export function Field({
  label,
  hint,
  children,
  className = "",
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="label mb-2 block">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs leading-relaxed text-slate-500">{hint}</span>}
    </label>
  );
}

export function Select({
  className = "",
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={`input appearance-none pr-9 ${className}`}>
      {children}
    </select>
  );
}

export function Input({ className = "", ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={`input ${className}`} />;
}

export function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
  hint,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  format?: (value: number) => string;
  hint?: string;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="label">{label}</span>
        <span className="rounded-md bg-white/[0.05] px-2 py-0.5 font-mono text-[11px] text-amber-300">
          {format ? format(value) : value}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-white/10 accent-amber-400"
      />
      {hint && <p className="mt-2 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled = false,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="group flex w-full items-start gap-3 text-left disabled:opacity-50"
    >
      <span
        className={`mt-0.5 flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors ${
          checked ? "border-amber-400/50 bg-amber-400/90" : "border-white/15 bg-white/[0.06]"
        }`}
      >
        <span
          className={`h-3.5 w-3.5 rounded-full bg-ink-950 transition-transform ${
            checked ? "translate-x-[18px]" : "translate-x-[3px]"
          }`}
        />
      </span>
      <span>
        <span className="block text-sm font-medium text-slate-200">{label}</span>
        {description && (
          <span className="mt-0.5 block text-xs leading-relaxed text-slate-500">{description}</span>
        )}
      </span>
    </button>
  );
}

/* -------------------------------------------------------------------- misc */
export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-10 text-sm text-slate-400">
      <Loader2 size={18} className="animate-spin text-amber-400" />
      {label || "Cargando…"}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {icon && <div className="mb-4 text-slate-600">{icon}</div>}
      <h3 className="text-base font-medium text-slate-200">{title}</h3>
      {description && <p className="mt-1.5 max-w-md text-sm text-slate-500">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function StatTile({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          {label}
        </span>
        {icon && <span className="text-slate-600">{icon}</span>}
      </div>
      <div className="mt-1.5 font-mono text-lg text-slate-100">{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-slate-500">{hint}</div>}
    </div>
  );
}

export function ErrorBanner({
  title,
  message,
  hint,
  action,
}: {
  title: string;
  message: string;
  hint?: string | null;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-red-500/25 bg-red-500/[0.07] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-red-200">{title}</p>
          <p className="mt-1 text-sm text-red-200/80">{message}</p>
          {hint && <p className="mt-2 text-xs leading-relaxed text-red-200/60">{hint}</p>}
        </div>
        {action}
      </div>
    </div>
  );
}
