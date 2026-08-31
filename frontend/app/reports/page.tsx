"use client";

import { BarChart3 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART_COLORS, ChartFrame } from "@/components/ChartFrame";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeading } from "@/components/shell/Header";
import {
  EmptyState,
  ErrorState,
  KpiCard,
  LoadingBlock,
  Mono,
  Panel,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { commodityLabel, inr, num, pct } from "@/lib/format";

interface SummaryData {
  duplicate_materials: {
    nmi: string;
    standardized_description: string;
    commodity_type: string;
    member_count: number;
    cpse_count: number;
    cpses: string[];
  }[];
  confidence_distribution: { band: string; n: number }[];
  commodity_distribution: {
    commodity_type: string;
    materials: number;
    golden_records: number;
    codes_consolidated: number;
  }[];
  cpse_overlap: { cpse_a: string; cpse_b: string; shared_materials: number }[];
}

interface Metrics {
  records: number;
  overall: { precision: number; recall: number; f1: number; true_positives: number; false_positives: number; false_negatives: number };
  hard_negative_slice: { precision: number; recall: number; f1: number };
  per_commodity: Record<string, { precision: number; recall: number; f1: number }>;
  candidate_recall: { k: number; pairs: number; retrieved: number; recall_at_k: number };
  unsafe_merges: number;
  definitions: Record<string, string>;
}

interface Surplus {
  disclaimer: string;
  items: {
    nmi: string;
    standardized_description: string;
    commodity_type: string;
    cpse_count: number;
    total_quantity: number;
    uom: string;
    unit_value_inr: number;
    holdings: { cpse_org: string; quantity: number; legacy_code: string }[];
  }[];
}

export default function ReportsPage() {
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [surplus, setSurplus] = useState<Surplus | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, sp] = await Promise.all([
        api.get<SummaryData>("/reports/summary"),
        api.get<Surplus>("/reports/surplus?limit=10"),
      ]);
      setSummary(s);
      setSurplus(sp);
    } catch (e: any) {
      setError(e?.detail ?? "Unexpected error");
    } finally {
      setLoading(false);
    }

    try {
      const latest = await api.get<{ metrics: Metrics }>("/evaluate/latest");
      setMetrics(latest.metrics);
    } catch {
      setMetrics(null);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runEvaluation = useCallback(async () => {
    setEvaluating(true);
    try {
      setMetrics(await api.post<Metrics>("/evaluate"));
    } catch (e: any) {
      setError(e?.detail ?? "Evaluation failed.");
    } finally {
      setEvaluating(false);
    }
  }, []);

  return (
    <AppShell crumbs={[{ label: "Overview", href: "/" }, { label: "Reports" }]}>
      <PageHeading
        title="Reports"
        description="Harmonization outcomes, matching quality and cross-CPSE overlap."
        actions={
          <button type="button" className="btn-primary" onClick={runEvaluation} disabled={evaluating}>
            <BarChart3 className="h-3.5 w-3.5" aria-hidden />
            {evaluating ? "Evaluating…" : "Run evaluation"}
          </button>
        }
      />

      {loading && <LoadingBlock label="Loading reports" />}
      {error && !loading && <ErrorState message={error} onRetry={load} />}

      {summary && !loading && !error && (
        <div className="space-y-4">
          {metrics && (
            <Panel
              title="Matching Quality"
              description="Measured against a hidden ground truth the pipeline never sees. A pair is two source records of the same commodity; a positive means they derive from the same canonical material."
              bodyClassName="px-4 py-3 space-y-3"
            >
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                <KpiCard label="Precision" value={pct(metrics.overall.precision, 1)} />
                <KpiCard label="Recall" value={pct(metrics.overall.recall, 1)} />
                <KpiCard label="F1" value={pct(metrics.overall.f1, 1)} />
                <KpiCard
                  label={`Candidate Recall@${metrics.candidate_recall.k}`}
                  value={pct(metrics.candidate_recall.recall_at_k, 1)}
                  hint="Ceiling imposed by retrieval"
                />
                <KpiCard
                  label="Unsafe Merges"
                  value={num(metrics.unsafe_merges)}
                  tone={metrics.unsafe_merges > 0 ? "danger" : "ok"}
                  hint="Hard negatives wrongly combined"
                />
              </div>

              <div className="grid lg:grid-cols-2 gap-3">
                <div className="border border-line rounded overflow-hidden">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Slice</th>
                        <th className="text-right">Precision</th>
                        <th className="text-right">Recall</th>
                        <th className="text-right">F1</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td className="font-medium">All pairs</td>
                        <td className="text-right tnum">{pct(metrics.overall.precision, 1)}</td>
                        <td className="text-right tnum">{pct(metrics.overall.recall, 1)}</td>
                        <td className="text-right tnum">{pct(metrics.overall.f1, 1)}</td>
                      </tr>
                      <tr>
                        <td className="font-medium">
                          Hard negatives
                          <span className="block text-2xs font-normal text-ink-subtle">
                            deliberately confusable materials
                          </span>
                        </td>
                        <td className="text-right tnum">{pct(metrics.hard_negative_slice.precision, 1)}</td>
                        <td className="text-right tnum">{pct(metrics.hard_negative_slice.recall, 1)}</td>
                        <td className="text-right tnum">{pct(metrics.hard_negative_slice.f1, 1)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div className="border border-line rounded overflow-hidden">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Commodity</th>
                        <th className="text-right">Precision</th>
                        <th className="text-right">Recall</th>
                        <th className="text-right">F1</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(metrics.per_commodity).map(([c, m]) => (
                        <tr key={c}>
                          <td>{commodityLabel(c)}</td>
                          <td className="text-right tnum">{pct(m.precision, 1)}</td>
                          <td className="text-right tnum">{pct(m.recall, 1)}</td>
                          <td className="text-right tnum">{pct(m.f1, 1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <p className="text-2xs text-ink-subtle">
                TP {num(metrics.overall.true_positives)} · FP {num(metrics.overall.false_positives)} ·
                FN {num(metrics.overall.false_negatives)} over {num(metrics.records)} labelled records.
              </p>
            </Panel>
          )}

          {!metrics && (
            <Panel title="Matching Quality">
              <EmptyState
                title="No evaluation run yet"
                description="Run an evaluation to score the pipeline against the hidden synthetic ground truth."
                action={
                  <button type="button" className="btn-primary" onClick={runEvaluation} disabled={evaluating}>
                    Run evaluation
                  </button>
                }
              />
            </Panel>
          )}

          <div className="grid lg:grid-cols-2 gap-4">
            <Panel title="Commodity Distribution" bodyClassName="px-4 py-3">
              <ChartFrame height={240}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={summary.commodity_distribution.map((c) => ({
                      name: commodityLabel(c.commodity_type),
                      Materials: c.materials,
                      "Golden Records": c.golden_records,
                    }))}
                    margin={{ top: 4, right: 8, left: -18, bottom: 0 }}
                    barGap={2}
                  >
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" tickLine={false} axisLine={false} />
                    <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
                    <Tooltip cursor={{ fill: "#eef1f5" }} />
                    <Bar dataKey="Materials" fill={CHART_COLORS[0]} radius={[2, 2, 0, 0]} />
                    <Bar dataKey="Golden Records" fill={CHART_COLORS[2]} radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>

            <Panel title="Confidence Distribution" bodyClassName="px-4 py-3">
              {summary.confidence_distribution.length === 0 ? (
                <EmptyState title="No crosswalk links yet" />
              ) : (
                <ChartFrame height={240}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={summary.confidence_distribution.map((c) => ({
                          name: c.band,
                          value: c.n,
                        }))}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={45}
                        outerRadius={80}
                        paddingAngle={1}
                        label={(e: any) => e.name}
                        labelLine={false}
                      >
                        {summary.confidence_distribution.map((_, i) => (
                          <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </ChartFrame>
              )}
            </Panel>
          </div>

          <Panel
            title="Duplicate Materials Across CPSEs"
            description="Identities where more than one enterprise holds its own code for the same material."
          >
            {summary.duplicate_materials.length === 0 ? (
              <EmptyState title="No cross-CPSE duplicates found" />
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>NMI</th>
                      <th>Standardized Description</th>
                      <th>Commodity</th>
                      <th className="text-right">Legacy Codes</th>
                      <th className="text-right">CPSEs</th>
                      <th>Held by</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.duplicate_materials.map((d) => (
                      <tr key={d.nmi}>
                        <td>
                          <Link href={`/crosswalk/${d.nmi}`} className="text-accent-500 hover:underline">
                            <Mono>{d.nmi}</Mono>
                          </Link>
                        </td>
                        <td className="max-w-md">{d.standardized_description}</td>
                        <td className="text-ink-muted whitespace-nowrap">
                          {commodityLabel(d.commodity_type)}
                        </td>
                        <td className="text-right tnum">{num(d.member_count)}</td>
                        <td className="text-right tnum">{num(d.cpse_count)}</td>
                        <td className="text-xs text-ink-muted">{d.cpses.join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel
            title="CPSE Overlap"
            description="Number of shared material identities between each pair of enterprises."
          >
            {summary.cpse_overlap.length === 0 ? (
              <EmptyState title="No overlap detected" />
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>CPSE A</th>
                      <th>CPSE B</th>
                      <th className="text-right">Shared Identities</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.cpse_overlap.map((o) => (
                      <tr key={`${o.cpse_a}-${o.cpse_b}`}>
                        <td>{o.cpse_a}</td>
                        <td>{o.cpse_b}</td>
                        <td className="text-right tnum">{num(o.shared_materials)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          {surplus && surplus.items.length > 0 && (
            <Panel
              title="Cross-CPSE Surplus Opportunities"
              description={surplus.disclaimer}
            >
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>NMI</th>
                      <th>Material</th>
                      <th className="text-right">CPSEs</th>
                      <th className="text-right">Total Quantity</th>
                      <th className="text-right">Indicative Value</th>
                      <th>Holdings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {surplus.items.map((s) => (
                      <tr key={s.nmi}>
                        <td>
                          <Link href={`/crosswalk/${s.nmi}`} className="text-accent-500 hover:underline">
                            <Mono>{s.nmi}</Mono>
                          </Link>
                        </td>
                        <td className="max-w-sm">{s.standardized_description}</td>
                        <td className="text-right tnum">{num(s.cpse_count)}</td>
                        <td className="text-right tnum">
                          {num(s.total_quantity)} {s.uom}
                        </td>
                        <td className="text-right tnum">
                          {inr(s.total_quantity * s.unit_value_inr)}
                        </td>
                        <td className="text-xs text-ink-muted">
                          {s.holdings
                            .map((h) => `${h.cpse_org} ${num(h.quantity)}`)
                            .join(" · ")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
        </div>
      )}
    </AppShell>
  );
}
