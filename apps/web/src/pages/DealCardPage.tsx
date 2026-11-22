import { RotateCw } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Avatar } from "../components/ui/Avatar";
import { Button } from "../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NextStep, PageHeader } from "../components/ui/PageHeader";
import { Timeline } from "../components/ui/Timeline";
import { useCase, type Deal } from "../lib/api";
import { useCases } from "../lib/cases";
import { formatCount, formatDate, formatUsd } from "../lib/format";
import { useSession } from "../lib/session";
import { StagePill } from "./CasesPage";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="py-1.5">
      <dt className="text-[0.6875rem] text-muted">{label}</dt>
      <dd className="text-[0.8125rem] font-medium">{children}</dd>
    </div>
  );
}

function Progress() {
  const { data } = useCases();
  const item = data?.cases.find((entry) => entry.active);
  if (!item) {
    return <Skeleton className="h-40 w-full" />;
  }
  const rows: [string, string, number, number][] = [
    ["Documents received", "/intake", item.documents.received, item.documents.expected],
    ["Terms approved", "/terms", item.terms.approved, item.terms.total],
    ["Exceptions worked", "/exceptions", item.exceptions.total - item.exceptions.open, item.exceptions.total],
    ["Queries closed or answered", "/queries", item.queries.total - item.queries.with_client, item.queries.total],
  ];
  return (
    <table className="w-full text-left text-[0.8125rem]">
      <tbody>
        {rows.map(([label, to, done, total]) => (
          <tr key={label} className="border-b border-sand last:border-0">
            <td className="py-1.5 pr-3">
              <Link to={to} className="hover:underline">
                {label}
              </Link>
            </td>
            <td className="numeric w-16 py-1.5 pr-3 text-right font-medium">
              {done}/{total}
            </td>
            <td className="w-1/3 py-1.5">
              <div className="h-1.5 rounded bg-sand" aria-hidden>
                <div className="h-full rounded bg-ink" style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
              </div>
            </td>
          </tr>
        ))}
        <tr>
          <td className="py-1.5 pr-3">
            <Link to="/qc" className="hover:underline">
              QC variances open
            </Link>
          </td>
          <td className="numeric py-1.5 pr-3 text-right font-medium">{item.qc_variances_open}</td>
          <td />
        </tr>
      </tbody>
    </table>
  );
}

function Overview({ deal, number }: { deal: Deal; number: string }) {
  const { facility, lender, borrower, pricing, analysts } = deal;
  const { state } = useSession();
  const { data: pipeline } = useCases();
  const stage = pipeline?.cases.find((entry) => entry.active)?.stage;
  const goLive = deal.case.target_go_live;

  return (
    <div className="space-y-4">
      <PageHeader
        title={`${number} · ${borrower.name}`}
        summary={`${lender.name} · ${facility.type} · ${formatUsd(facility.limit_usd)}`}
        actions={
          <>
            {stage && <StagePill stage={stage} />}
            <NextStep to="/intake" label="Start onboarding" />
          </>
        }
      />
      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_22rem] items-start gap-4">
        <Card className="p-4">
          <SectionLabel>Facility</SectionLabel>
          <dl className="mt-1 grid grid-cols-2 gap-x-4">
            <Field label="Lender">{lender.name}</Field>
            <Field label="Desk">{lender.desk}</Field>
            <Field label="Borrower">{borrower.name}</Field>
            <Field label="Parent">{borrower.parent}</Field>
            <Field label="Facility">{facility.type}</Field>
            <Field label="Limit">
              <span className="numeric">{formatUsd(facility.limit_usd)}</span>
            </Field>
            <Field label="Collateral">{facility.collateral}</Field>
            <Field label="First tape">
              <span className="numeric">{formatCount(facility.first_tape_loans)} loans</span>
            </Field>
            <Field label="Margin">{pricing.margin}</Field>
            <Field label="Unused fee">{pricing.unused_fee}</Field>
          </dl>
        </Card>
        <div className="space-y-4">
          <Card className="p-4">
            <SectionLabel>Key dates</SectionLabel>
            <table className="mt-1 w-full text-[0.8125rem]">
              <tbody>
                {deal.dates.map((item) => (
                  <tr key={item.label} className="border-b border-sand last:border-0">
                    <td className="py-1.5 pr-3 text-muted">{item.label}</td>
                    <td className="numeric py-1.5 text-right font-medium">{formatDate(item.date)}</td>
                  </tr>
                ))}
                <tr>
                  <td className="py-1.5 pr-3 text-muted">Target go-live</td>
                  <td className="numeric py-1.5 text-right font-medium">{goLive ? formatDate(goLive) : "Not set"}</td>
                </tr>
              </tbody>
            </table>
          </Card>
          <Card className="p-4">
            <SectionLabel>Progress</SectionLabel>
            <div className="mt-1">
              <Progress />
            </div>
          </Card>
        </div>
        <div className="space-y-4">
          <Card className="p-4">
            <SectionLabel>Team</SectionLabel>
            <ul className="mt-2 space-y-2 text-[0.8125rem]">
              <li className="flex items-center gap-2">
                <Avatar name="Onboarding analyst" />
                <span>
                  <span className="block font-medium">{analysts.preparer}</span>
                  <span className="block text-[0.6875rem] text-muted">Preparer</span>
                </span>
              </li>
              <li className="flex items-center gap-2">
                <Avatar name="Second analyst" />
                <span>
                  <span className="block font-medium">Second analyst</span>
                  <span className="block text-[0.6875rem] text-muted">Reviewer, four-eyes</span>
                </span>
              </li>
            </ul>
          </Card>
          <Card className="p-4">
            <SectionLabel>Activity</SectionLabel>
            <Timeline className="mt-2" entries={[...state.audit].reverse().slice(0, 6)} empty="No activity yet" />
            {state.audit.length > 6 && (
              <Link to="/approve#audit" className="mt-2 block text-xs font-medium text-info hover:underline">
                Full audit log ({state.audit.length})
              </Link>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

export function DealCardPage() {
  const { data, isPending, isError, refetch } = useCase();

  return (
    <div>
      {data && <Overview deal={data.deal} number={data.number} />}
      {isPending && (
        <Card className="space-y-3 p-6" role="status" aria-label="Loading case">
          <Skeleton className="h-5 w-80" />
          <Skeleton className="h-4 w-56" />
          <Skeleton className="h-40 w-full" />
        </Card>
      )}
      {isError && !data && (
        <Card role="alert" className="p-5">
          <p className="font-medium">The case could not be loaded.</p>
          <Button variant="secondary" className="mt-3" onClick={() => void refetch()}>
            <RotateCw aria-hidden className="size-4" />
            Try again
          </Button>
        </Card>
      )}
    </div>
  );
}
