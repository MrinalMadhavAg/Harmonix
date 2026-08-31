"use client";

import clsx from "clsx";
import { CheckCircle2, FileSpreadsheet, Upload } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageHeading } from "@/components/shell/Header";
import {
  EmptyState,
  InlineError,
  KpiCard,
  Mono,
  Panel,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { dateTime, num } from "@/lib/format";

const STAGES = [
  "Validating file",
  "Normalizing descriptions",
  "Extracting attributes and embeddings",
  "Matching and golden record generation",
];

interface UploadResult {
  job_id: string;
  report: {
    received: number;
    inserted: number;
    skipped_duplicates: number;
    unknown_commodity: number;
    warnings: string[];
    errors: string[];
  };
  harmonization: { golden_records: number; records: number; blocked_pairs: number };
}

interface TemplateInfo {
  required_columns: string[];
  optional_columns: string[];
  accepted_aliases: Record<string, string[]>;
  example_csv: string;
  notes: string[];
}

interface BatchRow {
  source_batch: string | null;
  records: number;
  first_seen: string;
}

export default function DataSourcesPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [stage, setStage] = useState(-1);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [template, setTemplate] = useState<TemplateInfo | null>(null);

  useEffect(() => {
    api.get<TemplateInfo>("/ingest/template").then(setTemplate).catch(() => setTemplate(null));
  }, []);

  const upload = useCallback(async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    setResult(null);
    setStage(0);

    // The request is synchronous end-to-end; the stage ticker reflects the
    // fixed pipeline order so the user can see roughly where it is.
    const ticker = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 1200);
    try {
      const r = await api.upload<UploadResult>("/ingest/upload", file);
      setResult(r);
      setStage(STAGES.length);
    } catch (e: any) {
      setError(e?.detail ?? "The upload failed.");
      setStage(-1);
    } finally {
      clearInterval(ticker);
      setUploading(false);
    }
  }, [file]);

  const downloadTemplate = useCallback(() => {
    if (!template) return;
    const url = URL.createObjectURL(
      new Blob([template.example_csv], { type: "text/csv;charset=utf-8" })
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "harmonix-import-template.csv";
    a.click();
    URL.revokeObjectURL(url);
  }, [template]);

  return (
    <AppShell crumbs={[{ label: "Overview", href: "/" }, { label: "Data Sources" }]}>
      <PageHeading
        title="Data Sources"
        description="Import a CPSE material master export. Records are normalized, attributed, embedded, matched and harmonized in one pass."
        actions={
          <button type="button" className="btn-secondary" onClick={downloadTemplate} disabled={!template}>
            <FileSpreadsheet className="h-3.5 w-3.5" aria-hidden />
            Download template
          </button>
        }
      />

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <Panel title="Upload Material Export" bodyClassName="px-4 py-4 space-y-3">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const f = e.dataTransfer.files?.[0];
                if (f) {
                  setFile(f);
                  setResult(null);
                  setError(null);
                }
              }}
              className={clsx(
                "border border-dashed rounded-lg px-6 py-8 text-center transition-colors",
                dragging ? "border-accent-500 bg-accent-50" : "border-line-strong bg-surface-subtle"
              )}
            >
              <Upload className="h-5 w-5 mx-auto text-ink-faint" aria-hidden />
              <p className="text-sm text-ink mt-2">
                Drop a CSV or Excel file here, or{" "}
                <button
                  type="button"
                  className="text-accent-500 hover:underline"
                  onClick={() => inputRef.current?.click()}
                >
                  browse
                </button>
              </p>
              <p className="text-xs text-ink-subtle mt-1">
                Required columns: cpse_org, legacy_code, description
              </p>
              <input
                ref={inputRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) {
                    setFile(f);
                    setResult(null);
                    setError(null);
                  }
                }}
              />
            </div>

            {file && (
              <div className="flex items-center justify-between gap-3 rounded border border-line px-3 py-2">
                <div className="min-w-0">
                  <p className="text-sm text-ink truncate">{file.name}</p>
                  <p className="text-xs text-ink-subtle">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    className="btn-ghost text-xs"
                    onClick={() => {
                      setFile(null);
                      setResult(null);
                      setError(null);
                      setStage(-1);
                    }}
                    disabled={uploading}
                  >
                    Remove
                  </button>
                  <button type="button" className="btn-primary" onClick={upload} disabled={uploading}>
                    {uploading ? "Processing…" : "Ingest and harmonize"}
                  </button>
                </div>
              </div>
            )}

            {error && <InlineError message={error} />}

            {stage >= 0 && (
              <ol className="space-y-1.5">
                {STAGES.map((s, i) => {
                  const done = stage > i;
                  const active = stage === i;
                  return (
                    <li key={s} className="flex items-center gap-2.5 text-sm">
                      <span
                        className={clsx(
                          "h-5 w-5 rounded-full border flex items-center justify-center text-2xs shrink-0",
                          done
                            ? "bg-state-ok border-state-ok text-white"
                            : active
                            ? "border-accent-500 text-accent-500"
                            : "border-line-strong text-ink-faint"
                        )}
                      >
                        {done ? "✓" : i + 1}
                      </span>
                      <span className={clsx(done || active ? "text-ink" : "text-ink-faint")}>
                        Step {i + 1}/{STAGES.length} — {s}
                      </span>
                    </li>
                  );
                })}
              </ol>
            )}
          </Panel>

          {result && (
            <Panel title="Ingestion Result" bodyClassName="px-4 py-3 space-y-3">
              <div className="flex items-start gap-2 rounded border border-state-ok/25 bg-state-okBg px-3 py-2.5 text-xs text-state-ok">
                <CheckCircle2 className="h-3.5 w-3.5 mt-px shrink-0" aria-hidden />
                <span>
                  Ingested and harmonized. Job <Mono>{result.job_id}</Mono>.
                </span>
              </div>

              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <KpiCard label="Rows received" value={num(result.report.received)} />
                <KpiCard label="Records inserted" value={num(result.report.inserted)} tone="ok" />
                <KpiCard
                  label="Duplicates skipped"
                  value={num(result.report.skipped_duplicates)}
                  tone={result.report.skipped_duplicates > 0 ? "warn" : "default"}
                />
                <KpiCard
                  label="Golden records now"
                  value={num(result.harmonization.golden_records)}
                />
              </div>

              {result.report.warnings.length > 0 && (
                <div>
                  <p className="field-label">Warnings</p>
                  <ul className="space-y-1 max-h-48 overflow-y-auto">
                    {result.report.warnings.map((w, i) => (
                      <li key={i} className="text-xs text-state-warn">• {w}</li>
                    ))}
                  </ul>
                </div>
              )}

              <Link href="/materials" className="btn-secondary inline-flex">
                Review the imported materials
              </Link>
            </Panel>
          )}
        </div>

        <div className="space-y-4">
          {template && (
            <Panel title="Expected Format" bodyClassName="px-4 py-3 space-y-3">
              <div>
                <p className="field-label">Required columns</p>
                <div className="flex flex-wrap gap-1">
                  {template.required_columns.map((c) => (
                    <Mono key={c} className="badge bg-accent-50 text-accent-600 border-accent-200">
                      {c}
                    </Mono>
                  ))}
                </div>
              </div>
              <div>
                <p className="field-label">Optional columns</p>
                <div className="flex flex-wrap gap-1">
                  {template.optional_columns.map((c) => (
                    <Mono key={c} className="badge bg-surface-muted text-ink-muted border-line-strong">
                      {c}
                    </Mono>
                  ))}
                </div>
              </div>
              <div>
                <p className="field-label">Example</p>
                <pre className="text-2xs bg-surface-subtle border border-line rounded p-2 overflow-x-auto font-mono text-ink-muted whitespace-pre">
                  {template.example_csv}
                </pre>
              </div>
              <ul className="space-y-1">
                {template.notes.map((n, i) => (
                  <li key={i} className="text-xs text-ink-subtle">• {n}</li>
                ))}
              </ul>
            </Panel>
          )}
          {!template && (
            <Panel title="Expected Format">
              <EmptyState title="Format guidance unavailable" description="The backend could not be reached." />
            </Panel>
          )}
        </div>
      </div>
    </AppShell>
  );
}
