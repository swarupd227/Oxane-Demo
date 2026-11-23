import clsx from "clsx";
import { CheckCircle2, FileSpreadsheet, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { StatusPill } from "../components/ui/badges";
import { Button } from "../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader } from "../components/ui/PageHeader";
import { Timeline, useHistory } from "../components/ui/Timeline";
import { caseworkFileUrl, formatStamp, useCasework, usd2, type QcLine } from "../lib/casework";
import { useSession } from "../lib/session";

function show(value: number | string | null, unit: string): string {
  if (value === null || value === "") {
    return "(blank)";
  }
  if (typeof value === "string") {
    return value;
  }
  if (unit === "US$") {
    return usd2.format(value);
  }
  return unit === "count" ? value.toLocaleString("en-US") : String(value);
}

const TONE: Record<QcLine["class"], string> = {
  agrees: "text-ok",
  blank: "text-info",
  rounding: "text-info",
  sign: "text-info",
  percent: "text-info",
  genuine: "text-danger font-semibold",
};

function Resolve({ line, options }: { line: QcLine; options: string[] }) {
  const { dispatch, state } = useSession();
  const [resolution, setResolution] = useState(options[0]);
  const [reason, setReason] = useState("");
  return (
    <form
      className="mt-2 flex flex-wrap items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        dispatch({ type: "resolve-variance", line: line.line, resolution, reason });
      }}
    >
      <label className="text-xs font-medium">
        Resolution
        <select
          value={resolution}
          onChange={(event) => setResolution(event.target.value)}
          className="mt-1 block h-8 rounded-md border border-line bg-surface px-2 text-[0.8125rem] font-normal"
        >
          {options.map((option) => (
            <option key={option}>{option}</option>
          ))}
        </select>
      </label>
      <label className="min-w-56 flex-1 text-xs font-medium">
        Reason
        <input
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          aria-label={`Reason for ${line.line}`}
          className="mt-1 block h-8 w-full rounded-md border border-line px-2 text-[0.8125rem] font-normal"
        />
      </label>
      <Button size="sm" type="submit" disabled={!reason.trim() || state.actor !== "analyst"}>
        Record
      </Button>
    </form>
  );
}

function VarianceHistory({ line }: { line: string }) {
  const history = useHistory([`qc:${line}`]);
  return history.length ? <Timeline className="mt-2 border-t border-line pt-2" entries={history} /> : null;
}

export function QcPage() {
  const { state, dispatch } = useSession();
  const { data } = useCasework();

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }
  const qc = data.qc;
  const genuine = qc.lines.filter((line) => line.class === "genuine");

  return (
    <div className="space-y-4">
      <PageHeader
        title="Independent QC"
        summary={`Borrowing base report, April 2026 · ${qc.file} · ${qc.lines.length} lines · ${qc.agrees} agree · ${qc.presentation} presentation · ${qc.genuine.length} genuine`}
        actions={
          <a
            href={caseworkFileUrl(qc.file)}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-line bg-surface px-4 text-sm font-medium hover:bg-canvas"
          >
            <FileSpreadsheet aria-hidden className="size-4" />
            QC workbook
          </a>
        }
      />

      <div
        className={clsx(
          "flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg px-4 py-3 text-sm",
          qc.status === "released" ? "bg-ok-tint" : "bg-warn-tint",
        )}
      >
        <StatusPill
          status={qc.status === "released" ? "approved" : "review"}
          label={qc.status === "released" ? "Released" : "Provisional"}
        />
        <span>Genuine variances open: {qc.open.length}</span>
        <span>Case approved: {state.approvedAt ? formatStamp(state.approvedAt) : "No"}</span>
        {qc.released_at && (
          <span>
            Released {formatStamp(qc.released_at)} by {qc.released_by}
          </span>
        )}
        <span className="ml-auto">
          <Button
            size="sm"
            disabled={!qc.can_release}
            onClick={() => dispatch({ type: "release-report" })}
          >
            <ShieldCheck aria-hidden className="size-3.5" />
            Release report
          </Button>
        </span>
      </div>

      <Card className="overflow-hidden">
        <table className="w-full text-left text-[0.8125rem]">
          <thead>
            <tr className="border-b border-line text-xs font-medium text-subtle">
              <th className="py-2 pr-3 pl-4">Line</th>
              <th className="py-2 pr-3 text-right">Platform</th>
              <th className="py-2 pr-3 text-right">Independent QC</th>
              <th className="py-2 pr-3">Cell</th>
              <th className="py-2 pr-4">Class</th>
            </tr>
          </thead>
          <tbody>
            {qc.lines.map((line) => (
              <tr key={line.line} className="border-b border-sand last:border-0">
                <td className="py-1.5 pr-3 pl-4">{line.line}</td>
                <td className="numeric py-1.5 pr-3 text-right">{show(line.platform, line.unit)}</td>
                <td className="numeric py-1.5 pr-3 text-right">{show(line.qc, line.unit)}</td>
                <td className="py-1.5 pr-3 font-mono text-xs text-muted">{line.cell}</td>
                <td className={clsx("py-1.5 pr-4 text-xs", TONE[line.class])}>
                  {line.label}
                  {line.resolution && " · resolved"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="grid grid-cols-2 gap-4">
        {genuine.map((line) => (
          <Card key={line.line} className="p-4 text-[0.8125rem]">
            <SectionLabel>Genuine variance</SectionLabel>
            <h3 className="mt-0.5 font-semibold">{line.line}</h3>
            <p className="numeric mt-1">
              Difference {(line.difference ?? 0) < 0 ? "-" : ""}US${usd2.format(Math.abs(line.difference ?? 0))}
            </p>
            {line.explained_by && (
              <p className="mt-1 text-muted">
                Matches {line.explained_by.loans} {line.explained_by.label}, US$
                {usd2.format(line.explained_by.amount)}:{" "}
                <span className="font-mono text-xs">
                  {line.explained_by.loan_ids.slice(0, 4).join(", ")}
                  {line.explained_by.loans > 4 ? ", ..." : ""}
                </span>
              </p>
            )}
            {line.resolution ? (
              <p className="mt-2 flex items-start gap-1.5 rounded-md bg-ok-tint px-3 py-2 text-ok">
                <CheckCircle2 aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  {line.resolution.resolution} · {line.resolution.by} ·{" "}
                  {formatStamp(line.resolution.at)}
                  <span className="block text-ink">{line.resolution.reason}</span>
                </span>
              </p>
            ) : (
              <Resolve line={line} options={qc.resolutions} />
            )}
            <VarianceHistory line={line.line} />
          </Card>
        ))}
      </div>
    </div>
  );
}
