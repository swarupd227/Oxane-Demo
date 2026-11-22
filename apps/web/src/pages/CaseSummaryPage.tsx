import clsx from "clsx";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { Avatar } from "../components/ui/Avatar";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { PageHeader } from "../components/ui/PageHeader";
import { caseworkFileUrl } from "../lib/casework";
import { ownerName, useCases } from "../lib/cases";
import { formatCount, formatDate, formatUsd } from "../lib/format";
import { StagePill } from "./CasesPage";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="py-1.5">
      <dt className="text-[0.6875rem] text-muted">{label}</dt>
      <dd className="numeric text-[0.8125rem] font-medium">{children}</dd>
    </div>
  );
}

export function CaseSummaryPage() {
  const { number } = useParams();
  const { data } = useCases();
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }
  const item = data.cases.find((entry) => entry.number === number);
  if (!item) {
    return (
      <Card className="p-6 text-sm">
        Case {number} not found. <Link to="/cases" className="font-medium underline">All cases</Link>
      </Card>
    );
  }
  const reached = data.stages.indexOf(item.stage);
  const progress: [string, number, number][] = [
    ["Documents received", item.documents.received, item.documents.expected],
    ["Terms extracted", item.terms.extracted, item.terms.total],
    ["Terms approved", item.terms.approved, item.terms.total],
    ["Exceptions worked", item.exceptions.total - item.exceptions.open, item.exceptions.total],
    ["Queries answered", item.queries.total - item.queries.with_client, item.queries.total],
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title={`${item.number} · ${item.facility}`}
        summary={`${item.client} · ${item.deal_type}${item.parent ? ` · backbook of case ${item.parent}` : ""}`}
        actions={
          item.backbook ? (
            <Link
              to="/backbook"
              className="inline-flex h-8 items-center rounded-lg border border-line bg-surface px-3 text-[0.8125rem] font-medium hover:bg-canvas"
            >
              Open backbook load
            </Link>
          ) : undefined
        }
      />
      <ol aria-label="Stage" className="flex overflow-hidden rounded-md border border-line bg-surface text-xs">
        {data.stages.map((stage, index) => (
          <li
            key={stage}
            aria-current={index === reached ? "step" : undefined}
            className={clsx(
              "flex h-8 flex-1 items-center justify-center border-r border-line last:border-0",
              index < reached && "bg-sand text-muted",
              index === reached && "bg-ink font-semibold text-white",
              index > reached && "text-muted",
            )}
          >
            {stage}
          </li>
        ))}
      </ol>
      <div className="grid grid-cols-[minmax(0,1fr)_22rem] items-start gap-4">
        <Card className="overflow-hidden">
          <table className="w-full text-left text-[0.8125rem]">
            <thead>
              <tr className="border-b border-line text-[0.6875rem] font-semibold tracking-[0.04em] text-muted uppercase">
                <th className="py-2 pr-3 pl-4">Progress</th>
                <th className="py-2 pr-3 text-right">Done</th>
                <th className="py-2 pr-3 text-right">Total</th>
                <th className="w-1/3 py-2 pr-4" />
              </tr>
            </thead>
            <tbody>
              {progress.map(([label, done, total]) => (
                <tr key={label} className="border-b border-sand last:border-0">
                  <td className="py-2 pr-3 pl-4">{label}</td>
                  <td className="numeric py-2 pr-3 text-right font-medium">{done}</td>
                  <td className="numeric py-2 pr-3 text-right text-muted">{total}</td>
                  <td className="py-2 pr-4">
                    <div className="h-1.5 rounded bg-sand" aria-hidden>
                      <div className="h-full rounded bg-ink" style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
                    </div>
                  </td>
                </tr>
              ))}
              <tr className="border-b border-sand last:border-0">
                <td className="py-2 pr-3 pl-4">Rules configured</td>
                <td className="numeric py-2 pr-3 text-right font-medium">{item.rules}</td>
                <td colSpan={2} />
              </tr>
              <tr>
                <td className="py-2 pr-3 pl-4">QC variances open</td>
                <td className="numeric py-2 pr-3 text-right font-medium">{item.qc_variances_open}</td>
                <td colSpan={2} />
              </tr>
            </tbody>
          </table>
        </Card>
        <Card className="p-4">
          <SectionLabel>Case</SectionLabel>
          <dl className="mt-1 grid grid-cols-2 gap-x-4">
            <Field label="Stage">
              <StagePill stage={item.stage} />
            </Field>
            <Field label="Owner">
              <span className="flex items-center gap-1.5">
                <Avatar name={ownerName(data, item.owner)} />
                {ownerName(data, item.owner)}
              </span>
            </Field>
            <Field label="Opened">{formatDate(item.opened)}</Field>
            <Field label={item.went_live ? "Live since" : "Target go-live"}>
              {item.went_live ? formatDate(item.went_live) : item.target_go_live ? formatDate(item.target_go_live) : "-"}
            </Field>
            <Field label="Business days open">{item.business_days_open}</Field>
            <Field label="Days in stage">{item.business_days_in_stage ?? "-"}</Field>
            <Field label="Facility limit">{item.limit_usd ? formatUsd(item.limit_usd) : "-"}</Field>
            <Field label={item.deal_type === "Fund finance" ? "Investors" : "Records"}>{formatCount(item.records)}</Field>
            <Field label="Pool balance">{item.pool_balance === null ? "-" : formatUsd(item.pool_balance)}</Field>
            {item.columns && (
              <Field label="Columns mapped">
                {item.columns.matched}/{item.columns.total}
              </Field>
            )}
          </dl>
          {item.file && (
            <a href={caseworkFileUrl(item.file)} className="mt-2 block truncate font-mono text-xs text-info hover:underline">
              {item.file}
            </a>
          )}
        </Card>
      </div>
    </div>
  );
}
