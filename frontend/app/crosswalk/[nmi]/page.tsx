"use client";

import clsx from "clsx";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageHeading } from "@/components/shell/Header";
import {
  ConfidenceBar,
  DefinitionRow,
  EmptyState,
  ErrorState,
  LoadingBlock,
  Mono,
  Panel,
  ReviewBadge,
  StateBadge,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { STATE_STYLE, attrValue, commodityLabel, dateTime, num, pct } from "@/lib/format";
import type { CrosswalkMember, EvidenceMatrix, GoldenRecord } from "@/lib/types";

interface CrosswalkResponse {
  golden_record: GoldenRecord;
  members: CrosswalkMember[];
  audit: {
    id: number;
    changed_field: string;
    old_value: string | null;
    new_value: string | null;
    changed_by: string;
    reason: string | null;
    changed_at: string;
  }[];
  demo_inventory_by_cpse: {
    cpse_org: string;
    quantity: number;
    uom: string;
    unit_value_inr: number;
  }[];
  evidence_matrix: EvidenceMatrix | null;
}

export default function CrosswalkDetailPage() {
  const params = useParams();
  const nmi = String(Array.isArray(params?.nmi) ? params.nmi[0] : params?.nmi ?? "");

  const [data, setData] = useState<CrosswalkResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.get<CrosswalkResponse>(`/crosswalk/${encodeURIComponent(nmi)}`));
    } catch (e: any) {
      setError(e?.detail ?? "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, [nmi]);

  useEffect(() => {
    load();
  }, [load]);

  const gr = data?.golden_record;
  const matrix = data?.evidence_matrix;

  return (
    <AppShell
      crumbs={[
        { label: "Overview", href: "/" },
        { label: "Harmonization", href: "/harmonization" },
        { label: nmi },
      ]}
    >
      {loading && <LoadingBlock label="Loading crosswalk" />}
      {error && !loading && <ErrorState message={error} onRetry={load} />}

      {data && gr && !loading && !error && (
        <div className="space-y-4">
          {/* The central idea, stated visually: many legacy codes, one identity. */}
          <section className="panel p-5">
            <div className="flex flex-col lg:flex-row lg:items-center gap-5">
              <div className="flex-1 min-w-0">
                <p className="text-2xs font-medium uppercase tracking-wide text-ink-subtle mb-1.5">
                  {data.members.length} CPSE legacy code
                  {data.members.length === 1 ? "" : "s"}
                </p>
                <ul className="space-y-1">
                  {data.members.map((m) => (
                    <li key={m.crosswalk_id} className="flex items-center gap-2 text-sm">
                      <span className="badge bg-surface-muted text-ink-muted border-line-strong w-16 justify-center">
                        {m.cpse_org}
                      </span>
                      <Mono className="text-ink">{m.legacy_code}</Mono>
                    </li>
                  ))}
                </ul>
              </div>

              <ArrowRight className="hidden lg:block h-6 w-6 text-ink-faint shrink-0" aria-hidden />
              <div className="lg:hidden text-center text-ink-faint" aria-hidden>↓</div>

              <div className="flex-1 min-w-0 lg:border-l lg:border-line lg:pl-5">
                <p className="text-2xs font-medium uppercase tracking-wide text-ink-subtle mb-1.5">
                  National Material Identifier
                </p>
                <p className="text-2xl font-semibold tracking-tight text-accent-500 font-mono">
                  {gr.nmi}
                </p>
                <p className="text-sm text-ink mt-1.5">{gr.standardized_description}</p>
                <p className="text-xs text-ink-subtle mt-1">
                  {commodityLabel(gr.commodity_type)}
                  {gr.unspsc_class && <> · UNSPSC {gr.unspsc_class}</>} · version {gr.version}
                </p>
              </div>
            </div>
          </section>

          <PageHeading
            title="Crosswalk Detail"
            description="Each CPSE keeps its own code. The NMI is a neutral identity layer above them, not a replacement."
          />

          <Panel title="CPSE Legacy Codes">
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>CPSE</th>
                    <th>Legacy Code</th>
                    <th>Original Description</th>
                    <th className="w-40">Match Score</th>
                    <th>Relationship</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.members.map((m) => (
                    <tr key={m.crosswalk_id}>
                      <td className="whitespace-nowrap font-medium">{m.cpse_org}</td>
                      <td className="whitespace-nowrap"><Mono>{m.legacy_code}</Mono></td>
                      <td className="max-w-md">
                        <Link
                          href={`/materials/${m.record_id}`}
                          className="text-accent-500 hover:underline"
                        >
                          {m.raw_description}
                        </Link>
                      </td>
                      <td><ConfidenceBar value={m.match_score} /></td>
                      <td className="text-xs text-ink-muted whitespace-nowrap">{m.relationship}</td>
                      <td><ReviewBadge status={m.review_status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {matrix && matrix.rows.length > 0 && (
            <Panel
              title="Attribute Evidence"
              description="How each CPSE describes this material, and what the golden record concluded."
            >
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="sticky left-0 bg-surface-subtle z-10">Attribute</th>
                      {matrix.cpses.map((c) => (
                        <th key={c.record_id}>
                          {c.cpse_org}
                          <span className="block font-normal normal-case text-ink-faint">
                            {c.legacy_code}
                          </span>
                        </th>
                      ))}
                      <th className="bg-accent-50 text-accent-600">Golden Record</th>
                    </tr>
                  </thead>
                  <tbody>
                    {matrix.rows.map((row) => (
                      <tr key={row.key}>
                        <td className="sticky left-0 bg-surface z-10 whitespace-nowrap">
                          <span className="text-ink">{row.label}</span>
                          {row.safety_critical && (
                            <span className="ml-1.5 badge bg-accent-50 text-accent-600 border-accent-200">
                              Safety
                            </span>
                          )}
                        </td>
                        {row.cells.map((cell) => (
                          <td key={cell.record_id}>
                            <span
                              className={clsx(
                                "inline-block px-1.5 py-0.5 rounded border text-xs",
                                STATE_STYLE[cell.state],
                                cell.value === null && "italic"
                              )}
                            >
                              {attrValue(cell.value)}
                            </span>
                          </td>
                        ))}
                        <td className="bg-accent-50/40">
                          <p className="text-ink font-medium">{attrValue(row.golden.value)}</p>
                          {row.golden.agreement && (
                            <p className="text-2xs text-ink-subtle mt-0.5">
                              agreement {row.golden.agreement}
                              {row.golden.confidence !== null && (
                                <> · confidence {pct(row.golden.confidence, 0)}</>
                              )}
                            </p>
                          )}
                          {row.golden.contested_values?.length ? (
                            <p className="text-2xs text-state-warn mt-0.5">
                              outvoted: {row.golden.contested_values.join(", ")}
                            </p>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap items-center gap-3 px-4 py-2.5 border-t border-line">
                <span className="text-2xs uppercase tracking-wide text-ink-subtle">Legend</span>
                <StateBadge state="MATCH" />
                <span className="text-xs text-ink-subtle">agrees with the golden record</span>
                <StateBadge state="MISMATCH" />
                <span className="text-xs text-ink-subtle">differs from it</span>
                <StateBadge state="UNKNOWN" />
                <span className="text-xs text-ink-subtle">this CPSE did not state a value</span>
              </div>
            </Panel>
          )}

          <div className="grid lg:grid-cols-2 gap-4">
            <Panel title="Golden Record Attributes" bodyClassName="px-4 py-2">
              <dl>
                {Object.entries(gr.attributes || {}).map(([key, a]) => (
                  <DefinitionRow key={key} label={key.replace(/_/g, " ")}>
                    <span className="text-ink">{attrValue(a.value)}</span>
                    <span className="text-2xs text-ink-subtle ml-2">
                      {a.agreement && <>agreement {a.agreement} · </>}
                      confidence {pct(a.confidence, 0)}
                    </span>
                  </DefinitionRow>
                ))}
                {Object.keys(gr.attributes || {}).length === 0 && (
                  <p className="py-3 text-xs text-ink-subtle">No attributes survived.</p>
                )}
              </dl>
            </Panel>

            <div className="space-y-4">
              {data.demo_inventory_by_cpse.length > 0 && (
                <Panel
                  title="Holdings by CPSE"
                  description="Illustrative demo inventory — synthetic quantities, not real CPSE stock."
                >
                  <div className="overflow-x-auto">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>CPSE</th>
                          <th className="text-right">Quantity</th>
                          <th>UoM</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.demo_inventory_by_cpse.map((i) => (
                          <tr key={i.cpse_org}>
                            <td>{i.cpse_org}</td>
                            <td className="text-right tnum">{num(i.quantity)}</td>
                            <td className="text-ink-muted">{i.uom}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              )}

              <Panel title="Audit Trail">
                {data.audit.length === 0 ? (
                  <EmptyState
                    title="No manual changes"
                    description="This identity was produced by the pipeline and has not been altered by a steward."
                  />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Field</th>
                          <th>Change</th>
                          <th>By</th>
                          <th>When</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.audit.map((a) => (
                          <tr key={a.id}>
                            <td className="whitespace-nowrap">{a.changed_field}</td>
                            <td className="text-xs">
                              <span className="text-ink-subtle">{a.old_value ?? "—"}</span>
                              {" → "}
                              <span className="text-ink">{a.new_value ?? "—"}</span>
                              {a.reason && (
                                <p className="text-2xs text-ink-subtle mt-0.5">{a.reason}</p>
                              )}
                            </td>
                            <td className="text-xs whitespace-nowrap">{a.changed_by}</td>
                            <td className="text-xs text-ink-subtle whitespace-nowrap">
                              {dateTime(a.changed_at)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Panel>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
