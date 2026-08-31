"use client";

import clsx from "clsx";
import { CircleAlert, CircleCheck, Info, Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { MatchExplanation } from "@/components/MatchExplanation";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeading } from "@/components/shell/Header";
import {
  EmptyState,
  InlineError,
  LoadingBlock,
  Mono,
  Panel,
  SafetyBadge,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { commodityLabel, dateTime, pct } from "@/lib/format";
import type { GovernanceResult } from "@/lib/types";

const COMMODITIES = ["gate_valve", "pipe", "bearing", "electrical_cable", "fastener"];

const EXAMPLES = [
  { label: "Duplicate of an existing valve", text: "GATE VALVE 6 INCH CARBON STEEL CLASS 150 FLANGED" },
  { label: "Same valve, higher pressure class", text: "GATE VALVE 6 INCH CARBON STEEL CLASS 300 FLANGED" },
  { label: "Genuinely new material", text: "PRESSURE GAUGE 100MM DIAL 0-16 BAR SS316 BOTTOM ENTRY" },
];

interface Override {
  id: number;
  description: string;
  suggested_nmi: string | null;
  decision: string;
  new_legacy_code: string | null;
  cpse_org: string | null;
  justification: string | null;
  actor: string;
  created_at: string;
}

export default function GovernancePage() {
  const [description, setDescription] = useState("");
  const [commodity, setCommodity] = useState("");
  const [result, setResult] = useState<GovernanceResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState(0);
  const [cpse, setCpse] = useState("");
  const [newCode, setNewCode] = useState("");
  const [justification, setJustification] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  const [overrides, setOverrides] = useState<Override[]>([]);

  const loadOverrides = useCallback(async () => {
    try {
      const d = await api.get<{ items: Override[] }>("/governance/overrides?limit=25");
      setOverrides(d.items);
    } catch {
      setOverrides([]);
    }
  }, []);

  useEffect(() => {
    loadOverrides();
  }, [loadOverrides]);

  const check = useCallback(async () => {
    if (!description.trim()) return;
    setChecking(true);
    setError(null);
    setResult(null);
    setConfirmation(null);
    setDecisionError(null);
    setSelected(0);
    try {
      const r = await api.post<GovernanceResult>("/check-new-material", {
        description: description.trim(),
        commodity_type: commodity || null,
      });
      setResult(r);
    } catch (e: any) {
      setError(e?.detail ?? "The check could not be completed.");
    } finally {
      setChecking(false);
    }
  }, [description, commodity]);

  const submitDecision = useCallback(
    async (decision: "CREATE_NEW_ANYWAY" | "USE_EXISTING") => {
      if (!result) return;
      const candidate = result.candidates[selected];
      setSubmitting(true);
      setDecisionError(null);
      try {
        await api.post("/governance/override", {
          description: result.description,
          commodity_type: result.commodity_type,
          decision,
          suggested_nmi: candidate?.nmi ?? null,
          suggested_score: candidate?.score ?? null,
          new_legacy_code: decision === "CREATE_NEW_ANYWAY" ? newCode.trim() || null : null,
          cpse_org: cpse.trim().toUpperCase() || null,
          justification: justification.trim() || null,
          actor: "demo.user",
        });
        setConfirmation(
          decision === "CREATE_NEW_ANYWAY"
            ? "A new material code was authorised. The override is recorded in the audit trail."
            : `Adopted ${candidate?.nmi}. The decision is recorded in the audit trail.`
        );
        await loadOverrides();
      } catch (e: any) {
        setDecisionError(e?.detail ?? "The decision could not be recorded.");
      } finally {
        setSubmitting(false);
      }
    },
    [result, selected, newCode, cpse, justification, loadOverrides]
  );

  const candidate = result?.candidates[selected] ?? null;

  const tone =
    result?.recommendation === "USE_EXISTING"
      ? "bg-state-warnBg border-state-warn/25 text-state-warn"
      : result?.recommendation === "REVIEW"
      ? "bg-state-infoBg border-state-info/25 text-state-info"
      : "bg-state-okBg border-state-ok/25 text-state-ok";

  const Icon =
    result?.recommendation === "USE_EXISTING"
      ? CircleAlert
      : result?.recommendation === "REVIEW"
      ? Info
      : CircleCheck;

  return (
    <AppShell crumbs={[{ label: "Overview", href: "/" }, { label: "Governance Gate" }]}>
      <PageHeading
        title="Governance Gate"
        description="Check a proposed material against the national catalogue before a new code is created."
      />

      <div className="space-y-4">
        <Panel bodyClassName="px-4 py-3 space-y-3">
          <div className="grid gap-3 lg:grid-cols-[1fr_14rem_auto] lg:items-end">
            <div>
              <label className="field-label" htmlFor="g-desc">Material description</label>
              <input
                id="g-desc"
                className="input"
                placeholder="e.g. GATE VALVE 6 INCH CARBON STEEL CLASS 150 FLANGED"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") check();
                }}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="g-commodity">Commodity type</label>
              <select
                id="g-commodity"
                className="input"
                value={commodity}
                onChange={(e) => setCommodity(e.target.value)}
              >
                <option value="">Detect automatically</option>
                {COMMODITIES.map((c) => (
                  <option key={c} value={c}>{commodityLabel(c)}</option>
                ))}
              </select>
            </div>
            <button
              type="button"
              className="btn-primary"
              onClick={check}
              disabled={checking || !description.trim()}
            >
              <Search className="h-3.5 w-3.5" aria-hidden />
              {checking ? "Checking…" : "Check catalogue"}
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-2xs uppercase tracking-wide text-ink-subtle mr-1">
              Try
            </span>
            {EXAMPLES.map((ex) => (
              <button
                key={ex.text}
                type="button"
                className="btn-secondary h-6 px-2 text-2xs"
                onClick={() => {
                  setDescription(ex.text);
                  setCommodity("");
                }}
              >
                {ex.label}
              </button>
            ))}
          </div>

          {error && <InlineError message={error} />}
        </Panel>

        {checking && <LoadingBlock label="Comparing against the catalogue" />}

        {result && !checking && (
          <>
            <div className={clsx("panel px-4 py-3 border", tone)}>
              <div className="flex items-start gap-2.5">
                <Icon className="h-4 w-4 mt-0.5 shrink-0" aria-hidden />
                <div className="min-w-0">
                  <p className="text-sm font-semibold">{result.message}</p>
                  <p className="text-xs mt-1 opacity-90">
                    Detected commodity: {commodityLabel(result.commodity_type)}
                    {result.commodity_detected && " (inferred from the description)"}
                    {result.normalized_description && (
                      <> · normalized to “{result.normalized_description}”</>
                    )}
                  </p>
                </div>
              </div>
            </div>

            {result.candidates.length === 0 ? (
              <Panel title="Existing Materials">
                <EmptyState
                  title="No comparable material found"
                  description="Nothing in the same commodity partition was similar enough to consider a duplicate."
                />
              </Panel>
            ) : (
              <div className="grid lg:grid-cols-5 gap-4">
                <Panel
                  title="Closest Existing Identities"
                  className="lg:col-span-2"
                >
                  <div className="overflow-x-auto">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>NMI</th>
                          <th>Standardized Description</th>
                          <th className="text-right">Score</th>
                          <th>Gate</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.candidates.map((c, i) => (
                          <tr
                            key={c.nmi}
                            className={clsx("cursor-pointer", selected === i && "bg-accent-50")}
                            onClick={() => setSelected(i)}
                          >
                            <td>
                              <Link
                                href={`/crosswalk/${c.nmi}`}
                                className="text-accent-500 hover:underline"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <Mono>{c.nmi}</Mono>
                              </Link>
                              <p className="text-2xs text-ink-subtle mt-0.5">
                                {c.cpse_count} CPSE{c.cpse_count === 1 ? "" : "s"}
                              </p>
                            </td>
                            <td className="max-w-xs">
                              <p className="line-clamp-2">{c.standardized_description}</p>
                            </td>
                            <td className="text-right tnum font-medium">{pct(c.score, 1)}</td>
                            <td><SafetyBadge status={c.safety.status} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>

                <Panel
                  title="Match Explanation"
                  description={candidate ? `Against ${candidate.nmi}` : undefined}
                  className="lg:col-span-3"
                  bodyClassName="px-4 py-3"
                >
                  {candidate && (
                    <MatchExplanation
                      explanation={candidate.explanation}
                      safety={candidate.safety}
                    />
                  )}
                </Panel>
              </div>
            )}

            <Panel
              title="Decision"
              description="The gate advises; it never blocks. Every decision is recorded."
              bodyClassName="px-4 py-3 space-y-3"
            >
              {confirmation ? (
                <div className="flex items-start gap-2 rounded border border-state-ok/25 bg-state-okBg px-3 py-2.5 text-xs text-state-ok">
                  <CircleCheck className="h-3.5 w-3.5 mt-px shrink-0" aria-hidden />
                  <span>{confirmation}</span>
                </div>
              ) : (
                <>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div>
                      <label className="field-label" htmlFor="g-cpse">Your CPSE</label>
                      <input
                        id="g-cpse"
                        className="input"
                        placeholder="e.g. BHEL"
                        value={cpse}
                        onChange={(e) => setCpse(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="field-label" htmlFor="g-code">Proposed new code</label>
                      <input
                        id="g-code"
                        className="input font-mono"
                        placeholder="e.g. 10099412"
                        value={newCode}
                        onChange={(e) => setNewCode(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="field-label" htmlFor="g-just">Justification</label>
                      <input
                        id="g-just"
                        className="input"
                        placeholder="Why a separate code is needed"
                        value={justification}
                        onChange={(e) => setJustification(e.target.value)}
                      />
                    </div>
                  </div>

                  {decisionError && <InlineError message={decisionError} />}

                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={submitting}
                      onClick={() => submitDecision("CREATE_NEW_ANYWAY")}
                    >
                      Create new code anyway
                    </button>
                    {candidate && (
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={submitting}
                        onClick={() => submitDecision("USE_EXISTING")}
                      >
                        Adopt {candidate.nmi}
                      </button>
                    )}
                  </div>
                </>
              )}
            </Panel>
          </>
        )}

        <Panel
          title="Override Audit Log"
          description="Every governance decision, including the ones that went against the recommendation."
        >
          {overrides.length === 0 ? (
            <EmptyState title="No governance decisions recorded yet" />
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Proposed Description</th>
                    <th>Suggested NMI</th>
                    <th>Decision</th>
                    <th>CPSE</th>
                    <th>New Code</th>
                    <th>Justification</th>
                    <th>By</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {overrides.map((o) => (
                    <tr key={o.id}>
                      <td className="max-w-xs"><p className="line-clamp-2">{o.description}</p></td>
                      <td>
                        {o.suggested_nmi ? (
                          <Link href={`/crosswalk/${o.suggested_nmi}`} className="text-accent-500 hover:underline">
                            <Mono>{o.suggested_nmi}</Mono>
                          </Link>
                        ) : (
                          <span className="text-ink-faint">—</span>
                        )}
                      </td>
                      <td>
                        <span
                          className={clsx(
                            "badge",
                            o.decision === "CREATE_NEW_ANYWAY"
                              ? "bg-state-warnBg text-state-warn border-state-warn/25"
                              : "bg-state-okBg text-state-ok border-state-ok/25"
                          )}
                        >
                          {o.decision.replace(/_/g, " ").toLowerCase()}
                        </span>
                      </td>
                      <td>{o.cpse_org ?? "—"}</td>
                      <td>{o.new_legacy_code ? <Mono>{o.new_legacy_code}</Mono> : "—"}</td>
                      <td className="max-w-xs text-xs text-ink-subtle">
                        {o.justification ?? "—"}
                      </td>
                      <td className="text-xs whitespace-nowrap">{o.actor}</td>
                      <td className="text-xs text-ink-subtle whitespace-nowrap">
                        {dateTime(o.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </AppShell>
  );
}
