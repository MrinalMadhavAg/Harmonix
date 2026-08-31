"use client";

import Link from "next/link";

import { AppShell } from "@/components/shell/AppShell";
import { PageHeading } from "@/components/shell/Header";
import { Mono, Panel, StateBadge } from "@/components/ui/primitives";

const DEMO_STEPS = [
  { step: 1, action: "Open the Overview dashboard", where: "/", note: "Totals, status mix and CPSE coverage." },
  { step: 2, action: "Open Materials and filter to one commodity", where: "/materials", note: "See how differently each CPSE describes the same thing." },
  { step: 3, action: "Open a material and read its candidate matches", where: "/materials", note: "Every score is broken into semantic, lexical and attribute components." },
  { step: 4, action: "Open the NMI crosswalk from that material", where: "/harmonization", note: "Several legacy codes, one neutral identity, plus the attribute evidence grid." },
  { step: 5, action: "On Harmonization, turn safety constraints OFF", where: "/harmonization", note: "The pipeline genuinely re-runs. Watch blocked pairs fall to zero and golden records collapse." },
  { step: 6, action: "Turn safety constraints back ON", where: "/harmonization", note: "The blocked table repopulates: CL150 vs CL300, SS316 vs SS316L, 25 mm vs 30 mm bore." },
  { step: 7, action: "Work an item in the Review Queue", where: "/review", note: "Approve or reject with the evidence in view. The decision persists across restarts." },
  { step: 8, action: "Run the Governance Gate on a new description", where: "/governance", note: "It advises, never blocks, and logs whatever you decide." },
  { step: 9, action: "Run the evaluation on Reports", where: "/reports", note: "Precision, recall, F1 and Recall@K against a ground truth the pipeline never sees." },
];

export default function HelpPage() {
  return (
    <AppShell crumbs={[{ label: "Overview", href: "/" }, { label: "Help" }]}>
      <PageHeading
        title="Help"
        description="What this system does, the vocabulary it uses, and how to walk through it."
      />

      <div className="space-y-4">
        <Panel title="The core idea" bodyClassName="px-4 py-4">
          <p className="text-sm text-ink max-w-3xl">
            Every CPSE keeps its own material codes. Harmonix does not replace them. It
            establishes a neutral <strong>National Material Identifier</strong> above them and
            maintains a crosswalk from each legacy code to that identity.
          </p>
          <pre className="mt-3 text-xs font-mono text-ink-muted bg-surface-subtle border border-line rounded p-3 overflow-x-auto">
{`BHEL   10023841       ─┐
IOCL   MAT-GV-0284    ─┼──▶  NMI-000001   GATE VALVE, DN150, CARBON STEEL, CL150
NTPC   400000918273   ─┘`}
          </pre>
          <p className="text-sm text-ink-muted mt-3 max-w-3xl">
            No source code is ever deleted or rewritten. The crosswalk is the product.
          </p>
        </Panel>

        <Panel title="Three-state attribute comparison" bodyClassName="px-4 py-4">
          <p className="text-sm text-ink-muted max-w-3xl mb-3">
            Every attribute comparison resolves to exactly one of three states. The distinction
            between the last two is what keeps the system honest.
          </p>
          <dl className="space-y-2.5">
            <div className="flex items-start gap-3">
              <dt className="w-28 shrink-0"><StateBadge state="MATCH" /></dt>
              <dd className="text-sm text-ink-muted">
                Both records state a value and the values agree.
              </dd>
            </div>
            <div className="flex items-start gap-3">
              <dt className="w-28 shrink-0"><StateBadge state="MISMATCH" /></dt>
              <dd className="text-sm text-ink-muted">
                Both records state a value and the values conflict.
              </dd>
            </div>
            <div className="flex items-start gap-3">
              <dt className="w-28 shrink-0"><StateBadge state="UNKNOWN" /></dt>
              <dd className="text-sm text-ink-muted">
                At least one record does not state a value. This is <em>not</em> a mismatch —
                absence of evidence is not evidence of difference — and it is <em>not</em> a
                match, because agreement may not be invented. It routes to human review.
              </dd>
            </div>
          </dl>
        </Panel>

        <Panel title="Safety constraints" bodyClassName="px-4 py-4">
          <p className="text-sm text-ink-muted max-w-3xl mb-3">
            Similarity scoring and safety are separate. The scorer says how alike two
            descriptions are; the safety layer says whether they may be declared the same
            material. A 95% similarity between a CL150 and a CL300 gate valve is a correct
            score and an unacceptable merge.
          </p>
          <table className="data-table border border-line rounded overflow-hidden">
            <thead>
              <tr>
                <th>Verdict</th>
                <th>Meaning</th>
                <th>Effect</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><Mono>PASS</Mono></td>
                <td>Every safety-critical field is stated on both records and agrees.</td>
                <td>May merge.</td>
              </tr>
              <tr>
                <td><Mono>BLOCK</Mono></td>
                <td>At least one safety-critical field is confirmed to differ.</td>
                <td>No edge is created. The blocking field is logged.</td>
              </tr>
              <tr>
                <td><Mono>INSUFFICIENT_EVIDENCE</Mono></td>
                <td>A safety-critical field is unstated on one or both records.</td>
                <td>Routed to review. Never merged automatically.</td>
              </tr>
            </tbody>
          </table>
        </Panel>

        <Panel title="Five-minute walkthrough">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="w-10">#</th>
                  <th>Action</th>
                  <th>Screen</th>
                  <th>What to point out</th>
                </tr>
              </thead>
              <tbody>
                {DEMO_STEPS.map((s) => (
                  <tr key={s.step}>
                    <td className="tnum text-ink-subtle">{s.step}</td>
                    <td className="text-ink">{s.action}</td>
                    <td>
                      <Link href={s.where} className="text-accent-500 hover:underline">
                        {s.where}
                      </Link>
                    </td>
                    <td className="text-xs text-ink-subtle">{s.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Data provenance" bodyClassName="px-4 py-4">
          <ul className="space-y-2 text-sm text-ink-muted max-w-3xl">
            <li>
              • <strong className="text-ink">Material records</strong> are synthetic but modelled on
              real CPSE description conventions — abbreviations, unit notations, OCR damage,
              vendor codes and missing fields.
            </li>
            <li>
              • <strong className="text-ink">Stock quantities</strong> are illustrative demo
              inventory. They are clearly labelled wherever they appear and do not represent real
              CPSE holdings.
            </li>
            <li>
              • <strong className="text-ink">Transfer requests</strong> are a demonstration only.
              Nothing in this system initiates a procurement, financial or ERP transaction.
            </li>
            <li>
              • <strong className="text-ink">Ground truth</strong> used for the evaluation on
              Reports lives in a separate table that the matching pipeline never reads.
            </li>
          </ul>
        </Panel>
      </div>
    </AppShell>
  );
}
