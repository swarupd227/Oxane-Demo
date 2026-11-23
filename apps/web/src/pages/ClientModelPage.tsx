import clsx from "clsx";
import { FileSpreadsheet } from "lucide-react";
import { useState } from "react";
import { EvidencePanel } from "../components/evidence/EvidencePanel";
import { ProvenanceChip, StatusPill } from "../components/ui/badges";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, NextStep, PageHeader } from "../components/ui/PageHeader";
import { caseworkFileUrl, useCasework, usd2, type ModelRow } from "../lib/casework";
import { useSession } from "../lib/session";
import { useWorkbench } from "../lib/workbench";

const STATUS: Record<ModelRow["status"], { status: "approved" | "review" | "open" | "pending"; label: string }> = {
  agrees: { status: "approved", label: "Agrees" },
  differs: { status: "review", label: "Differs: query" },
  silent: { status: "open", label: "Agreement silent: query" },
  adopted: { status: "pending", label: "Reporting: adopted" },
  not_compared: { status: "pending", label: "Not compared" },
};

function change(row: ModelRow): string {
  if (row.borrowing_base_change) {
    const sign = row.borrowing_base_change > 0 ? "+" : "-";
    return `${sign}US$${usd2.format(Math.abs(row.borrowing_base_change))}`;
  }
  return row.status === "differs" || row.status === "silent" ? "None this month" : "";
}

export function ClientModelPage() {
  const { state } = useSession();
  const workbench = useWorkbench();
  const { data } = useCasework();
  const [selected, setSelected] = useState("advance_rate");

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (!data || !workbench.data) {
    return <Skeleton className="h-96 w-full" />;
  }

  const model = data.client_model;
  const parameters = model.rows.filter((row) => row.kind === "parameter");
  const reporting = model.rows.filter((row) => row.kind === "reporting");
  const differences = parameters.filter((row) => row.status === "differs" || row.status === "silent");
  const total = differences.reduce((sum, row) => sum + (row.borrowing_base_change ?? 0), 0);
  const current = model.rows.find((row) => row.topic === selected) ?? differences[0];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Agreement against the client's model"
        summary={`${model.file} · template v${model.template_version} · against rule set v1`}
        actions={
          <a
            href={caseworkFileUrl(model.file)}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-line bg-surface px-4 text-sm font-medium hover:bg-canvas"
          >
            <FileSpreadsheet aria-hidden className="size-4" />
            Client's model
          </a>
        }
      />

      <div className="grid grid-cols-3 gap-3">
        <Card className="px-4 py-3">
          <SectionLabel>Cells read</SectionLabel>
          <p className="numeric mt-0.5 text-lg font-semibold">
            {model.rows.length}
            <span className="text-base font-normal text-muted"> cells</span>
          </p>
          <p className="text-xs text-muted">
            {model.rows.length} verified · {model.rejected.length} rejected
          </p>
        </Card>
        <Card className="px-4 py-3">
          <SectionLabel>Differences</SectionLabel>
          <p className="numeric mt-0.5 text-lg font-semibold">{differences.length}</p>
          <p className="text-xs text-muted">{differences.length} queries raised</p>
        </Card>
        <Card className="px-4 py-3">
          <SectionLabel>Borrowing base effect, sum of differences</SectionLabel>
          <p className="numeric mt-0.5 text-lg font-semibold">US${usd2.format(total)}</p>
          <p className="text-xs text-muted">
            Availability per agreement US$
            {usd2.format(Number(data.qc.lines.find((line) => line.line === "Availability")?.platform ?? 0))}
          </p>
        </Card>
      </div>

      <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] items-start gap-4">
        <Card className="overflow-hidden">
          <table className="w-full text-left text-[0.8125rem]">
            <thead>
              <tr className="border-b border-line text-xs font-medium text-subtle">
                <th className="py-2 pr-3 pl-4">Point</th>
                <th className="py-2 pr-3">Client's model</th>
                <th className="py-2 pr-3">Agreement</th>
                <th className="py-2 pr-3 text-right">Effect on April</th>
                <th className="py-2 pr-4">Status</th>
              </tr>
            </thead>
            <tbody>
              {parameters.map((row) => (
                <tr
                  key={row.topic}
                  onClick={() => setSelected(row.topic)}
                  className={clsx(
                    "cursor-pointer border-b border-sand align-top last:border-0",
                    row.topic === current?.topic ? "bg-sand" : "hover:bg-canvas",
                  )}
                >
                  <td className="py-2 pr-3 pl-4 font-medium">
                    {row.label}
                    <span className="block font-mono text-[0.6875rem] font-normal text-muted">
                      {row.cell}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-muted">{row.quote}</td>
                  <td className="py-2 pr-3">{row.agreement}</td>
                  <td className="numeric py-2 pr-3 text-right font-medium">{change(row)}</td>
                  <td className="py-2 pr-4">
                    <StatusPill {...STATUS[row.status]} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <div className="sticky top-14 space-y-3">
          {current && (
            <Card className="space-y-2 p-4 text-[0.8125rem]">
              <div className="flex items-center justify-between gap-2">
                <SectionLabel>{current.label}</SectionLabel>
                <ProvenanceChip kind="extracted" detail={`cell ${current.cell}`} tip={`“${current.quote}”`} />
              </div>
              <p>
                <span className="font-medium">Client's model, {current.cell}:</span> {current.reading}
              </p>
              <p>
                <span className="font-medium">Agreement, {current.clause}:</span>{" "}
                {current.agreement}
              </p>
              {current.impact && (
                <p className="rounded-md bg-canvas px-3 py-2">
                  <span className="font-medium">Impact:</span> {current.impact}.
                  {current.availability_with_model !== undefined &&
                    current.borrowing_base_change !== 0 &&
                    ` Availability would read US$${usd2.format(current.availability_with_model)}.`}
                </p>
              )}
            </Card>
          )}
          <EvidencePanel
            citation={current?.source}
            documents={workbench.data.documents}
            emptyText="No provision in the agreement"
          />
        </div>
      </div>

      <Card className="p-4">
        <SectionLabel>Reporting requirements</SectionLabel>
        <ul className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-[0.8125rem]">
          {reporting.map((row) => (
            <li key={row.topic}>
              <span className="font-mono text-xs text-muted">{row.cell}</span> {row.quote}
            </li>
          ))}
        </ul>
      </Card>

      <div className="flex justify-end">
        <NextStep to="/queries" label="Query tracker" />
      </div>
    </div>
  );
}
