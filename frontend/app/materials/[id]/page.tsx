"use client";

import clsx from "clsx";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { MatchExplanation } from "@/components/MatchExplanation";
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
  SafetyBadge,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { attrValue, commodityLabel, dateTime, num, pct } from "@/lib/format";
import type { Candidate, Material } from "@/lib/types";

export default function MaterialDetailPage() {
  const params = useParams();
  const id = Number(Array.isArray(params?.id) ? params.id[0] : params?.id);

  const [material, setMaterial] = useState<Material | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [threshold, setThreshold] = useState(0.62);
  const [selected, setSelected] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [candidatesLoading, setCandidatesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!Number.isFinite(id)) {
      setError("Invalid material id.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setMaterial(await api.get<Material>(`/materials/${id}`));
    } catch (e: any) {
      setError(e?.detail ?? "Unexpected error");
    } finally {
      setLoading(false);
    }

    setCandidatesLoading(true);
    try {
      const data = await api.get<{ candidates: Candidate[]; threshold: number }>(
        `/materials/${id}/candidates?k=8`
      );
      setCandidates(data.candidates);
      setThreshold(data.threshold);
      setSelected(data.candidates[0]?.record_id ?? null);
    } catch {
      setCandidates([]);
    } finally {
      setCandidatesLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const active = candidates.find((c) => c.record_id === selected) ?? null;
  const schema = material?.attribute_schema ?? [];

  return (
    <AppShell
      crumbs={[
        { label: "Overview", href: "/" },
        { label: "Materials", href: "/materials" },
        { label: material?.legacy_code ?? `#${id}` },
      ]}
    >
      {loading && <LoadingBlock label="Loading material" />}
      {error && !loading && <ErrorState message={error} onRetry={load} />}

      {material && !loading && !error && (
        <div className="space-y-4">
          <PageHeading
            title={material.raw_description}
            description={`${material.cpse_org} · ${material.legacy_code} · ${commodityLabel(
              material.commodity_type
            )}`}
            actions={<ReviewBadge status={material.review_status} />}
          />

          <div className="grid lg:grid-cols-2 gap-4">
            <Panel title="Source Material" bodyClassName="px-4 py-2">
              <dl>
                <DefinitionRow label="Original code"><Mono>{material.legacy_code}</Mono></DefinitionRow>
                <DefinitionRow label="CPSE">{material.cpse_org}</DefinitionRow>
                <DefinitionRow label="Description">{material.raw_description}</DefinitionRow>
                <DefinitionRow label="Normalized">
                  <Mono className="text-ink-muted">{material.normalized_description}</Mono>
                </DefinitionRow>
                <DefinitionRow label="Category">{commodityLabel(material.commodity_type)}</DefinitionRow>
                <DefinitionRow label="UNSPSC class">
                  {material.unspsc_class ? <Mono>{material.unspsc_class}</Mono> : "Not assigned"}
                </DefinitionRow>
                <DefinitionRow label="Ingested">{dateTime(material.created_at)}</DefinitionRow>
                {material.demo_inventory && (
                  <DefinitionRow label="Demo inventory">
                    <span className="tnum">{num(material.demo_inventory.quantity)}</span>{" "}
                    {material.demo_inventory.uom}
                    <span className="ml-2 badge bg-state-neutralBg text-state-neutral border-line-strong">
                      Illustrative
                    </span>
                  </DefinitionRow>
                )}
              </dl>
            </Panel>

            <Panel title="Harmonization Result" bodyClassName="px-4 py-2">
              <dl>
                <DefinitionRow label="NMI">
                  {material.nmi ? (
                    <Link href={`/crosswalk/${material.nmi}`} className="text-accent-500 hover:underline">
                      <Mono>{material.nmi}</Mono>
                    </Link>
                  ) : (
                    <span className="text-ink-faint">Not assigned</span>
                  )}
                </DefinitionRow>
                <DefinitionRow label="Standardized description">
                  {material.standardized_description ?? "Not generated"}
                </DefinitionRow>
                <DefinitionRow label="Confidence">
                  <div className="w-48"><ConfidenceBar value={material.match_score} /></div>
                </DefinitionRow>
                <DefinitionRow label="Relationship">
                  {material.relationship ?? "—"}
                </DefinitionRow>
                <DefinitionRow label="Status"><ReviewBadge status={material.review_status} /></DefinitionRow>
                {material.review_reason && (
                  <DefinitionRow label="Reason">
                    <span className="text-ink-muted">{material.review_reason}</span>
                  </DefinitionRow>
                )}
                <DefinitionRow label="Other CPSE codes">
                  {material.nmi_siblings && material.nmi_siblings.length > 0 ? (
                    <ul className="space-y-1">
                      {material.nmi_siblings.map((s) => (
                        <li key={s.id} className="text-xs">
                          <Link href={`/materials/${s.id}`} className="text-accent-500 hover:underline">
                            {s.cpse_org} · <Mono>{s.legacy_code}</Mono>
                          </Link>
                          <span className="text-ink-subtle"> — {s.raw_description}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="text-ink-faint">No other CPSE currently shares this NMI</span>
                  )}
                </DefinitionRow>
              </dl>
            </Panel>
          </div>

          <Panel
            title="Extracted Attributes"
            description="Every value carries the text it came from, the method that produced it and a confidence."
          >
            {schema.length === 0 ? (
              <EmptyState
                title="No attribute schema for this commodity"
                description="The commodity type could not be determined, so no attributes were extracted."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Attribute</th>
                      <th>Value</th>
                      <th>Extracted from</th>
                      <th>Method</th>
                      <th className="text-right">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {schema.map(({ key, label }) => {
                      const a = material.attributes?.[key];
                      return (
                        <tr key={key}>
                          <td className="whitespace-nowrap text-ink">{label}</td>
                          <td className={clsx(!a && "text-ink-faint italic")}>
                            {attrValue(a?.value)}
                          </td>
                          <td>
                            {a ? (
                              <Mono className="text-ink-muted">“{a.source}”</Mono>
                            ) : (
                              <span className="text-ink-faint">—</span>
                            )}
                          </td>
                          <td>
                            {a ? (
                              <span className="badge bg-state-neutralBg text-state-neutral border-line-strong">
                                {a.method}
                              </span>
                            ) : (
                              <span className="text-ink-faint">—</span>
                            )}
                          </td>
                          <td className="text-right tnum">{a ? pct(a.confidence, 0) : "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <div className="grid lg:grid-cols-5 gap-4">
            <Panel
              title="Candidate Matches"
              description={`Merge threshold ${pct(threshold, 0)}`}
              className="lg:col-span-2"
            >
              {candidatesLoading && <LoadingBlock label="Retrieving candidates" />}
              {!candidatesLoading && candidates.length === 0 && (
                <EmptyState
                  title="No candidates retrieved"
                  description="Nothing in the same commodity partition was similar enough to consider."
                />
              )}
              {!candidatesLoading && candidates.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th className="w-8">#</th>
                        <th>Material</th>
                        <th className="text-right">Score</th>
                        <th>Gate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {candidates.map((c) => (
                        <tr
                          key={c.record_id}
                          onClick={() => setSelected(c.record_id)}
                          className={clsx(
                            "cursor-pointer",
                            selected === c.record_id && "bg-accent-50"
                          )}
                        >
                          <td className="tnum text-ink-subtle">{c.rank}</td>
                          <td>
                            <p className="line-clamp-2">{c.raw_description}</p>
                            <p className="text-2xs text-ink-subtle mt-0.5">
                              {c.cpse_org} · {c.legacy_code}
                              {c.nmi && <> · {c.nmi}</>}
                            </p>
                          </td>
                          <td className="text-right tnum font-medium">{pct(c.score, 1)}</td>
                          <td><SafetyBadge status={c.safety.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>

            <Panel
              title="Match Explanation"
              description={
                active
                  ? `Against ${active.cpse_org} · ${active.legacy_code}`
                  : "Select a candidate to see how its score was produced"
              }
              className="lg:col-span-3"
              bodyClassName="px-4 py-3"
            >
              {active ? (
                <MatchExplanation explanation={active.explanation} safety={active.safety} />
              ) : (
                <EmptyState title="No candidate selected" />
              )}
            </Panel>
          </div>
        </div>
      )}
    </AppShell>
  );
}
