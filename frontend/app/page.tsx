"use client";

import { AlertOctagon, CheckCircle2, Layers, Package } from "lucide-react";
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
  ConfidenceBar,
  EmptyState,
  ErrorState,
  KpiCard,
  LoadingBlock,
  Mono,
  Panel,
  ReviewBadge,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { REVIEW_LABEL, commodityLabel, dateTime, num, pct } from "@/lib/format";
import type { DashboardData } from "@/lib/types";

export default function OverviewPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.get<DashboardData>("/dashboard"));
    } catch (e: any) {
      setError(e?.detail ?? "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <AppShell crumbs={[{ label: "Overview" }]}>
      <PageHeading
        title="Material Harmonization"
        description="Standardize and reconcile material identities across CPSE sources."
      />

      {loading && <LoadingBlock label="Loading overview" />}
      {error && !loading && <ErrorState message={error} onRetry={load} />}

      {data && !loading && !error && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <KpiCard
              label="Total Materials"
              value={num(data.totals.total_materials)}
              hint={`${data.cpse_overview.length} contributing CPSEs`}
              icon={<Package className="h-4 w-4" />}
            />
            <KpiCard
              label="Golden Records"
              value={num(data.totals.golden_records)}
              hint={`${num(data.totals.duplicates_removed)} duplicate codes consolidated`}
              icon={<Layers className="h-4 w-4" />}
            />
            <KpiCard
              label="Pending Review"
              value={num(data.totals.pending_review)}
              tone={data.totals.pending_review > 0 ? "warn" : "default"}
              hint="Awaiting steward confirmation"
              icon={<CheckCircle2 className="h-4 w-4" />}
            />
            <KpiCard
              label="Blocked Matches"
              value={num(data.totals.blocked_matches)}
              tone={data.totals.blocked_matches > 0 ? "danger" : "default"}
              hint="Prevented by safety constraints"
              icon={<AlertOctagon className="h-4 w-4" />}
            />
          </div>

          <div className="grid lg:grid-cols-3 gap-4">
            <Panel
              title="Harmonization Activity"
              description="Source records and resulting golden records by commodity"
              className="lg:col-span-2"
              bodyClassName="px-4 py-3"
            >
              {data.commodity_breakdown.length === 0 ? (
                <EmptyState title="No materials ingested yet" />
              ) : (
                <ChartFrame height={240}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={data.commodity_breakdown.map((c) => ({
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
              )}
            </Panel>

            <Panel
              title="Status Breakdown"
              description="Harmonization outcome per source record"
              bodyClassName="px-4 py-3"
            >
              {data.status_breakdown.length === 0 ? (
                <EmptyState title="Nothing processed yet" />
              ) : (
                <>
                  <ChartFrame height={160}>
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={data.status_breakdown.map((s) => ({
                            name: REVIEW_LABEL[s.status as keyof typeof REVIEW_LABEL] ?? s.status,
                            value: s.n,
                          }))}
                          dataKey="value"
                          nameKey="name"
                          innerRadius={38}
                          outerRadius={62}
                          paddingAngle={1}
                        >
                          {data.status_breakdown.map((_, i) => (
                            <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </ChartFrame>
                  <ul className="mt-2 space-y-1">
                    {data.status_breakdown.map((s, i) => (
                      <li key={s.status} className="flex items-center gap-2 text-xs">
                        <span
                          className="h-2 w-2 rounded-sm shrink-0"
                          style={{ background: CHART_COLORS[i % CHART_COLORS.length] }}
                        />
                        <span className="flex-1 text-ink-muted truncate">
                          {REVIEW_LABEL[s.status as keyof typeof REVIEW_LABEL] ?? s.status}
                        </span>
                        <span className="tnum text-ink font-medium">{num(s.n)}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Panel>
          </div>

          <Panel
            title="Recent Harmonization Activity"
            actions={
              <Link href="/materials" className="btn-secondary h-7 px-2.5 text-xs">
                View all materials
              </Link>
            }
          >
            {data.recent_activity.length === 0 ? (
              <EmptyState title="No activity yet" />
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Material</th>
                      <th>CPSE</th>
                      <th>Original Code</th>
                      <th>Recommended NMI</th>
                      <th className="w-40">Confidence</th>
                      <th>Status</th>
                      <th>Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_activity.map((r) => (
                      <tr key={r.id}>
                        <td className="max-w-md">
                          <Link
                            href={`/materials/${r.id}`}
                            className="text-accent-500 hover:underline line-clamp-1"
                          >
                            {r.raw_description}
                          </Link>
                        </td>
                        <td className="whitespace-nowrap">{r.cpse_org}</td>
                        <td>
                          <Mono>{r.legacy_code}</Mono>
                        </td>
                        <td>
                          {r.nmi ? (
                            <Link href={`/crosswalk/${r.nmi}`} className="text-accent-500 hover:underline">
                              <Mono>{r.nmi}</Mono>
                            </Link>
                          ) : (
                            <span className="text-ink-faint">—</span>
                          )}
                        </td>
                        <td>
                          <ConfidenceBar value={r.match_score} />
                        </td>
                        <td>
                          <ReviewBadge status={r.status} />
                        </td>
                        <td className="text-xs text-ink-subtle whitespace-nowrap">
                          {dateTime(r.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel
            title="CPSE Overview"
            actions={
              <Link href="/cpses" className="btn-secondary h-7 px-2.5 text-xs">
                CPSE detail
              </Link>
            }
          >
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>CPSE</th>
                    <th className="text-right">Materials</th>
                    <th className="text-right">Harmonized</th>
                    <th className="text-right">Pending</th>
                    <th className="text-right">Blocked</th>
                    <th className="w-40">Match Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.cpse_overview.map((c) => (
                    <tr key={c.cpse_org}>
                      <td>
                        <Link href={`/cpses/${c.cpse_org}`} className="text-accent-500 hover:underline font-medium">
                          {c.cpse_org}
                        </Link>
                      </td>
                      <td className="text-right tnum">{num(c.materials)}</td>
                      <td className="text-right tnum">{num(c.harmonized)}</td>
                      <td className="text-right tnum">{num(c.pending)}</td>
                      <td className="text-right tnum">{num(c.blocked)}</td>
                      <td>
                        <ConfidenceBar value={c.materials ? c.harmonized / c.materials : 0} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {data.last_job && (
            <p className="text-xs text-ink-subtle">
              Last pipeline run <Mono>{data.last_job.job_id}</Mono> · {data.last_job.status} ·{" "}
              {dateTime(data.last_job.finished_at ?? data.last_job.started_at)}
              {typeof (data.last_job.stats as any)?.threshold === "number" && (
                <> · merge threshold {pct((data.last_job.stats as any).threshold, 0)}</>
              )}
            </p>
          )}
        </div>
      )}
    </AppShell>
  );
}
