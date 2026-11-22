import clsx from "clsx";
import { Calculator, FileText, ListTree } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { PageTitle } from "../ui";
import { useCycle, type Source } from "../cycle";
import { NoAiBadge, SourcePanel, usd2 } from "../parts";

interface Line {
  label: string;
  amount: number;
  sign: "" | "+" | "-" | "=";
  note: string;
  source?: Source | null;
  emphasis?: boolean;
}

/** Larkspur's positions rolled forward from April: trades explain every change but one, which is
 * the same loan under new identifiers. Code only: Thornbury does not permit AI. */
function LarkspurPositions() {
  const { data: cycle } = useCycle();
  if (!cycle) {
    return null;
  }
  const l = cycle.tests.larkspur;
  const roll = l.par_roll;
  const m = (v: number) => `US$${(v / 1e6).toFixed(2)}m`;
  return (
    <Card className="mt-3">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <p className="flex items-center gap-2 text-[0.8125rem] font-semibold">
          <Calculator aria-hidden className="size-4 text-muted" />
          Larkspur par roll-forward, Apr to May
          <NoAiBadge compact />
        </p>
        <SectionLabel>{l.positions_file}</SectionLabel>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-4 p-3">
        <table className="w-full text-sm">
          <tbody>
            {[
              ["Par at 30 April", roll.opening, ""],
              ["Sold (trade record)", roll.sold, "-"],
              ["Bought (trade records)", roll.bought, "+"],
              ["Expected par at 29 May", roll.expected, "="],
              ["Par on the May report", roll.closing, ""],
            ].map(([label, value, sign]) => (
              <tr key={label as string} className="border-b border-sand last:border-0">
                <td className="w-6 py-1.5 text-muted">{sign}</td>
                <td className="py-1.5">{label}</td>
                <td className="numeric py-1.5 text-right">{m(value as number)}</td>
              </tr>
            ))}
            <tr>
              <td />
              <td className="py-1.5 font-semibold">Gap</td>
              <td className="numeric py-1.5 text-right font-semibold text-ok">{m(roll.gap)}</td>
            </tr>
          </tbody>
        </table>
        <div className="space-y-3">
          {l.changes.relinked.map((c) => (
            <div key={c.old_loanx} className="rounded-lg border-2 border-info/40 p-3 text-sm">
              <p className="font-semibold">Identifier change linked</p>
              <p className="mt-1">
                {c.issuer}: LoanX <span className="font-mono">{c.old_loanx}</span> → <span className="font-mono">{c.new_loanx}</span>, CUSIP <span className="font-mono">{c.old_cusip}</span> →{" "}
                <span className="font-mono">{c.new_cusip}</span>.
              </p>
              <p className="mt-1 text-xs text-muted">
                No trade · matched on {c.matched_on.join(", ").replace("_bps", "")} · history carried over · logged
              </p>
            </div>
          ))}
          <p className="text-xs text-muted">
            Trades: {l.changes.sold.length} sold, {l.changes.bought.length} bought · unexplained {l.changes.unexplained_gone.length + l.changes.unexplained_new.length}
          </p>
        </div>
      </div>
    </Card>
  );
}

export function ReconciliationPage() {
  const { data: cycle } = useCycle();
  const [source, setSource] = useState<Source | null | undefined>(undefined);
  const [drill, setDrill] = useState<"missing" | "charge" | null>(null);
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const roll = cycle.reconciliation.roll_forward;
  const offs = cycle.reconciliation.charge_offs;
  const lines: Line[] = [
    { label: "April tape pool balance", amount: roll.opening, sign: "", note: "April tape" },
    { label: `New loans purchased (${roll.new_loans})`, amount: roll.additions, sign: "+", note: "May tape, new loan IDs" },
    { label: "Principal collections", amount: roll.collections, sign: "-", note: "Servicer report, section 1", source: roll.sources.collections },
    { label: "Charge-offs on the tape", amount: roll.charge_offs, sign: "-", note: "May tape, status charged off" },
    { label: "Expected May pool balance", amount: roll.expected, sign: "=", note: "Calculated", emphasis: true },
    { label: "May tape pool balance", amount: roll.actual, sign: "", note: "May tape", emphasis: true },
  ];
  const shown = source === undefined ? roll.sources.collections : source;
  return (
    <>
      <PageTitle title="Reconciliation" meta={`${cycle.cycle.label} · Bramble, Larkspur`} />
      <div className="grid grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] gap-3">
        <div className="space-y-3">
          <Card>
            <div className="flex items-center justify-between border-b border-line px-3 py-2">
              <p className="flex items-center gap-2 text-[0.8125rem] font-semibold">
                <Calculator aria-hidden className="size-4 text-muted" />
                Bramble tape roll-forward
              </p>
              <SectionLabel>Tolerance US${cycle.tolerances.roll_forward_usd}</SectionLabel>
            </div>
            <table className="w-full">
              <tbody>
                {lines.map((line) => (
                  <tr key={line.label} className={clsx("border-b border-sand", line.emphasis && "bg-canvas")}>
                    <td className="w-14 py-2.5 pr-2 pl-5 text-center font-mono text-base font-semibold text-muted">{line.sign}</td>
                    <td className="py-2.5 pr-3">
                      <p className={clsx("text-sm", line.emphasis && "font-semibold")}>{line.label}</p>
                      <p className="text-xs text-muted">
                        {line.source ? (
                          <button type="button" onClick={() => setSource(line.source)} className="inline-flex cursor-pointer items-center gap-1 font-medium text-info hover:underline">
                            <FileText aria-hidden className="size-3" />
                            {line.note}
                          </button>
                        ) : (
                          line.note
                        )}
                      </p>
                    </td>
                    <td className={clsx("numeric py-2.5 pr-5 text-right text-sm", line.emphasis && "font-semibold")}>{usd2(line.amount)}</td>
                  </tr>
                ))}
                <tr className={clsx(roll.within_tolerance ? "bg-ok-tint" : "bg-danger-tint")}>
                  <td className="pl-5" />
                  <td className="py-3 pr-3">
                    <p className={clsx("text-sm font-semibold", roll.within_tolerance ? "text-ok" : "text-danger")}>Gap</p>
                    <p className="text-xs text-muted">Expected less May tape</p>
                  </td>
                  <td className={clsx("numeric py-3 pr-5 text-right text-lg font-semibold", roll.within_tolerance ? "text-ok" : "text-danger")}>{usd2(roll.gap)}</td>
                </tr>
              </tbody>
            </table>
            {!roll.within_tolerance && (
              <div className="flex items-center justify-between gap-4 px-5 py-3">
                <p className="text-[0.8125rem]">
                  <strong className="numeric">{roll.missing.length} loans</strong> on April tape, absent from May tape
                </p>
                <Button size="sm" onClick={() => setDrill("missing")}>
                  <ListTree aria-hidden className="size-3.5" />
                  View {roll.missing.length} loans
                </Button>
              </div>
            )}
          </Card>

          <Card>
            <div className="flex items-center justify-between border-b border-line px-3 py-2">
              <p className="flex items-center gap-2 text-[0.8125rem] font-semibold">
                <Calculator aria-hidden className="size-4 text-muted" />
                Charge-offs: tape against servicer report
              </p>
            </div>
            <div className="grid grid-cols-3 gap-4 px-5 py-4">
              <div>
                <p className="text-xs text-muted">On the tape</p>
                <p className="numeric text-lg font-semibold">{usd2(offs.tape)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">
                  <button type="button" onClick={() => setSource(offs.source)} className="inline-flex cursor-pointer items-center gap-1 font-medium text-info hover:underline">
                    <FileText aria-hidden className="size-3" />
                    In the servicer report
                  </button>
                </p>
                <p className="numeric text-lg font-semibold">{usd2(offs.report)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">Difference</p>
                <p className="numeric text-lg font-semibold text-danger">{usd2(offs.difference)}</p>
              </div>
            </div>
            <div className="flex items-center justify-between gap-4 border-t border-sand px-5 py-3">
              <p className="text-[0.8125rem]">
                <strong className="numeric">{offs.loans.length} loans</strong> charged off in report schedule, live on tape
              </p>
              <Button size="sm" variant="secondary" onClick={() => setDrill("charge")}>
                <ListTree aria-hidden className="size-3.5" />
                View {offs.loans.length} loans
              </Button>
            </div>
          </Card>
        </div>
        <div className="space-y-2">
          <SectionLabel>Source</SectionLabel>
          <SourcePanel source={shown} tall />
        </div>
      </div>
      <LarkspurPositions />

      <Dialog open={drill === "missing"} onOpenChange={(open) => !open && setDrill(null)} title={`${roll.missing.length} loans missing from the May tape`} description={`April balance ${usd2(roll.missing_april_balance)}`}>
        <div className="max-h-[60vh] overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-surface">
              <tr className="border-b border-line text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
                <th className="py-2 pr-2">Loan</th>
                <th className="py-2 pr-2">Dealer</th>
                <th className="py-2 pr-2">State</th>
                <th className="py-2 text-right">April balance</th>
              </tr>
            </thead>
            <tbody>
              {roll.missing.map((loan) => (
                <tr key={loan.loan_id} className="border-b border-sand">
                  <td className="numeric py-1.5 pr-2 font-medium">{loan.loan_id}</td>
                  <td className="truncate py-1.5 pr-2 text-muted">{loan.dealer}</td>
                  <td className="py-1.5 pr-2 text-muted">{loan.state}</td>
                  <td className="numeric py-1.5 text-right">{usd2(loan.april_balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Dialog>
      <Dialog open={drill === "charge"} onOpenChange={(open) => !open && setDrill(null)} title={`${offs.loans.length} loans charged off in the report, live on the tape`} description={`Difference ${usd2(offs.difference)}`}>
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-line text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
              <th className="py-2 pr-2">Loan</th>
              <th className="py-2 pr-2">Tape status</th>
              <th className="py-2 pr-2 text-right">Days past due</th>
              <th className="py-2 text-right">Report charge-off</th>
            </tr>
          </thead>
          <tbody>
            {offs.loans.map((loan) => (
              <tr key={loan.loan_id} className="border-b border-sand">
                <td className="numeric py-1.5 pr-2 font-medium">{loan.loan_id}</td>
                <td className="py-1.5 pr-2 text-muted">{loan.tape_status.toLowerCase()}</td>
                <td className="numeric py-1.5 pr-2 text-right">{loan.days_past_due}</td>
                <td className="numeric py-1.5 text-right">{usd2(loan.report_amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {offs.schedule_source && (
          <Button className="mt-3" variant="secondary" size="sm" onClick={() => { setSource(offs.schedule_source); setDrill(null); }}>
            <FileText aria-hidden className="size-3.5" />
            Report schedule
          </Button>
        )}
      </Dialog>
    </>
  );
}
