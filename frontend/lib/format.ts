import type { AttrState, ReviewStatus, SafetyStatus } from "./types";

export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function num(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toLocaleString("en-IN");
}

export function inr(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `₹${Math.round(v).toLocaleString("en-IN")}`;
}

/**
 * Dates are rendered with an explicit, fixed locale and UTC timezone.
 * `toLocaleString()` with defaults produces different output on the server and
 * in the browser, which React reports as a hydration mismatch.
 */
export function dateTime(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "—";
  const p = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC",
  }).format(d);
  return `${p} UTC`;
}

export function dateOnly(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", year: "numeric", timeZone: "UTC",
  }).format(d);
}

export function attrValue(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "Not specified";
  return String(v);
}

export const STATE_STYLE: Record<AttrState, string> = {
  MATCH: "bg-state-okBg text-state-ok border-state-ok/25",
  MISMATCH: "bg-state-dangerBg text-state-danger border-state-danger/25",
  UNKNOWN: "bg-state-neutralBg text-state-neutral border-line-strong",
};

export const STATE_LABEL: Record<AttrState, string> = {
  MATCH: "Match",
  MISMATCH: "Mismatch",
  UNKNOWN: "Unknown",
};

export const SAFETY_STYLE: Record<SafetyStatus, string> = {
  PASS: "bg-state-okBg text-state-ok border-state-ok/25",
  BLOCK: "bg-state-dangerBg text-state-danger border-state-danger/25",
  INSUFFICIENT_EVIDENCE: "bg-state-warnBg text-state-warn border-state-warn/25",
};

export const SAFETY_LABEL: Record<SafetyStatus, string> = {
  PASS: "Pass",
  BLOCK: "Blocked",
  INSUFFICIENT_EVIDENCE: "Insufficient evidence",
};

export const REVIEW_STYLE: Record<ReviewStatus, string> = {
  AUTO_MATCHED: "bg-state-okBg text-state-ok border-state-ok/25",
  NEEDS_REVIEW: "bg-state-warnBg text-state-warn border-state-warn/25",
  INSUFFICIENT_EVIDENCE: "bg-state-warnBg text-state-warn border-state-warn/25",
  BLOCKED: "bg-state-dangerBg text-state-danger border-state-danger/25",
  APPROVED: "bg-state-infoBg text-state-info border-state-info/25",
  REJECTED: "bg-state-neutralBg text-state-neutral border-line-strong",
};

export const REVIEW_LABEL: Record<ReviewStatus, string> = {
  AUTO_MATCHED: "Auto matched",
  NEEDS_REVIEW: "Needs review",
  INSUFFICIENT_EVIDENCE: "Insufficient evidence",
  BLOCKED: "Blocked",
  APPROVED: "Approved",
  REJECTED: "Rejected",
};

export const COMMODITY_LABEL: Record<string, string> = {
  gate_valve: "Gate Valve",
  pipe: "Pipe",
  bearing: "Bearing",
  electrical_cable: "Electrical Cable",
  fastener: "Fastener",
  unknown: "Unknown",
};

export function commodityLabel(c: string | null | undefined): string {
  if (!c) return "Unclassified";
  return COMMODITY_LABEL[c] ?? c;
}

/** Confidence colour ramp, used only where a number needs emphasis. */
export function confidenceTone(v: number | null | undefined): string {
  if (v === null || v === undefined) return "text-ink-faint";
  if (v >= 0.85) return "text-state-ok";
  if (v >= 0.62) return "text-ink";
  if (v >= 0.45) return "text-state-warn";
  return "text-ink-subtle";
}
