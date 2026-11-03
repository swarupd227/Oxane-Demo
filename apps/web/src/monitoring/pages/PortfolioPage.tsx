import clsx from "clsx";
import { ArrowRight, CheckCircle2, CircleAlert, Clock3, FileCheck2, Scale, ShieldAlert, TriangleAlert } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { PageHeader, SeedNotice } from "../../components/ui/PageHeader";
import { formatDate } from "../../lib/format";
import { useCycle, useCycleSession, type Cycle, type CycleSession, type FacilityId } from "../cycle";
import { FacilityTag } from "../parts";

interface Row {
  documents: { received: number; total: number; late: number };
  reconciliation: { tone: "ok" | "warn" | "neutral"; text: string };
  tests: { tone: "ok" | "warn" | "danger"; text: string }[];
  trend: { label: string; values: number[]; limit: number; direction: "max" | "min" } | null;
  open: number;
  held: number;
}

function summarise(cycle: Cycle, session: CycleSession | undefined, id: FacilityId): Row {
  const subs = cycle.submissions.filter((s) => s.facility === id);
  const findings = cycle.findings.filter((f) => f.facility.split(",").includes(id));
  const outcome = (f: (typeof findings)[number]) => session?.decisions[f.id] ?? f.suggested.outcome;
  const documents = {
    received: subs.filter((s) => s.received).length,
    total: subs.length,
    late: subs.filter((s) => s.status === "late").length,
  };
  const t = cycle.tests;
  if (id === "bramble") {
    const roll = cycle.reconciliation.roll_forward;
    return {
      documents,
      reconciliation: roll.within_tolerance
        ? { tone: "ok", text: "Roll-forward agrees" }
        : { tone: "warn", text: `${roll.missing.length} loans missing; charge-offs differ` },
      tests: [
        { tone: t.bramble.borrowing_base.within_tolerance ? "ok" : "danger", text: "Borrowing base agrees with certificate" },
        { tone: t.bramble.delinquency.early_warning ? "warn" : "ok", text: `Delinquency ${t.bramble.delinquency.average.toFixed(2)}% vs ${t.bramble.delinquency.limit}%` },
        { tone: "warn", text: `Leverage ${t.bramble.leverage.reported.toFixed(2)}x reported; ${t.bramble.leverage.with_guarantees.toFixed(2)}x needs a view` },
      ],
      trend: { label: "60+ day delinquency", values: t.bramble.delinquency.monthly.map((m) => m.value), limit: t.bramble.delinquency.limit, direction: "max" },
      open: findings.filter((f) => outcome(f) !== "logged").length,
      held: findings.filter((f) => outcome(f) === "logged").length,
    };
  }
  if (id === "northmoor") {
    const d = t.northmoor.delinquency;
    return {
      documents,
      reconciliation: { tone: "neutral", text: "Pending servicer report" },
      tests: [
        { tone: d.breached ? "danger" : d.early_warning ? "warn" : "ok", text: `Delinquency average ${d.average.toFixed(2)}% vs ${d.limit}% trigger` },
        { tone: "ok", text: `Excess spread ${t.northmoor.excess_spread.average.toFixed(2)}%, 2 of 3 months` },
      ],
      trend: { label: "60+ day delinquency", values: d.monthly.map((m) => m.value), limit: d.limit, direction: "max" },
      open: findings.filter((f) => outcome(f) !== "logged").length,
      held: findings.filter((f) => outcome(f) === "logged").length,
    };
  }
  const k = t.kestrel;
  return {
    documents,
    reconciliation: { tone: "ok", text: "NAV ties to positions" },
    tests: [
      { tone: "warn", text: `Loan-to-value ${k.ltv.reported.toFixed(1)}%, or ${k.ltv.with_markdown.toFixed(1)}% with markdown, vs ${k.ltv.limit}%` },
      { tone: k.valuations.stale.length ? "warn" : "ok", text: `${k.valuations.stale.length} stale valuation` },
      { tone: k.concentration.passed ? "ok" : "danger", text: "Concentration within limits" },
    ],
    trend: null,
    open: findings.filter((f) => outcome(f) !== "logged").length,
    held: findings.filter((f) => outcome(f) === "logged").length,
  };
}

const toneIcon = { ok: CheckCircle2, warn: TriangleAlert, danger: CircleAlert, neutral: Clock3 };
const toneText = { ok: "text-ok", warn: "text-warn", danger: "text-danger", neutral: "text-muted" };

function Spark({ values, limit }: { values: number[]; limit: number }) {
  // Scaled to the facility's own values, so a low, steady trend still shows its shape.
  const top = Math.max(...values) * 1.15 || 1;
  return (
    <span className="flex items-end gap-2">
      <span className="flex h-9 items-end gap-1" aria-hidden>
        {values.map((v, i) => (
          <span key={i} className={clsx("w-3 rounded-sm", v > limit ? "bg-danger" : limit - v < 0.5 ? "bg-warn" : "bg-subtle")} style={{ height: `${(v / top) * 100}%` }} />
        ))}
      </span>
      <span className="numeric text-xs font-semibold">{values.at(-1)?.toFixed(2)}%</span>
    </span>
  );
}

export function PortfolioPage() {
  const { data: cycle, isPending } = useCycle();
  const { data: session } = useCycleSession();
  const navigate = useNavigate();
  if (isPending || !cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const lastIn = cycle.submissions.map((s) => s.received).filter(Boolean).sort().pop();
  const totals = cycle.findings.reduce(
    (acc, f) => {
      const o = session?.decisions[f.id] ?? f.suggested.outcome;
      acc[o === "logged" ? "held" : "open"] += 1;
      return acc;
    },
    { open: 0, held: 0 },
  );
  return (
    <>
      <PageHeader
        title="Portfolio monitor"
        summary={`${cycle.lender}: ${cycle.facilities.length} facilities, ${cycle.cycle.label} cycle. Submissions collected, reconciled, tested against the terms in force, and triaged.`}
        actions={
          <Button onClick={() => navigate("/monitoring/submissions")}>
            Start with submissions
            <ArrowRight aria-hidden className="size-4" />
          </Button>
        }
      />
      <SeedNotice>All documents and data in this cycle are synthetic. Not connected to Panorama or Oxane Accelerate.</SeedNotice>

      <div className="mb-5 grid grid-cols-4 gap-3">
        {[
          { icon: FileCheck2, label: "Collect", value: `${cycle.submissions.filter((s) => s.received).length} of ${cycle.submissions.length} received`, note: `Last in ${lastIn ? formatDate(lastIn) : "–"}` },
          { icon: Scale, label: "Reconcile", value: "Tapes, reports, certificates", note: "Every gap traced to rows" },
          { icon: ShieldAlert, label: "Test", value: "Terms in force for May", note: "Triggers, covenants, NAV, collateral" },
          { icon: TriangleAlert, label: "Triage and report", value: `${totals.open} to act on`, note: `${totals.held} held back with a reason` },
        ].map(({ icon: Icon, label, value, note }) => (
          <Card key={label} className="px-4 py-3">
            <p className="flex items-center gap-1.5 text-xs font-semibold tracking-[0.06em] text-muted uppercase">
              <Icon aria-hidden className="size-3.5" />
              {label}
            </p>
            <p className="mt-1 text-[0.9375rem] font-semibold">{value}</p>
            <p className="text-xs text-muted">{note}</p>
          </Card>
        ))}
      </div>

      <Card>
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-line text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
              <th className="py-3 pr-3 pl-5">Facility</th>
              <th className="py-3 pr-3">Documents</th>
              <th className="py-3 pr-3">Reconciliation</th>
              <th className="py-3 pr-3">Covenants and triggers</th>
              <th className="py-3 pr-3">Trend</th>
              <th className="py-3 pr-3 text-right">Open items</th>
              <th className="py-3 pr-5 text-right">Held back</th>
            </tr>
          </thead>
          <tbody>
            {cycle.facilities.map((facility) => {
              const row = summarise(cycle, session, facility.id);
              const RIcon = toneIcon[row.reconciliation.tone];
              return (
                <tr key={facility.id} className="border-b border-sand align-top last:border-0">
                  <td className="py-4 pr-3 pl-5">
                    <p className="font-semibold">{facility.name}</p>
                    <p className="mt-0.5 text-xs text-muted">
                      {facility.type} · {facility.size}
                      {facility.size_note ? ` (${facility.size_note})` : ""}
                    </p>
                    <p className="mt-1.5 flex items-center gap-1.5">
                      <FacilityTag id={facility.id} name={facility.asset_class} />
                      <span className="text-xs text-muted">{facility.role}</span>
                    </p>
                  </td>
                  <td className="py-4 pr-3 text-sm">
                    <p className="numeric font-medium">
                      {row.documents.received} of {row.documents.total}
                    </p>
                    {row.documents.late > 0 ? (
                      <p className="mt-0.5 inline-flex items-center gap-1 text-xs font-medium text-danger">
                        <Clock3 aria-hidden className="size-3" /> {row.documents.late} late, chased
                      </p>
                    ) : (
                      <p className="mt-0.5 text-xs text-muted">All in</p>
                    )}
                  </td>
                  <td className="py-4 pr-3 text-sm">
                    <span className={clsx("inline-flex items-start gap-1.5", toneText[row.reconciliation.tone])}>
                      <RIcon aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                      {row.reconciliation.text}
                    </span>
                  </td>
                  <td className="py-4 pr-3">
                    <ul className="space-y-1 text-sm">
                      {row.tests.map((test) => {
                        const Icon = toneIcon[test.tone];
                        return (
                          <li key={test.text} className={clsx("flex items-start gap-1.5", toneText[test.tone])}>
                            <Icon aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                            <span className="text-ink">{test.text}</span>
                          </li>
                        );
                      })}
                    </ul>
                  </td>
                  <td className="py-4 pr-3">
                    {row.trend ? (
                      <div>
                        <Spark values={row.trend.values} limit={row.trend.limit} />
                        <p className="mt-1 text-[0.6875rem] text-muted">{row.trend.label}, Mar to May</p>
                      </div>
                    ) : (
                      <p className="text-xs text-muted">Quarterly reporting</p>
                    )}
                  </td>
                  <td className="numeric py-4 pr-3 text-right text-lg font-semibold">{row.open}</td>
                  <td className="numeric py-4 pr-5 text-right text-lg font-semibold text-muted">{row.held}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
      <div className="mt-4 flex items-center justify-between">
        <SectionLabel>Cross-facility checks use only {cycle.lender}'s own facilities</SectionLabel>
        <Button variant="secondary" size="sm" onClick={() => navigate("/monitoring/triage")}>
          Open triage
          <ArrowRight aria-hidden className="size-3.5" />
        </Button>
      </div>
    </>
  );
}
