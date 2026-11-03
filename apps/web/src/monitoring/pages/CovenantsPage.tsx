import clsx from "clsx";
import { ArrowRight, CheckCircle2, CircleAlert, FileText, FlaskConical, Scale, TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { PageHeader } from "../../components/ui/PageHeader";
import { formatDate } from "../../lib/format";
import { useCycle, useWhatIf, type Cycle, type FacilityId, type Source } from "../cycle";
import { FacilityTag, SourcePanel, Stat, TrendBars, usd2 } from "../parts";

type Status = "pass" | "warning" | "stale" | "expert" | "fail" | "pending";

const statuses: Record<Status, { label: string; className: string; icon: typeof CheckCircle2 }> = {
  pass: { label: "Pass", className: "bg-ok-tint text-ok", icon: CheckCircle2 },
  stale: { label: "Out of date", className: "bg-warn-tint text-warn", icon: TriangleAlert },
  warning: { label: "Early warning", className: "bg-warn-tint text-warn", icon: TriangleAlert },
  expert: { label: "Needs an expert view", className: "bg-warn-tint text-warn", icon: Scale },
  fail: { label: "Fails", className: "bg-danger-tint text-danger", icon: CircleAlert },
  pending: { label: "Pending", className: "bg-sand text-muted", icon: FlaskConical },
};

function Test({ title, clause, status, children, onSource, source }: { title: string; clause: string; status: Status; children: ReactNode; onSource: (s: Source | null) => void; source?: Source | null }) {
  const view = statuses[status];
  const Icon = view.icon;
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{title}</p>
          <p className="text-xs text-muted">
            {source ? (
              <button type="button" onClick={() => onSource(source)} className="cursor-pointer text-left font-medium text-info hover:underline">
                <FileText aria-hidden className="mr-1 inline size-3 align-[-2px]" />
                {clause}
              </button>
            ) : (
              clause
            )}
          </p>
        </div>
        <span className={clsx("inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium", view.className)}>
          <Icon aria-hidden className="size-3.5" />
          {view.label}
        </span>
      </div>
      <div className="mt-4">{children}</div>
    </Card>
  );
}

function Northmoor({ cycle, onSource }: { cycle: Cycle; onSource: (s: Source | null) => void }) {
  const n = cycle.tests.northmoor;
  const d = n.delinquency;
  // Starts just past the breach level, so the first run shows what the trigger is for.
  const [june, setJune] = useState(5.9);
  const whatIf = useWhatIf();
  const result = whatIf.data;
  return (
    <div className="space-y-5">
      <Test title="60+ day delinquency trigger" clause={`${d.clause}: three-month average above ${d.limit}% is an amortisation event`} status={d.breached ? "fail" : d.early_warning ? "warning" : "pass"} source={d.source} onSource={onSource}>
        <div className="grid grid-cols-[minmax(0,1fr)_14rem] gap-6">
          <TrendBars values={d.monthly} limit={d.limit} extra={result ? { month: "June 2026", value: result.value, breached: result.breached } : null} />
          <div className="space-y-3">
            <Stat label="Three-month average" value={`${d.average.toFixed(2)}%`} note={`${d.headroom.toFixed(2)} points below the trigger`} tone="warn" />
            <Stat label="June breaches above" value={`${d.next_month_breaches_beyond?.toFixed(2)}%`} note="Recomputed from the tapes" />
          </div>
        </div>
        <div className="mt-5 rounded-lg bg-canvas p-4">
          <p className="text-sm font-semibold">What-if: June 60+ day delinquency</p>
          <div className="mt-3 flex items-center gap-4">
            <input
              type="range"
              min={4.5}
              max={7.5}
              step={0.1}
              value={june}
              onChange={(event) => setJune(Number(event.target.value))}
              aria-label="June delinquency"
              className="flex-1 accent-ink"
            />
            <span className="numeric w-14 text-right font-semibold">{june.toFixed(1)}%</span>
            <Button size="sm" onClick={() => whatIf.mutate(june)} disabled={whatIf.isPending}>
              Run what-if for June
            </Button>
          </div>
          {result && (
            <p role="status" className={clsx("mt-3 text-sm font-medium", result.breached ? "text-danger" : "text-ok")}>
              With June at {result.value.toFixed(1)}%, the average of {result.window.map((m) => m.split(" ")[0]).join(", ")} is {result.average.toFixed(2)}%:{" "}
              {result.breached ? "the trigger is breached and new advances stop." : "the trigger holds."}
            </p>
          )}
        </div>
      </Test>
      <div className="grid grid-cols-2 gap-5">
        <Test title="Excess spread trigger" clause={`${n.excess_spread.clause}: three-month average below ${n.excess_spread.limit}%`} status="pending" source={n.excess_spread.source} onSource={onSource}>
          <div className="flex gap-6">
            {n.excess_spread_months.map((m) => (
              <button key={m.month} type="button" onClick={() => onSource(m.source)} className="cursor-pointer text-left">
                <Stat label={m.month} value={`${m.value.toFixed(2)}%`} note={`Stated ${m.stated}`} />
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted">Recomputed from its parts in each servicer report. May waits for the servicer report, so the three-month test cannot run yet.</p>
        </Test>
        <Test title="Borrowing base" clause="Section 2.3" status="pending" onSource={onSource}>
          <p className="text-sm">{n.borrowing_base.reason}. The May tape and certificate are in, so the test runs as soon as the report arrives.</p>
          <p className="mt-2 text-xs text-muted">
            Collections from the tapes: May {n.collections.change < 0 ? "down" : "up"} {Math.abs(n.collections.change * 100).toFixed(1)}% on April, against {Math.abs(n.collections.last_year_change * 100).toFixed(1)}% last May.
          </p>
        </Test>
      </div>
    </div>
  );
}

function Bramble({ cycle, onSource }: { cycle: Cycle; onSource: (s: Source | null) => void }) {
  const b = cycle.tests.bramble;
  const lev = b.leverage;
  const bb = b.borrowing_base;
  return (
    <div className="space-y-5">
      <Test title="Financial covenant: maximum leverage" clause={`Section 6.12(b): ${lev.maximum.toFixed(2)} to 1.00`} status={lev.with_guarantees > lev.maximum ? "expert" : "pass"} source={lev.clauses[0]} onSource={onSource}>
        <div className="grid grid-cols-3 gap-4">
          <button type="button" onClick={() => onSource(lev.reported_source)} className="cursor-pointer rounded-lg border border-line p-3 text-left hover:border-stone">
            <Stat label="Borrower reports" value={`${lev.reported.toFixed(2)}x`} note="Compliance certificate, Q1" />
          </button>
          <div className="rounded-lg border border-line p-3">
            <Stat label="Recomputed, balance sheet" value={`${lev.recomputed.toFixed(2)}x`} note="Spread from the Q1 statements" tone="ok" />
          </div>
          <button type="button" onClick={() => onSource(lev.guarantees[0]?.source ?? null)} className="cursor-pointer rounded-lg border-2 border-warn p-3 text-left">
            <Stat label="If the guarantee counts" value={`${lev.with_guarantees.toFixed(2)}x`} note={`Adds US$${(lev.guarantees_k / 1000).toFixed(1)}m kept off the balance sheet`} tone="danger" />
          </button>
        </div>
        <p className="mt-4 text-sm">
          The certificate discloses a guarantee of an affiliate's floor plan facility and leaves it out of Total Liabilities, which the agreement defines as liabilities that would appear on a GAAP balance sheet.
          Whether a guarantee counts is a reading of that clause, so it goes to an expert, not to the system.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {lev.clauses.map((clause) => (
            <Button key={clause.label} size="sm" variant="secondary" onClick={() => onSource(clause)}>
              <FileText aria-hidden className="size-3.5" />
              {clause.label?.split(",")[0]} {clause.label?.split(",")[1]}
            </Button>
          ))}
        </div>
      </Test>
      <div className="grid grid-cols-2 gap-5">
        <Test title="Borrowing base against the certificate" clause={`Tolerance US$${bb.tolerance}`} status={bb.within_tolerance ? "pass" : "fail"} onSource={onSource}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
                <th />
                <th className="pb-1 text-right font-semibold">Recomputed</th>
                <th className="pb-1 pl-3 text-right font-semibold">Certificate</th>
              </tr>
            </thead>
            <tbody>
              {(["eligible_pool", "borrowing_base", "availability"] as const).map((key) => (
                <tr key={key} className="border-b border-sand last:border-0">
                  <td className="py-1.5">{{ eligible_pool: "Eligible pool", borrowing_base: "Borrowing base", availability: "Availability" }[key]}</td>
                  <td className="numeric py-1.5 text-right">{usd2(bb.system[key])}</td>
                  <td className="numeric py-1.5 pl-3 text-right text-xs text-muted">{bb.differences[key] >= 0 ? "+" : ""}{bb.differences[key].toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted">Recomputed by the rules engine at the {bb.system.advance_rate_pct}% advance rate in force for May. Certificate differences are within tolerance and logged.</p>
        </Test>
        <Test title="60+ day delinquency trigger" clause={`${b.delinquency.clause}: three-month average above ${b.delinquency.limit}%`} status="pass" onSource={onSource}>
          <Stat label="Three-month average" value={`${b.delinquency.average.toFixed(2)}%`} note={b.delinquency.monthly.map((m) => `${m.month.split(" ")[0]} ${m.value.toFixed(2)}%`).join(", ")} tone="ok" />
        </Test>
      </div>
    </div>
  );
}

function Kestrel({ cycle, onSource }: { cycle: Cycle; onSource: (s: Source | null) => void }) {
  const k = cycle.tests.kestrel;
  const event = k.ltv.events[0];
  const bar = (value: number) => `${(value / 40) * 100}%`;
  return (
    <div className="space-y-5">
      <Test title="Loan-to-value" clause={`${k.ltv.clause}: no more than ${k.ltv.limit}%`} status="expert" source={k.ltv.clauses[0]} onSource={onSource}>
        <div className="space-y-3">
          {[
            { label: "On the reported NAV", value: k.ltv.reported, note: `${usd2(k.drawn).replace(".00", "")} drawn on ${usd2(k.nav).replace(".00", "")} NAV`, source: k.nav_source },
            { label: "Counting the post-quarter markdown", value: k.ltv.with_markdown, note: event ? `${event.position} marked down US$${(event.amount / 1e6).toFixed(0)}m on ${formatDate(event.date)}` : "", source: event?.source ?? null },
          ].map((row) => (
            <button key={row.label} type="button" onClick={() => onSource(row.source)} className="block w-full cursor-pointer text-left">
              <div className="flex items-baseline justify-between text-sm">
                <span className="font-medium">{row.label}</span>
                <span className="numeric text-lg font-semibold">{row.value.toFixed(1)}%</span>
              </div>
              <div className="relative mt-1 h-2.5 rounded bg-sand">
                <div className="h-full rounded bg-subtle" style={{ width: bar(row.value) }} />
                <span className="absolute -top-1 h-4.5 w-0.5 bg-ink" style={{ left: bar(k.ltv.limit) }} />
              </div>
              <p className="mt-1 text-xs text-muted">{row.note}</p>
            </button>
          ))}
        </div>
        <p className="mt-4 text-sm">
          Both pass the {k.ltv.limit}% limit. The question is which NAV the test uses: the agreement adjusts NAV only for a Valuation Event the Manager has declared, and none was. That is a reading of the
          definition, so it goes to an expert.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {k.ltv.clauses.map((clause) => (
            <Button key={clause.label} size="sm" variant="secondary" onClick={() => onSource(clause)}>
              <FileText aria-hidden className="size-3.5" />
              {clause.label?.split(", ")[1]}
            </Button>
          ))}
        </div>
      </Test>
      <div className="grid grid-cols-2 gap-5">
        <Test title="Valuation freshness" clause={`${k.valuations.clause}: valued within ${k.valuations.max_age_days} days`} status={k.valuations.stale.length ? "stale" : "pass"} onSource={onSource}>
          {k.valuations.stale.map((s) => (
            <button key={s.name} type="button" onClick={() => onSource(s.source)} className="block w-full cursor-pointer rounded-lg border border-line p-3 text-left hover:border-stone">
              <p className="text-sm font-semibold">{s.name}</p>
              <p className="numeric text-sm">
                Valued {formatDate(s.valued)}: <strong className="text-warn">{s.age_days} days</strong> before the calculation date
              </p>
            </button>
          ))}
          <p className="mt-2 text-xs text-muted">
            {k.valuations.positions - k.valuations.stale.length} of {k.valuations.positions} positions valued within the limit.
          </p>
        </Test>
        <Test title="Concentration" clause={k.concentration.clause} status={k.concentration.passed ? "pass" : "fail"} onSource={onSource}>
          <div className="flex gap-6">
            <Stat label="Largest position" value={`${k.concentration.largest_pct.toFixed(1)}%`} note={`Limit ${k.concentration.largest_limit}%`} />
            <Stat label="Five largest" value={`${k.concentration.top_five_pct.toFixed(1)}%`} note={`Limit ${k.concentration.top_five_limit}%`} />
          </div>
        </Test>
      </div>
    </div>
  );
}

export function CovenantsPage() {
  const { data: cycle } = useCycle();
  const navigate = useNavigate();
  const [tab, setTab] = useState<FacilityId>("northmoor");
  const [source, setSource] = useState<Source | null | undefined>(undefined);
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const pick = (id: FacilityId) => {
    setTab(id);
    setSource(undefined);
  };
  const fallback = tab === "northmoor" ? cycle.tests.northmoor.delinquency.source : tab === "bramble" ? cycle.tests.bramble.leverage.guarantees[0]?.source : cycle.tests.kestrel.ltv.events[0]?.source;
  return (
    <>
      <PageHeader
        title="Covenants and triggers"
        summary="Recomputed by code from the tapes and the statements, against the terms in force for the period. The system flags; experts and the lender decide."
        actions={
          <Button onClick={() => navigate("/monitoring/collateral")}>
            Collateral
            <ArrowRight aria-hidden className="size-4" />
          </Button>
        }
      />
      <div role="tablist" aria-label="Facility" className="mb-5 flex gap-1 border-b border-line">
        {(["northmoor", "bramble", "kestrel"] as FacilityId[]).map((id) => {
          const facility = cycle.facilities.find((f) => f.id === id)!;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              onClick={() => pick(id)}
              className={clsx("-mb-px flex h-11 cursor-pointer items-center gap-2 border-b-2 px-3 text-sm font-medium", tab === id ? "border-ink text-ink" : "border-transparent text-muted hover:text-ink")}
            >
              {facility.name}
              <FacilityTag id={id} name={facility.asset_class} />
            </button>
          );
        })}
      </div>
      <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-5">
        <div>
          {tab === "northmoor" && <Northmoor cycle={cycle} onSource={setSource} />}
          {tab === "bramble" && <Bramble cycle={cycle} onSource={setSource} />}
          {tab === "kestrel" && <Kestrel cycle={cycle} onSource={setSource} />}
        </div>
        <div className="space-y-2">
          <SectionLabel>Source</SectionLabel>
          <SourcePanel source={source === undefined ? fallback : source} tall />
        </div>
      </div>
    </>
  );
}
