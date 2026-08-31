"use client";

import { RotateCcw, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageHeading } from "@/components/shell/Header";
import {
  ErrorState,
  InlineError,
  LoadingBlock,
  Mono,
  Panel,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { commodityLabel, pct } from "@/lib/format";

interface WeightConfig {
  commodity_type: string;
  label: string;
  semantic: number;
  lexical: number;
  attributes: number;
  attribute_weights: Record<string, number>;
  safety_critical_fields: { key: string; label: string }[];
}

interface SafetyConfig {
  items: { commodity_type: string; label: string; fields: { key: string; label: string }[] }[];
  verdicts: Record<string, string>;
}

interface StandardsConfig {
  equivalences: {
    source: string;
    target: string;
    confidence: number;
    commodities: string[];
    context: string;
  }[];
  note: string;
}

interface RuntimeSettings {
  match_threshold: number;
  review_floor: number;
  candidate_k: number;
  embedding_model: string;
  auto_seed: boolean;
}

export default function SettingsPage() {
  const [weights, setWeights] = useState<WeightConfig[]>([]);
  const [safety, setSafety] = useState<SafetyConfig | null>(null);
  const [standards, setStandards] = useState<StandardsConfig | null>(null);
  const [runtime, setRuntime] = useState<RuntimeSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [draft, setDraft] = useState<Record<string, WeightConfig>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [w, s, st, rt] = await Promise.all([
        api.get<{ items: WeightConfig[] }>("/config/weights"),
        api.get<SafetyConfig>("/config/safety"),
        api.get<StandardsConfig>("/config/standards"),
        api.get<RuntimeSettings>("/config/settings"),
      ]);
      setWeights(w.items);
      setDraft(Object.fromEntries(w.items.map((i) => [i.commodity_type, i])));
      setSafety(s);
      setStandards(st);
      setRuntime(rt);
    } catch (e: any) {
      setError(e?.detail ?? "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const update = (commodity: string, patch: Partial<WeightConfig>) => {
    setDraft((d) => ({ ...d, [commodity]: { ...d[commodity], ...patch } }));
    setSaved(null);
  };

  const updateAttr = (commodity: string, key: string, value: number) => {
    setDraft((d) => ({
      ...d,
      [commodity]: {
        ...d[commodity],
        attribute_weights: { ...d[commodity].attribute_weights, [key]: value },
      },
    }));
    setSaved(null);
  };

  const save = useCallback(
    async (commodity: string) => {
      const c = draft[commodity];
      if (!c) return;
      setSaving(commodity);
      setSaveError(null);
      try {
        await api.put(`/config/weights/${commodity}`, {
          semantic: c.semantic,
          lexical: c.lexical,
          attributes: c.attributes,
          attribute_weights: c.attribute_weights,
        });
        setSaved(commodity);
      } catch (e: any) {
        setSaveError(e?.detail ?? "The weights could not be saved.");
      } finally {
        setSaving(null);
      }
    },
    [draft]
  );

  const reset = useCallback(
    async (commodity: string) => {
      setSaving(commodity);
      setSaveError(null);
      try {
        const r = await api.post<{ updated: WeightConfig }>(
          `/config/weights/${commodity}/reset`
        );
        setDraft((d) => ({
          ...d,
          [commodity]: { ...d[commodity], ...r.updated },
        }));
        setSaved(commodity);
      } catch (e: any) {
        setSaveError(e?.detail ?? "The weights could not be reset.");
      } finally {
        setSaving(null);
      }
    },
    []
  );

  return (
    <AppShell crumbs={[{ label: "Overview", href: "/" }, { label: "Settings" }]}>
      <PageHeading
        title="Settings"
        description="Matching weights, safety-critical fields and standard equivalences."
      />

      {loading && <LoadingBlock label="Loading configuration" />}
      {error && !loading && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && (
        <div className="space-y-4">
          {runtime && (
            <Panel title="Runtime Configuration" bodyClassName="px-4 py-3">
              <dl className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3 text-sm">
                <div>
                  <dt className="field-label">Merge threshold</dt>
                  <dd className="tnum">{pct(runtime.match_threshold, 0)}</dd>
                </div>
                <div>
                  <dt className="field-label">Review floor</dt>
                  <dd className="tnum">{pct(runtime.review_floor, 0)}</dd>
                </div>
                <div>
                  <dt className="field-label">Candidate k</dt>
                  <dd className="tnum">{runtime.candidate_k}</dd>
                </div>
                <div className="lg:col-span-2">
                  <dt className="field-label">Embedding model</dt>
                  <dd><Mono className="text-ink-muted">{runtime.embedding_model}</Mono></dd>
                </div>
              </dl>
              <p className="text-xs text-ink-subtle mt-2">
                These are set by environment variable and apply to every commodity. The weights
                below are per commodity and stored in the database.
              </p>
            </Panel>
          )}

          {saveError && <InlineError message={saveError} />}

          {weights.map((w) => {
            const d = draft[w.commodity_type] ?? w;
            const total = d.semantic + d.lexical + d.attributes;
            return (
              <Panel
                key={w.commodity_type}
                title={commodityLabel(w.commodity_type)}
                description={`Safety-critical: ${w.safety_critical_fields
                  .map((f) => f.label)
                  .join(", ")}`}
                actions={
                  <>
                    {saved === w.commodity_type && (
                      <span className="text-xs text-state-ok">Saved</span>
                    )}
                    <button
                      type="button"
                      className="btn-secondary h-7 px-2.5 text-xs"
                      onClick={() => reset(w.commodity_type)}
                      disabled={saving === w.commodity_type}
                    >
                      <RotateCcw className="h-3 w-3" aria-hidden />
                      Reset
                    </button>
                    <button
                      type="button"
                      className="btn-primary h-7 px-2.5 text-xs"
                      onClick={() => save(w.commodity_type)}
                      disabled={saving === w.commodity_type}
                    >
                      <Save className="h-3 w-3" aria-hidden />
                      {saving === w.commodity_type ? "Saving…" : "Save"}
                    </button>
                  </>
                }
                bodyClassName="px-4 py-3 space-y-4"
              >
                <div>
                  <p className="field-label">Score components</p>
                  <div className="grid sm:grid-cols-3 gap-3">
                    {(["semantic", "lexical", "attributes"] as const).map((k) => (
                      <label key={k} className="block">
                        <span className="text-xs text-ink-muted capitalize">
                          {k}
                          <span className="text-ink-faint ml-1 tnum">
                            ({total > 0 ? pct(d[k] / total, 0) : "—"} effective)
                          </span>
                        </span>
                        <div className="flex items-center gap-2 mt-1">
                          <input
                            type="range"
                            min={0}
                            max={1}
                            step={0.05}
                            value={d[k]}
                            onChange={(e) =>
                              update(w.commodity_type, { [k]: Number(e.target.value) } as any)
                            }
                            className="flex-1 accent-accent-500"
                          />
                          <span className="text-xs tnum w-9 text-right">{d[k].toFixed(2)}</span>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="field-label">Attribute weights</p>
                  <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {Object.entries(d.attribute_weights).map(([key, val]) => {
                      const critical = w.safety_critical_fields.some((f) => f.key === key);
                      return (
                        <label key={key} className="block">
                          <span className="text-xs text-ink-muted">
                            {key.replace(/_/g, " ")}
                            {critical && (
                              <span className="ml-1.5 badge bg-accent-50 text-accent-600 border-accent-200">
                                Safety
                              </span>
                            )}
                          </span>
                          <div className="flex items-center gap-2 mt-1">
                            <input
                              type="range"
                              min={0}
                              max={2}
                              step={0.05}
                              value={val}
                              onChange={(e) =>
                                updateAttr(w.commodity_type, key, Number(e.target.value))
                              }
                              className="flex-1 accent-accent-500"
                            />
                            <span className="text-xs tnum w-9 text-right">{val.toFixed(2)}</span>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <p className="text-xs text-ink-subtle">
                  After saving, run the pipeline from{" "}
                  <a href="/harmonization" className="text-accent-500 hover:underline">
                    Harmonization
                  </a>{" "}
                  to apply the new weights.
                </p>
              </Panel>
            );
          })}

          {safety && (
            <Panel
              title="Safety Constraint Configuration"
              description="A confirmed difference in any of these fields prevents two codes from sharing an NMI."
            >
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Commodity</th>
                      <th>Safety-critical fields</th>
                    </tr>
                  </thead>
                  <tbody>
                    {safety.items.map((i) => (
                      <tr key={i.commodity_type}>
                        <td className="whitespace-nowrap font-medium">{i.label}</td>
                        <td>
                          <div className="flex flex-wrap gap-1">
                            {i.fields.map((f) => (
                              <span
                                key={f.key}
                                className="badge bg-accent-50 text-accent-600 border-accent-200"
                              >
                                {f.label}
                              </span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <dl className="px-4 py-3 border-t border-line space-y-1.5">
                {Object.entries(safety.verdicts).map(([k, v]) => (
                  <div key={k} className="flex gap-3 text-xs">
                    <dt className="w-44 shrink-0 font-mono text-ink">{k}</dt>
                    <dd className="text-ink-subtle">{v}</dd>
                  </div>
                ))}
              </dl>
            </Panel>
          )}

          {standards && (
            <Panel title="Standard Equivalences" description={standards.note}>
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Notation A</th>
                      <th>Notation B</th>
                      <th className="text-right">Confidence</th>
                      <th>Applies to</th>
                      <th>Context</th>
                    </tr>
                  </thead>
                  <tbody>
                    {standards.equivalences.map((e) => (
                      <tr key={`${e.source}-${e.target}`}>
                        <td><Mono>{e.source}</Mono></td>
                        <td><Mono>{e.target}</Mono></td>
                        <td className="text-right tnum">{pct(e.confidence, 0)}</td>
                        <td className="text-xs text-ink-muted">
                          {e.commodities.map(commodityLabel).join(", ")}
                        </td>
                        <td className="text-xs text-ink-subtle">{e.context}</td>
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
