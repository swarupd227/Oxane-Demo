import clsx from "clsx";
import { CheckCircle2, CircleAlert, Download } from "lucide-react";
import { useState } from "react";
import { StatusPill } from "../components/ui/badges";
import { Card, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader } from "../components/ui/PageHeader";
import { useCasework, type Threshold } from "../lib/casework";
import { useSession } from "../lib/session";

type Tab = "thresholds" | "fields" | "report" | "conventions";

const TABS: { id: Tab; label: string }[] = [
  { id: "thresholds", label: "Rules and thresholds" },
  { id: "fields", label: "Field map" },
  { id: "report", label: "Report lines" },
  { id: "conventions", label: "Client conventions" },
];

const head =
  "border-b border-line text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase";

function ThresholdRow({ row }: { row: Threshold }) {
  return (
    <tr className="border-b border-sand align-top last:border-0">
      <td className="numeric py-2 pr-3 pl-4 font-mono text-xs whitespace-nowrap">{row.id}</td>
      <td className="py-2 pr-3 text-muted">{row.area}</td>
      <td className="py-2 pr-3">
        {row.term ?? row.parameter}
        {row.change && <p className="mt-0.5 text-xs text-warn">Changed: {row.change}</p>}
      </td>
      <td className="numeric py-2 pr-3 font-medium">{row.value}</td>
      <td className="numeric py-2 pr-3">{row.engine}</td>
      <td className="py-2 pr-3 text-xs text-muted">
        {row.clause}
        {row.source && `, p. ${row.source.page}`}
      </td>
      <td className="py-2 pr-4">
        {row.in_source ? (
          <span className="flex items-center gap-1 text-xs font-medium text-ok">
            <CheckCircle2 aria-hidden className="size-3.5" />
            Matches source
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs font-medium text-warn">
            <CircleAlert aria-hidden className="size-3.5" />
            Differs from source
          </span>
        )}
        {row.term && !row.validated && (
          <span className="mt-0.5 block text-xs text-muted">Term not yet approved</span>
        )}
      </td>
    </tr>
  );
}

export function ConfigurationPage() {
  const { state } = useSession();
  const { data } = useCasework();
  const [tab, setTab] = useState<Tab>("thresholds");

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }
  const config = data.config;
  const matched = config.thresholds.filter((row) => row.in_source).length;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Configuration workbook"
        summary={`Case 0412 · ${config.thresholds.length} thresholds · ${config.fields.length} fields · ${config.report.length} report lines · rule set ${config.ruleset_digest.slice(0, 12)}`}
        actions={
          <a
            href="/api/casework/config-workbook.xlsx"
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-4 text-sm font-medium text-white hover:bg-accent-strong"
          >
            <Download aria-hidden className="size-4" />
            Export .xlsx
          </a>
        }
      />

      <div
        className={clsx(
          "flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg px-4 py-3 text-sm",
          config.status.final ? "bg-ok-tint" : "bg-warn-tint",
        )}
      >
        <StatusPill
          status={config.status.final ? "approved" : "review"}
          label={config.status.final ? "Final" : "Provisional"}
        />
        <span>Prepared: {config.status.prepared_by}</span>
        <span>Approved: {config.status.approved_by ?? "Pending"}</span>
        <span>QC: {config.status.qc_passed ? "Passed" : "Open variances"}</span>
        <span>First report: {config.status.released ? config.status.released.slice(0, 10) : "Not released"}</span>
        <span className="numeric ml-auto font-medium">
          Thresholds matching source {matched}/{config.thresholds.length}
        </span>
      </div>

      <div role="tablist" className="flex gap-1">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={clsx(
              "cursor-pointer rounded-md px-3 py-1.5 text-sm",
              tab === item.id ? "bg-accent-tint text-accent-strong font-medium" : "text-muted hover:bg-sand",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      <Card className="overflow-x-auto">
        {tab === "thresholds" && (
          <table className="w-full text-left text-[0.8125rem]">
            <thead>
              <tr className={head}>
                <th className="py-2 pr-3 pl-4">ID</th>
                <th className="py-2 pr-3">Area</th>
                <th className="py-2 pr-3">Parameter</th>
                <th className="py-2 pr-3">Configured</th>
                <th className="py-2 pr-3">Engine</th>
                <th className="py-2 pr-3">Source</th>
                <th className="py-2 pr-4">Check</th>
              </tr>
            </thead>
            <tbody>
              {config.thresholds.map((row) => (
                <ThresholdRow key={row.id} row={row} />
              ))}
            </tbody>
          </table>
        )}
        {tab === "fields" && (
          <table className="w-full text-left text-[0.8125rem]">
            <thead>
              <tr className={head}>
                <th className="py-2 pr-3 pl-4">Source field</th>
                <th className="py-2 pr-3">Sample</th>
                <th className="py-2 pr-3">Loader field</th>
                <th className="py-2 pr-3">Transform</th>
                <th className="py-2 pr-4">Expected output</th>
              </tr>
            </thead>
            <tbody>
              {config.fields.map((row) => (
                <tr key={row.source} className="border-b border-sand last:border-0">
                  <td className="py-1.5 pr-3 pl-4 font-mono text-xs">{row.source}</td>
                  <td className="numeric py-1.5 pr-3 text-muted">{row.sample}</td>
                  <td className="py-1.5 pr-3 font-mono text-xs">{row.field}</td>
                  <td className="py-1.5 pr-3 text-muted">{row.transform}</td>
                  <td className="numeric py-1.5 pr-4">{row.expected}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tab === "report" && (
          <table className="w-full text-left text-[0.8125rem]">
            <thead>
              <tr className={head}>
                <th className="py-2 pr-3 pl-4">Line</th>
                <th className="py-2 pr-3 text-right">Platform</th>
                <th className="py-2 pr-3">Unit</th>
                <th className="py-2 pr-4 text-right">Client format</th>
              </tr>
            </thead>
            <tbody>
              {config.report.map((row) => (
                <tr key={row.line} className="border-b border-sand last:border-0">
                  <td className="py-1.5 pr-3 pl-4">{row.line}</td>
                  <td className="numeric py-1.5 pr-3 text-right">
                    {row.value === null ? "" : row.value.toLocaleString("en-US")}
                  </td>
                  <td className="py-1.5 pr-3 text-muted">{row.unit}</td>
                  <td className="numeric py-1.5 pr-4 text-right font-medium">{row.client_format}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tab === "conventions" && (
          <table className="w-full text-left text-[0.8125rem]">
            <thead>
              <tr className={head}>
                <th className="py-2 pr-3 pl-4">Topic</th>
                <th className="py-2 pr-3">Client model</th>
                <th className="py-2 pr-3">Cell</th>
                <th className="py-2 pr-4">Platform treatment</th>
              </tr>
            </thead>
            <tbody>
              {config.conventions.map((row) => (
                <tr key={row.topic} className="border-b border-sand align-top last:border-0">
                  <td className="py-1.5 pr-3 pl-4 font-medium">{row.label}</td>
                  <td className="py-1.5 pr-3 text-muted">{row.quote}</td>
                  <td className="py-1.5 pr-3 font-mono text-xs">{row.cell}</td>
                  <td className="py-1.5 pr-4">{row.treatment}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
