"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

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
import { api, qs } from "@/lib/api";
import { commodityLabel, num, pct } from "@/lib/format";
import type { Material } from "@/lib/types";

interface CpseDetail {
  summary: {
    cpse_org: string;
    materials: number;
    harmonized: number;
    pending: number;
    blocked: number;
    avg_confidence: number | null;
  };
  shared_materials: {
    nmi: string;
    standardized_description: string;
    other_cpse_count: number;
    other_cpses: string[];
  }[];
}

export default function CpseDetailPage() {
  const params = useParams();
  const cpse = String(Array.isArray(params?.cpse) ? params.cpse[0] : params?.cpse ?? "");

  const [detail, setDetail] = useState<CpseDetail | null>(null);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, m] = await Promise.all([
        api.get<CpseDetail>(`/cpses/${encodeURIComponent(cpse)}`),
        api.get<{ items: Material[] }>(`/materials${qs({ cpse, limit: 25 })}`),
      ]);
      setDetail(d);
      setMaterials(m.items);
    } catch (e: any) {
      setError(e?.detail ?? "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, [cpse]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <AppShell
      crumbs={[
        { label: "Overview", href: "/" },
        { label: "CPSEs", href: "/cpses" },
        { label: cpse },
      ]}
    >
      {loading && <LoadingBlock label="Loading CPSE" />}
      {error && !loading && <ErrorState message={error} onRetry={load} />}

      {detail && !loading && !error && (
        <div className="space-y-4">
          <PageHeading
            title={detail.summary.cpse_org}
            description="Material inventory and cross-CPSE overlap for this enterprise."
          />

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <KpiCard label="Materials" value={num(detail.summary.materials)} />
            <KpiCard label="Harmonized" value={num(detail.summary.harmonized)} />
            <KpiCard
              label="Pending Review"
              value={num(detail.summary.pending)}
              tone={detail.summary.pending > 0 ? "warn" : "default"}
            />
            <KpiCard
              label="Blocked"
              value={num(detail.summary.blocked)}
              tone={detail.summary.blocked > 0 ? "danger" : "default"}
            />
          </div>

          <Panel
            title="Materials Also Held by Other CPSEs"
            description="Identities where this CPSE's code shares an NMI with at least one other enterprise."
          >
            {detail.shared_materials.length === 0 ? (
              <EmptyState title="No shared identities" />
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>NMI</th>
                      <th>Standardized Description</th>
                      <th className="text-right">Other CPSEs</th>
                      <th>Also held by</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.shared_materials.map((s) => (
                      <tr key={s.nmi}>
                        <td>
                          <Link href={`/crosswalk/${s.nmi}`} className="text-accent-500 hover:underline">
                            <Mono>{s.nmi}</Mono>
                          </Link>
                        </td>
                        <td className="max-w-lg">{s.standardized_description}</td>
                        <td className="text-right tnum">{s.other_cpse_count}</td>
                        <td className="text-xs text-ink-muted">{s.other_cpses.join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel
            title="Material Inventory"
            actions={
              <Link
                href={`/materials?cpse=${encodeURIComponent(cpse)}`}
                className="btn-secondary h-7 px-2.5 text-xs"
              >
                Open in Materials
              </Link>
            }
          >
            {materials.length === 0 ? (
              <EmptyState title="No materials for this CPSE" />
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Material Code</th>
                      <th>Description</th>
                      <th>Commodity</th>
                      <th>NMI</th>
                      <th className="w-36">Confidence</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {materials.map((m) => (
                      <tr key={m.id}>
                        <td><Mono>{m.legacy_code}</Mono></td>
                        <td className="max-w-sm">
                          <Link href={`/materials/${m.id}`} className="text-accent-500 hover:underline line-clamp-2">
                            {m.raw_description}
                          </Link>
                        </td>
                        <td className="text-ink-muted whitespace-nowrap">
                          {commodityLabel(m.commodity_type)}
                        </td>
                        <td>
                          {m.nmi ? (
                            <Link href={`/crosswalk/${m.nmi}`} className="text-accent-500 hover:underline">
                              <Mono>{m.nmi}</Mono>
                            </Link>
                          ) : (
                            <span className="text-ink-faint">—</span>
                          )}
                        </td>
                        <td><ConfidenceBar value={m.match_score} /></td>
                        <td><ReviewBadge status={m.review_status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>
      )}
    </AppShell>
  );
}
