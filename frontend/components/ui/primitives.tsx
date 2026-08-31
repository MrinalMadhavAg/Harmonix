"use client";

import clsx from "clsx";
import { AlertCircle, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import type { AttrState, ReviewStatus, SafetyStatus } from "@/lib/types";
import {
  REVIEW_LABEL,
  REVIEW_STYLE,
  SAFETY_LABEL,
  SAFETY_STYLE,
  STATE_LABEL,
  STATE_STYLE,
} from "@/lib/format";

export function Panel({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={clsx("panel", className)}>
      {(title || actions) && (
        <header className="panel-header">
          <div className="min-w-0">
            {title && <h2 className="panel-title">{title}</h2>}
            {description && (
              <p className="text-xs text-ink-subtle mt-0.5">{description}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

export function StateBadge({ state }: { state: AttrState }) {
  return <span className={clsx("badge", STATE_STYLE[state])}>{STATE_LABEL[state]}</span>;
}

export function SafetyBadge({ status }: { status: SafetyStatus }) {
  return <span className={clsx("badge", SAFETY_STYLE[status])}>{SAFETY_LABEL[status]}</span>;
}

export function ReviewBadge({ status }: { status: ReviewStatus | null | undefined }) {
  if (!status) {
    return <span className="badge bg-state-neutralBg text-state-neutral border-line-strong">Not processed</span>;
  }
  return <span className={clsx("badge", REVIEW_STYLE[status])}>{REVIEW_LABEL[status]}</span>;
}

export function KpiCard({
  label,
  value,
  hint,
  tone = "default",
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "warn" | "danger" | "ok";
  icon?: ReactNode;
}) {
  const toneClass = {
    default: "text-ink",
    ok: "text-state-ok",
    warn: "text-state-warn",
    danger: "text-state-danger",
  }[tone];

  return (
    <div className="panel px-4 py-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-2xs font-medium uppercase tracking-wide text-ink-subtle">
          {label}
        </p>
        {icon && <span className="text-ink-faint shrink-0">{icon}</span>}
      </div>
      <p className={clsx("kpi-value mt-1.5", toneClass)}>{value}</p>
      {hint && <p className="text-xs text-ink-subtle mt-1 leading-snug">{hint}</p>}
    </div>
  );
}

export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-sm text-ink-subtle">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      <span>{label}…</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 px-6 text-center">
      <Inbox className="h-6 w-6 text-ink-faint" aria-hidden />
      <p className="text-sm font-medium text-ink">{title}</p>
      {description && <p className="text-xs text-ink-subtle max-w-md">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 px-6 text-center">
      <AlertCircle className="h-6 w-6 text-state-danger" aria-hidden />
      <p className="text-sm font-medium text-ink">Could not load this view</p>
      <p className="text-xs text-ink-subtle max-w-lg">{message}</p>
      {onRetry && (
        <button type="button" className="btn-secondary mt-2" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function InlineError({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded border border-state-danger/30 bg-state-dangerBg px-3 py-2 text-xs text-state-danger"
    >
      <AlertCircle className="h-3.5 w-3.5 mt-px shrink-0" aria-hidden />
      <span>{message}</span>
    </div>
  );
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={clsx("font-mono text-xs", className)}>{children}</span>;
}

export function DefinitionRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 py-1.5 border-b border-line last:border-b-0">
      <dt className="w-40 shrink-0 text-xs text-ink-subtle">{label}</dt>
      <dd className="text-sm text-ink min-w-0 break-words">{children}</dd>
    </div>
  );
}

export function Pagination({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-line">
      <p className="text-xs text-ink-subtle tnum">
        {from.toLocaleString()}–{to.toLocaleString()} of {total.toLocaleString()}
      </p>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          className="btn-secondary h-7 px-2.5 text-xs"
          disabled={!canPrev}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <button
          type="button"
          className="btn-secondary h-7 px-2.5 text-xs"
          disabled={!canNext}
          onClick={() => onChange(offset + limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

export function ConfidenceBar({ value }: { value: number | null | undefined }) {
  const v = value ?? 0;
  const tone =
    v >= 0.85 ? "bg-state-ok" : v >= 0.62 ? "bg-accent-500" : v >= 0.45 ? "bg-state-warn" : "bg-line-strong";
  return (
    <div className="flex items-center gap-2 min-w-[7rem]">
      <div className="h-1.5 flex-1 rounded-full bg-surface-sunken overflow-hidden">
        <div className={clsx("h-full rounded-full", tone)} style={{ width: `${Math.max(0, Math.min(1, v)) * 100}%` }} />
      </div>
      <span className="text-xs tnum text-ink-muted w-11 text-right">
        {value === null || value === undefined ? "—" : `${(v * 100).toFixed(0)}%`}
      </span>
    </div>
  );
}
