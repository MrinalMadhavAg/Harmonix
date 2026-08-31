"use client";

import { Download, Upload } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageHeading } from "@/components/shell/Header";
import {
  ConfidenceBar,
  EmptyState,
  ErrorState,
  LoadingBlock,
  Mono,
  Pagination,
  Panel,
  ReviewBadge,
} from "@/components/ui/primitives";
import { api, qs } from "@/lib/api";
import { commodityLabel, dateTime } from "@/lib/format";
import type { Material, ReviewStatus } from "@/lib/types";

const STATUSES: ReviewStatus[] = [
  "AUTO_MATCHED",
  "NEEDS_REVIEW",
  "INSUFFICIENT_EVIDENCE",
  "BLOCKED",
  "APPROVED",
  "REJECTED",
];

const COMMODITIES = ["gate_valve", "pipe", "bearing", "electrical_cable", "fastener"];

const SORTABLE: { key: string; label: string; className?: string }[] = [
  { key: "code", label: "Material Code" },
  { key: "description", label: "Description" },
  { key: "cpse", label: "CPSE" },
  { key: "commodity", label: "Commodity" },
  { key: "nmi", label: "Standardized NMI" },
  { key: "confidence", label: "Confidence", className: "w-40" },
  { key: "status", label: "Status" },
  { key: "updated", label: "Last Updated" },
];

const LIMIT = 25;

function MaterialsInner() {
  const params = useSearchParams();

  const [search, setSearch] = useState(params?.get("search") ?? "");
  const [debounced, setDebounced] = useState(search);
  const [cpse, setCpse] = useState(params?.get("cpse") ?? "");
  const [commodity, setCommodity] = useState(params?.get("commodity") ?? "");
  const [status, setStatus] = useState(params?.get("status") ?? "");
  const [minConfidence, setMinConfidence] = useState("");
  const [sort, setSort] = useState("id");
  const [direction, setDirection] = useState<"asc" | "desc">("asc");
  const [offset, setOffset] = useState(0);

  const [rows, setRows] = useState<Material[]>([]);
  const [total, setTotal] = useState(0);
  const [cpses, setCpses] = useState<string[]>([]);
  const [threshold, setThreshold] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    setOffset(0);
  }, [debounced, cpse, commodity, status, minConfidence, sort, direction]);

  useEffect(() => {
    api
      .get<{ items: { cpse_org: string }[] }>("/cpses")
      .then((d) => setCpses(d.items.map((i) => i.cpse_org)))
      .catch(() => setCpses([]));
    // The merge threshold is a backend setting; read it rather than
    // duplicating the number here where it would drift.
    api
      .get<{ match_threshold: number }>("/config/settings")
      .then((s) => setThreshold(s.match_threshold))
      .catch(() => setThreshold(null));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<{ items: Material[]; total: number }>(
        `/materials${qs({
          search: debounced,
          cpse,
          commodity,
          status,
          min_confidence: minConfidence,
          sort,
          direction,
          limit: LIMIT,
          offset,
        })}`
      );
      setRows(data.items);
      setTotal(data.total);
    } catch (e: any) {
      setError(e?.detail ?? "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, [debounced, cpse, commodity, status, minConfidence, sort, direction, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleSort = (key: string) => {
    if (sort === key) setDirection(direction === "asc" ? "desc" : "asc");
    else {
      setSort(key);
      setDirection("asc");
    }
  };

  const exportCsv = useCallback(() => {
    const header = [
      "cpse_org", "legacy_code", "raw_description", "commodity_type",
      "nmi", "match_score", "status",
    ];
    const escape = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const csv = [
      header.join(","),
      ...rows.map((r) =>
        [
          r.cpse_org, r.legacy_code, r.raw_description, r.commodity_type ?? "",
          r.nmi ?? "", r.match_score ?? "", r.review_status ?? "",
        ]
          .map(escape)
          .join(",")
      ),
    ].join("\n");

    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `harmonix-materials-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [rows]);

  const filtersActive = useMemo(
    () => Boolean(debounced || cpse || commodity || status || minConfidence),
    [debounced, cpse, commodity, status, minConfidence]
  );

  return (
    <AppShell crumbs={[{ label: "Overview", href: "/" }, { label: "Materials" }]}>
      <PageHeading
        title="Materials"
        description="Search and manage material records across CPSE sources."
        actions={
          <>
            <Link href="/data-sources" className="btn-secondary">
              <Upload className="h-3.5 w-3.5" aria-hidden />
              Import
            </Link>
            <button
              type="button"
              className="btn-secondary"
              onClick={exportCsv}
              disabled={rows.length === 0}
              title={rows.length === 0 ? "Nothing to export" : "Export the current page as CSV"}
            >
              <Download className="h-3.5 w-3.5" aria-hidden />
              Export
            </button>
          </>
        }
      />

      <Panel>
        <div className="grid gap-3 px-4 py-3 border-b border-line sm:grid-cols-2 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <label className="field-label" htmlFor="m-search">Search</label>
            <input
              id="m-search"
              className="input"
              placeholder="Description, legacy code or NMI"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div>
            <label className="field-label" htmlFor="m-cpse">CPSE</label>
            <select id="m-cpse" className="input" value={cpse} onChange={(e) => setCpse(e.target.value)}>
              <option value="">All CPSEs</option>
              {cpses.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="m-commodity">Commodity</label>
            <select
              id="m-commodity"
              className="input"
              value={commodity}
              onChange={(e) => setCommodity(e.target.value)}
            >
              <option value="">All commodities</option>
              {COMMODITIES.map((c) => (
                <option key={c} value={c}>{commodityLabel(c)}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="m-status">Status</label>
            <select id="m-status" className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, " ").toLowerCase().replace(/^./, (m) => m.toUpperCase())}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="m-conf">Minimum confidence</label>
            <select
              id="m-conf"
              className="input"
              value={minConfidence}
              onChange={(e) => setMinConfidence(e.target.value)}
            >
              <option value="">Any</option>
              <option value="0.9">90% and above</option>
              <option value="0.8">80% and above</option>
              {threshold !== null && (
                <option value={String(threshold)}>
                  {(threshold * 100).toFixed(0)}% (merge threshold)
                </option>
              )}
              <option value="0.5">50% and above</option>
            </select>
          </div>
          {filtersActive && (
            <div className="flex items-end">
              <button
                type="button"
                className="btn-ghost text-xs"
                onClick={() => {
                  setSearch("");
                  setCpse("");
                  setCommodity("");
                  setStatus("");
                  setMinConfidence("");
                }}
              >
                Clear filters
              </button>
            </div>
          )}
        </div>

        {loading && <LoadingBlock label="Loading materials" />}
        {error && !loading && <ErrorState message={error} onRetry={load} />}
        {!loading && !error && rows.length === 0 && (
          <EmptyState
            title={filtersActive ? "No materials match these filters" : "No materials ingested yet"}
            description={
              filtersActive
                ? "Try widening the search, or clear the filters to see all records."
                : "Upload a CPSE material export from Data Sources to get started."
            }
            action={
              filtersActive ? undefined : (
                <Link href="/data-sources" className="btn-primary">Go to Data Sources</Link>
              )
            }
          />
        )}

        {!loading && !error && rows.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    {SORTABLE.map((col) => (
                      <th key={col.key} className={col.className}>
                        <button
                          type="button"
                          onClick={() => toggleSort(col.key)}
                          className="inline-flex items-center gap-1 hover:text-ink"
                        >
                          {col.label}
                          {sort === col.key && (
                            <span aria-hidden className="text-accent-500">
                              {direction === "asc" ? "▲" : "▼"}
                            </span>
                          )}
                        </button>
                      </th>
                    ))}
                    <th className="w-20 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td className="whitespace-nowrap"><Mono>{r.legacy_code}</Mono></td>
                      <td className="max-w-sm">
                        <Link href={`/materials/${r.id}`} className="text-accent-500 hover:underline line-clamp-2">
                          {r.raw_description}
                        </Link>
                      </td>
                      <td className="whitespace-nowrap">{r.cpse_org}</td>
                      <td className="whitespace-nowrap text-ink-muted">
                        {commodityLabel(r.commodity_type)}
                      </td>
                      <td className="whitespace-nowrap">
                        {r.nmi ? (
                          <Link href={`/crosswalk/${r.nmi}`} className="text-accent-500 hover:underline">
                            <Mono>{r.nmi}</Mono>
                          </Link>
                        ) : (
                          <span className="text-ink-faint">Not assigned</span>
                        )}
                      </td>
                      <td><ConfidenceBar value={r.match_score} /></td>
                      <td><ReviewBadge status={r.review_status} /></td>
                      <td className="text-xs text-ink-subtle whitespace-nowrap">
                        {dateTime(r.created_at)}
                      </td>
                      <td className="text-right">
                        <Link href={`/materials/${r.id}`} className="btn-ghost h-6 px-2 text-xs">
                          Open
                        </Link>
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
    </AppShell>
  );
}

export default function MaterialsPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <MaterialsInner />
    </Suspense>
  );
}
