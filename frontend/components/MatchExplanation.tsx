"use client";

/**
 * The single explanation component, reused by candidate results, material
 * detail, the review queue and crosswalk detail.
 *
 * Every number here comes from the scoring pipeline. A confidence is never
 * shown on its own -- the components that produced it and the per-attribute
 * evidence behind it are always one glance away.
 */

import clsx from "clsx";
import { ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";

import { SAFETY_LABEL, SAFETY_STYLE, attrValue, pct } from "@/lib/format";
import type { Comparison, MatchExplanation as Explanation, SafetyVerdict } from "@/lib/types";
import { StateBadge } from "@/components/ui/primitives";

function ComponentBar({
  label,
  value,
  weight,
}: {
  label: string;
  value: number;
  weight?: number;
}) {
  return (
    <div className="grid grid-cols-[8.5rem_1fr_3.25rem] items-center gap-3">
      <span className="text-xs text-ink-muted">
        {label}
        {weight !== undefined && (
          <span className="text-ink-faint"> · w {weight.toFixed(2)}</span>
        )}
      </span>
      <div className="h-1.5 rounded-full bg-surface-sunken overflow-hidden">
        <div
          className="h-full rounded-full bg-accent-500"
          style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
        />
      </div>
      <span className="text-xs tnum text-ink text-right">{value.toFixed(3)}</span>
    </div>
  );
}

export function EvidenceTable({ comparisons }: { comparisons: Comparison[] }) {
  if (!comparisons.length) {
    return (
      <p className="px-4 py-3 text-xs text-ink-subtle">
        No comparable attributes were extracted from either record.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>
            <th>Attribute</th>
            <th>This record</th>
            <th>Candidate</th>
            <th>State</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {comparisons.map((c) => (
            <tr key={c.key}>
              <td className="whitespace-nowrap">
                <span className="text-ink">{c.label ?? c.key}</span>
                {c.safety_critical && (
                  <span
                    className="ml-1.5 badge bg-accent-50 text-accent-600 border-accent-200"
                    title="A confirmed difference here prevents a merge"
                  >
                    Safety
                  </span>
                )}
              </td>
              <td className={clsx(c.value_a === null && "text-ink-faint italic")}>
                {attrValue(c.value_a)}
              </td>
              <td className={clsx(c.value_b === null && "text-ink-faint italic")}>
                {attrValue(c.value_b)}
              </td>
              <td>
                <StateBadge state={c.state} />
              </td>
              <td className="text-xs text-ink-subtle max-w-xs">{c.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SafetyVerdictPanel({ safety }: { safety: SafetyVerdict }) {
  const Icon =
    safety.status === "PASS"
      ? ShieldCheck
      : safety.status === "BLOCK"
      ? ShieldAlert
      : ShieldQuestion;

  return (
    <div
      className={clsx(
        "flex items-start gap-2.5 rounded border px-3 py-2.5",
        SAFETY_STYLE[safety.status]
      )}
    >
      <Icon className="h-4 w-4 mt-px shrink-0" aria-hidden />
      <div className="min-w-0">
        <p className="text-xs font-semibold">
          Hard constraints: {SAFETY_LABEL[safety.status]}
          {safety.blocked_field_label && ` — ${safety.blocked_field_label}`}
        </p>
        <p className="text-xs mt-0.5 opacity-90 leading-snug">{safety.reason}</p>
      </div>
    </div>
  );
}

export function MatchExplanation({
  explanation,
  safety,
  compact = false,
}: {
  explanation: Explanation;
  safety?: SafetyVerdict;
  compact?: boolean;
}) {
  const counts = explanation.counts || { MATCH: 0, MISMATCH: 0, UNKNOWN: 0 };

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <ComponentBar
          label="Semantic similarity"
          value={explanation.semantic}
          weight={explanation.weights?.semantic}
        />
        <ComponentBar
          label="Lexical similarity"
          value={explanation.lexical}
          weight={explanation.weights?.lexical}
        />
        <ComponentBar
          label="Attribute agreement"
          value={explanation.attribute_agreement}
          weight={explanation.weights?.attributes}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 pt-2.5 border-t border-line">
        <div className="flex items-center gap-3 text-xs text-ink-subtle">
          <span>
            <span className="text-state-ok font-medium tnum">{counts.MATCH ?? 0}</span> match
          </span>
          <span>
            <span className="text-state-danger font-medium tnum">{counts.MISMATCH ?? 0}</span> mismatch
          </span>
          <span>
            <span className="text-ink-muted font-medium tnum">{counts.UNKNOWN ?? 0}</span> unknown
          </span>
          <span className="text-ink-faint">
            · evidence coverage {pct(explanation.coverage, 0)}
          </span>
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-2xs uppercase tracking-wide text-ink-subtle">
            Final confidence
          </span>
          <span className="text-lg font-semibold tnum text-ink">
            {pct(explanation.score, 1)}
          </span>
        </div>
      </div>

      {safety && <SafetyVerdictPanel safety={safety} />}

      {!compact && (
        <div className="border border-line rounded overflow-hidden">
          <EvidenceTable comparisons={explanation.comparisons} />
        </div>
      )}
    </div>
  );
}
