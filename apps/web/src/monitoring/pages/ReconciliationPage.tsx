import clsx from "clsx";
import { ArrowRight, Calculator, FileText, ListTree } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { PageHeader } from "../../components/ui/PageHeader";
import { useCycle, type Source } from "../cycle";
import { SourcePanel, usd2 } from "../parts";

interface Line {
  label: string;
  amount: number;
  sign: "" | "+" | "-" | "=";
  note: string;
  source?: Source | null;
  emphasis?: boolean;
}

export function ReconciliationPage() {
  const { data: cycle } = useCycle();
  const navigate = useNavigate();
  const [source, setSource] = useState<Source | null | undefined>(undefined);
  const [drill, setDrill] = useState<"missing" | "charge" | null>(null);
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const roll = cycle.reconciliation.roll_forward;
  const offs = cycle.reconciliation.charge_offs;
  const lines: Line[] = [
    { label: "April tape pool balance", amount: roll.opening, sign: "", note: "Last month's tape, from the facility record" },
    { label: `New loans purchased (${roll.new_loans})`, amount: roll.additions, sign: "+", note: "On the May tape, not on April's" },
    { label: "Principal collections", amount: roll.collections, sign: "-", note: "Servicer report, section 1", source: roll.sources.collections },
    { label: "Charge-offs on the tape", amount: roll.charge_offs, sign: "-", note: "May tape, status charged off" },
    { label: "Expected May pool balance", amount: roll.expected, sign: "=", note: "Calculated", emphasis: true },
    { label: "May tape pool balance", amount: roll.actual, sign: "", note: "As delivered", emphasis: true },
  ];
  const shown = source === undefined ? roll.sources.collections : source;
  return (
    <>
      <PageHeader
        title="Reconciliation: Bramble, May 2026"
        summary="Each new tape is rolled forward from the last one and checked against the servicer report. No AI here: every figure is calculated, and every gap is traced to rows."
        actions={
          <Button onClick={() => navigate("/monitoring/terms")}>
            Effective terms
            <ArrowRight aria-hidden className="size-4" />
          </Button>
        }
      />
      <div className="grid grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] gap-5">
        <div className="space-y-5">
          <Card>
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <p className="flex items-center gap-2 font-semibold">
                <Calculator aria-hidden className="size-4 text-muted" />
                Tape roll-forward
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
                    <p className="text-xs text-muted">Expected less delivered</p>
                  </td>
                  <td className={clsx("numeric py-3 pr-5 text-right text-lg font-semibold", roll.within_tolerance ? "text-ok" : "text-danger")}>{usd2(roll.gap)}</td>
                </tr>
              </tbody>
            </table>
            {!roll.within_tolerance && (
              <div className="flex items-center justify-between gap-4 px-5 py-3">
                <p className="text-sm">
                  The gap traces to <strong>{roll.missing.length} loans</strong> on the April tape that the May tape does not list at all, not even as paid off or charged off.
                </p>
                <Button size="sm" onClick={() => setDrill("missing")}>
                  <ListTree aria-hidden className="size-3.5" />
                  Open the {roll.missing.length} loans
                </Button>
              </div>
            )}
          </Card>

          <Card>
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <p className="flex items-center gap-2 font-semibold">
                <Calculator aria-hidden className="size-4 text-muted" />
                Tape against servicer report: charge-offs
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
              <p className="text-sm">
                <strong>{offs.loans.length} loans</strong> are charged off in the report's schedule but live on the tape.
              </p>
              <Button size="sm" variant="secondary" onClick={() => setDrill("charge")}>
                <ListTree aria-hidden className="size-3.5" />
                Open the {offs.loans.length} loans
              </Button>
            </div>
          </Card>
        </div>
        <div className="space-y-2">
          <SectionLabel>Source</SectionLabel>
          <SourcePanel source={shown} tall />
        </div>
      </div>

      <Dialog open={drill === "missing"} onOpenChange={(open) => !open && setDrill(null)} title={`${roll.missing.length} loans missing from the May tape`} description={`Last seen on the April tape with balances totalling ${usd2(roll.missing_april_balance)}. The servicer collected on them in May, so they belong in the pool.`}>
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
      <Dialog open={drill === "charge"} onOpenChange={(open) => !open && setDrill(null)} title={`${offs.loans.length} loans charged off in the report, live on the tape`} description={`The report charges off ${usd2(offs.difference)} more than the tape.`}>
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
            Show the report's schedule
          </Button>
        )}
      </Dialog>
    </>
  );
}
