"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageHeading } from "@/components/shell/Header";
import {
  ConfidenceBar,
  EmptyState,
  ErrorState,
  LoadingBlock,
  Panel,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { num } from "@/lib/format";

interface CpseRow {
  cpse_org: string;
  materials: number;
  harmonized: number;
  pending: number;
  blocked: number;
  distinct_nmis: number;
  avg_confidence: number | null;
}

export default function CpsesPage() {
  const [rows, setRows] = useState<CpseRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await api.get<{ items: CpseRow[] }>("/cpses");
      setRows(d.items);
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
    <AppShell crumbs={[{ label: "Overview", href: "/" }, { label: "CPSEs" }]}>
      <PageHeading
        title="CPSEs"
        description="Participating enterprises and how much of their material master has been harmonized."
      />

      <Panel>
        {loading && <LoadingBlock label="Loading CPSEs" />}
        {error && !loading && <ErrorState message={error} onRetry={load} />}
        {!loading && !error && rows.length === 0 && (
          <EmptyState title="No CPSE data" description="Ingest a material export to populate this view." />
        )}
        {!loading && !error && rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>CPSE</th>
                  <th className="text-right">Material Count</th>
                  <th className="text-right">Harmonized</th>
                  <th className="text-right">Pending Review</th>
                  <th className="text-right">Blocked</th>
                  <th className="text-right">Distinct NMIs</th>
                  <th className="w-40">Match Rate</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.cpse_org}>
                    <td>
                      <Link href={`/cpses/${r.cpse_org}`} className="text-accent-500 hover:underline font-medium">
                        {r.cpse_org}
                      </Link>
                    </td>
                    <td className="text-right tnum">{num(r.materials)}</td>
                    <td className="text-right tnum">{num(r.harmonized)}</td>
                    <td className="text-right tnum">{num(r.pending)}</td>
                    <td className="text-right tnum">{num(r.blocked)}</td>
                    <td className="text-right tnum">{num(r.distinct_nmis)}</td>
                    <td>
                      <ConfidenceBar value={r.materials ? r.harmonized / r.materials : 0} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </AppShell>
  );
}
