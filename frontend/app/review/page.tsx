"use client";

import clsx from "clsx";
import { Check, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EvidenceTable, SafetyVerdictPanel } from "@/components/MatchExplanation";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeading } from "@/components/shell/Header";
import {
  ConfidenceBar,
  EmptyState,
  ErrorState,
  InlineError,
  LoadingBlock,
  Mono,
  Pagination,
  Panel,
  ReviewBadge,
} from "@/components/ui/primitives";
import { api, qs } from "@/lib/api";
import { REVIEW_LABEL, commodityLabel, dateTime, pct } from "@/lib/format";
import type { ReviewItem, ReviewStatus } from "@/lib/types";

const FILTERS: { key: string; label: string }[] = [
  { key: "ALL", label: "All" },
  { key: "NEEDS_REVIEW", label: "Needs Review" },
  { key: "INSUFFICIENT_EVIDENCE", label: "Insufficient Evidence" },
  { key: "BLOCKED", label: "Blocked" },
  { key: "APPROVED", label: "Approved" },
  { key: "REJECTED", label: "Rejected" },
  { key: "AUTO_MATCHED", label: "Auto Matched" },
];

const LIMIT = 20;

export default function ReviewQueuePage() {
  const [filter, setFilter] = useState("NEEDS_REVIEW");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [openId, setOpenId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ReviewItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [overrideNmi, setOverrideNmi] = useState("");
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<{
        items: ReviewItem[];
        total: number;
        counts: Record<string, number>;
      }>(`/review-queue${qs({ status: filter, limit: LIMIT, offset })}`);
      setItems(data.items);
      setTotal(data.total);
      setCounts(data.counts);
    } catch (e: any) {
      setError(e?.detail ?? "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, [filter, offset]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setOffset(0);
  }, [filter]);

  const openDetail = useCallback(async (id: number) => {
    setOpenId(id);
    setDetail(null);
    setActionError(null);
    setOverrideNmi("");
    setReason("");
    setDetailLoading(true);
    try {
      setDetail(await api.get<ReviewItem>(`/review-queue/${id}`));
    } catch (e: any) {
      setActionError(e?.detail ?? "Could not load the evidence for this item.");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const decide = useCallback(
    async (decision: "APPROVE" | "REJECT") => {
      if (!detail) return;
      setSubmitting(true);
      setActionError(null);
      try {
        await api.post(`/review-queue/${detail.id}/decide`, {
          decision,
          steward: "demo.steward",
          reason: reason || null,
          override_nmi: overrideNmi.trim() || null,
        });
        setOpenId(null);
        setDetail(null);
        await load();
      } catch (e: any) {
        setActionError(e?.detail ?? "The decision could not be saved.");
      } finally {
        setSubmitting(false);
      }
    },
    [detail, overrideNmi, reason, load]
  );

  const canAct =
    detail && !["APPROVED", "REJECTED"].includes(detail.status) && !detailLoading;

  return (
    <AppShell crumbs={[{ label: "Overview", href: "/" }, { label: "Review Queue" }]}>
      <PageHeading
        title="Review Queue"
        description="Pairs the pipeline would not merge on its own, with the evidence behind each decision."
      />

      <div className="flex flex-wrap gap-1.5 mb-4">
        {FILTERS.map((f) => {
          const count =
            f.key === "ALL"
              ? Object.values(counts).reduce((a, b) => a + b, 0)
              : counts[f.key] ?? 0;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={clsx(
                "btn h-7 px-2.5 text-xs",
                filter === f.key
                  ? "bg-accent-500 border-accent-500 text-white"
                  : "bg-surface border-line-strong text-ink-muted hover:bg-surface-subtle"
              )}
            >
              {f.label}
              <span
                className={clsx(
                  "ml-1 tnum",
                  filter === f.key ? "text-white/80" : "text-ink-faint"
                )}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      <Panel>
        {loading && <LoadingBlock label="Loading review queue" />}
        {error && !loading && <ErrorState message={error} onRetry={load} />}
        {!loading && !error && items.length === 0 && (
          <EmptyState
            title="Nothing in this queue"
            description={
              filter === "NEEDS_REVIEW"
                ? "No records are currently waiting on a steward decision."
                : `No records currently have status “${
                    REVIEW_LABEL[filter as ReviewStatus] ?? filter
                  }”.`
            }
          />
        )}

        {!loading && !error && items.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Material</th>
                    <th>CPSE</th>
                    <th>Original Code</th>
                    <th>Candidate NMI</th>
                    <th className="w-36">Confidence</th>
                    <th>Reason</th>
                    <th>Status</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((it) => (
                    <tr
                      key={it.id}
                      className="cursor-pointer"
                      onClick={() => openDetail(it.id)}
                    >
                      <td className="max-w-xs">
                        <p className="line-clamp-2 text-ink">{it.raw_description}</p>
                        <p className="text-2xs text-ink-subtle mt-0.5">
                          {commodityLabel(it.commodity_type)}
                        </p>
                      </td>
                      <td className="whitespace-nowrap">{it.cpse_org}</td>
                      <td><Mono>{it.legacy_code}</Mono></td>
                      <td>
                        {it.candidate_nmi ? (
                          <Mono className="text-accent-500">{it.candidate_nmi}</Mono>
                        ) : (
                          <span className="text-ink-faint">—</span>
                        )}
                      </td>
                      <td><ConfidenceBar value={it.score} /></td>
                      <td className="max-w-sm text-xs text-ink-subtle">
                        <p className="line-clamp-2">{it.reason}</p>
                        {it.blocked_field && (
                          <span className="badge bg-state-dangerBg text-state-danger border-state-danger/25 mt-1">
                            {it.blocked_field.replace(/_/g, " ")}
                          </span>
                        )}
                      </td>
                      <td><ReviewBadge status={it.status} /></td>
                      <td className="text-xs text-ink-subtle whitespace-nowrap">
                        {dateTime(it.reviewed_at ?? it.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination total={total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </>
        )}
      </Panel>

      {openId !== null && (
        <div
          className="fixed inset-0 z-40 bg-ink/25 flex justify-end"
          onClick={() => setOpenId(null)}
        >
          <div
            className="w-full max-w-3xl h-full bg-surface border-l border-line overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Review item evidence"
          >
            <div className="sticky top-0 bg-surface border-b border-line px-5 py-3 flex items-start justify-between gap-3 z-10">
              <div className="min-w-0">
                <h2 className="text-sm font-semibold text-ink">Review Evidence</h2>
                {detail && (
                  <p className="text-xs text-ink-subtle mt-0.5 truncate">
                    {detail.cpse_org} · {detail.legacy_code}
                  </p>
                )}
              </div>
              <button
                type="button"
                className="btn-ghost h-7 w-7 p-0"
                onClick={() => setOpenId(null)}
                aria-label="Close"
              >
                <X className="h-4 w-4" aria-hidden />
              </button>
            </div>

            {detailLoading && <LoadingBlock label="Loading evidence" />}
            {actionError && (
              <div className="px-5 pt-4">
                <InlineError message={actionError} />
              </div>
            )}

            {detail && !detailLoading && (
              <div className="p-5 space-y-4">
                <div className="grid sm:grid-cols-2 gap-3">
                  <div className="panel px-3 py-2.5">
                    <p className="text-2xs uppercase tracking-wide text-ink-subtle mb-1">
                      Source record
                    </p>
                    <p className="text-sm text-ink">{detail.raw_description}</p>
                    <p className="text-xs text-ink-subtle mt-1">
                      {detail.cpse_org} · <Mono>{detail.legacy_code}</Mono>
                    </p>
                    <Link
                      href={`/materials/${detail.record_id}`}
                      className="text-xs text-accent-500 hover:underline mt-1 inline-block"
                    >
                      Open material →
                    </Link>
                  </div>
                  <div className="panel px-3 py-2.5">
                    <p className="text-2xs uppercase tracking-wide text-ink-subtle mb-1">
                      Proposed match
                    </p>
                    {detail.candidate_record ? (
                      <>
                        <p className="text-sm text-ink">
                          {detail.candidate_record.raw_description}
                        </p>
                        <p className="text-xs text-ink-subtle mt-1">
                          {detail.candidate_record.cpse_org} ·{" "}
                          <Mono>{detail.candidate_record.legacy_code}</Mono>
                        </p>
                      </>
                    ) : (
                      <p className="text-sm text-ink-subtle">
                        {detail.candidate_description ?? "No candidate proposed."}
                      </p>
                    )}
                    {detail.candidate_nmi && (
                      <Link
                        href={`/crosswalk/${detail.candidate_nmi}`}
                        className="text-xs text-accent-500 hover:underline mt-1 inline-block"
                      >
                        {detail.candidate_nmi} →
                      </Link>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between gap-3 panel px-3 py-2.5">
                  <div>
                    <p className="text-2xs uppercase tracking-wide text-ink-subtle">
                      Match confidence
                    </p>
                    <p className="text-lg font-semibold tnum text-ink">{pct(detail.score, 1)}</p>
                  </div>
                  <ReviewBadge status={detail.status} />
                </div>

                <div className="panel px-3 py-2.5">
                  <p className="text-2xs uppercase tracking-wide text-ink-subtle mb-1">
                    Why this needs a human
                  </p>
                  <p className="text-sm text-ink">{detail.reason}</p>
                </div>

                {detail.safety && <SafetyVerdictPanel safety={detail.safety} />}

                {detail.evidence_table && detail.evidence_table.length > 0 && (
                  <Panel title="Attribute Evidence">
                    <EvidenceTable comparisons={detail.evidence_table} />
                  </Panel>
                )}

                {canAct ? (
                  <Panel title="Steward Decision" bodyClassName="px-4 py-3 space-y-3">
                    <div>
                      <label className="field-label" htmlFor="r-reason">
                        Reason (recorded in the audit trail)
                      </label>
                      <input
                        id="r-reason"
                        className="input"
                        placeholder="e.g. Confirmed against vendor datasheet"
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="field-label" htmlFor="r-nmi">
                        Change recommendation (optional)
                      </label>
                      <input
                        id="r-nmi"
                        className="input font-mono"
                        placeholder={detail.candidate_nmi ?? "NMI-000001"}
                        value={overrideNmi}
                        onChange={(e) => setOverrideNmi(e.target.value)}
                      />
                      <p className="text-2xs text-ink-subtle mt-1">
                        Leave blank to accept {detail.candidate_nmi ?? "the proposed identity"}. The
                        NMI must already exist.
                      </p>
                    </div>
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={submitting}
                        onClick={() => decide("APPROVE")}
                      >
                        <Check className="h-3.5 w-3.5" aria-hidden />
                        Approve
                      </button>
                      <button
                        type="button"
                        className="btn-danger"
                        disabled={submitting}
                        onClick={() => decide("REJECT")}
                      >
                        <X className="h-3.5 w-3.5" aria-hidden />
                        Reject
                      </button>
                    </div>
                  </Panel>
                ) : (
                  detail && (
                    <p className="text-xs text-ink-subtle">
                      This item was already {REVIEW_LABEL[detail.status].toLowerCase()}
                      {detail.reviewer && <> by {detail.reviewer}</>}
                      {detail.reviewed_at && <> on {dateTime(detail.reviewed_at)}</>}.
                    </p>
                  )
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </AppShell>
  );
}
