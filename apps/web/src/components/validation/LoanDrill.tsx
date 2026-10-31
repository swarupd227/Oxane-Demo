import { CarFront } from "lucide-react";
import { formatUsd } from "../../lib/format";
import type { BridgeLine, LoanRow } from "../../lib/workbench";
import { SectionLabel } from "../ui/layout";

function PastDueTable({ rows }: { rows: LoanRow[] }) {
  return (
    <div tabIndex={0} role="region" aria-label="Affected loans" className="max-h-96 overflow-y-auto">
      <table className="w-full text-left">
        <thead className="sticky top-0 bg-surface">
          <tr className="border-b border-line text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
            <th className="py-2 pr-4 pl-5">Loan</th>
            <th className="py-2 pr-4 text-right">Days past due</th>
            <th className="py-2 pr-4 text-right">Balance</th>
            <th className="py-2 pr-4 text-right">FICO</th>
            <th className="py-2 pr-4">State</th>
            <th className="py-2 pr-4">Dealer</th>
            <th className="py-2 pr-5">Vehicle</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.loan_id} className="numeric border-b border-sand text-sm last:border-0">
              <td className="py-1.5 pr-4 pl-5 font-medium">{row.loan_id}</td>
              <td className="py-1.5 pr-4 text-right">{row.days_past_due}</td>
              <td className="py-1.5 pr-4 text-right">{formatUsd(row.balance)}</td>
              <td className="py-1.5 pr-4 text-right">{row.fico}</td>
              <td className="py-1.5 pr-4">{row.state}</td>
              <td className="py-1.5 pr-4">{row.dealer}</td>
              <td className="py-1.5 pr-5 text-muted">{row.vehicle}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VinClusters({ rows }: { rows: LoanRow[] }) {
  const clusters = new Map<string, LoanRow[]>();
  for (const row of rows) {
    clusters.set(row.vin, [...(clusters.get(row.vin) ?? []), row]);
  }

  return (
    <div className="grid grid-cols-3 gap-4 p-5">
      {[...clusters].map(([vin, loans]) => (
        <div key={vin} className="rounded-lg border border-line">
          <div className="flex items-center gap-2 border-b border-line bg-canvas px-3 py-2">
            <CarFront aria-hidden className="size-4 shrink-0 text-muted" />
            <div className="min-w-0">
              <p className="truncate font-mono text-[0.8125rem] font-medium">{vin}</p>
              <p className="truncate text-xs text-muted">{loans[0].vehicle}</p>
            </div>
          </div>
          {loans.map((loan) => (
            <div key={loan.loan_id} className="border-b border-sand px-3 py-2 last:border-0">
              <div className="numeric flex items-baseline justify-between text-sm">
                <span className="font-medium">{loan.loan_id}</span>
                <span>{formatUsd(loan.balance)}</span>
              </div>
              <p className="truncate text-xs text-muted">
                {loan.dealer}, {loan.state}
              </p>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export function LoanDrill({ line }: { line: BridgeLine }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-4 border-b border-line px-5 py-3">
        <div>
          <SectionLabel>
            {line.rule_id}: {line.label}
          </SectionLabel>
          <p className="mt-1 text-sm font-medium">
            {line.rule_id === "E12"
              ? "Each VIN appears on two loans. This may be double pledging, within this pool only."
              : `${line.loans} loans the certificate counted as eligible`}
          </p>
        </div>
        <span className="numeric text-sm font-semibold">{formatUsd(line.amount)}</span>
      </div>
      {line.rule_id === "E12" ? <VinClusters rows={line.rows} /> : <PastDueTable rows={line.rows} />}
    </div>
  );
}
