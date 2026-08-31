"use client";

import clsx from "clsx";
import { Play, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageHeading } from "@/components/shell/Header";
import {
  ConfidenceBar,
  EmptyState,
  ErrorState,
  InlineError,
  KpiCard,
  LoadingBlock,
  Mono,
  Pagination,
  Panel,
} from "@/components/ui/primitives";
import { api, qs } from "@/lib/api";
import { commodityLabel, dateTime, num, pct } from "@/lib/format";
import type { GoldenRecord } from "@/lib/types";

interface SafetyBlock {
  id: number;
  blocked_field: string;
  value_a: string;
  value_b: string;
  score: number;
  commodity_type: string | null;
  description_a: string;
  cpse_a: string;
  code_a: string;
  description_b: string;
  cpse_b: string;
  code_b: string;
}

interface HarmonizeStats {
  records: number;
  candidate_pairs: number;
  edges: number;
  components: number;
  golden_records: number;
  clusters_split: number;
  blocked_pairs: number;
  threshold: number;
  enforce_safety: boolean;
  status_counts: Record<string, number>;
}

const LIMIT = 20;

export default function HarmonizationPage() {
  const [enforceSafety, setEnforceSafety] = useState(true);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<{
    job_id: string;
    duration_seconds: number;
    stats: HarmonizeStats;
  } | null>(null);

  const [blocks, setBlocks] = useState<SafetyBlock[]>([]);
  const [records, setRecords] = useState<GoldenRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [gr, sb] = await Promise.all([
        api.get<{ items: GoldenRecord[]; total: number }>(
          `/golden-records${qs({ limit: LIMIT, offset })}`
        ),
        api.get<{ items: SafetyBlock[] }>("/safety-blocks?limit=25"),
      ]);
      setRecords(gr.items);
      setTotal(gr.total);
      setBlocks(sb.items);
    } catch (e: any) {
      setError(e?.detail ?? "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    load();
  }, [load]);

  const run = useCallback(
    async (safety: boolean) => {
      setRunning(true);
      setRunError(null);
      try {
        const result = await api.post<{
          job_id: string;
          duration_seconds: number;
          stats: HarmonizeStats;
        }>("/harmonize", { enforce_safety: safety });
        setLastRun(result);
        setOffset(0);
        await load();
      } catch (e: any) {
        setRunError(e?.detail ?? "The pipeline run failed.");
      } finally {
        setRunning(false);
      }
    },
    [load]
  );

  const toggleSafety = useCallback(
    async (next: boolean) => {
      setEnforceSafety(next);
      await run(next);
    },
    [run]
  );

  const stats = lastRun?.stats;

  return (
    <AppShell crumbs={[{ label: "Overview", href: "/" }, { label: "Harmonization" }]}>
      <PageHeading
        title="Harmonization"
        description="Run the matching pipeline and inspect the identities it produced."
        actions={
          <button
            type="button"
            className="btn-primary"
            onClick={() => run(enforceSafety)}
            disabled={running}
          >
            <Play className="h-3.5 w-3.5" aria-hidden />
            {running ? "Running…" : "Run pipeline"}
          </button>
        }
      />

      <div className="space-y-4">
        <Panel
          title="Safety Constraints"
          description="Turning enforcement off re-runs the entire pipeline. The results below are recomputed, not pre-recorded."
          bodyClassName="px-4 py-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div
              className={clsx(
                "flex items-start gap-2.5 rounded border px-3 py-2.5 flex-1 min-w-[20rem]",
                enforceSafety
                  ? "bg-state-okBg border-state-ok/25 text-state-ok"
                  : "bg-state-dangerBg border-state-danger/25 text-state-danger"
              )}
            >
              {enforceSafety ? (
                <ShieldCheck className="h-4 w-4 mt-px shrink-0" aria-hidden />
              ) : (
                <ShieldAlert className="h-4 w-4 mt-px shrink-0" aria-hidden />
              )}
              <div>
                <p className="text-xs font-semibold">
                  {enforceSafety
                    ? "Safety constraints enforced"
                    : "Safety constraints DISABLED — demonstration only"}
                </p>
                <p className="text-xs mt-0.5 opacity-90 leading-snug">
                  {enforceSafety
                    ? "A confirmed difference in a safety-critical attribute prevents two codes from sharing an NMI."
                    : "Records are merged on similarity alone. Materials that differ in pressure class, grade, bore or voltage will be incorrectly combined."}
                </p>
              </div>
            </div>

            <label className="flex items-center gap-2.5 cursor-pointer select-none shrink-0">
              <span className="text-sm text-ink">Enforce safety constraints</span>
              <button
                type="button"
                role="switch"
                aria-checked={enforceSafety}
                disabled={running}
                onClick={() => toggleSafety(!enforceSafety)}
                className={clsx(
                  "relative h-5 w-9 rounded-full transition-colors disabled:opacity-50",
                  enforceSafety ? "bg-state-ok" : "bg-line-strong"
                )}
              >
                <span
                  className={clsx(
                    "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform shadow-sm",
                    enforceSafety ? "translate-x-4.5 left-0.5" : "left-0.5"
                  )}
                  style={{ transform: enforceSafety ? "translateX(1rem)" : "translateX(0)" }}
                />
              </button>
            </label>
          </div>

          {runError && (
            <div className="mt-3">
              <InlineError message={runError} />
            </div>
          )}

          {running && <LoadingBlock label="Re-running the full pipeline" />}

          {stats && !running && (
            <div className="mt-3 grid grid-cols-2 lg:grid-cols-5 gap-3">
              <KpiCard label="Golden Records" value={num(stats.golden_records)} />
              <KpiCard label="Graph Edges" value={num(stats.edges)} hint="Pairs linked" />
              <KpiCard
                label="Clusters Split"
                value={num(stats.clusters_split)}
                hint="Contradictory values"
                tone={stats.clusters_split > 0 ? "warn" : "default"}
              />
              <KpiCard
                label="Blocked Pairs"
                value={num(stats.blocked_pairs)}
                tone={stats.blocked_pairs > 0 ? "danger" : "default"}
                hint={stats.enforce_safety ? "Refused by safety" : "Safety was off"}
              />
              <KpiCard
                label="Candidate Pairs"
                value={num(stats.candidate_pairs)}
                hint={`from ${num(stats.records)} records`}
              />
            </div>
          )}

          {lastRun && !running && (
            <p className="text-xs text-ink-subtle mt-3">
              Job <Mono>{lastRun.job_id}</Mono> finished in {lastRun.duration_seconds}s ·
              merge threshold {pct(stats?.threshold, 0)} · safety{" "}
              {stats?.enforce_safety ? "enforced" : "disabled"}
            </p>
          )}
        </Panel>

        <Panel
          title="Blocked Matches"
          description="Pairs the scorer rated highly but the safety layer refused. This is what the toggle above is preventing."
        >
          {loading && <LoadingBlock />}
          {error && !loading && <ErrorState message={error} onRetry={load} />}
          {!loading && !error && blocks.length === 0 && (
            <EmptyState
              title="No blocked pairs"
              description={
                enforceSafety
                  ? "No high-scoring pair currently conflicts on a safety-critical attribute."
                  : "Safety enforcement is off, so nothing was blocked in the last run."
              }
            />
          )}
          {!loading && !error && blocks.length > 0 && (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Record A</th>
                    <th>Record B</th>
                    <th>Blocking Attribute</th>
                    <th>Conflict</th>
                    <th className="w-36">Similarity</th>
                  </tr>
                </thead>
                <tbody>
                  {blocks.map((b) => (
                    <tr key={b.id}>
                      <td className="max-w-xs">
                        <p className="line-clamp-2">{b.description_a}</p>
                        <p className="text-2xs text-ink-subtle mt-0.5">
                          {b.cpse_a} · {b.code_a}
                        </p>
                      </td>
                      <td className="max-w-xs">
                        <p className="line-clamp-2">{b.description_b}</p>
                        <p className="text-2xs text-ink-subtle mt-0.5">
                          {b.cpse_b} · {b.code_b}
                        </p>
                      </td>
                      <td>
                        <span className="badge bg-state-dangerBg text-state-danger border-state-danger/25">
                          {b.blocked_field.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="text-xs">
                        <span className="text-ink">{b.value_a}</span>
                        <span className="text-ink-faint"> vs </span>
                        <span className="text-ink">{b.value_b}</span>
                      </td>
                      <td><ConfidenceBar value={b.score} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel
          title="Golden Records"
          description="One neutral identity per validated cluster of legacy codes."
        >
          {loading && <LoadingBlock />}
          {!loading && !error && records.length === 0 && (
            <EmptyState title="No golden records yet" description="Run the pipeline to generate them." />
          )}
          {!loading && !error && records.length > 0 && (
            <>
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>NMI</th>
                      <th>Standardized Description</th>
                      <th>Commodity</th>
                      <th className="text-right">Legacy Codes</th>
                      <th className="text-right">CPSEs</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {records.map((g) => (
                      <tr key={g.nmi}>
                        <td>
                          <Link href={`/crosswalk/${g.nmi}`} className="text-accent-500 hover:underline">
                            <Mono>{g.nmi}</Mono>
                          </Link>
                        </td>
                        <td className="max-w-lg">{g.standardized_description}</td>
                        <td className="text-ink-muted whitespace-nowrap">
                          {commodityLabel(g.commodity_type)}
                        </td>
                        <td className="text-right tnum">{num(g.member_count)}</td>
                        <td className="text-right tnum">{num(g.cpse_count ?? 0)}</td>
                        <td className="text-xs text-ink-subtle whitespace-nowrap">
                          {dateTime(g.created_at)}
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
      </div>
    </AppShell>
  );
}
